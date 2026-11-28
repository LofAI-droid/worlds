"""Rave against the machine — de dansers, gebouwd met Blender uit Mixamo-bronnen.

Gebruik (vanuit de map rave/):

    python3.11 blender/bouw_figuren.py              # figuren.glb + blender/figuren.blend
    python3.11 blender/bouw_figuren.py -- --render  # ook blender/voorbeeld-figuren.png

Wat het doet
------------
1. Leest de animaties (Mixamo-FBX) en zet ze om naar een neutrale vorm: per bot een
   draaiing *in wereldassen van de rustpose (T-pose)* en een heupverschuiving gedeeld door
   de heuphoogte. Zo kunnen ze op elk personage met een Mixamo-skelet gezet worden.
   - horizontale wortelbeweging (heup) wordt weggefilterd (trage verplaatsing eruit,
     het heupwiegen blijft), verticale beweging blijft;
   - dansen worden lussen: beste begin/eindpunt zoeken + kruisovervloeien;
   - backflip vloeit aan het einde over naar de houding van `staan` (neutraal, sluit aan).
2. Maakt zelf `staan` (4 s) en `wiegen` (16 beats rond 142 BPM) met keyframes,
   benen met een kleine IK zodat de voeten op de grond blijven.
3. Importeert elk personage uit PERSONAGES, schaalt naar HOOGTE, voeten op 0, gecentreerd,
   kijkt naar -Y in Blender (= +z in three.js), voegt de meshes samen met materiaal
   `figuur_huid` en zet alle clips als NLA-sporen op het skelet `danser_<naam>`.
4. Modelleert de accessoires (glowstick, halsband, koptelefoon, masker) passend op het
   eerste personage; oorsprong op het hechtpunt; bot + lokale offset als glTF-extras.
5. Exporteert ../figuren.glb en blender/figuren.blend (en met --render een voorbeeldbeeld).

Coördinaten: Blender Z omhoog, figuur kijkt naar -Y, zijn rechterkant is -X.
"""
import json
import math
import os
import sys

import bpy  # eerst bpy: dan zijn bmesh en mathutils beschikbaar
import bmesh
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

HIER = os.path.dirname(os.path.abspath(__file__))
UIT = os.path.dirname(HIER)
BRON = os.path.join(HIER, 'bronnen', 'mixamo')

# ---------------------------------------------------------------------
#  Instellingen
# ---------------------------------------------------------------------
# Personages: (naam, bestand). Elk wordt skelet `danser_<naam>`. Het eerste is de referentie
# (accessoires passen op hem; zijn clips heten exact zoals in ANIMATIES). Clips van latere
# personages heten `<naam>:<clip>` zodat botnamen in één glTF-clip niet botsen.
PERSONAGES = [
    ('xbot', 'xbot.fbx'),
]
# Animaties: (clipnaam, bestand, soort) — soort 'lus' of 'eenmalig'.
ANIMATIES = [
    ('house_1', 'house_1.fbx', 'lus'),
    ('house_2', 'house_2.fbx', 'lus'),
    ('house_3', 'house_3.fbx', 'lus'),
    ('backflip', 'backflip.fbx', 'eenmalig'),
]
DECIMEREN = 0.3       # fractie van de driehoeken die overblijft (silhouetten in het donker)
HOOGTE = 1.75          # m, kruin
FPS = 30
BPM = 142.0
STAAN_S = 4.0          # duur van `staan`
WIEGEN_BEATS = 16      # lengte van `wiegen` in beats (lus)
WORTEL_VENSTER = 1.5   # s, glijdend gemiddelde van de heup dat als wortelbeweging verdwijnt
OVERVLOEI = 15         # beelden kruisovervloeien bij lussen
TERUG = 30             # beelden waarin de backflip overvloeit naar `staan` (beeld 0)
DRACO = True           # Draco getest: skinning blijft werken in three.js (DRACOLoader nodig)
GLOED = '#3dff7a'      # standaardkleur glowstick (viewer mag variëren)

ZAAD = 7


# =====================================================================
#  Kleine hulpjes
# =====================================================================
def lineair(hexkleur):
    h = hexkleur.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def materiaal(naam, kleur, ruwheid=0.6, metaal=0.0, emissie=None, sterkte=1.0, spiegel=0.5,
              laklaag=0.0):
    m = bpy.data.materials.get(naam) or bpy.data.materials.new(naam)
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    lin = lineair(kleur)
    b.inputs['Base Color'].default_value = (*lin, 1)
    b.inputs['Roughness'].default_value = ruwheid
    b.inputs['Metallic'].default_value = metaal
    b.inputs['Specular IOR Level'].default_value = spiegel
    if laklaag:
        b.inputs['Coat Weight'].default_value = laklaag
        b.inputs['Coat Roughness'].default_value = 0.35
    if emissie:
        b.inputs['Emission Color'].default_value = (*lineair(emissie), 1)
        b.inputs['Emission Strength'].default_value = sterkte
    m.diffuse_color = (*lin, 1)
    return m


def wis_alles():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.render.fps_base = 1.0


def importeer_fbx(pad):
    voor = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=pad, automatic_bone_orientation=False,
                             ignore_leaf_bones=False)
    nieuw = [o for o in bpy.data.objects if o not in voor]
    arm = next(o for o in nieuw if o.type == 'ARMATURE')
    return arm, [o for o in nieuw if o.type == 'MESH']


def kort(botnaam):
    """'mixamorig:LeftArm' -> 'LeftArm' (werkt ook voor 'mixamorigLeftArm')."""
    if ':' in botnaam:
        return botnaam.split(':', 1)[1]
    return botnaam[9:] if botnaam.startswith('mixamorig') else botnaam


# --- quaternions in numpy (w, x, y, z) ---------------------------------
def qmul(a, b):
    aw, ax, ay, az = np.moveaxis(a, -1, 0)
    bw, bx, by, bz = np.moveaxis(b, -1, 0)
    return np.stack([aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw], -1)


def qconj(a):
    return a * np.array([1, -1, -1, -1])


def qnorm(a):
    return a / np.linalg.norm(a, axis=-1, keepdims=True)


def qcontinu(q):
    """Zelfde halfruimte voor opeenvolgende beelden (q en -q zijn dezelfde draaiing)."""
    q = q.copy()
    for i in range(1, len(q)):
        s = np.where(np.sum(q[i] * q[i - 1], -1, keepdims=True) < 0, -1.0, 1.0)
        q[i] *= s
    return q


def qmeng(a, b, w):
    """Genormaliseerde lineaire menging (nlerp) met tekenkeuze; w kan per beeld."""
    s = np.where(np.sum(a * b, -1, keepdims=True) < 0, -1.0, 1.0)
    return qnorm(a * (1 - w) + b * s * w)


def zacht(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


# =====================================================================
#  1. Animaties lezen -> neutrale vorm
# =====================================================================
class Clip:
    """Neutrale clip: D[n, bot] = draaiing in wereldassen van de T-pose (w,x,y,z),
    h[n] = heupverschuiving in wereld (Z omhoog) gedeeld door de heuphoogte."""

    def __init__(self, naam, botten, D, h, soort):
        self.naam, self.botten, self.D, self.h, self.soort = naam, list(botten), D, h, soort

    @property
    def beelden(self):
        return len(self.D)


def lees_animatie(naam, bestand, soort):
    wis_alles()
    arm, _ = importeer_fbx(os.path.join(BRON, bestand))
    ad = arm.animation_data
    act = ad.action
    cb = None
    for laag in act.layers:
        for strook in laag.strips:
            cb = strook.channelbag(ad.action_slot) or (strook.channelbags[0] if strook.channelbags else None)
    fcs = {(f.data_path, f.array_index): f for f in cb.fcurves}
    keys = [k.co[0] for f in cb.fcurves for k in f.keyframe_points]
    f0, f1 = int(round(min(keys))), int(round(max(keys)))
    frames = np.arange(f0, f1 + 1)
    n = len(frames)

    wobj = arm.matrix_world.to_3x3()
    schaal = wobj.to_scale()[0]
    wrot = wobj.normalized()
    botten = [b.name for b in arm.data.bones]
    D = np.zeros((n, len(botten), 4))
    D[..., 0] = 1
    for j, b in enumerate(arm.data.bones):
        pad = f'pose.bones["{b.name}"].rotation_quaternion'
        if (pad, 0) not in fcs:
            continue
        L = np.array([[fcs[(pad, i)].evaluate(f) for i in range(4)] for f in frames])
        nul = np.linalg.norm(L, axis=-1) < 1e-6  # eindbotjes: soms (0,0,0,0)
        L[nul] = (1, 0, 0, 0)
        W = np.array((wrot @ b.matrix_local.to_3x3().normalized()).to_quaternion())
        D[:, j] = qmul(qmul(W[None], qnorm(L)), qconj(W)[None])
    heup = arm.data.bones[0]
    while heup.parent:
        heup = heup.parent
    pad = f'pose.bones["{heup.name}"].location'
    loc = np.array([[fcs[(pad, i)].evaluate(f) if (pad, i) in fcs else 0.0 for i in range(3)]
                    for f in frames])
    R = np.array(wrot @ heup.matrix_local.to_3x3().normalized())
    hoogte = (arm.matrix_world @ heup.head_local).z
    h = (loc @ R.T) * schaal / hoogte
    D = qcontinu(D)
    print(f'  {naam}: {n} beelden uit {bestand}, heuphoogte bron {hoogte:.3f} m')
    return Clip(naam, botten, D, h, soort)


def glijdend_gemiddelde(x, venster, periodiek=False):
    k = np.ones(venster) / venster
    pad = venster // 2
    xp = np.pad(x, ((pad, venster - 1 - pad),) + ((0, 0),) * (x.ndim - 1),
                mode='wrap' if periodiek else 'edge')
    return np.stack([np.convolve(xp[:, i], k, mode='valid') for i in range(x.shape[1])], 1)


def zonder_wortel(clip, periodiek=False):
    """Trage horizontale verplaatsing van de heup eruit; wiegen en hoogte blijven.
    periodiek: de clip is al een lus (laatste beeld = eerste), dan rond filteren."""
    v = max(3, int(WORTEL_VENSTER * FPS) | 1)
    h = clip.h.copy()
    if periodiek:
        glad = glijdend_gemiddelde(h[:-1, :2], v, periodiek=True)
        glad = np.concatenate([glad, glad[:1]])
    else:
        glad = glijdend_gemiddelde(h[:, :2], v)
    h[:, :2] -= glad
    h[:, :2] -= h[:-1, :2].mean(0)
    clip.h = h


def is_al_lus(clip):
    """Mixamo levert sommige dansen al als lus: laatste beeld = eerste, en de beweging
    loopt door (versnelling over de naad niet groter dan gewoonlijk)."""
    D = clip.D[:, hoofdbotten(clip) > 0]  # vingers tellen niet (naad_glad lost die op)
    n = len(D)
    if n < 10:
        return False
    eind = np.max(1 - np.abs(np.sum(D[0] * D[-1], -1))) + np.abs(clip.h[0] - clip.h[-1]).max()
    if eind > 1e-4:
        return False

    def versn(i0, i1, i2):
        a = D[i0]
        b = D[i1] * np.where(np.sum(D[i1] * a, -1, keepdims=True) < 0, -1, 1)
        c = D[i2] * np.where(np.sum(D[i2] * a, -1, keepdims=True) < 0, -1, 1)
        return np.abs(a - 2 * b + c).sum()

    gewoon = np.percentile([versn(i, i + 1, i + 2) for i in range(n - 2)], 90)
    return versn(n - 2, 0, 1) <= gewoon


def naad_glad(clip, k=12):
    """Kleine resterende verschillen tussen laatste en eerste beeld (bv. vingers) over de
    laatste k beelden wegwerken, zodat het slotbeeld exact het eerste is."""
    D = clip.D.copy()
    n = len(D)
    fout = qmul(D[0], qconj(D[-1]))  # per bot: draai van laatste naar eerste
    fout *= np.where(fout[:, :1] < 0, -1.0, 1.0)
    een = np.zeros_like(fout)
    een[:, 0] = 1
    for i in range(k):
        g = zacht((i + 1) / k)
        D[n - k + i] = qnorm(qmul(qmeng(een, fout, g), D[n - k + i]))
    clip.D = qcontinu(D)


def hoofdbotten(clip):
    w = []
    for b in clip.botten:
        k = kort(b)
        if any(s in k for s in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky', '_End')):
            w.append(0.0)
        elif k in ('Hips', 'Spine', 'Spine1', 'Spine2', 'LeftUpLeg', 'RightUpLeg'):
            w.append(3.0)
        else:
            w.append(1.0)
    return np.array(w)


def maak_lus(clip):
    """Zoek begin a en einde b met gelijkaardige houding (en beweging), kruisovervloei
    het einde naar de beelden net vóór a. Resultaat: beelden a..b-1 + slotbeeld = beeld a."""
    D, h = clip.D, clip.h
    n = len(D)
    w = hoofdbotten(clip)
    F = OVERVLOEI

    # afstand tussen houdingen: per bot 1-|<a,b>| (tekenvrij), plus heuphoogte/-plaats;
    # ook 3 beelden ervoor en erna, zodat de beweging (snelheid) ook aansluit
    kand_a = np.arange(F + 3, max(F + 4, n // 4))
    kand_b = np.arange(max(kand_a[-1] + 1, int(n * 0.7)), n - 3)
    beste = None
    for a in kand_a:
        for b in kand_b:
            c = 0.0
            for o, g in ((0, 1.0), (-3, 0.5), (3, 0.5)):
                dq = 1 - np.abs(np.sum(D[a + o] * D[b + o], -1))
                c += g * (np.sum(w * dq) / w.sum() * 50 + abs(h[a + o, 2] - h[b + o, 2]) * 4
                          + np.linalg.norm(h[a + o, :2] - h[b + o, :2]) * 2)
            c -= 0.02 * (b - a) / n
            if beste is None or c < beste[0]:
                beste = (c, a, b)
    _, a, b = beste
    L = b - a
    nD = D[a:b].copy()
    nh = h[a:b].copy()
    gew = zacht((np.arange(F) + 1) / F)
    for k in range(F):
        t = L - F + k
        bron = a - F + k
        nD[t] = qmeng(nD[t], D[bron], gew[k])
        nh[t] = nh[t] * (1 - gew[k]) + h[bron] * gew[k]
    clip.D = qcontinu(np.concatenate([nD, nD[:1]]))
    clip.h = np.concatenate([nh, nh[:1]])
    print(f'  {clip.naam}: lus beeld {a}..{b} ({L} beelden = {L / FPS:.2f} s), kost {beste[0]:.4f}')


def eindig_neutraal(clip, doel):
    """Laatste TERUG beelden vloeien over naar beeld 0 van `doel` (de neutrale `staan`),
    zodat de clip eindigt in een rustige stand die naadloos aansluit op staan/wiegen."""
    D, h = clip.D.copy(), clip.h.copy()
    n = len(D)
    idx = {b: j for j, b in enumerate(doel.botten)}
    dD = np.array([doel.D[0, idx[b]] if b in idx else D[-1, j] for j, b in enumerate(clip.botten)])
    for k in range(TERUG):
        t = n - TERUG + k
        g = zacht((k + 1) / TERUG)
        D[t] = qmeng(D[t], dD, g)
        h[t] = h[t] * (1 - g) + doel.h[0] * g
    clip.D, clip.h = qcontinu(D), h
    print(f'  {clip.naam}: {n} beelden ({(n - 1) / FPS:.2f} s), eindigt in de houding van '
          f'{doel.naam} (beeld 0)')


# =====================================================================
#  2. Zelfgemaakte clips: staan en wiegen
# =====================================================================
def Q(x=0.0, y=0.0, z=0.0):
    """Draaiing in wereldassen (graden), eerst x, dan y, dan z."""
    q = Quaternion((1, 0, 0), math.radians(x))
    q = Quaternion((0, 1, 0), math.radians(y)) @ q
    return Quaternion((0, 0, 1), math.radians(z)) @ q


class Rust:
    """Rustpose van een personage in wereldcoördinaten (meter, na schalen)."""

    def __init__(self, arm):
        self.botten = [b.name for b in arm.data.bones]
        self.kop = {kort(b.name): arm.matrix_world @ b.head_local for b in arm.data.bones}
        self.staart = {kort(b.name): arm.matrix_world @ b.tail_local for b in arm.data.bones}
        self.ouder = {kort(b.name): (kort(b.parent.name) if b.parent else None)
                      for b in arm.data.bones}
        self.vol = {kort(b.name): b.name for b in arm.data.bones}
        self.heuphoogte = self.kop['Hips'].z


def been_ik(rust, kant, heup_pos, A_heup, doel):
    """Twee-botten-IK: knie naar voren (-Y). Geeft absolute draaiingen (dij, scheen)."""
    Ph, Pu = rust.kop['Hips'], rust.kop[kant + 'UpLeg']
    Pk, Pe = rust.kop[kant + 'Leg'], rust.kop[kant + 'Foot']
    l1, l2 = (Pk - Pu).length, (Pe - Pk).length
    P = heup_pos + A_heup @ (Pu - Ph)
    d = doel - P
    D = min(d.length, (l1 + l2) * 0.9995)
    dn = d.normalized()
    cos_a = max(-1.0, min(1.0, (l1 * l1 + D * D - l2 * l2) / (2 * l1 * D)))
    alfa = math.acos(cos_a)
    voor = Vector((0, -1, 0))
    loodrecht = (voor - dn * voor.dot(dn)).normalized()
    dij = dn * math.cos(alfa) + loodrecht * math.sin(alfa)
    knie = P + dij * l1
    scheen = (P + dn * D - knie).normalized()
    A_dij = (Pk - Pu).normalized().rotation_difference(dij)
    A_scheen = (A_dij @ (Pe - Pk).normalized()).rotation_difference(scheen) @ A_dij
    return A_dij, A_scheen


def armen(d, kant, neer, voor, elleboog, pols=0.0, krul=12.0):
    """Arm vanuit T-pose naar beneden (neer°), wat naar voren (voor°), elleboog gebogen.
    Rechts ligt op -X, links op +X; assen zijn die van de T-pose."""
    s = -1 if kant == 'Right' else 1
    d[kant + 'Arm'] = Q(x=-voor) @ Q(y=s * neer)
    d[kant + 'ForeArm'] = Q(z=-s * elleboog)
    d[kant + 'Hand'] = Q(y=s * pols)
    for v in ('Index', 'Middle', 'Ring', 'Pinky'):
        for i, f in ((1, 1.0), (2, 1.3), (3, 1.1)):
            d[f'{kant}Hand{v}{i}'] = Q(y=s * krul * f)
    d[kant + 'HandThumb1'] = Q(z=-s * 10)
    d[kant + 'HandThumb2'] = Q(y=s * 8)


def bouw_pose(rust, h, A_heup, rel, voeten):
    """Zet een houding om naar de neutrale vorm (D per bot, h genormaliseerd)."""
    heup_pos = rust.kop['Hips'] + h
    A = {'Hips': A_heup}
    for kant in ('Left', 'Right'):
        dij, scheen = been_ik(rust, kant, heup_pos, A_heup, voeten[kant])
        A[kant + 'UpLeg'] = dij
        A[kant + 'Leg'] = scheen
        A[kant + 'Foot'] = Quaternion()
    D = []
    acc = {}
    for b in rust.botten:
        k = kort(b)
        p = rust.ouder[k]
        Ap = acc.get(p, Quaternion()) if p else Quaternion()
        if k in A:
            acc[k] = A[k]
            d = Ap.inverted() @ A[k]
        else:
            d = rel.get(k, Quaternion())
            acc[k] = Ap @ d
        D.append(tuple(d))
    return np.array(D), np.array(h) / rust.heuphoogte


def maak_staan(rust):
    n = int(round(STAAN_S * FPS))
    D, H = [], []
    voeten = {k: rust.kop[k + 'Foot'] + Vector((0.025 * (1 if k == 'Left' else -1), 0, 0))
              for k in ('Left', 'Right')}
    for i in range(n + 1):
        t = i / n  # 0..1 over de lus
        w = math.sin(2 * math.pi * t)            # gewicht links/rechts (1x per lus)
        a = math.sin(2 * math.pi * t * 2 - 0.6)  # adem (2x per lus)
        kijk = math.sin(2 * math.pi * t + 0.8) * 0.7 + 0.3 * math.sin(2 * math.pi * 3 * t)
        h = Vector((0.03 * w, 0.004 * math.sin(4 * math.pi * t), -0.012 + 0.002 * a))
        A_heup = Q(y=-2.5 * w, z=3 * w)
        rel = {
            'Spine': Q(x=2 + 0.6 * a, y=1.5 * w),
            'Spine1': Q(x=0.5 - 0.8 * a),
            'Spine2': Q(x=-0.8 * a, y=0.8 * w),
            'Neck': Q(x=3),
            'Head': Q(x=-2 + 2.5 * math.sin(2 * math.pi * 2 * t + 1.3), y=1.5 * w, z=9 * kijk),
            'RightShoulder': Q(y=-1.2 * a),
            'LeftShoulder': Q(y=1.2 * a),
        }
        armen(rel, 'Right', 74 + 2 * w, 6 + 1.5 * a, 14 + 3 * w)
        armen(rel, 'Left', 74 - 2 * w, 6 + 1.5 * a, 14 - 3 * w)
        d, hh = bouw_pose(rust, h, A_heup, rel, voeten)
        D.append(d)
        H.append(hh)
    return Clip('staan', rust.botten, qcontinu(np.array(D)), np.array(H), 'lus')


def maak_wiegen(rust):
    """16 beats; lengte afgerond op hele beelden -> werkelijke BPM in het verslag."""
    n = int(round(WIEGEN_BEATS * 60 / BPM * FPS))
    D, H = [], []
    voeten = {k: rust.kop[k + 'Foot'] + Vector((0.05 * (1 if k == 'Left' else -1),
                                                  -0.02 if k == 'Left' else 0.03, 0))
              for k in ('Left', 'Right')}
    for i in range(n + 1):
        p = i / n * WIEGEN_BEATS                   # beat-fase
        tl = i / n                                  # 0..1 over de lus
        c = math.cos(2 * math.pi * p)
        veer = (0.5 + 0.5 * c) ** 1.6               # 1 op de beat (diep), 0 ertussen
        knik = (0.5 + 0.5 * math.cos(2 * math.pi * p - 0.7)) ** 1.5   # hoofd iets na de beat
        zij = math.sin(math.pi * p)                 # zijwaarts: 2 beats per heen-en-weer
        traag = math.sin(2 * math.pi * tl)          # één keer per lus
        h = Vector((0.035 * zij, -0.008 + 0.01 * veer, -0.035 - 0.045 * veer))
        A_heup = Q(x=2 * veer, y=-3 * zij, z=6 * zij + 8 * traag)
        rel = {
            'Spine': Q(x=4 + 3 * veer, y=2 * zij),
            'Spine1': Q(x=1 + 2 * veer, y=1.5 * zij, z=-3 * zij),
            'Spine2': Q(x=1, z=-2 * zij - 4 * traag),
            'Neck': Q(x=2 + 3 * knik),
            'Head': Q(x=-4 + 9 * knik, y=-2 * zij, z=-4 * traag),
            'RightShoulder': Q(y=-3 * veer + 3 * max(0.0, -zij)),
            'LeftShoulder': Q(y=3 * veer - 3 * max(0.0, zij)),
        }
        armen(rel, 'Right', 62 + 4 * zij, 12 + 5 * veer, 38 + 14 * veer - 6 * zij, pols=10, krul=30)
        armen(rel, 'Left', 62 - 4 * zij, 12 + 5 * veer, 38 + 14 * veer + 6 * zij, pols=10, krul=30)
        d, hh = bouw_pose(rust, h, A_heup, rel, voeten)
        D.append(d)
        H.append(hh)
    bpm = WIEGEN_BEATS * 60 / (n / FPS)
    print(f'  wiegen: {n} beelden = {n / FPS:.3f} s = {WIEGEN_BEATS} beats aan {bpm:.2f} BPM')
    return Clip('wiegen', rust.botten, qcontinu(np.array(D)), np.array(H), 'lus'), bpm


# =====================================================================
#  3. Personage importeren
# =====================================================================
def importeer_personage(naam, bestand, col):
    arm, meshes = importeer_fbx(os.path.join(BRON, bestand))
    # het meegeleverde (T-pose-)actiontje weg
    if arm.animation_data:
        arm.animation_data.action = None
    for o in meshes:
        if o.animation_data:
            o.animation_data_clear()
    # maten in wereld (na de objectmatrix van de FBX)
    pts = [o.matrix_world @ v.co for o in meshes for v in o.data.vertices]
    zmin = min(p.z for p in pts)
    zmax = max(p.z for p in pts)
    s = HOOGTE / (zmax - zmin)
    heup = next(b for b in arm.data.bones if b.parent is None)
    hp = arm.matrix_world @ heup.head_local
    M = (Matrix.Translation((-hp.x * s, -hp.y * s, -zmin * s)) @ Matrix.Scale(s, 4))
    for o in meshes:
        o.data.transform(M @ o.matrix_world)
    arm.data.transform(M @ arm.matrix_world)
    arm.matrix_world = Matrix()
    for o in meshes:
        o.parent = arm
        o.matrix_parent_inverse = Matrix()
        o.matrix_basis = Matrix()

    # meshes samenvoegen tot één lijf met één materiaal
    huid = bpy.data.materials['figuur_huid']
    hoofd = max(meshes, key=lambda o: len(o.data.vertices))
    with bpy.context.temp_override(active_object=hoofd, selected_editable_objects=meshes,
                                   selected_objects=meshes):
        bpy.ops.object.join()
    lijf = hoofd
    lijf.name = lijf.data.name = f'danser_{naam}_lijf'
    lijf.data.materials.clear()
    lijf.data.materials.append(huid)
    for p in lijf.data.polygons:
        p.material_index = 0
        p.use_smooth = True
    while lijf.data.uv_layers:
        lijf.data.uv_layers.remove(lijf.data.uv_layers[0])
    for mod in lijf.modifiers:
        if mod.type == 'ARMATURE':
            mod.object = arm
    # minder driehoeken: 60 dansers in het halfduister hebben geen 39k driehoeken elk nodig
    if DECIMEREN < 1.0:
        voor = sum(len(p.vertices) - 2 for p in lijf.data.polygons)
        dec = lijf.modifiers.new('decimeren', 'DECIMATE')
        dec.ratio = DECIMEREN
        with bpy.context.temp_override(object=lijf, active_object=lijf):
            bpy.ops.object.modifier_move_to_index(modifier=dec.name, index=0)
            bpy.ops.object.modifier_apply(modifier=dec.name)
        na = sum(len(p.vertices) - 2 for p in lijf.data.polygons)
        print(f'  decimeren: {voor} -> {na} driehoeken')
    arm.name = arm.data.name = f'danser_{naam}'
    arm.data.pose_position = 'POSE'
    arm.data.display_type = 'STICK'
    for o in (arm, lijf):
        for c in o.users_collection:
            c.objects.unlink(o)
        col.objects.link(o)
    for pb in arm.pose.bones:
        pb.rotation_mode = 'QUATERNION'
    print(f'  danser_{naam}: schaalfactor {s:.4f} (na cm->m), {len(lijf.data.vertices)} punten, '
          f'{len(arm.data.bones)} botten')
    return arm, lijf


def schrijf_actie(arm, rust, clip, naam):
    """Neutrale clip -> Blender-actie met lokale bot-draaiingen (+ heuplocatie)."""
    act = bpy.data.actions.new(naam)
    act.use_fake_user = True
    slot = act.slots.new(id_type='OBJECT', name=arm.name)
    laag = act.layers.new('Laag')
    strook = laag.strips.new(type='KEYFRAME')
    cb = strook.channelbag(slot, ensure=True)
    n = clip.beelden
    frames = np.arange(n, dtype=np.float64)
    idx = {kort(b): j for j, b in enumerate(clip.botten)}

    def zet(pad, i, waarden, groep):
        fc = cb.fcurves.new(pad, index=i, group_name=groep)
        fc.keyframe_points.add(n)
        co = np.empty(2 * n)
        co[0::2] = frames
        co[1::2] = waarden
        fc.keyframe_points.foreach_set('co', co)
        fc.keyframe_points.foreach_set('interpolation', [1] * n)  # LINEAR
        fc.update()

    for b in arm.data.bones:
        k = kort(b.name)
        if k not in idx:
            continue
        if k.endswith('_End') or (k[-1] == '4' and 'Hand' in k):
            continue  # eindbotjes bewegen niet
        W = np.array(b.matrix_local.to_3x3().normalized().to_quaternion())
        L = qcontinu(qmul(qmul(qconj(W)[None], clip.D[:, idx[k]]), W[None]))
        pad = f'pose.bones["{b.name}"].rotation_quaternion'
        for i in range(4):
            zet(pad, i, L[:, i], b.name)
        if b.parent is None:
            R = np.array(b.matrix_local.to_3x3().normalized())
            loc = (clip.h * rust.heuphoogte) @ R  # = R^T @ h
            pad = f'pose.bones["{b.name}"].location'
            for i in range(3):
                zet(pad, i, loc[:, i], b.name)
    act.frame_range = (0, n - 1)
    act.use_frame_range = True
    act.use_cyclic = clip.soort == 'lus'
    return act, slot


def zet_nla(arm, sporen):
    ad = arm.animation_data_create()
    ad.action = None
    for spoornaam, act, slot in sporen:
        tr = ad.nla_tracks.new()
        tr.name = spoornaam
        st = tr.strips.new(spoornaam, 0, act)
        if hasattr(st, 'action_slot'):
            st.action_slot = slot
        st.extrapolation = 'HOLD'
        tr.mute = True


# =====================================================================
#  4. Accessoires
# =====================================================================
def lathe(bm, profiel, n, M):
    """Draaiprofiel [(r, z), ...] rond de lokale Z-as; M plaatst het. Polen bij r=0."""
    ringen = []
    for r, z in profiel:
        if r < 1e-6:
            ringen.append([bm.verts.new(M @ Vector((0, 0, z)))])
        else:
            ringen.append([bm.verts.new(M @ Vector((r * math.cos(2 * math.pi * i / n),
                                                    r * math.sin(2 * math.pi * i / n), z)))
                           for i in range(n)])
    for a, b in zip(ringen, ringen[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        if len(a) == 1:
            for i in range(n):
                bm.faces.new((a[0], b[i], b[(i + 1) % n]))
        elif len(b) == 1:
            for i in range(n):
                bm.faces.new((a[i], b[0], a[(i + 1) % n]))
        else:
            for i in range(n):
                bm.faces.new((a[i], b[i], b[(i + 1) % n], a[(i + 1) % n]))
    return ringen


def buis(bm, punten, doorsnede, gesloten=False, boven=Vector((0, 0, 1))):
    """Sleep een 2D-doorsnede [(u, v), ...] (u = zijwaarts, v = 'boven') langs een pad."""
    ringen = []
    m = len(punten)
    for i, p in enumerate(punten):
        if gesloten:
            t = (punten[(i + 1) % m] - punten[i - 1]).normalized()
        else:
            t = (punten[min(i + 1, m - 1)] - punten[max(i - 1, 0)]).normalized()
        b = boven(p) if callable(boven) else boven
        u = t.cross(b).normalized()
        v = u.cross(t).normalized()
        ringen.append([bm.verts.new(p + u * a + v * c) for a, c in doorsnede])
    k = len(doorsnede)
    paren = list(zip(ringen, ringen[1:])) + ([(ringen[-1], ringen[0])] if gesloten else [])
    for a, b in paren:
        for i in range(k):
            bm.faces.new((a[i], a[(i + 1) % k], b[(i + 1) % k], b[i]))
    if not gesloten:
        bm.faces.new(list(reversed(ringen[0])))
        bm.faces.new(ringen[-1])
    return ringen


def rond_profiel(b, d, n=4):
    """Afgeronde rechthoek b x d (doorsnede), tegen de klok in."""
    r = min(b, d) * 0.45
    pts = []
    for hx, hy, a0 in ((b / 2 - r, d / 2 - r, 0), (-b / 2 + r, d / 2 - r, 90),
                       (-b / 2 + r, -d / 2 + r, 180), (b / 2 - r, -d / 2 + r, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((hx + r * math.cos(a), hy + r * math.sin(a)))
    return pts


def mesh_object(naam, bm, materialen, col, oorsprong):
    me = bpy.data.meshes.new(naam)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    for m in materialen:
        me.materials.append(m)
    for p in me.polygons:
        p.use_smooth = True
    me.transform(Matrix.Translation(-oorsprong))
    ob = bpy.data.objects.new(naam, me)
    ob.location = oorsprong
    col.objects.link(ob)
    return ob


class Hoofdmaat:
    """Straalt vanuit het hoofd naar buiten om de vorm van het lijf te volgen."""

    def __init__(self, lijf):
        dg = bpy.context.evaluated_depsgraph_get()
        self.bvh = BVHTree.FromObject(lijf, dg)

    def straal(self, midden, richting, maxi=0.4, binnen=False):
        # van buitenaf naar binnen schieten: eerste treffer = buitenkant;
        # binnen=True: vanuit het midden naar buiten (eerste wand, bv. de hals)
        if binnen:
            hit = self.bvh.ray_cast(midden, richting, maxi)
            return None if hit[0] is None else (hit[0] - midden).dot(richting)
        start = midden + richting * maxi
        hit = self.bvh.ray_cast(start, -richting, maxi)
        if hit[0] is None:
            return None
        return (hit[0] - midden).dot(richting)


def accessoires(arm, lijf, rust, col):
    mg = materiaal('gloed_glowstick', '#0e3a1a', 0.35, emissie=GLOED, sterkte=1.0)
    mk = materiaal('acc_kunststof', '#0b0b0e', 0.32, spiegel=0.6, laklaag=0.3)
    mm = materiaal('acc_masker', '#1a0f24', 0.28, metaal=0.6, spiegel=0.7)
    maat = Hoofdmaat(lijf)
    kop = rust.kop['Head']
    top = rust.kop['HeadTop_End']
    stuk = {}

    # --- hoofdmaten: midden, ooghoogte -----------------------------------
    hoofdmidden = Vector((kop.x, kop.y, kop.z + 0.45 * (top.z - kop.z)))
    oog_z = kop.z + 0.43 * (top.z - kop.z)
    # straal per hoek in een horizontaal vlak, en in het vlak door de oren
    def r_hor(theta, z):
        c = Vector((hoofdmidden.x, hoofdmidden.y, z))
        r = maat.straal(c, Vector((math.sin(theta), -math.cos(theta), 0)))
        return r if r else 0.09

    # --- masker (oogmasker met kattenoortjes) -------------------------------
    half = [(0.0, 0.021), (0.018, 0.026), (0.036, 0.033), (0.050, 0.046), (0.060, 0.066),
            (0.067, 0.071), (0.075, 0.055), (0.083, 0.030), (0.086, 0.010), (0.082, -0.010),
            (0.068, -0.024), (0.046, -0.030), (0.026, -0.024), (0.014, -0.012), (0.0, -0.006)]
    omtrek = half + [(-x, y) for x, y in reversed(half[1:-1])]
    omtrek = catmull(omtrek, 6)
    cu = bpy.data.curves.new('acc_masker_vorm', 'CURVE')
    cu.dimensions = '2D'
    cu.fill_mode = 'BOTH'
    cu.extrude = 0.0012
    cu.bevel_depth = 0.0012
    cu.bevel_resolution = 2
    cu.resolution_u = 2

    def spline(pts):
        sp = cu.splines.new('POLY')
        sp.points.add(len(pts) - 1)
        for p, (x, y) in zip(sp.points, pts):
            p.co = (x, y, 0, 1)
        sp.use_cyclic_u = True

    spline(omtrek)
    for s in (-1, 1):
        oog = []
        for i in range(28):
            t = 2 * math.pi * i / 28
            x = 0.0165 * math.cos(t)
            y = 0.0085 * math.sin(t) * (1 - 0.25 * math.cos(t) * s * -1)
            # amandel, buitenhoek iets omhoog
            hoek = math.radians(10) * s
            xr = x * math.cos(hoek) - y * math.sin(hoek)
            yr = x * math.sin(hoek) + y * math.cos(hoek)
            oog.append((s * 0.034 + xr, 0.002 + yr))
        spline(oog)
    tmp = bpy.data.objects.new('tmp_masker', cu)
    col.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp)
    bpy.data.curves.remove(cu)
    R0 = r_hor(0.0, oog_z)
    bm = bmesh.new()
    bm.from_mesh(me)
    bpy.data.meshes.remove(me)
    for v in bm.verts:
        x, y, z = v.co
        theta = x / (R0 + 0.006)
        hz = oog_z + y
        r = r_hor(theta, hz) + 0.0045 + (z + 0.0024)
        v.co = Vector((hoofdmidden.x + r * math.sin(theta), hoofdmidden.y - r * math.cos(theta), hz))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    oorsprong = Vector((hoofdmidden.x, hoofdmidden.y - R0, oog_z))
    stuk['acc_masker'] = (mesh_object('acc_masker', bm, [mm], col, oorsprong), 'Head')

    # --- koptelefoon ----------------------------------------------------------
    oor_z = oog_z - 0.012
    oor_y = hoofdmidden.y + 0.012
    oor_c = Vector((hoofdmidden.x, oor_y, oor_z))
    zijkant = []
    for s in (-1, 1):
        r = maat.straal(oor_c, Vector((s, 0, 0)))
        zijkant.append(r if r else 0.08)
    zr = max(zijkant)
    bm = bmesh.new()
    schelp = [(0.0, 0.0), (0.026, 0.0), (0.034, 0.003), (0.037, 0.009), (0.037, 0.022),
              (0.033, 0.029), (0.022, 0.032), (0.0, 0.033)]
    ring = []
    for s in (-1, 1):
        x0 = s * (zr + 0.003)
        M = (Matrix.Translation((hoofdmidden.x + x0, oor_y, oor_z))
             @ Matrix.Rotation(math.radians(90 * s), 4, 'Y'))
        lathe(bm, schelp, 24, M)
        ring.append(M)
    n_kop = len(bm.faces)
    # gloeiende ring op de buitenkant van de schelpen
    for M in ring:
        punten = [M @ Vector((0.029 * math.cos(2 * math.pi * i / 32),
                              0.029 * math.sin(2 * math.pi * i / 32), 0.031)) for i in range(32)]
        as_ = (M.to_3x3() @ Vector((0, 0, 1))).normalized()
        buis(bm, punten, [(0.0025 * math.cos(2 * math.pi * k / 6), 0.0025 * math.sin(2 * math.pi * k / 6))
                          for k in range(6)], gesloten=True,
             boven=lambda p, a=as_, c=M.translation: (p - c - a * (p - c).dot(a)).normalized())
    n_ring = len(bm.faces)
    # hoofdband: boog over de kruin, in het vlak door de oren
    boog = []
    for i in range(41):
        phi = math.radians(-78 + 156 * i / 40)
        d = Vector((math.sin(phi), 0, math.cos(phi)))
        r = maat.straal(oor_c, d)
        boog.append((phi, d, (r if r else 0.1) + 0.012))
    # zachte straal (glad) en aansluiting op de schelpen
    rs = [b[2] for b in boog]
    rs = [sum(rs[max(0, i - 3):i + 4]) / len(rs[max(0, i - 3):i + 4]) for i in range(len(rs))]
    pad = [oor_c + d * r for (phi, d, _), r in zip(boog, rs)]
    for s, idx in ((-1, 0), (1, -1)):
        eind = Vector((hoofdmidden.x + s * (zr + 0.018), oor_y, oor_z + 0.03))
        if idx == 0:
            pad.insert(0, eind)
        else:
            pad.append(eind)
    pad = [Vector(p) for p in catmull([tuple(p) for p in pad], 2, open_=True)]
    buis(bm, pad, rond_profiel(0.026, 0.007),
         boven=lambda p: (p - oor_c).normalized())
    ob = mesh_object('acc_koptelefoon', bm, [mk, mg], col, oor_c.copy())
    for i, p in enumerate(ob.data.polygons):
        p.material_index = 1 if n_kop <= i < n_ring else 0
    stuk['acc_koptelefoon'] = (ob, 'Head')

    # --- halsband ---------------------------------------------------------------
    nek, nek2 = rust.kop['Neck'], rust.staart['Neck']
    c = nek + (nek2 - nek) * 0.3
    stralen = [maat.straal(c, Vector((math.cos(a), math.sin(a), 0)), 0.2, binnen=True) or 0.06
               for a in np.linspace(0, 2 * math.pi, 16, endpoint=False)]
    r = max(stralen) + 0.004
    kanteling = Matrix.Rotation(math.radians(-14), 4, 'X')  # voorkant lager
    bm = bmesh.new()
    punten = [c + kanteling.to_3x3() @ Vector((r * math.cos(a), r * math.sin(a), 0))
              for a in np.linspace(0, 2 * math.pi, 48, endpoint=False)]
    buis(bm, punten, [(0.0042 * math.cos(2 * math.pi * k / 8), 0.0042 * math.sin(2 * math.pi * k / 8))
                      for k in range(8)], gesloten=True,
         boven=lambda p: (kanteling.to_3x3() @ Vector((0, 0, 1))))
    stuk['acc_halsband'] = (mesh_object('acc_halsband', bm, [mg], col, c), 'Neck')

    # --- glowstick (rechterhand, tegen de handpalm, dwars over de vingers) --------
    pols = rust.kop['RightHand']
    m1 = rust.kop['RightHandMiddle1']
    wijs, pink = rust.kop['RightHandIndex1'], rust.kop['RightHandPinky1']
    greep = pols + (m1 - pols) * 0.95
    onder = maat.straal(greep, Vector((0, 0, -1))) or 0.015
    greep = greep + Vector((0, 0, -(onder + 0.011)))
    as_ = (pink - wijs).normalized()
    bm = bmesh.new()
    L, rr = 0.17, 0.0085
    prof = [(0.0, -L / 2)]
    for i in range(1, 5):
        a = math.pi / 2 * i / 4
        prof.append((rr * math.sin(a), -L / 2 + rr * (1 - math.cos(a))))
    for i in range(4, -1, -1):
        a = math.pi / 2 * i / 4
        prof.append((rr * math.sin(a), L / 2 - rr * (1 - math.cos(a))))
    prof[-1] = (0.0, L / 2)
    M = Matrix.Translation(greep) @ Vector((0, 0, 1)).rotation_difference(as_).to_matrix().to_4x4()
    lathe(bm, prof, 12, M)
    stuk['acc_glowstick'] = (mesh_object('acc_glowstick', bm, [mg], col, greep), 'RightHand')

    # --- hechting: bot + lokale offset (Blender en three.js) ----------------------
    C = Matrix.Rotation(math.radians(-90), 4, 'X')  # Blender (Z op) -> glTF (Y op)
    hechting = {}
    bpy.context.view_layer.update()
    for naam, (ob, bot) in stuk.items():
        b = arm.data.bones[rust.vol[bot]]
        lok = b.matrix_local.inverted() @ ob.matrix_world
        drie = lok @ C.inverted()  # bot in three.js = C @ B (geen correctie rechts); acc = C @ A @ C^-1
        pos, q, _ = drie.decompose()
        ob['bot'] = b.name.replace(':', '')            # naam in three.js (GLTFLoader)
        ob['bot_gltf'] = b.name                        # naam in de glb
        ob['positie'] = [round(v, 5) for v in pos]
        ob['rotatie'] = [round(q.x, 6), round(q.y, 6), round(q.z, 6), round(q.w, 6)]
        hechting[naam] = (b.name, lok, pos, q)
        ob.data.name = naam
    return stuk, hechting


def catmull(pts, stappen, open_=False):
    """Catmull-Rom-verfijning van een (gesloten) lijst 2D/3D-punten."""
    P = [np.array(p, dtype=float) for p in pts]
    n = len(P)
    uit = []
    rng = range(n - 1) if open_ else range(n)
    for i in rng:
        p0 = P[max(i - 1, 0)] if open_ else P[(i - 1) % n]
        p1, p2 = P[i], P[(i + 1) % n]
        p3 = P[min(i + 2, n - 1)] if open_ else P[(i + 2) % n]
        for k in range(stappen):
            t = k / stappen
            t2, t3 = t * t, t * t * t
            uit.append(tuple(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                                    + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)))
    if open_:
        uit.append(tuple(P[-1]))
    return uit


# =====================================================================
#  5. Voorbeeldbeeld
# =====================================================================
def render(dansers, stuk, hechting, clips):
    sc = bpy.context.scene
    arm0, lijf0 = dansers[0]
    col = bpy.data.collections.new('Voorbeeld')
    sc.collection.children.link(col)
    opstelling = [  # (x, y, draai, clip, beeld, accessoires)
        (-2.1, 0.9, 25, 'house_1', 95, ('acc_koptelefoon', 'acc_halsband')),
        (-0.95, 0.15, 8, 'wiegen', 6, ('acc_masker', 'acc_glowstick', 'acc_halsband')),
        (0.25, -0.35, -5, 'house_2', 310, ('acc_glowstick', 'acc_halsband')),
        (1.45, 0.25, -15, 'backflip', 62, ()),
        (2.5, 1.0, -30, 'house_3', 170, ('acc_masker', 'acc_halsband')),
        (-0.3, 2.4, 0, 'staan', 30, ('acc_halsband',)),
        (1.3, 2.9, 10, 'house_1', 400, ('acc_glowstick',)),
    ]
    F = 100
    sc.frame_set(F)
    for i, (x, y, draai, clipnaam, beeld, accs) in enumerate(opstelling):
        a = arm0.copy()
        a.data = arm0.data
        a.animation_data_clear()
        col.objects.link(a)
        l = lijf0.copy()
        col.objects.link(l)
        l.parent = a
        for m in l.modifiers:
            if m.type == 'ARMATURE':
                m.object = a
        a.location = (x, y, 0)
        a.rotation_euler = (0, 0, math.radians(draai))
        act, slot = clips[clipnaam]
        ad = a.animation_data_create()
        tr = ad.nla_tracks.new()
        st = tr.strips.new(clipnaam, int(F - beeld), act)
        if hasattr(st, 'action_slot'):
            st.action_slot = slot
        st.extrapolation = 'HOLD'
        for acc in accs:
            bron = stuk[acc][0]
            o = bron.copy()
            col.objects.link(o)
            bot, lok, _, _ = hechting[acc]
            b = a.data.bones[bot]
            o.parent = a
            o.parent_type = 'BONE'
            o.parent_bone = bot
            o.matrix_parent_inverse = Matrix.Translation((0, -b.length, 0))
            o.matrix_basis = lok
    # originelen niet in beeld
    for o in [arm0, lijf0] + [s[0] for s in stuk.values()]:
        o.hide_render = True
        o.hide_set(True)

    # gloed feller voor de foto
    b = bpy.data.materials['gloed_glowstick'].node_tree.nodes['Principled BSDF']
    b.inputs['Emission Strength'].default_value = 6.0

    vloer = bpy.data.meshes.new('vloer')
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=30)
    bm.to_mesh(vloer)
    bm.free()
    vo = bpy.data.objects.new('vloer', vloer)
    col.objects.link(vo)
    vloer.materials.append(materiaal('v_aarde', '#110e0b', 0.7))

    def lamp(naam, soort, kleur, energie, pos, doel, hoek=40, straal=0.2):
        ld = bpy.data.lights.new(naam, soort)
        ld.color = lineair(kleur)
        ld.energy = energie
        if soort == 'SPOT':
            ld.spot_size = math.radians(hoek)
            ld.spot_blend = 0.6
        ld.shadow_soft_size = straal
        o = bpy.data.objects.new(naam, ld)
        o.location = pos
        o.rotation_euler = (Vector(doel) - Vector(pos)).to_track_quat('-Z', 'Y').to_euler()
        col.objects.link(o)

    # tegenlicht van het podium (achter de figuren, +Y), wat zijlicht, zwak front
    lamp('podium_cyaan', 'SPOT', '#2fe6ff', 9000, (-3.5, 9, 4.5), (0, 0, 1.0), 55, 0.5)
    lamp('podium_magenta', 'SPOT', '#ff2fd0', 9000, (3.8, 9, 4.0), (0, 0, 1.0), 55, 0.5)
    lamp('podium_paars', 'SPOT', '#8a3bff', 5000, (0, 10, 7), (0, 0, 0.5), 50, 0.5)
    lamp('vuur', 'POINT', '#ff8a3a', 120, (-4.5, -2.5, 0.6), (0, 0, 0), straal=0.3)
    lamp('front', 'AREA', '#3a4a8a', 25, (0, -7, 3), (0, 0, 1), straal=4)

    w = bpy.data.worlds.new('Nacht')
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs['Color'].default_value = (0.004, 0.005, 0.012, 1)
    w.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
    # lichte mist voor de stralen
    mist = bpy.data.meshes.new('mist')
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1)
    bm.to_mesh(mist)
    bm.free()
    mo = bpy.data.objects.new('mist', mist)
    mo.scale = (24, 20, 9)      # vooral achter de figuren: stralen, geen waas ervoor
    mo.location = (0, 9.5, 4.4)
    col.objects.link(mo)
    mm = bpy.data.materials.new('mist')
    mm.use_nodes = True
    nt = mm.node_tree
    nt.nodes.remove(nt.nodes['Principled BSDF'])
    vol = nt.nodes.new('ShaderNodeVolumePrincipled')
    vol.inputs['Density'].default_value = 0.014
    vol.inputs['Anisotropy'].default_value = 0.55
    nt.links.new(vol.outputs[0], nt.nodes['Material Output'].inputs['Volume'])
    mist.materials.append(mm)

    cam = bpy.data.cameras.new('cam')
    cam.lens = 32
    co = bpy.data.objects.new('cam', cam)
    co.location = (0, -6.4, 1.35)
    co.rotation_euler = (Vector((0, 0.8, 1.05)) - co.location).to_track_quat('-Z', 'Y').to_euler()
    col.objects.link(co)
    sc.camera = co

    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.cycles.volume_bounces = 1
    sc.cycles.max_bounces = 4
    sc.cycles.seed = ZAAD
    sc.render.resolution_x, sc.render.resolution_y = 1280, 640
    sc.view_settings.view_transform = 'AgX'
    sc.view_settings.look = 'AgX - Medium High Contrast'
    sc.render.filepath = os.path.join(HIER, 'voorbeeld-figuren.png')
    bpy.ops.render.render(write_still=True)
    print('Gerenderd:', sc.render.filepath)


# =====================================================================
def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    np.random.seed(ZAAD)

    print('Animaties lezen...')
    clips = []
    for naam, bestand, soort in ANIMATIES:
        c = lees_animatie(naam, bestand, soort)
        if soort == 'lus' and is_al_lus(c):
            zonder_wortel(c, periodiek=True)
            naad_glad(c)
            print(f'  {naam}: is al een naadloze lus ({c.beelden - 1} beelden = '
                  f'{(c.beelden - 1) / FPS:.2f} s), volledig behouden')
        elif soort == 'lus':
            zonder_wortel(c)
            maak_lus(c)
        else:
            zonder_wortel(c)  # einde: zie eindig_neutraal, zodra `staan` bestaat
        clips.append(c)

    wis_alles()
    materiaal('figuur_huid', '#0e0e12', 0.55, spiegel=0.55)
    col = bpy.data.collections.new('Dansers')
    bpy.context.scene.collection.children.link(col)
    acol = bpy.data.collections.new('Accessoires')
    bpy.context.scene.collection.children.link(acol)

    print('Personages...')
    dansers = []
    eigen = None
    wiegen_bpm = None
    verslag = {'clips': {}}
    alle_acties = {}
    for pi, (naam, bestand) in enumerate(PERSONAGES):
        arm, lijf = importeer_personage(naam, bestand, col)
        rust = Rust(arm)
        if eigen is None:
            staan = maak_staan(rust)
            wiegen, wiegen_bpm = maak_wiegen(rust)
            eigen = [staan, wiegen]
            for c in clips:
                if c.soort != 'lus':
                    eindig_neutraal(c, staan)
        sporen = []
        for c in clips + eigen:
            spoor = c.naam if pi == 0 else f'{naam}:{c.naam}'
            act, slot = schrijf_actie(arm, rust, c, f'danser_{naam}|{c.naam}')
            sporen.append((spoor, act, slot))
            if pi == 0:
                alle_acties[c.naam] = (act, slot)
                verslag['clips'][c.naam] = round((c.beelden - 1) / FPS, 3)
        zet_nla(arm, sporen)
        arm['hoogte'] = HOOGTE
        arm['fps'] = FPS
        arm['wiegen_bpm'] = round(wiegen_bpm, 3)
        arm['clips'] = json.dumps(verslag['clips'])
        dansers.append((arm, lijf))
        if pi == 0:
            rust0 = rust

    print('Accessoires...')
    stuk, hechting = accessoires(dansers[0][0], dansers[0][1], rust0, acol)
    for naam, (bot, lok, pos, q) in hechting.items():
        print(f'  {naam}: bot {bot}, positie {tuple(round(v, 4) for v in pos)}, '
              f'rotatie (x,y,z,w) {(round(q.x, 4), round(q.y, 4), round(q.z, 4), round(q.w, 4))}')

    bpy.context.scene.frame_start = 0
    bpy.context.scene.frame_end = max(c.beelden for c in clips + eigen) - 1
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HIER, 'figuren.blend'), compress=True)

    for o in bpy.context.view_layer.objects:
        o.select_set(o.users_collection[0] in (col, acol))
    pad = os.path.join(UIT, 'figuren.glb')
    bpy.ops.export_scene.gltf(
        filepath=pad, export_format='GLB', use_selection=True, export_yup=True,
        export_apply=False, export_texcoords=False, export_normals=True,
        export_tangents=False, export_materials='EXPORT', export_extras=True,
        export_skins=True, export_def_bones=False, export_animations=True,
        export_animation_mode='NLA_TRACKS', export_frame_range=False,
        export_force_sampling=True, export_frame_step=1, export_optimize_animation_size=True,
        export_anim_slide_to_zero=True, export_reset_pose_bones=True,
        export_morph=False, export_lights=False, export_cameras=False,
        export_draco_mesh_compression_enable=DRACO)
    print(f'Figuren klaar: {pad} ({os.path.getsize(pad) / 1e6:.2f} MB)')
    for k, v in verslag['clips'].items():
        print(f'  clip {k}: {v:.3f} s')

    if '--render' in argv:
        render(dansers, stuk, hechting, alle_acties)


if __name__ == '__main__':
    main()
