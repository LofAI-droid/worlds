"""Rave against the machine — bouwt met Blender het terrein: een open plek in een nachtelijk bos
met een psytrance-podium, dansvloer, reuzenboom, chill-out, kampvuur, chai-kraam, ruïnemuur,
string-art en gloeiende paddenstoelen.

Gebruik (vanuit de map rave/):

    python3.11 blender/bouw_rave.py                 # bouwen + exporteren
    python3.11 blender/bouw_rave.py -- --render     # ook de voorbeeldbeelden (Cycles, CPU)
    python3.11 blender/bouw_rave.py -- --render boom   # enkel één beeld (totaal, boom, chill)

Het script maakt:
    blender/rave.blend        het bewerkbare Blender-bestand (met lampen, mist en camera voor renders)
    rave.glb                  het terrein voor de viewer (Draco, JPG-texturen)
    botsing.json              obstakels, zitplaatsen en danserplaatsen (three.js-coördinaten)
    blender/texturen/*        gebruikte texturen (Poly Haven, CC0, verkleind) en zelfgemaakte prints
    blender/voorbeeld-*.png   (met --render) voorbeeldbeelden

Ruwe downloads van Poly Haven (CC0) komen in blender/bronnen/polyhaven/ (gitignored) en worden
alleen opgehaald als ze ontbreken. Vaste toevalszaad: elke run geeft hetzelfde terrein.
Afspraken met de viewer en de figuren: zie ../AFSPRAKEN.md.
"""
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector, noise  # noqa: E402

import natuur as N  # noqa: E402
from natuur import MAT, Geo, buis, doek, gloed, kop, pbr, rond_blok, staaf, veer, zeil  # noqa: E402

ZAAD = 2026
HIER = os.path.dirname(os.path.abspath(__file__))
UIT = os.path.dirname(HIER)                      # rave/
rnd = random.Random(ZAAD)

VLOER_R = 16.5        # dansvloer
SPEEL_R = 45.0        # vlakke speelzone
GRENS = 44.0
# zones in BLENDER-coördinaten (three.js z = -blender y)
PODIUM = (0.0, 24.0)
BOOM = (-20.0, 6.0)
CHILL = (24.0, -6.0)
VUUR = (-14.0, -22.0)
KRAAM = (16.0, -24.0)
MUUR = (-34.0, -14.0)

# verzameld voor botsing.json (Blender-coördinaten, omgezet bij het wegschrijven)
vakken = []           # (x0, y0, x1, y1, h)
rondjes = []          # (x, y, r, h)
zitplaatsen = []      # (x, y, z, h)
dansers = []          # (x, y, h, zone, z)
ankers = []


def collectie(naam, ouder=None):
    c = bpy.data.collections.new(naam)
    (ouder or bpy.context.scene.collection).children.link(c)
    return c


def hoogte(x, y):
    """Grondhoogte: vlak binnen de speelzone, glooiend daarbuiten."""
    r = math.hypot(x, y)
    if r <= SPEEL_R:
        return 0.0
    t = min(1.0, (r - SPEEL_R) / 25.0)
    t = t * t * (3 - 2 * t)
    h = t * (1.2 + 1.8 * noise.noise(Vector((x * 0.03, y * 0.03, 1.7))))
    if r > 85:
        h += (r - 85) * 0.05
    return h


# =====================================================================
#  Texturen en materialen
# =====================================================================
def _tint(f):
    f = np.array(f, dtype=np.float32)

    def bewerk(p):
        p[..., :3] *= f
        return p
    return bewerk


def psy_patroon(naam, kleuren, zaad, n=512, symm=8, jpg=True):
    """Fluorescerende print (UV-doek / visuals): kaleidoscopische mandala, lichte lijnen op donker."""
    g = np.random.default_rng(zaad)
    y, x = np.mgrid[-1:1:n * 1j, -1:1:n * 1j].astype(np.float32)
    r = np.sqrt(x * x + y * y)
    th = np.arctan2(y, x)
    k = np.abs(((th * symm / (2 * np.pi)) % 1.0) - 0.5) * 2          # 0..1 in elke sector
    f1, f2, f3 = g.uniform(10, 18), g.uniform(4, 9), g.uniform(6, 12)
    v1 = np.sin(r * f1 * np.pi + np.cos(k * f2) * 2.5)
    v2 = np.sin(k * f3 + r * 7.0) * np.cos(r * 5.0 - k * 3.0)
    v3 = np.sin((x * 9 + np.sin(y * 7)) * 1.3) * np.sin((y * 9 + np.cos(x * 6)) * 1.3)
    lijn1 = np.exp(-(v1 ** 2) * 70)
    lijn2 = np.exp(-(v2 ** 2) * 80) * 0.8
    lijn3 = np.exp(-(v3 ** 2) * 120) * 0.35
    K = [np.array(N.lin(c), dtype=np.float32) ** (1 / 2.2) for c in kleuren]
    rgb = (lijn1[..., None] * K[0] + lijn2[..., None] * K[1 % len(K)] + lijn3[..., None] * K[2 % len(K)])
    rgb += 0.025 * K[0] * (0.5 + 0.5 * np.sin(r * 30))[..., None]
    rgb = np.clip(rgb, 0, 1)
    rgba = np.ones((n, n, 4), dtype=np.float32)
    rgba[..., :3] = rgb
    return N.bewaar_rgba(naam, rgba, jpg=jpg)


def vlam_textuur():
    """Vlammentong met alfa: wit-gele kern, oranje, rode rand."""
    w, h = 128, 256
    y, x = np.mgrid[0:1:h * 1j, -1:1:w * 1j].astype(np.float32)
    t = 1 - y                                            # 0 = onder, 1 = boven
    g = np.random.default_rng(5)
    bochten = np.sin(t * 7 + 1.3) * 0.10 * t + np.sin(t * 15) * 0.04 * t
    breedte = 0.62 * np.clip(1 - t, 0, 1) ** 0.75 * np.clip(t * 5, 0, 1) ** 0.5 + 1e-3
    d = np.abs(x - bochten) / breedte
    a = np.clip(1 - d, 0, 1) ** 0.8
    a *= np.clip(t * 8, 0, 1)
    kern = np.clip(1 - d * 1.6, 0, 1) * np.clip(1 - t * 1.2, 0, 1)
    rgb = np.stack([np.ones_like(a), 0.35 + 0.55 * kern, 0.05 + 0.55 * kern ** 2], -1)
    rgb *= (0.6 + 0.4 * a)[..., None]
    _ = g
    rgba = np.concatenate([rgb, a[..., None]], -1)
    return N.bewaar_rgba('vlam', rgba)


def kelim_textuur(naam, palet, zaad):
    """Kelim-tapijt: geometrisch patroon, vermenigvuldigd met de weefstructuur van echt jute."""
    n = 512
    g = np.random.default_rng(zaad)
    y, x = np.mgrid[0:1:n * 1j, 0:1:n * 1j].astype(np.float32)
    P = [np.array(N.lin(c), dtype=np.float32) ** (1 / 2.2) for c in palet]
    rgb = np.empty((n, n, 3), dtype=np.float32)
    rgb[:] = P[0]
    rand = np.minimum(np.minimum(x, 1 - x), np.minimum(y, 1 - y))
    rgb[rand < 0.10] = P[1]
    rgb[(rand > 0.035) & (rand < 0.06)] = P[2]
    # ruiten in het middenveld
    cx, cy = (x - 0.5) * 4.0, (y - 0.5) * 2.6
    for k in range(3):
        oy = (k - 1) * 0.9
        d = np.abs(cx) * 0.7 + np.abs(cy - oy)
        rgb[(d < 0.42) & (rand > 0.1)] = P[2]
        rgb[(d < 0.30) & (rand > 0.1)] = P[3]
        rgb[(d < 0.14) & (rand > 0.1)] = P[1]
    # zigzag
    zz = np.abs(((x * 22) % 2) - 1) * 0.02
    rgb[(np.abs(rand - 0.08 - zz) < 0.006)] = P[3]
    # weefstructuur van Poly Haven-jute
    img = bpy.data.images.load(N.ph_bron('hessian_230', 'diff'))
    img.scale(n, n)
    w = N._pixels(img)[::-1, :, :3].mean(-1, keepdims=True)
    bpy.data.images.remove(img)
    rgb *= 0.55 + 0.9 * (w / max(1e-3, w.mean()) - 1) * 0.6 + 0.45
    rgb *= (0.9 + 0.1 * g.random((n, 1, 1))).astype(np.float32)
    rgba = np.ones((n, n, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(rgb * 0.8, 0, 1)
    return N.bewaar_rgba(naam, rgba, jpg=True)


def maak_materialen():
    T = N.ph_tex
    # grond
    pbr('grond_vloer', T('brown_mud_dry', 'diff', 1024, bewerk=_tint((0.85, 0.78, 0.7))),
        T('brown_mud_dry', 'nor_gl', 1024), ruwheid=0.95, puntkleur=True)
    pbr('grond_gras', T('sparse_grass', 'diff', 1024, bewerk=_tint((0.55, 0.6, 0.5))),
        T('sparse_grass', 'nor_gl', 1024), ruwheid=0.95, puntkleur=True)
    pbr('grond_bos', T('leaves_forest_ground', 'diff', 1024, bewerk=_tint((0.7, 0.66, 0.6))),
        T('leaves_forest_ground', 'nor_gl', 1024), ruwheid=0.9, puntkleur=True)
    # natuur
    pbr('schors', T('bark_brown_02', 'diff', 1024, bewerk=_tint((0.8, 0.78, 0.75))),
        T('bark_brown_02', 'nor_gl', 512), ruwheid=0.95)
    pbr('schors_reus', T('bark_platanus', 'diff', 1024), T('bark_platanus', 'nor_gl', 1024), ruwheid=0.9, normaal=1.5)
    N.blad_mat('blad', N.bladatlas())
    pbr('rots', T('lichen_rock', 'diff', 512), T('lichen_rock', 'nor_gl', 512), ruwheid=0.9)
    pbr('steen_muur', T('mossy_stone_wall', 'diff', 1024), T('mossy_stone_wall', 'nor_gl', 1024),
        ruwheid=0.92, normaal=1.6)
    pbr('stamsnede', kleur='#5a3d26', ruwheid=0.9)
    pbr('houtskool', kleur='#141110', ruwheid=1.0)
    # podium en bouwsels
    pbr('podiumvloer', T('black_painted_planks', 'diff', 512), T('black_painted_planks', 'nor_gl', 512), ruwheid=0.7)
    pbr('hout', T('weathered_planks', 'diff', 512), T('weathered_planks', 'nor_gl', 512), ruwheid=0.85)
    pbr('alu', kleur='#c9ccd2', ruwheid=0.32, metaal=1.0)
    pbr('zwart_metaal', kleur='#101012', ruwheid=0.45, metaal=0.7)
    pbr('kast', kleur='#0d0d0e', ruwheid=0.75)
    pbr('luidsprekerdoek', T('hessian_230', 'diff', 256, bewerk=_tint((0.09, 0.09, 0.1)), naam='luidsprekerdoek'),
        T('hessian_230', 'nor_gl', 256), ruwheid=0.95)
    pbr('rok', T('hessian_230', 'diff', 256, bewerk=_tint((0.05, 0.05, 0.06)), naam='rok_zwart'),
        ruwheid=1.0, dubbel=True)
    pbr('bamboe', kleur='#6f5a35', ruwheid=0.6)
    pbr('touw', kleur='#8c7a5a', ruwheid=0.9)
    pbr('messing', kleur='#b88a3e', ruwheid=0.3, metaal=1.0)
    pbr('rubber', kleur='#1a1a1a', ruwheid=0.8)
    # textiel
    pbr('tentdoek', T('hessian_230', 'diff', 512, bewerk=_tint((0.85, 0.32, 0.18)), naam='tentdoek_rood'),
        T('hessian_230', 'nor_gl', 512), ruwheid=0.95, dubbel=True)
    pbr('kraamdoek', T('hessian_230', 'diff', 256, bewerk=_tint((1.0, 0.62, 0.2)), naam='kraamdoek_saffraan'),
        ruwheid=0.95, dubbel=True)
    pbr('tapijt_1', kelim_textuur('tapijt_1', ['#6e0f16', '#1d1a3a', '#c98a2a', '#e8d8b0'], 1), ruwheid=1.0)
    pbr('tapijt_2', kelim_textuur('tapijt_2', ['#1f2a4a', '#7a1420', '#d07a24', '#d9c9a0'], 2), ruwheid=1.0)
    for naam, f in (('kussen_rood', (0.9, 0.12, 0.12)), ('kussen_paars', (0.45, 0.12, 0.6)),
                    ('kussen_oranje', (1.0, 0.45, 0.08)), ('kussen_teal', (0.05, 0.45, 0.45))):
        pbr(naam, T('floral_jacquard', 'diff', 256, bewerk=_tint(f), naam=naam), ruwheid=0.8)
    # gloed: de viewer stuurt de sterkte, hier sterkte 1
    gloed('gloed_led_magenta', '#ff1fb4')
    gloed('gloed_led_cyaan', '#14e6ff')
    gloed('gloed_doek_uv', '#9a3cff', psy_patroon('doek_uv', ['#a040ff', '#ff2fd0', '#30d0ff'], 11, symm=8))
    gloed('gloed_doek_magenta', '#ff2fd0', psy_patroon('doek_magenta', ['#ff2fd0', '#ff7a1a', '#a040ff'], 12, symm=6))
    gloed('gloed_doek_cyaan', '#18e8ff', psy_patroon('doek_cyaan', ['#18e8ff', '#9dff2a', '#a040ff'], 13, symm=10))
    gloed('gloed_scherm', '#ffffff', psy_patroon('scherm', ['#ff2fd0', '#18e8ff', '#ffb020'], 21, symm=12))
    gloed('gloed_scherm_blauw', '#2f8cff')
    gloed('gloed_stringart_cyaan', '#18e8ff')
    gloed('gloed_stringart_magenta', '#ff2fd0')
    gloed('gloed_stringart_groen', '#9dff2a')
    gloed('gloed_stringart_uv', '#9a3cff')
    gloed('gloed_paddenstoel_cyaan', '#3ff2ff', basis='#0a2a2a')
    gloed('gloed_paddenstoel_groen', '#a6ff3a', basis='#1a2a0a')
    gloed('gloed_paddenstoel_uv', '#b05cff', basis='#1a0a2a')
    gloed('gloed_lampion_rood', '#ff3a1c', basis='#3a0a05')
    gloed('gloed_lampion_warm', '#ffa040', basis='#3a2005')
    gloed('gloed_vuur', '#ff8a2a', vlam_textuur(), alfa=True)
    gloed('gloed_vuur_sintel', '#ff4a0a', basis='#1a0500')
    gloed('gloed_podium_wit', '#fff4e0', basis='#202020')
    gloed('gloed_podium_warm', '#ffb060', basis='#202020')


# =====================================================================
#  Lichtankers
# =====================================================================
def anker(col, naam, pos, doel, kleur, **extra):
    """Empty licht_*: lokale -Z = schijnrichting (zoals een Blender-spot), custom property kleur."""
    o = bpy.data.objects.new(naam, None)
    o.empty_display_type = 'SINGLE_ARROW'
    o.empty_display_size = 0.6
    o.location = pos
    d = (Vector(doel) - Vector(pos)).normalized()
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    o['kleur'] = kleur
    o['richting'] = [round(d.x, 4), round(d.z, 4), round(-d.y, 4)]       # three.js-wereld
    for k, v in extra.items():
        o[k] = v
    col.objects.link(o)
    ankers.append((naam, tuple(pos), d, kleur, extra))
    return o


# =====================================================================
#  Grond
# =====================================================================
def bouw_grond(col):
    g = Geo()
    g.kleur = []
    SEG = 192
    ringen = [0.0]
    r = 0.7
    while r < VLOER_R - 0.01:
        ringen.append(r)
        r += 0.75
    ringen.append(VLOER_R)
    r = VLOER_R + 0.8
    while r < SPEEL_R:
        ringen.append(r)
        r += 0.85
    ringen.append(SPEEL_R)
    stap = 1.0
    r = SPEEL_R
    while r < 150:
        stap *= 1.12
        r += stap
        ringen.append(r)

    def kleur(x, y, rr):
        n1 = noise.noise(Vector((x * 0.08, y * 0.08, 3.1)))
        n2 = noise.noise(Vector((x * 0.35, y * 0.35, 7.7)))
        k = 0.82 + 0.16 * n1 + 0.06 * n2
        if rr < VLOER_R:
            k *= 0.9 + 0.1 * (rr / VLOER_R)          # midden wat donkerder: platgetrapt
        if rr > 40:
            k *= max(0.2, 1 - (rr - 40) * 0.02)
        k = max(0.3, min(1.0, k))
        return (k, k * 0.98, k * 0.96)

    rijen = []
    for i, rr in enumerate(ringen):
        if rr == 0:
            x, y = 0.0, 0.0
            rijen.append([g.p((0, 0, 0))])
            g.kleur.append(kleur(0, 0, 0))
            continue
        rij = []
        for j in range(SEG):
            a = 2 * math.pi * j / SEG
            x, y = rr * math.cos(a), rr * math.sin(a)
            rij.append(g.p((x, y, hoogte(x, y))))
            g.kleur.append(kleur(x, y, rr))
        rijen.append(rij)

    def zone(x, y, rr):
        if rr < VLOER_R:
            return 'grond_vloer', 4.0
        grens = 37.0 + 4.0 * noise.noise(Vector((x * 0.12, y * 0.12, 0.5))) + 1.5 * noise.noise(Vector((x * 0.5, y * 0.5, 2.5)))
        # rond de reuzenboom en bij de muur: bladeren
        if math.hypot(x - BOOM[0], y - BOOM[1]) < 9 + 2 * noise.noise(Vector((x * 0.3, y * 0.3, 9.0))):
            return 'grond_bos', 3.0
        return ('grond_gras', 3.0) if rr < grens else ('grond_bos', 3.0)

    V = g.v
    for j in range(SEG):
        j2 = (j + 1) % SEG
        a, b, c = rijen[0][0], rijen[1][j], rijen[1][j2]
        m, t = zone(V[b][0], V[b][1], 0.5)
        g.vlak([a, b, c], m, [(V[k][0] / t, V[k][1] / t) for k in (a, b, c)], True)
    for i in range(1, len(rijen) - 1):
        for j in range(SEG):
            j2 = (j + 1) % SEG
            q = [rijen[i][j], rijen[i][j2], rijen[i + 1][j2], rijen[i + 1][j]]
            cx = sum(V[k][0] for k in q) / 4
            cy = sum(V[k][1] for k in q) / 4
            m, t = zone(cx, cy, (ringen[i] + ringen[i + 1]) / 2)
            g.vlak(q, m, [(V[k][0] / t, V[k][1] / t) for k in q], True)
    ob = g.object('grond', col)
    print('  grond:', g.tris(), 'driehoeken')
    return ob


# =====================================================================
#  Bos
# =====================================================================
BOOMSOORTEN = {
    'hoog': dict(hoogte=11.5, stam_r=0.36, seg=[6, 3, 2], zijden=[9, 6, 4], aantal=[6, 3],
                 vanaf=[0.5, 0.3], hoek=[(35, 60), (30, 55)], lengte=[(0.45, 0.6), (0.45, 0.65)],
                 dikte=[0.5, 0.55], eind=[0.35, 0.3, 0.25], buig=[0.08, 0.2, 0.3], tropisme=[0.02, 0.1, 0.05],
                 kaarten=9, kaart=(2.0, 3.0), tegel=1.5, knoest=0.08),
    'breed': dict(hoogte=8.0, stam_r=0.42, seg=[5, 4, 2], zijden=[9, 6, 4], aantal=[5, 4],
                  vanaf=[0.4, 0.25], hoek=[(45, 70), (30, 60)], lengte=[(0.7, 0.9), (0.4, 0.6)],
                  dikte=[0.55, 0.55], eind=[0.4, 0.3, 0.25], buig=[0.1, 0.18, 0.3], tropisme=[0.02, 0.06, 0.02],
                  kaarten=9, kaart=(2.0, 3.0), tegel=1.5, knoest=0.1),
    'slank': dict(hoogte=13.5, stam_r=0.28, seg=[7, 3, 2], zijden=[8, 5, 4], aantal=[6, 2],
                  vanaf=[0.55, 0.3], hoek=[(30, 55), (25, 50)], lengte=[(0.3, 0.45), (0.5, 0.7)],
                  dikte=[0.45, 0.55], eind=[0.3, 0.3, 0.25], buig=[0.06, 0.2, 0.3], tropisme=[0.0, 0.12, 0.05],
                  kaarten=10, kaart=(1.8, 2.8), tegel=1.5, knoest=0.06),
    'scheef': dict(hoogte=11.0, stam_r=0.33, seg=[6, 3, 2], zijden=[8, 6, 4], aantal=[5, 3],
                   vanaf=[0.45, 0.3], hoek=[(35, 65), (30, 55)], lengte=[(0.5, 0.7), (0.45, 0.65)],
                   dikte=[0.5, 0.55], eind=[0.35, 0.3, 0.25], buig=[0.18, 0.22, 0.3], tropisme=[0.03, 0.08, 0.03],
                   kaarten=9, kaart=(2.0, 3.0), tegel=1.5, knoest=0.1),
    # goedkope bomen voor ver weg: weinig takken, grote kaarten
    'ver_a': dict(hoogte=14.0, stam_r=0.35, seg=[3, 2], zijden=[5, 4], aantal=[5],
                  vanaf=[0.45], hoek=[(35, 60)], lengte=[(0.45, 0.6)], dikte=[0.5], eind=[0.4, 0.3],
                  buig=[0.08, 0.2], tropisme=[0.02, 0.1], kaarten=12, kaart=(3.0, 4.2), tegel=1.5),
    'ver_b': dict(hoogte=10.0, stam_r=0.4, seg=[3, 2], zijden=[5, 4], aantal=[5],
                  vanaf=[0.35], hoek=[(45, 70)], lengte=[(0.6, 0.8)], dikte=[0.5], eind=[0.4, 0.3],
                  buig=[0.1, 0.2], tropisme=[0.02, 0.05], kaarten=12, kaart=(3.0, 4.2), tegel=1.5),
}


def boom_object(col, naam, soort, zaad):
    """Maakt de schors- en bladmesh van een boomsoort (wordt daarna hergebruikt)."""
    r = random.Random(zaad)
    p = dict(BOOMSOORTEN[soort])
    p['schors'], p['blad'] = 'schors', 'blad'
    gs, gb = N.boom(r, p)
    return gs.mesh(naam + '_schors'), gb.mesh(naam + '_blad'), gs.tris() + gb.tris()


def plaats_instanties(col, naam, meshes, plaatsen):
    """Hergebruikte boommeshes als kinderen van één Empty (glTF EXT_mesh_gpu_instancing)."""
    ouder = bpy.data.objects.new(naam, None)
    col.objects.link(ouder)
    for k, (x, y, z, rot, s) in enumerate(plaatsen):
        for me in meshes:
            o = bpy.data.objects.new(f'{me.name}.{k:03d}', me)
            o.location = (x, y, z)
            o.rotation_euler = (0, 0, rot)
            o.scale = (s, s, s)
            o.parent = ouder
            col.objects.link(o)
    return ouder


def verspreid(n, rmin, rmax, afstand, bezet, poging=20000, extra=None):
    """Willekeurige plaatsen in een ring, met minimale onderlinge afstand."""
    uit = []
    for _ in range(poging):
        if len(uit) >= n:
            break
        a = rnd.uniform(0, 2 * math.pi)
        r = math.sqrt(rnd.uniform(rmin * rmin, rmax * rmax))
        x, y = r * math.cos(a), r * math.sin(a)
        if extra and not extra(x, y):
            continue
        if any((x - bx) ** 2 + (y - by) ** 2 < (afstand * max(1, bs)) ** 2 for bx, by, bs in bezet):
            continue
        uit.append((x, y))
        bezet.append((x, y, 1))
    return uit


def bouw_bos(col):
    c = collectie('Bos', col)
    tri = 0
    bezet = [(MUUR[0], MUUR[1], 3.0)]
    # boomvarianten
    soorten = ['hoog', 'breed', 'slank', 'scheef']
    meshes = {}
    for i, s in enumerate(soorten):
        ms, mb, t = boom_object(c, f'boom_{s}', s, 100 + i)
        meshes[s] = (ms, mb, t)
        print(f'  boom {s}: {t} driehoeken')
    for i, s in enumerate(['ver_a', 'ver_b']):
        ms, mb, t = boom_object(c, f'boom_{s}', s, 200 + i)
        meshes[s] = (ms, mb, t)
        print(f'  boom {s}: {t} driehoeken')

    def vrij(x, y):
        # laat de ruïne, het pad naar de start en de zones vrij
        if math.hypot(x - MUUR[0], y - MUUR[1]) < 7:
            return False
        return True

    dicht = verspreid(170, 42.5, 62, 4.6, bezet, extra=vrij)
    ver = verspreid(330, 62, 115, 6.0, bezet)
    ver += verspreid(170, 115, 140, 7.5, bezet)
    per = {s: [] for s in meshes}
    for k, (x, y) in enumerate(dicht):
        s = soorten[k % 4]
        sc = rnd.uniform(0.8, 1.25)
        per[s].append((x, y, hoogte(x, y), rnd.uniform(0, 6.28), sc))
        if math.hypot(x, y) < 58:
            rondjes.append((x, y, BOOMSOORTEN[s]['stam_r'] * sc * 1.15 + 0.1, 12.0))
    for k, (x, y) in enumerate(ver):
        s = 'ver_a' if k % 2 else 'ver_b'
        per[s].append((x, y, hoogte(x, y), rnd.uniform(0, 6.28), rnd.uniform(0.9, 1.35)))
    for s, pl in per.items():
        ms, mb, t = meshes[s]
        plaats_instanties(c, f'bos_{s}', [ms, mb], pl)
        tri += t * len(pl)
    print(f'  bos: {len(dicht)} dichte + {len(ver)} verre bomen, {tri} driehoeken')
    return dicht


def varen_geo(zaad, n=11):
    """Varen of laag struikgewas: een rozet van bladveren die uitbuigt."""
    r = random.Random(zaad)
    g = Geo()
    for k in range(n):
        a = 2 * math.pi * k / n + r.uniform(-0.3, 0.3)
        op = r.uniform(0.4, 1.1)
        d = Vector((math.cos(a), math.sin(a), op))
        veer(g, (0, 0, 0.02), d, r.uniform(0.8, 1.4), 'blad', r, rol=r.uniform(-0.4, 0.4), knik=0.12)
    return g


def bouw_onderbegroei(col, bomen):
    c = collectie('Onderbegroei', col)
    varens = [varen_geo(300 + i).mesh(f'varen_{i}') for i in range(3)]
    stenen = [N.rots(random.Random(400 + i), 0.5, 'rots', sub=2, tegel=1.2).mesh(f'steen_{i}') for i in range(3)]
    plaatsen = [[], [], []]
    for x, y in verspreid(260, 38.5, 60, 1.4, [(bx, by, 0.6) for bx, by in bomen]):
        if math.hypot(x - MUUR[0], y - MUUR[1]) < 3.0:
            continue
        plaatsen[rnd.randrange(3)].append((x, y, hoogte(x, y), rnd.uniform(0, 6.28), rnd.uniform(0.7, 1.4)))
    # extra varens aan de voet van de ruïne en de reuzenboom
    for cx, cy, rr, n in ((MUUR[0], MUUR[1], 7, 16), (BOOM[0], BOOM[1], 6, 10)):
        for _ in range(n):
            a = rnd.uniform(0, 6.28)
            d = rnd.uniform(rr * 0.5, rr)
            x, y = cx + d * math.cos(a), cy + d * math.sin(a)
            plaatsen[rnd.randrange(3)].append((x, y, 0.0, rnd.uniform(0, 6.28), rnd.uniform(0.6, 1.1)))
    tri = 0
    for i in range(3):
        plaats_instanties(c, f'varens_{i}', [varens[i]], plaatsen[i])
        tri += len(varens[i].polygons) * 4 // 3 * len(plaatsen[i])
    sp = [[], [], []]
    for x, y in verspreid(40, 36, 55, 3.0, [(bx, by, 0.5) for bx, by in bomen]):
        s = rnd.uniform(0.5, 1.6)
        sp[rnd.randrange(3)].append((x, y, hoogte(x, y) - 0.05, rnd.uniform(0, 6.28), s))
        if math.hypot(x, y) < 46 and s > 0.8:
            rondjes.append((x, y, 0.45 * s, 0.6 * s))
    for i in range(3):
        plaats_instanties(c, f'stenen_{i}', [stenen[i]], sp[i])
    print(f'  onderbegroei: {sum(map(len, plaatsen))} varens, {sum(map(len, sp))} stenen')


# =====================================================================
#  Reuzenboom
# =====================================================================
def bouw_reuzenboom(col, ac):
    c = collectie('Reuzenboom', col)
    p = dict(hoogte=11.5, stam_r=2.0, seg=[5, 5, 3, 2], zijden=[16, 10, 6, 4], aantal=[6, 4, 3],
             vanaf=[0.55, 0.3, 0.3], hoek=[(48, 72), (25, 50), (25, 55)], lengte=[(1.3, 1.6), (0.55, 0.7), (0.45, 0.6)],
             dikte=[0.55, 0.5, 0.55], eind=[0.7, 0.45, 0.3, 0.25], buig=[0.05, 0.12, 0.2, 0.3],
             tropisme=[0.0, 0.04, 0.08, 0.05], kaarten=30, kaart=(3.0, 4.3), tegel=2.0, knoest=0.12,
             wortels=7, schors='schors_reus', blad='blad')
    gs, gb = N.boom(random.Random(77), p)
    me_s, me_b = gs.mesh('reuzenboom_schors'), gb.mesh('reuzenboom_blad')
    # schaal zodat de kroon ~25 m breed en ~18 m hoog is
    xs = [v.co.x for v in me_b.vertices]
    ys = [v.co.y for v in me_b.vertices]
    zs = [v.co.z for v in me_b.vertices]
    breed = max(max(xs) - min(xs), max(ys) - min(ys))
    s = 25.0 / breed
    sz = 18.0 / max(zs)
    for me in (me_s, me_b):
        o = bpy.data.objects.new(me.name, me)
        o.location = (BOOM[0], BOOM[1], 0)
        o.scale = (s, s, sz)
        o.rotation_euler = (0, 0, 0.6)
        c.objects.link(o)
    print(f'  reuzenboom: {gs.tris() + gb.tris()} driehoeken, schaal {s:.2f}, kroon {breed * s:.1f} m, '
          f'hoogte {max(zs) * sz:.1f} m, stam {2 * 2.0 * s:.1f} m dik')
    rondjes.append((BOOM[0], BOOM[1], 2.0 * s * 1.25, 20.0))
    # uplights: magenta en oranje aan de voet
    for k in range(6):
        a = 2 * math.pi * k / 6 + 0.4
        q = (BOOM[0] + 3.4 * math.cos(a), BOOM[1] + 3.4 * math.sin(a), 0.15)
        uit = 7.0 if k % 2 else 0.6                    # om en om: kroon en stam
        doel = (BOOM[0] + uit * math.cos(a), BOOM[1] + uit * math.sin(a), 11 if k % 2 else 7)
        anker(ac, f'licht_boom_{k + 1}', q, doel, '#ff2fd0' if k % 2 == 0 else '#ff7a1a')
        # het lampje zelf: een kleine schijnwerper op de grond
        g = Geo()
        rond_blok(g, (0, 0, 0.12), (0.14, 0.12, 0.1), 0.03, 'zwart_metaal', glad=False)
        g.object(f'uplight_{k + 1}', c, None).location = (q[0], q[1], 0)
    for k, (dx, dy) in enumerate(((2.5, -2.0), (-3.0, 1.5))):
        anker(ac, f'licht_rook_{k + 4}', (BOOM[0] + dx, BOOM[1] + dy, 0.2), (BOOM[0] + dx, BOOM[1] + dy, 5), '#d0c8ff')


# =====================================================================
#  Podium, truss, DJ, scherm, luidsprekers
# =====================================================================
def truss(g, a, b, w=0.3, mat='alu'):
    """Vierkante vakwerkligger (truss) van a naar b: vier buizen met diagonalen."""
    a, b = Vector(a), Vector(b)
    d = (b - a)
    L = d.length
    d.normalize()
    x, y = N.assenstelsel(d)
    h = w / 2
    hoeken = [x * h + y * h, -x * h + y * h, -x * h - y * h, x * h - y * h]
    for c in hoeken:
        staaf(g, a + c, b + c, 0.024, mat, n=6)
    n = max(1, round(L / w))
    for k in range(n):
        p0 = a + d * (L * k / n)
        p1 = a + d * (L * (k + 1) / n)
        for i in range(4):
            c0, c1 = hoeken[i], hoeken[(i + 1) % 4]
            if k % 2:
                staaf(g, p0 + c0, p1 + c1, 0.009, mat, n=4)
            else:
                staaf(g, p0 + c1, p1 + c0, 0.009, mat, n=4)


def bewegende_kop(g, pos, doel, hangend=True):
    """Moving head: voet, beugel en kop die naar het doel kijkt, met gloeiende lens."""
    pos = Vector(pos)
    zin = -1 if hangend else 1
    rond_blok(g, pos + Vector((0, 0, zin * 0.1)), (0.2, 0.15, 0.08), 0.03, 'zwart_metaal', glad=False)
    d = (Vector(doel) - pos).normalized()
    kp = pos + Vector((0, 0, zin * 0.38))
    buis(g, [kp - d * 0.2, kp + d * 0.18], [0.12, 0.13], 'zwart_metaal', n=10, dop=True, glad=True)
    x, y = N.assenstelsel(d)
    lens = Geo()
    buis(lens, [kp + d * 0.18, kp + d * 0.19], [0.1, 0.1], 'gloed_podium_wit', n=10, dop='gloed_podium_wit')
    g.voeg(lens)
    for s in (-1, 1):
        staaf(g, pos + Vector((0, 0, zin * 0.15)) + x * 0.15 * s, kp + x * 0.15 * s, 0.02, 'zwart_metaal', n=4)


def blinder(g, pos, richting):
    """Blinder (4 lampen in een kader) die naar richting kijkt."""
    pos, d = Vector(pos), Vector(richting).normalized()
    x = d.cross(Vector((0, 0, 1))).normalized()
    z = x.cross(d)
    m = Matrix((x, z, -d)).transposed().to_4x4()
    m.translation = pos
    kader = Geo()
    rond_blok(kader, (0, 0, 0), (0.42, 0.2, 0.08), 0.02, 'zwart_metaal', glad=False)
    for k in range(4):
        cx = -0.3 + 0.2 * k
        buis(kader, [(cx, 0, -0.09), (cx, 0, -0.1)], [0.08, 0.08], 'gloed_podium_warm', n=10, dop='gloed_podium_warm')
    g.voeg(kader, m)


def bouw_podium(col, ac):
    c = collectie('Podium', col)
    px, py = PODIUM
    y0, y1 = py - 4, py + 4           # 20 .. 28
    H = 1.2
    g = Geo()
    # podiumvloer: afgeschuinde plaat met planken
    rond_blok(g, (px, py, H - 0.06), (8.0, 4.0, 0.06), 0.02, 'podiumvloer', tegel=2.0, glad=False)
    # onderbouw (zwart) en rok met plooien aan de voorkant
    rond_blok(g, (px, py + 0.2, (H - 0.12) / 2), (7.9, 3.75, (H - 0.12) / 2), 0.02, 'kast', glad=False)
    nplooi = 120
    rij_o, rij_b = [], []
    for k in range(nplooi + 1):
        x = -8.05 + 16.1 * k / nplooi
        dy = 0.05 * math.sin(k * 1.9) + 0.03 * math.sin(k * 0.7)
        rij_o.append(g.p((x, y0 - 0.06 + dy, 0.0)))
        rij_b.append(g.p((x, y0 - 0.03 + dy * 0.4, H - 0.02)))
    for k in range(nplooi):
        u0, u1 = k / nplooi * 8, (k + 1) / nplooi * 8
        g.vlak([rij_o[k], rij_o[k + 1], rij_b[k + 1], rij_b[k]], 'rok', [(u0, 0), (u1, 0), (u1, 1.2), (u0, 1.2)])
    # trap achteraan
    for k in range(4):
        hz = H * (k + 1) / 5
        rond_blok(g, (5.5, y1 + 1.2 - k * 0.3, hz / 2), (0.7, 0.16, hz / 2), 0.015, 'podiumvloer', glad=False)
    g.object('podium', c)
    vakken.append((px - 8, y0, px + 8, y1, H))

    # ---- truss: vier torens, bovenkader, middenligger
    t = Geo()
    TX, TY0, TY1, TH = 8.6, y0 - 0.4, y1 + 0.4, 8.2
    torens = [(-TX, TY0), (TX, TY0), (-TX, TY1), (TX, TY1)]
    for (x, y) in torens:
        truss(t, (x, y, 0.0), (x, y, TH + 0.15))
        rond_blok(t, (x, y, 0.02), (0.4, 0.4, 0.02), 0.01, 'zwart_metaal', glad=False)
        rondjes.append((x, y, 0.35, TH))
    for (a, b) in (((-TX, TY0), (TX, TY0)), ((-TX, TY1), (TX, TY1)), ((-TX, TY0), (-TX, TY1)),
                   ((TX, TY0), (TX, TY1)), ((-TX, py), (TX, py))):
        truss(t, (a[0], a[1], TH), (b[0], b[1], TH))
    # hoekblokken
    for (x, y) in torens:
        rond_blok(t, (x, y, TH), (0.2, 0.2, 0.2), 0.02, 'alu', glad=False)
    t.object('truss', c)

    # ---- LED-wand achter de DJ
    s = Geo()
    sx0, sx1, sz0, sz1, sy = -4.8, 4.8, H + 0.3, H + 5.3, y1 - 0.6
    s.vlak([s.p((sx0, sy, sz0)), s.p((sx1, sy, sz0)), s.p((sx1, sy, sz1)), s.p((sx0, sy, sz1))], 'gloed_scherm',
           [(0.0, 0.2), (1.0, 0.2), (1.0, 0.75), (0.0, 0.75)], False)
    rond_blok(s, (0, sy + 0.12, (sz0 + sz1) / 2), (4.9, 0.1, (sz1 - sz0) / 2 + 0.08), 0.02, 'kast', glad=False)
    # paneelnaden (dunne lijntjes) geven schaal
    for k in range(1, 8):
        x = sx0 + (sx1 - sx0) * k / 8
        staaf(s, (x, sy - 0.005, sz0), (x, sy - 0.005, sz1), 0.006, 'kast', n=4)
    for k in range(1, 5):
        z = sz0 + (sz1 - sz0) * k / 5
        staaf(s, (sx0, sy - 0.005, z), (sx1, sy - 0.005, z), 0.006, 'kast', n=4)
    for x in (sx0 - 0.15, sx1 + 0.15):
        staaf(s, (x, sy + 0.1, H), (x, sy + 0.1, TH), 0.05, 'zwart_metaal', n=6)
    s.object('ledwand', c)

    # ---- DJ-tafel met draaitafels en mengpaneel
    d = Geo()
    dy = py - 1.2
    rond_blok(d, (0, dy, H + 0.5), (1.9, 0.5, 0.5), 0.04, 'kast', glad=False)
    # UV-doek over de voorkant van de tafel
    doek(d, [(-1.95, dy - 0.53, H + 0.05), (1.95, dy - 0.53, H + 0.05), (1.95, dy - 0.53, H + 1.02),
             (-1.95, dy - 0.53, H + 1.02)], 'gloed_doek_uv', nu=12, nv=4, zak=-0.04, golf=0.05)
    for k, x in enumerate((-1.15, 0.0, 1.15)):
        breed = 0.33 if k != 1 else 0.3
        rond_blok(d, (x, dy - 0.05, H + 1.04), (breed, 0.3 if k != 1 else 0.24, 0.045), 0.02, 'zwart_metaal', glad=False)
        if k != 1:
            buis(d, [(x, dy - 0.08, H + 1.085), (x, dy - 0.08, H + 1.10)], [0.12, 0.12], 'rubber', n=16, dop=True)
            d.vlak([d.p((x - 0.1, dy + 0.12, H + 1.09)), d.p((x + 0.1, dy + 0.12, H + 1.09)),
                    d.p((x + 0.1, dy + 0.2, H + 1.13)), d.p((x - 0.1, dy + 0.2, H + 1.13))],
                   'gloed_scherm_blauw', [(0, 0), (1, 0), (1, 1), (0, 1)], False)
        else:
            for kk in range(4):
                for z in range(3):
                    buis(d, [(x - 0.15 + kk * 0.1, dy - 0.15 + z * 0.12, H + 1.085),
                             (x - 0.15 + kk * 0.1, dy - 0.15 + z * 0.12, H + 1.115)], [0.018, 0.018],
                         'rubber', n=6, dop=True)
    # monitorspeakers naast de DJ
    for x in (-2.4, 2.4):
        rond_blok(d, (x, dy - 0.2, H + 0.32), (0.3, 0.25, 0.32), 0.05, 'kast', glad=False)
        rond_blok(d, (x, dy - 0.46, H + 0.32), (0.25, 0.01, 0.27), 0.02, 'luidsprekerdoek', tegel=0.3, glad=False)
    d.object('dj_tafel', c)

    # ---- luidsprekers: grondstacks en gevlogen line arrays
    l = Geo()
    for zin in (-1, 1):
        x = zin * 10.6
        y = y0 - 0.6
        for k in range(2):           # subs
            z = 0.4 + k * 0.8
            rond_blok(l, (x, y, z), (0.75, 0.55, 0.39), 0.04, 'kast', glad=False)
            rond_blok(l, (x, y - 0.555, z), (0.66, 0.01, 0.32), 0.02, 'luidsprekerdoek', tegel=0.3, glad=False)
        for k in range(2):           # tops
            z = 1.6 + 0.27 + k * 0.55
            rond_blok(l, (x, y + 0.05, z), (0.6, 0.45, 0.26), 0.04, 'kast', glad=False)
            rond_blok(l, (x, y - 0.405, z), (0.52, 0.01, 0.2), 0.02, 'luidsprekerdoek', tegel=0.3, glad=False)
        vakken.append((x - 0.8, y - 0.6, x + 0.8, y + 0.6, 2.7))
        # line array aan de voorste toren
        xa = zin * (TX + 0.9)
        staaf(l, (xa, TY0, TH), (zin * TX, TY0, TH), 0.04, 'zwart_metaal', n=6)
        for k in range(7):
            z = TH - 0.5 - k * 0.36
            hoek = 0.03 * k * k
            kant = Matrix.Rotation(hoek, 4, 'X')
            rond_blok(l, (xa, TY0 - 0.05 - 0.04 * k * k * 0.1, z), (0.55, 0.32, 0.16), 0.03, 'kast', glad=False, kantel=kant)
            rond_blok(l, (xa, TY0 - 0.38 - 0.04 * k * k * 0.1, z), (0.5, 0.01, 0.12), 0.02, 'luidsprekerdoek',
                      tegel=0.3, glad=False, kantel=kant)
    l.object('luidsprekers', c)

    # ---- lampen op de truss + lichtankers
    f = Geo()
    kleuren = ['#ffffff', '#18e8ff', '#ff2fd0', '#a040ff', '#ff2fd0', '#18e8ff', '#ffffff', '#ff7a1a']
    for k in range(8):
        x = -7.0 + 2.0 * k
        pos = (x, TY0, TH - 0.25)
        doel = (x * 1.6 + rnd.uniform(-2, 2), -6 + rnd.uniform(-6, 6), 0)
        bewegende_kop(f, pos, doel)
        anker(ac, f'licht_spot_{k + 1}', (x, TY0, TH - 0.65), doel, kleuren[k])
    # twee spots op de achterste ligger die over het publiek scheren
    for k, x in enumerate((-5.0, 5.0)):
        pos = (x, TY1, TH - 0.25)
        doel = (x * 2.5, -25, 2)
        bewegende_kop(f, pos, doel)
        anker(ac, f'licht_spot_{k + 9}', (x, TY1, TH - 0.65), doel, '#ffffff')
    # blinders achter de DJ, naar het publiek
    for k, (x, z) in enumerate(((-6.6, 6.8), (6.6, 6.8), (-6.6, 3.2), (6.6, 3.2))):
        pos = (x, TY1 - 0.35, z)
        blinder(f, pos, (0, -1, -0.12))
        anker(ac, f'licht_blinder_{k + 1}', (x, TY1 - 0.5, z), (x * 0.6, -10, 1.5), '#ffd9a0')
    # lasers: op de voorrand van het podium en bovenop de truss
    laserkleuren = ['#39ff14', '#18e8ff', '#ff2fd0', '#39ff14', '#18e8ff', '#ff2fd0', '#39ff14', '#a040ff']
    lasers = [(-6.5, y0 + 0.4, H + 0.15), (-2.0, y0 + 0.4, H + 0.15), (2.0, y0 + 0.4, H + 0.15),
              (6.5, y0 + 0.4, H + 0.15), (-TX, TY0, TH + 0.5), (TX, TY0, TH + 0.5),
              (-3.0, py, TH - 0.4), (3.0, py, TH - 0.4)]
    for k, pos in enumerate(lasers):
        rond_blok(f, (pos[0], pos[1], pos[2] - 0.05 if pos[2] < 3 else pos[2]), (0.18, 0.2, 0.09), 0.02,
                  'zwart_metaal', glad=False)
        doel = (pos[0] * 2.2, -30, 4.0 if pos[2] < 3 else 1.5)
        anker(ac, f'licht_laser_{k + 1}', (pos[0], pos[1] - 0.22, pos[2]), doel, laserkleuren[k])
    f.object('podiumlampen', c)
    # rook voor het podium
    for k, x in enumerate((-5.0, 0.0, 5.0)):
        anker(ac, f'licht_rook_{k + 1}', (x, y0 - 1.0, 0.2), (x, y0 - 3.0, 1.0), '#c8d0ff')
    # dj en podiumdanser
    dansers.append((0.0, dy + 0.95, kop(0, -1), 'podium', H))
    dansers.append((-5.0, y0 + 2.0, kop(0.2, -1), 'podium', H))


# =====================================================================
#  UV-doeken boven podium en dansvloer, palen
# =====================================================================
def paal(g, x, y, h, mat='zwart_metaal', r=0.08, tuien=True, ankers_=None):
    staaf(g, (x, y, 0), (x, y, h), r, mat, n=8, dop=True)
    rond_blok(g, (x, y, 0.03), (0.25, 0.25, 0.03), 0.01, 'zwart_metaal', glad=False)
    if tuien:
        a0 = math.atan2(y, x)
        for k in (-0.7, 0.7):
            a = a0 + k
            q = (x + math.cos(a) * h * 0.55, y + math.sin(a) * h * 0.55, 0.05)
            staaf(g, (x, y, h * 0.95), q, 0.006, 'touw', n=3)
            rond_blok(g, q, (0.05, 0.05, 0.05), 0.01, 'zwart_metaal', glad=False)
    rondjes.append((x, y, r + 0.12, h))


def bouw_doeken(col):
    c = collectie('Doeken', col)
    g = Geo()
    TX, TY0, TY1, TH = 8.6, 19.6, 28.4, 8.2
    # links staat de reuzenboom: daar geen spanner (de kroon zelf overdekt die kant)
    palen = {'P2': (15.6, 7.0, 6.8), 'P3': (-9.5, -14.8, 6.0), 'P4': (9.5, -14.8, 6.0), 'P6': (17.5, -4.0, 5.5)}
    for x, y, h in palen.values():
        paal(g, x, y, h)
    P = {k: (v[0], v[1], v[2] - 0.1) for k, v in palen.items()}
    FL, FR = (-TX, TY0, TH), (TX, TY0, TH)
    BL, BR = (-TX, TY1, TH), (TX, TY1, TH)
    # boven het podium: twee gekruiste zeilen
    zeil(g, (FL[0], FL[1], TH + 0.2), (BR[0], BR[1], TH + 0.3), (BL[0] + 0.5, BL[1], TH + 1.8), 'gloed_doek_magenta',
         n=14, zak=0.4, zaad=1.0)
    zeil(g, (FR[0], FR[1], TH + 0.25), (BL[0], BL[1], TH + 0.35), (BR[0] - 0.5, BR[1], TH + 2.0), 'gloed_doek_cyaan',
         n=14, zak=0.4, zaad=2.0)
    # boven de dansvloer: lange spanners langs de zijkanten en twee smalle vingers naar voren
    zeil(g, (FR[0], FR[1] - 0.2, TH - 0.1), P['P2'], P['P6'], 'gloed_doek_uv', n=14, zak=0.6, zaad=4.0)
    zeil(g, (-5.5, TY0 - 0.2, TH - 0.1), (-2.2, TY0 - 0.2, TH - 0.1), P['P3'], 'gloed_doek_cyaan', n=18, zak=0.7, zaad=5.0)
    zeil(g, (2.2, TY0 - 0.2, TH - 0.1), (5.5, TY0 - 0.2, TH - 0.1), P['P4'], 'gloed_doek_magenta', n=18, zak=0.7, zaad=6.0)
    # spanbanden van de zeilhoeken naar de palen
    g.object('doeken', c)


# =====================================================================
#  LED-balken rond de dansvloer
# =====================================================================
def bouw_led(col):
    c = collectie('LED', col)
    g = Geo()
    n = 56
    R = VLOER_R + 0.25
    for k in range(n):
        a0 = 2 * math.pi * (k + 0.08) / n
        a1 = 2 * math.pi * (k + 0.92) / n
        p0 = Vector((R * math.cos(a0), R * math.sin(a0), 0.07))
        p1 = Vector((R * math.cos(a1), R * math.sin(a1), 0.07))
        mat = 'gloed_led_magenta' if k % 2 == 0 else 'gloed_led_cyaan'
        mid = (p0 + p1) / 2
        rot = math.atan2(p1.y - p0.y, p1.x - p0.x)
        half = (p1 - p0).length / 2
        rond_blok(g, (mid.x, mid.y, 0.045), (half, 0.035, 0.03), 0.008, 'alu', rot=rot, glad=False)
        # diffusor: halve buis bovenop
        buis(g, [p0 + Vector((0, 0, 0.005)), p1 + Vector((0, 0, 0.005))], [0.025, 0.025], mat, n=8, dop=True)
        for t in (0.15, 0.85):
            q = p0.lerp(p1, t)
            staaf(g, (q.x, q.y, 0.0), (q.x, q.y, 0.03), 0.012, 'zwart_metaal', n=4)
    g.object('led_balken', c)


# =====================================================================
#  Chill-out
# =====================================================================
def lampion(g, pos, mat, h=0.42, r=0.17, draad=0.8):
    x, y, z = pos
    n = 12
    pts, radii = [], []
    for k in range(9):
        t = k / 8
        pts.append((x, y, z - h * t))
        radii.append(r * (0.35 + 0.65 * math.sin(math.pi * t) ** 0.7))
    buis(g, pts, radii, mat, n=n, dop=True)
    for zz in (z + 0.01, z - h - 0.01):
        buis(g, [(x, y, zz - 0.015), (x, y, zz + 0.015)], [r * 0.38, r * 0.38], 'zwart_metaal', n=8, dop=True)
    if draad:
        staaf(g, (x, y, z), (x, y, z + draad), 0.004, 'touw', n=3)


def bouw_chill(col, ac):
    c = collectie('Chillout', col)
    cx, cy = CHILL
    g = Geo()
    # stretchtent: een gespannen doek over palen van verschillende hoogte, achteraan tot op de grond
    voor_a = math.atan2(-cy, -cx)                      # richting dansvloer: daar is de tent open
    stuur = [(0.0, 0.0, 4.4), (-2.3, 2.0, 3.3), (2.4, -1.9, 3.5)]
    for x, y, h in stuur:
        staaf(g, (cx + x, cy + y, 0), (cx + x, cy + y, h - 0.05), 0.06, 'bamboe', n=8)
        rondjes.append((cx + x, cy + y, 0.18, h))
    rand = []
    for k in range(9):
        a = voor_a + 2 * math.pi * k / 9
        achter = math.cos(a - voor_a) < -0.35
        rr = 7.6 if achter else 6.4
        h = 0.12 if achter else (2.5 if k % 2 == 0 else 2.2)
        x, y = rr * math.cos(a), rr * math.sin(a)
        rand.append((a, rr, h, achter))
        stuur.append((x, y, h))
        if achter:
            rond_blok(g, (cx + x, cy + y, 0.04), (0.06, 0.06, 0.06), 0.01, 'zwart_metaal', glad=False)
            rondjes.append((cx + x * 0.93, cy + y * 0.93, 0.6, 0.6))
        else:
            staaf(g, (cx + x, cy + y, 0), (cx + x, cy + y, h + 0.08), 0.05, 'bamboe', n=7, dop=True)
            q = (cx + (rr + 1.9) * math.cos(a), cy + (rr + 1.9) * math.sin(a), 0.03)
            staaf(g, (cx + x, cy + y, h + 0.05), q, 0.006, 'touw', n=3)
            rondjes.append((cx + x, cy + y, 0.15, h))

    def rand_r(a):
        # straal van de doekrand: tussen de hoekpunten trekt de rand naar binnen (holle randen)
        for k in range(9):
            a0_, r0, _, _ = rand[k]
            a1_, r1, _, _ = rand[(k + 1) % 9]
            d = (a - a0_) % (2 * math.pi)
            if d <= 2 * math.pi / 9 + 1e-6:
                t = d / (2 * math.pi / 9)
                return (r0 * (1 - t) + r1 * t) - 0.9 * math.sin(math.pi * t)
        return 6.5

    def doekh(x, y):
        som, w = 0.0, 0.0
        for px, py, h in stuur:
            d2 = (x - px) ** 2 + (y - py) ** 2
            wi = 1 / (d2 ** 0.9 + 0.05)
            som += wi * h
            w += wi
        return som / w

    nr, na = 12, 72
    idx = []
    for i in range(nr + 1):
        rij = []
        for j in range(na):
            a = 2 * math.pi * j / na
            rr = rand_r(a) * i / nr
            x, y = rr * math.cos(a), rr * math.sin(a)
            z = doekh(x, y) - 0.08 * math.sin(math.pi * i / nr)
            rij.append(g.p((cx + x, cy + y, z)))
        idx.append(rij)
    V = g.v
    for i in range(nr):
        for j in range(na):
            j2 = (j + 1) % na
            q = [idx[i][j], idx[i][j2], idx[i + 1][j2], idx[i + 1][j]]
            g.vlak(q, 'tentdoek', [(V[k][0] / 0.7, V[k][1] / 0.7) for k in q])
    MID_H, RAND_H, R, a0 = 4.4, 2.3, 6.4, voor_a
    # tapijten
    for k, (dx, dy, rot, sx, sy, m) in enumerate([(0, 0, 0.2, 2.6, 1.7, 'tapijt_1'), (-2.2, 1.6, 1.1, 2.2, 1.4, 'tapijt_2'),
                                                  (2.0, -1.8, -0.5, 2.3, 1.5, 'tapijt_2'), (1.8, 2.4, 0.7, 2.0, 1.3, 'tapijt_1'),
                                                  (-2.4, -2.0, -1.2, 2.2, 1.4, 'tapijt_1')]):
        z = 0.012 + 0.006 * k
        m_ = Matrix.Translation((cx + dx, cy + dy, z)) @ Matrix.Rotation(rot, 4, 'Z')
        P = [m_ @ Vector((-sx, -sy, 0)), m_ @ Vector((sx, -sy, 0)), m_ @ Vector((sx, sy, 0)), m_ @ Vector((-sx, sy, 0))]
        g.vlak([g.p(p) for p in P], m, [(0, 0), (1, 0), (1, 1), (0, 1)], False)
    # lage tafeltjes met theelichtjes
    for k, (dx, dy) in enumerate(((0.3, 0.2), (-2.0, -1.8))):
        buis(g, [(cx + dx, cy + dy, 0.02), (cx + dx, cy + dy, 0.30)], [0.35, 0.33], 'hout', n=14, dop=True, tegel=1)
        buis(g, [(cx + dx, cy + dy, 0.30), (cx + dx, cy + dy, 0.36)], [0.55, 0.55], 'hout', n=20, dop=True, tegel=1)
        for kk in range(3):
            a = kk * 2.1
            lampion(g, (cx + dx + 0.25 * math.cos(a), cy + dy + 0.25 * math.sin(a), 0.48), 'gloed_lampion_warm',
                    h=0.11, r=0.045, draad=0)
    # kussens in een kring
    kussens = ['kussen_rood', 'kussen_paars', 'kussen_oranje', 'kussen_teal']
    for ring, (rr, n) in enumerate(((3.4, 10), (5.2, 9))):
        for k in range(n):
            a = 2 * math.pi * (k + 0.5 * ring) / n + rnd.uniform(-0.1, 0.1)
            x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
            # de kant naar de dansvloer blijft open
            if math.cos(a) < -0.75 and ring == 1:
                continue
            m = kussens[(k + ring) % 4]
            rot = a + math.pi / 2 + rnd.uniform(-0.3, 0.3)
            rond_blok(g, (x, y, 0.12), (0.42, 0.36, 0.1), 0.09, m, rot=rot, seg=3, bol=0.35, tegel=0.6)
            # rugkussen
            xb, yb = cx + (rr + 0.4) * math.cos(a), cy + (rr + 0.4) * math.sin(a)
            buis(g, [(xb - 0.38 * math.sin(a), yb + 0.38 * math.cos(a), 0.17),
                     (xb + 0.38 * math.sin(a), yb - 0.38 * math.cos(a), 0.17)],
                 [0.15, 0.15], kussens[(k + ring + 1) % 4], n=10, dop=True, tegel=0.6)
            zitplaatsen.append((x, y, 0.25, kop(cx - x, cy - y)))
    # lampions onder het tentdoek
    for k in range(12):
        a = voor_a + 2 * math.pi * k / 12 + 0.2
        rr = 1.6 + 1.6 * (k % 3)
        x, y = rr * math.cos(a), rr * math.sin(a)
        z_doek = doekh(x, y) - 0.1
        if z_doek < 2.3:
            continue
        lampion(g, (cx + x, cy + y, z_doek - 0.6 - 0.25 * (k % 2)), 'gloed_lampion_rood' if k % 3 else 'gloed_lampion_warm',
                draad=0.6 + 0.25 * (k % 2) - 0.1)
    g.object('chillout', c)
    for k, (dx, dy) in enumerate(((0, 0), (-2.5, -2.5), (2.5, 2.5))):
        anker(ac, f'licht_warm_{k + 1}', (cx + dx, cy + dy, 2.2), (cx + dx, cy + dy, 0), '#ff5a2a')


# =====================================================================
#  Kampvuur
# =====================================================================
def stam(g, a, b, r, ruw=0.05, snede='stamsnede', zaad=0.0):
    def f(i, j):
        return 1 + ruw * noise.noise(Vector((i * 0.9, j * 0.8, zaad)))
    pts = [Vector(a).lerp(Vector(b), t / 5) for t in range(6)]
    buis(g, pts, [r * (1 - 0.06 * t / 5) for t in range(6)], 'schors', n=10, dop=snede, tegel=1.0, ruw=f)


def bouw_vuur(col, ac):
    c = collectie('Kampvuur', col)
    fx, fy = VUUR
    g = Geo()
    # stenen kring
    for k in range(12):
        a = 2 * math.pi * k / 12 + rnd.uniform(-0.1, 0.1)
        s = N.rots(random.Random(500 + k), rnd.uniform(0.18, 0.26), 'rots', sub=1, plat=0.7, tegel=0.8)
        g.voeg(s, Matrix.Translation((fx + 1.05 * math.cos(a), fy + 1.05 * math.sin(a), 0.03)) @ Matrix.Rotation(a, 4, 'Z'))
    # as en sintels
    buis(g, [(fx, fy, 0.0), (fx, fy, 0.03)], [0.95, 0.8], 'houtskool', n=16, dop=True)
    for k in range(14):
        a, d = rnd.uniform(0, 6.28), rnd.uniform(0, 0.6)
        rond_blok(g, (fx + d * math.cos(a), fy + d * math.sin(a), 0.06), (0.07, 0.05, 0.04), 0.02,
                  'gloed_vuur_sintel', rot=rnd.uniform(0, 3), seg=1)
    # brandhout als tipi
    for k in range(7):
        a = 2 * math.pi * k / 7 + rnd.uniform(-0.15, 0.15)
        voet = (fx + 0.62 * math.cos(a), fy + 0.62 * math.sin(a), 0.05)
        top = (fx + 0.06 * math.cos(a), fy + 0.06 * math.sin(a), 0.95)
        stam(g, voet, top, 0.065, snede='houtskool', zaad=k)
    # vlammen: gekruiste kaarten
    for k in range(6):
        a = math.pi * k / 6 + rnd.uniform(-0.1, 0.1)
        h = rnd.uniform(1.0, 1.6)
        b = h * 0.42
        d = rnd.uniform(-0.12, 0.12)
        cx_, cy_ = fx + d * math.cos(a + 1.5), fy + d * math.sin(a + 1.5)
        dx, dy = math.cos(a) * b / 2, math.sin(a) * b / 2
        u0 = 0.0
        g.vlak([g.p((cx_ - dx, cy_ - dy, 0.05)), g.p((cx_ + dx, cy_ + dy, 0.05)), g.p((cx_ + dx, cy_ + dy, 0.05 + h)),
                g.p((cx_ - dx, cy_ - dy, 0.05 + h))], 'gloed_vuur', [(u0, 0), (1, 0), (1, 1), (u0, 1)], False)
    # boomstammen als banken
    for k in range(4):
        a = 2 * math.pi * k / 4 + 0.4
        R = 3.0
        mx, my = fx + R * math.cos(a), fy + R * math.sin(a)
        tx, ty = -math.sin(a), math.cos(a)
        L = rnd.uniform(2.2, 2.8)
        r = 0.23
        stam(g, (mx - tx * L / 2, my - ty * L / 2, r * 0.85), (mx + tx * L / 2, my + ty * L / 2, r * 0.85), r, zaad=10 + k)
        for t in (-0.35, 0.0, 0.35):
            rondjes.append((mx + tx * L * t, my + ty * L * t, 0.32, 0.45))
            zitplaatsen.append((mx + tx * L * t, my + ty * L * t, 0.44, kop(fx - mx, fy - my)))
    g.object('kampvuur', c)
    rondjes.append((fx, fy, 1.3, 0.5))
    anker(ac, 'licht_vuur', (fx, fy, 0.7), (fx, fy, 3), '#ff8a2a')
    anker(ac, 'licht_rook_6', (fx, fy, 1.4), (fx, fy, 6), '#a0a0a0')


# =====================================================================
#  Chai-kraam
# =====================================================================
def bouw_kraam(col, ac):
    c = collectie('Chaikraam', col)
    kx, ky = KRAAM
    voor = Vector((-kx, -ky, 0)).normalized()          # toonbank kijkt naar het midden
    rot = math.atan2(voor.y, voor.x) - math.pi / 2       # lokale -y = voor
    M = Matrix.Translation((kx, ky, 0)) @ Matrix.Rotation(rot + math.pi, 4, 'Z')
    g = Geo()
    W, D = 1.9, 1.1
    # palen
    for sx in (-1, 1):
        for sy, h in ((-1, 2.45), (1, 2.15)):
            rond_blok(g, (sx * W, sy * D, h / 2), (0.06, 0.06, h / 2), 0.015, 'hout', glad=False, tegel=1.5)
    # toonbank
    rond_blok(g, (0, -D + 0.35, 0.52), (W - 0.05, 0.3, 0.52), 0.02, 'hout', glad=False, tegel=1.5)
    rond_blok(g, (0, -D + 0.3, 1.07), (W + 0.05, 0.4, 0.035), 0.015, 'hout', glad=False, tegel=1.5)
    # achterwand met plank
    rond_blok(g, (0, D - 0.05, 1.1), (W - 0.06, 0.03, 1.0), 0.01, 'hout', glad=False, tegel=1.5)
    rond_blok(g, (0, D - 0.25, 1.4), (W - 0.1, 0.18, 0.02), 0.01, 'hout', glad=False, tegel=1.5)
    # dak van saffraankleurig doek
    doek(g, [(-W - 0.3, -D - 0.5, 2.5), (W + 0.3, -D - 0.5, 2.5), (W + 0.3, D + 0.2, 2.2), (-W - 0.3, D + 0.2, 2.2)],
         'kraamdoek', nu=12, nv=6, zak=0.15, golf=0.05, uvschaal=7)
    # franje: plooien langs de voorkant
    rand = []
    for k in range(25):
        x = -W - 0.3 + (2 * W + 0.6) * k / 24
        rand.append((g.p((x, -D - 0.5, 2.5 - 0.01)), g.p((x, -D - 0.5 + 0.02 * math.sin(k * 2), 2.2))))
    for k in range(24):
        g.vlak([rand[k][0], rand[k + 1][0], rand[k + 1][1], rand[k][1]], 'kraamdoek',
               [(k / 4, 0), ((k + 1) / 4, 0), ((k + 1) / 4, 0.3), (k / 4, 0.3)])
    # grote messing ketel op een brander, bekers en kruiken
    buis(g, [(-0.9, -D + 0.35, 1.1), (-0.9, -D + 0.35, 1.22)], [0.18, 0.18], 'zwart_metaal', n=12, dop=True)
    prof = [(0.0, 0.2), (0.05, 0.27), (0.18, 0.29), (0.3, 0.26), (0.36, 0.2), (0.38, 0.0)]
    buis(g, [(-0.9, -D + 0.35, 1.22 + z) for z, _ in prof], [r for _, r in prof], 'messing', n=18, dop=True)
    for k in range(6):
        x = -0.2 + 0.13 * k
        buis(g, [(x, -D + 0.25, 1.105), (x, -D + 0.25, 1.2)], [0.035, 0.042], 'tapijt_1', n=8, dop=True, tegel=0.2)
    for k, x in enumerate((0.9, 1.25)):
        prof = [(0.0, 0.08), (0.12, 0.13), (0.22, 0.09), (0.3, 0.05)]
        buis(g, [(x, D - 0.25, 1.42 + z) for z, _ in prof], [r for _, r in prof], 'messing', n=12, dop=True)
    # kratten
    for k, (x, y) in enumerate(((1.4, 0.4), (1.1, 0.5), (-1.4, 0.5))):
        rond_blok(g, (x, y, 0.2 + 0.0 * k), (0.25, 0.2, 0.2), 0.015, 'hout', rot=0.1 * k, glad=False, tegel=1.0)
    # lichtjessnoer langs de dakrand
    nl = 18
    for k in range(nl + 1):
        t = k / nl
        x = -W - 0.25 + (2 * W + 0.5) * t
        z = 2.42 - 0.22 * math.sin(math.pi * t)
        buis(g, [(x, -D - 0.48, z), (x, -D - 0.48, z - 0.06)], [0.025, 0.02], 'gloed_lampion_warm', n=6, dop=True)
        if k < nl:
            x2 = -W - 0.25 + (2 * W + 0.5) * (k + 1) / nl
            z2 = 2.42 - 0.22 * math.sin(math.pi * (k + 1) / nl)
            staaf(g, (x, -D - 0.48, z), (x2, -D - 0.48, z2), 0.004, 'touw', n=3)
    # lantaarn aan een paal
    lampion(g, (W, -D - 0.05, 2.2), 'gloed_lampion_warm', h=0.3, r=0.12, draad=0.2)
    # bankjes voor de kraam
    for k, (x, y, r_) in enumerate(((-1.2, -3.0, 0.1), (1.4, -3.2, -0.15))):
        rond_blok(g, (x, y, 0.43), (0.8, 0.16, 0.03), 0.01, 'hout', rot=r_, glad=False, tegel=1.5)
        for sx in (-0.65, 0.65):
            rond_blok(g, (x + sx * math.cos(r_), y + sx * math.sin(r_), 0.2), (0.04, 0.13, 0.2), 0.01, 'hout',
                      rot=r_, glad=False)
    ob = g.object('chaikraam', c)
    ob.matrix_world = M
    # botsing: begrenzende rechthoek van toonbank + achterwand (wereld)
    hoeken = [M @ Vector((sx * (W + 0.1), sy, 0)) for sx in (-1, 1) for sy in (-D - 0.05, D + 0.05)]
    vakken.append((min(p.x for p in hoeken), min(p.y for p in hoeken), max(p.x for p in hoeken),
                   max(p.y for p in hoeken), 2.5))
    for k, (x, y, r_) in enumerate(((-1.2, -3.0, 0.1), (1.4, -3.2, -0.15))):
        q = M @ Vector((x, y, 0))
        for sx in (-0.4, 0.4):
            qq = M @ Vector((x + sx, y, 0))
            naar_kraam = M.to_3x3() @ Vector((0, 1, 0))
            zitplaatsen.append((qq.x, qq.y, 0.46, kop(naar_kraam.x, naar_kraam.y)))
        rondjes.append((q.x, q.y, 0.5, 0.45))
    q = M @ Vector((0, 0.3, 0))
    dansers.append((q.x, q.y, kop(*(M.to_3x3() @ Vector((0, -1, 0))).xy), 'chill', 0.0))
    p = M @ Vector((0, -D - 0.4, 2.3))
    anker(ac, 'licht_warm_4', tuple(p), tuple(M @ Vector((0, -2.5, 0))), '#ffa040')


# =====================================================================
#  Ruïnemuur
# =====================================================================
def muurstuk(g, s0, s1, top, dikte, mat, boog=None, zaad=0.0):
    """Muurstuk in lokale (s, z)-coördinaten: rafelige bovenrand, optioneel een boogopening.
    Wordt later met een matrix op zijn plaats gezet. top(s) = hoogte."""
    omtrek = [(s0, 0.0)]
    if boog:
        b0, b1, veer_h = boog
        omtrek += [(b0, 0.0), (b0, veer_h)]
        rb = (b1 - b0) / 2
        for k in range(1, 12):
            a = math.pi - math.pi * k / 12
            omtrek.append(((b0 + b1) / 2 + rb * math.cos(a), veer_h + rb * math.sin(a)))
        omtrek += [(b1, veer_h), (b1, 0.0)]
    omtrek.append((s1, 0.0))
    n = max(4, int((s1 - s0) / 0.35))
    for k in range(n + 1):
        s = s1 - (s1 - s0) * k / n
        omtrek.append((s, top(s)))
    # rafelig: kleine trapjes in de bovenrand zijn er al door top(); voor- en achterkant
    vo = [g.p((s, -dikte / 2, z)) for s, z in omtrek]
    ac = [g.p((s, dikte / 2, z)) for s, z in omtrek]
    T = 3.0
    g.vlak(vo, mat, [(s / T, z / T) for s, z in omtrek], False)
    g.vlak(ac[::-1], mat, [(-s / T, z / T) for s, z in omtrek[::-1]], False)
    m = len(omtrek)
    for k in range(m):
        k2 = (k + 1) % m
        (sa, za), (sb, zb) = omtrek[k], omtrek[k2]
        if za == 0 and zb == 0:
            continue
        L = math.hypot(sb - sa, zb - za)
        g.vlak([vo[k], vo[k2], ac[k2], ac[k]], mat, [(0, 0), (L / T, 0), (L / T, dikte / T), (0, dikte / T)], False)


def bouw_muur(col, ac):
    c = collectie('Ruine', col)
    mx, my = MUUR
    radiaal = Vector((mx, my, 0)).normalized()
    raak = Vector((-radiaal.y, radiaal.x, 0))
    rot = math.atan2(raak.y, raak.x)
    M = Matrix.Translation((mx, my, 0)) @ Matrix.Rotation(rot, 4, 'Z')
    g = Geo()
    r = random.Random(9)

    def rafel(basis, var, zaad):
        def top(s):
            v = basis(s) + var * noise.noise(Vector((s * 0.6, zaad, 0.3)))
            v = round(v / 0.28) * 0.28 + 0.06 * noise.noise(Vector((s * 3, zaad, 1.0)))   # steenlagen
            return max(0.4, v)
        return top

    stukken = [(-8.5, -4.6, rafel(lambda s: 2.2 + 0.25 * (s + 8.5), 0.6, 1.0), None),
               (-4.0, 2.2, rafel(lambda s: 3.9 - 0.12 * abs(s + 0.9) ** 1.4, 0.4, 2.0), (-2.1, 0.3, 1.55)),
               (2.8, 6.0, rafel(lambda s: 2.0 - 0.25 * (s - 2.8), 0.5, 3.0), None),
               (6.7, 8.4, rafel(lambda s: 0.9, 0.3, 4.0), None)]
    for k, (s0, s1, top, boog) in enumerate(stukken):
        muurstuk(g, s0, s1, top, 0.75, 'steen_muur', boog=boog, zaad=k)
        for s in np.arange(s0 + 0.4, s1, 0.8):
            q = M @ Vector((float(s), 0, 0))
            if boog and boog[0] < s < boog[1]:
                continue
            rondjes.append((q.x, q.y, 0.5, top(float(s))))
    # losse stenen
    for k in range(16):
        s = r.uniform(-9, 9)
        d = r.uniform(-2.5, 2.5)
        sz = r.uniform(0.15, 0.3)
        rond_blok(g, (s, d, sz * 0.8), (sz * 1.5, sz, sz * 0.8), 0.05, 'steen_muur', rot=r.uniform(0, 3), tegel=3.0,
                  glad=False)
    ob = g.object('ruinemuur', c)
    ob.matrix_world = M
    for k, s in enumerate((-6.5, -1.0, 4.2)):
        voet = M @ Vector((s, -1.6, 0.1))
        doel = M @ Vector((s + 0.5, -0.2, 3.5))
        anker(ac, f'licht_muur_{k + 1}', tuple(voet), tuple(doel), ['#ff8a2a', '#a040ff', '#ff8a2a'][k])


# =====================================================================
#  String-art en paddenstoelen
# =====================================================================
def draad(g, a, b, mat):
    staaf(g, a, b, 0.0055, mat, n=3)


def bouw_stringart(col):
    c = collectie('Stringart', col)
    g = Geo()
    werken = []
    # 1) mandala in een hoepel tussen twee bamboestokken
    for (hoek, R, soort, kleuren) in ((62, 41.5, 'mandala', ('gloed_stringart_magenta', 'gloed_stringart_uv', 'gloed_stringart_cyaan')),
                                       (118, 41.0, 'envelop', ('gloed_stringart_cyaan', 'gloed_stringart_magenta')),
                                       (245, 41.5, 'web', ('gloed_stringart_groen', 'gloed_stringart_uv')),
                                       (298, 41.0, 'mandala', ('gloed_stringart_cyaan', 'gloed_stringart_groen', 'gloed_stringart_uv')),
                                       (338, 41.5, 'envelop', ('gloed_stringart_uv', 'gloed_stringart_groen'))):
        a = math.radians(hoek)
        mx, my = R * math.cos(a), R * math.sin(a)
        naar = Vector((-math.cos(a), -math.sin(a), 0))       # kijkt naar het midden
        zij = Vector((-naar.y, naar.x, 0))
        werken.append((mx, my))

        def P(u, z):
            return Vector((mx, my, 0)) + zij * u + Vector((0, 0, z))
        if soort == 'mandala':
            Rm, zc = 1.45, 2.3
            for s in (-1, 1):
                staaf(g, P(s * (Rm + 0.15), 0) , P(s * (Rm + 0.15), zc + Rm + 0.5), 0.04, 'bamboe', n=6, dop=True)
                rondjes.append((P(s * (Rm + 0.15), 0).x, P(s * (Rm + 0.15), 0).y, 0.15, 4.0))
                staaf(g, P(s * (Rm + 0.15), zc), P(s * Rm, zc), 0.012, 'bamboe', n=4)
            ring = [P(Rm * math.cos(2 * math.pi * k / 48), zc + Rm * math.sin(2 * math.pi * k / 48)) for k in range(49)]
            buis(g, ring, [0.025] * 49, 'bamboe', n=5)
            for (n, stap, rr, m) in ((24, 7, Rm, kleuren[0]), (24, 11, Rm, kleuren[1]), (12, 5, Rm * 0.55, kleuren[2])):
                pts = [P(rr * math.cos(2 * math.pi * k / n + 0.13), zc + rr * math.sin(2 * math.pi * k / n + 0.13))
                       for k in range(n)]
                for k in range(n):
                    draad(g, pts[k], pts[(k + stap) % n], m)
            if True:
                pts = [P(Rm * 0.55 * math.cos(2 * math.pi * k / 12 + 0.13), zc + Rm * 0.55 * math.sin(2 * math.pi * k / 12 + 0.13)) for k in range(12)]
                buis(g, pts + [pts[0]], [0.012] * 13, 'bamboe', n=4)
        elif soort == 'envelop':
            W, Hh, z0 = 1.6, 3.2, 0.5
            for s in (-1, 1):
                staaf(g, P(s * W, 0), P(s * W, z0 + Hh + 0.3), 0.045, 'bamboe', n=6, dop=True)
                rondjes.append((P(s * W, 0).x, P(s * W, 0).y, 0.15, 4.0))
            staaf(g, P(-W, z0 + Hh), P(W, z0 + Hh), 0.03, 'bamboe', n=6)
            staaf(g, P(-W, z0), P(W, z0), 0.03, 'bamboe', n=6)
            n = 18
            for k in range(n + 1):
                t = k / n
                # vier parabolische enveloppen tussen de zijden van het kader
                draad(g, P(-W, z0 + Hh * t), P(-W + 2 * W * t, z0 + Hh), kleuren[0])
                draad(g, P(W, z0 + Hh * (1 - t)), P(W - 2 * W * t, z0), kleuren[0])
                draad(g, P(-W, z0 + Hh * (1 - t)), P(-W + 2 * W * t, z0), kleuren[1])
                draad(g, P(W, z0 + Hh * t), P(W - 2 * W * t, z0 + Hh), kleuren[1])
        else:   # web tussen drie scheve palen
            hoeken = [P(-2.0, 0), P(2.2, 0), P(0.3, 0) - naar * 1.8]
            toppen = [P(-2.3, 3.8), P(2.6, 3.4), P(0.3, 4.4) - naar * 2.1]
            for b, t in zip(hoeken, toppen):
                staaf(g, b, t, 0.05, 'bamboe', n=6, dop=True)
                rondjes.append((b.x, b.y, 0.15, 4.0))
            n = 16
            for i in range(3):
                a0, a1 = hoeken[i].lerp(toppen[i], 0.15), toppen[i]
                b0, b1 = hoeken[(i + 1) % 3].lerp(toppen[(i + 1) % 3], 0.15), toppen[(i + 1) % 3]
                for k in range(n + 1):
                    t = k / n
                    draad(g, a0.lerp(a1, t), b0.lerp(b1, 1 - t), kleuren[i % 2])
    g.object('stringart', c)
    return werken


def paddenstoel(g, pos, h, r, mat, scheef=(0, 0)):
    x, y, z = pos
    top = Vector((x + scheef[0], y + scheef[1], z + h))
    buis(g, [Vector((x, y, z)), Vector((x, y, z)).lerp(top, 0.5) + Vector((scheef[0] * 0.3, scheef[1] * 0.3, 0)), top],
         [r * 0.28, r * 0.22, r * 0.2], mat, n=5)
    prof = [(-0.05, 1.0), (0.0, 1.0), (0.4, 0.85), (0.8, 0.45), (1.0, 0.0)]
    buis(g, [top + Vector((0, 0, r * 0.55 * dz)) for dz, _ in prof], [r * f + 0.002 for _, f in prof], mat, n=8)


def bouw_paddenstoelen(col, bomen, werken):
    c = collectie('Paddenstoelen', col)
    g = Geo()
    mats = ['gloed_paddenstoel_cyaan', 'gloed_paddenstoel_groen', 'gloed_paddenstoel_uv']
    plekken = []
    # aan de voet van bomen aan de bosrand
    rand = sorted(bomen, key=lambda p: math.hypot(*p))[:40]
    for k, (bx, by) in enumerate(rand[::2]):
        a = math.atan2(-by, -bx) + rnd.uniform(-0.8, 0.8)
        plekken.append((bx + 0.6 * math.cos(a), by + 0.6 * math.sin(a)))
    for (wx, wy) in werken:
        for _ in range(2):
            a = rnd.uniform(0, 6.28)
            plekken.append((wx + 1.8 * math.cos(a), wy + 1.8 * math.sin(a)))
    # omgevallen stammen met paddenstoelen
    for k, hoek in enumerate((35, 160, 222, 275)):
        a = math.radians(hoek)
        mx, my = 43.0 * math.cos(a), 43.0 * math.sin(a)
        rr = 0.3
        t = Vector((-math.sin(a + 0.5), math.cos(a + 0.5), 0))
        L = rnd.uniform(3.5, 5.5)
        p0 = Vector((mx, my, rr * 0.8)) - t * L / 2
        p1 = Vector((mx, my, rr * 0.8)) + t * L / 2
        stam(g, p0, p1, rr, ruw=0.08, zaad=20 + k)
        for s in np.linspace(-0.4, 0.4, 3):
            q = Vector((mx, my, 0)) + t * L * float(s)
            rondjes.append((q.x, q.y, rr + 0.1, rr * 1.6))
        for kk in range(7):
            q = p0.lerp(p1, rnd.uniform(0.1, 0.9)) + Vector((0, 0, rr * 0.85))
            paddenstoel(g, tuple(q), rnd.uniform(0.04, 0.1), rnd.uniform(0.025, 0.05), mats[k % 3],
                        scheef=(rnd.uniform(-0.02, 0.02), rnd.uniform(-0.02, 0.02)))
        plekken.append((mx - math.cos(a) * 0.8, my - math.sin(a) * 0.8))
    for k, (x, y) in enumerate(plekken):
        m = mats[k % 3]
        for _ in range(rnd.randint(4, 9)):
            a, d = rnd.uniform(0, 6.28), rnd.uniform(0, 0.45)
            px, py = x + d * math.cos(a), y + d * math.sin(a)
            groot = rnd.random() < 0.25
            h = rnd.uniform(0.12, 0.32) if groot else rnd.uniform(0.05, 0.14)
            r = rnd.uniform(0.06, 0.11) if groot else rnd.uniform(0.025, 0.06)
            paddenstoel(g, (px, py, hoogte(px, py)), h, r, m,
                        scheef=(rnd.uniform(-0.04, 0.04), rnd.uniform(-0.04, 0.04)))
    g.object('paddenstoelen', c)
    print(f'  paddenstoelen: {g.tris()} driehoeken op {len(plekken)} plekken')
    return plekken


# =====================================================================
#  Dansers
# =====================================================================
def kies_dansers(plekken_rand, werken):
    bezet = []
    n = 0
    while n < 40:
        a = rnd.uniform(0, 2 * math.pi)
        r = 14.5 * math.sqrt(rnd.random())
        x, y = r * math.cos(a), r * math.sin(a)
        # dichter naar het podium toe (blender +y)
        if rnd.random() > 0.35 + 0.65 * (y + 14.5) / 29:
            continue
        if any((x - bx) ** 2 + (y - by) ** 2 < 1.25 ** 2 for bx, by in bezet):
            continue
        bezet.append((x, y))
        dx, dy = PODIUM[0] - x + rnd.uniform(-3, 3), PODIUM[1] - y
        dansers.append((x, y, kop(dx, dy), 'vloer', 0.0))
        n += 1
    cx, cy = CHILL
    for k in range(6):
        a = 2 * math.pi * k / 6 + 0.7
        x, y = cx + 2.2 * math.cos(a), cy + 2.2 * math.sin(a)
        dansers.append((x, y, kop(cx - x, cy - y), 'chill', 0.0))
    fx, fy = VUUR
    for k in range(5):
        a = 2 * math.pi * k / 5 + 0.2
        x, y = fx + 2.1 * math.cos(a), fy + 2.1 * math.sin(a)
        dansers.append((x, y, kop(fx - x, fy - y), 'vuur', 0.0))
    for k, (wx, wy) in enumerate(werken + plekken_rand[:2]):
        n_ = Vector((wx, wy, 0)).normalized()
        x, y = wx - n_.x * 2.5, wy - n_.y * 2.5
        dansers.append((x, y, kop(n_.x, n_.y), 'rand', 0.0))


# =====================================================================
#  Wereld, renderlicht, mist, camera
# =====================================================================
def maak_wereld():
    sc = bpy.context.scene
    w = bpy.data.worlds.new('Nachtlucht')
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes['Background']
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    # kleurverloop: nachtblauw boven, iets lichter (teal) aan de horizon
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.035, 0.06, 0.085, 1)
    ramp.color_ramp.elements[1].position = 0.35
    ramp.color_ramp.elements[1].color = (0.0015, 0.002, 0.007, 1)
    nt.links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    vor = nt.nodes.new('ShaderNodeTexVoronoi')
    vor.inputs['Scale'].default_value = 420
    nt.links.new(tc.outputs['Generated'], vor.inputs['Vector'])
    st = nt.nodes.new('ShaderNodeMapRange')
    st.inputs['From Min'].default_value = 0.06
    st.inputs['From Max'].default_value = 0.0
    st.inputs['To Min'].default_value = 0.0
    st.inputs['To Max'].default_value = 0.6
    nt.links.new(vor.outputs['Distance'], st.inputs['Value'])
    hor = nt.nodes.new('ShaderNodeMapRange')
    hor.inputs['From Min'].default_value = 0.02
    hor.inputs['From Max'].default_value = 0.25
    nt.links.new(sep.outputs['Z'], hor.inputs['Value'])
    mul = nt.nodes.new('ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    nt.links.new(st.outputs['Result'], mul.inputs[0])
    nt.links.new(hor.outputs['Result'], mul.inputs[1])
    add = nt.nodes.new('ShaderNodeMix')
    add.data_type = 'RGBA'
    add.blend_type = 'ADD'
    add.inputs['Factor'].default_value = 1.0
    nt.links.new(ramp.outputs['Color'], add.inputs['A'])
    nt.links.new(mul.outputs[0], add.inputs['B'])
    # de camera ziet de lucht; als licht (op grond en mist) telt ze maar voor een fractie
    lp = nt.nodes.new('ShaderNodeLightPath')
    zw = nt.nodes.new('ShaderNodeMix')
    zw.data_type = 'RGBA'
    zw.blend_type = 'MULTIPLY'
    zw.inputs['Factor'].default_value = 1.0
    zw.inputs['B'].default_value = (0.12, 0.12, 0.12, 1)
    nt.links.new(add.outputs['Result'], zw.inputs['A'])
    kies = nt.nodes.new('ShaderNodeMix')
    kies.data_type = 'RGBA'
    nt.links.new(lp.outputs['Is Camera Ray'], kies.inputs['Factor'])
    nt.links.new(zw.outputs['Result'], kies.inputs['A'])
    nt.links.new(add.outputs['Result'], kies.inputs['B'])
    nt.links.new(kies.outputs['Result'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 1.0


def renderlicht(col):
    """Echte lampen en zichtbare stralen voor de voorbeeldrenders (niet in de glb)."""
    def lamp(naam, soort, pos, d, kleur, kracht, hoek=None, straal=0.05, volume=1.0):
        L = bpy.data.lights.new(naam, soort)
        L.color = N.lin(kleur)
        L.energy = kracht
        if hasattr(L, 'shadow_soft_size'):
            L.shadow_soft_size = straal
        if soort == 'SPOT':
            L.spot_size = math.radians(hoek)
            L.spot_blend = 0.3
        try:
            L.volume_factor = volume
        except AttributeError:
            pass
        o = bpy.data.objects.new(naam, L)
        o.location = pos
        o.rotation_euler = Vector(d).to_track_quat('-Z', 'Y').to_euler()
        col.objects.link(o)
        return o

    for naam, pos, d, kleur, extra in ankers:
        if naam.startswith('licht_spot'):
            # voor de foto: een waaier van stralen over het publiek (de viewer beweegt ze zelf)
            i = int(naam.split('_')[-1]) - 1
            if i < 8:
                doel = Vector(((i - 3.5) * 6.0, -14.0, [0.5, 6, 2, 10, 10, 2, 6, 0.5][i]))
            else:
                doel = Vector((pos[0] * 4, 0.0, 30.0))
            d = (doel - Vector(pos)).normalized()
            lamp('R_' + naam, 'SPOT', pos, d, kleur, 50000, hoek=4.5, straal=0.05)
        elif naam.startswith('licht_blinder'):
            lamp('R_' + naam, 'SPOT', pos, d, kleur, 2500, hoek=28, straal=0.3)
        elif naam.startswith('licht_laser'):
            for k in range(5):
                dd = (Matrix.Rotation(math.radians(-14 + 7 * k), 3, 'Z') @ d)
                lamp(f'R_{naam}_{k}', 'SPOT', pos, dd, kleur, 200000, hoek=0.3, straal=0.002)
        elif naam.startswith('licht_boom'):
            lamp('R_' + naam, 'SPOT', pos, d, kleur, 150000, hoek=70, straal=0.15)
        elif naam == 'licht_vuur':
            lamp('R_' + naam, 'POINT', pos, d, kleur, 3000, straal=0.4)
        elif naam.startswith('licht_muur'):
            lamp('R_' + naam, 'SPOT', pos, d, kleur, 6000, hoek=70, straal=0.1)
        elif naam.startswith('licht_warm'):
            lamp('R_' + naam, 'POINT', pos, d, kleur, 700, straal=0.3)
    # zacht maanlicht van achter het podium: randlicht op het bos
    zon = bpy.data.lights.new('R_maan', 'SUN')
    zon.energy = 0.15
    zon.color = (0.55, 0.65, 1.0)
    zon.volume_factor = 0.0
    o = bpy.data.objects.new('R_maan', zon)
    o.rotation_euler = Vector((0.2, -1.0, -0.45)).to_track_quat('-Z', 'Y').to_euler()
    col.objects.link(o)
    # LED-wand werpt licht op het podium
    lamp('R_scherm', 'AREA', (0, 27.2, 3.7), (0, -1, -0.05), '#c070ff', 1500)
    bpy.data.lights['R_scherm'].size = 9.0

    # mist: volumeblok met dichtheid die naar boven toe afneemt
    me = bpy.data.meshes.new('R_mist')
    s = 75.0
    me.from_pydata([(-s, -s, -1), (s, -s, -1), (s, s, -1), (-s, s, -1), (-s, -s, 22), (s, -s, 22), (s, s, 22), (-s, s, 22)],
                   [], [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])
    m = bpy.data.materials.new('R_mist')
    m.use_nodes = True
    nt = m.node_tree
    for n_ in list(nt.nodes):
        if n_.type == 'BSDF_PRINCIPLED':
            nt.nodes.remove(n_)
    out = nt.nodes['Material Output']
    vol = nt.nodes.new('ShaderNodeVolumePrincipled')
    vol.inputs['Color'].default_value = (0.5, 0.52, 0.58, 1)
    vol.inputs['Anisotropy'].default_value = 0.7
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(geo.outputs['Position'], sep.inputs[0])
    ex = nt.nodes.new('ShaderNodeMath')
    ex.operation = 'MULTIPLY'
    ex.inputs[1].default_value = -1 / 1.2
    nt.links.new(sep.outputs['Z'], ex.inputs[0])
    e = nt.nodes.new('ShaderNodeMath')
    e.operation = 'EXPONENT'
    nt.links.new(ex.outputs[0], e.inputs[0])
    ns = nt.nodes.new('ShaderNodeTexNoise')
    ns.inputs['Scale'].default_value = 0.08
    nt.links.new(geo.outputs['Position'], ns.inputs['Vector'])
    mm = nt.nodes.new('ShaderNodeMath')
    mm.operation = 'MULTIPLY'
    nt.links.new(e.outputs[0], mm.inputs[0])
    nt.links.new(ns.outputs['Fac'], mm.inputs[1])
    sc_ = nt.nodes.new('ShaderNodeMath')
    sc_.operation = 'MULTIPLY_ADD'
    sc_.inputs[1].default_value = 0.075
    sc_.inputs[2].default_value = 0.002
    nt.links.new(mm.outputs[0], sc_.inputs[0])
    fm = nt.nodes.new('ShaderNodeMath')
    fm.name = 'mistfactor'
    fm.operation = 'MULTIPLY'
    fm.inputs[1].default_value = 1.0
    nt.links.new(sc_.outputs[0], fm.inputs[0])
    nt.links.new(fm.outputs[0], vol.inputs['Density'])
    nt.links.new(vol.outputs[0], out.inputs['Volume'])
    me.materials.append(m)
    o = bpy.data.objects.new('R_mist', me)
    col.objects.link(o)
    # rookwolken bij de rookmachines (licht_rook_*): dichtere, plaatselijke volumes
    rm = bpy.data.materials.new('R_rook')
    rm.use_nodes = True
    nt = rm.node_tree
    for n_ in list(nt.nodes):
        if n_.type == 'BSDF_PRINCIPLED':
            nt.nodes.remove(n_)
    vol = nt.nodes.new('ShaderNodeVolumePrincipled')
    vol.inputs['Color'].default_value = (0.85, 0.85, 0.9, 1)
    vol.inputs['Anisotropy'].default_value = 0.6
    tc = nt.nodes.new('ShaderNodeTexCoord')
    ns = nt.nodes.new('ShaderNodeTexNoise')
    ns.inputs['Scale'].default_value = 1.4
    ns.inputs['Detail'].default_value = 4
    nt.links.new(tc.outputs['Object'], ns.inputs['Vector'])
    gr = nt.nodes.new('ShaderNodeTexGradient')
    gr.gradient_type = 'SPHERICAL'
    nt.links.new(tc.outputs['Object'], gr.inputs['Vector'])
    mm = nt.nodes.new('ShaderNodeMath')
    mm.operation = 'MULTIPLY'
    nt.links.new(ns.outputs['Fac'], mm.inputs[0])
    nt.links.new(gr.outputs['Fac'], mm.inputs[1])
    m2 = nt.nodes.new('ShaderNodeMath')
    m2.operation = 'MULTIPLY'
    m2.inputs[1].default_value = 0.12
    nt.links.new(mm.outputs[0], m2.inputs[0])
    nt.links.new(m2.outputs[0], vol.inputs['Density'])
    nt.links.new(vol.outputs[0], nt.nodes['Material Output'].inputs['Volume'])
    import bmesh
    for naam, pos, d, kleur, extra in ankers:
        if not naam.startswith('licht_rook'):
            continue
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
        me = bpy.data.meshes.new('R_' + naam)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(rm)
        o = bpy.data.objects.new('R_' + naam, me)
        o.location = (pos[0], pos[1], 2.65)       # volledig boven de grond (geen snijlijn)
        o.scale = (4.5, 4.5, 2.6)
        col.objects.link(o)


def figuranten(col):
    """Alleen voor de voorbeeldrenders: zet dansers uit ../figuren.glb (van bouw_figuren.py)
    op de danserplaatsen, elk met een andere dans en een ander moment."""
    pad = os.path.join(UIT, 'figuren.glb')
    if not os.path.exists(pad):
        print('  (geen figuren.glb: renders zonder dansers)')
        return
    voor = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=pad)
    nieuw = [o for o in bpy.data.objects if o not in voor]
    arm = next((o for o in nieuw if o.type == 'ARMATURE'), None)
    lijf = next((o for o in nieuw if o.type == 'MESH' and o.parent == arm), None)
    if arm is None or lijf is None:
        return
    for o in nieuw:
        for c in list(o.users_collection):
            c.objects.unlink(o)
    dansen = [a for a in bpy.data.actions if a.name in ('house_1', 'house_2', 'house_3', 'wiegen')]
    r = random.Random(4)
    for k, (x, y, h, zone, z) in enumerate(dansers):
        a = arm.copy()
        col.objects.link(a)
        a.location = (x, y, z)
        a.rotation_euler = (0, 0, h + math.pi)
        s = r.uniform(0.93, 1.07)
        a.scale = (s, s, s)
        ad = a.animation_data
        for t in list(ad.nla_tracks):
            ad.nla_tracks.remove(t)
        act = dansen[r.randrange(3)] if zone in ('vloer', 'podium', 'rand') else dansen[-1]
        if zone == 'podium' and k == 0:
            act = dansen[-1]
        ad.action = act
        try:
            ad.action_slot = act.slots[0]
        except (AttributeError, IndexError):
            pass
        ad.action = None
        tr = ad.nla_tracks.new()
        st = tr.strips.new(act.name, int(1 - r.uniform(0, act.frame_range[1] - 30)), act)
        try:
            st.action_slot = act.slots[0]
        except (AttributeError, IndexError):
            pass
        m = lijf.copy()
        m.parent = a
        for mod in m.modifiers:
            if mod.type == 'ARMATURE':
                mod.object = a
        col.objects.link(m)
    for o in nieuw:
        bpy.data.objects.remove(o)
    print(f'  {len(dansers)} figuranten geplaatst')


def richt(obj, positie, doel):
    obj.location = positie
    d = Vector(doel) - Vector(positie)
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


RENDER_GLOED = {'led': 6.0, 'doek': 1.0, 'scherm': 3.0, 'stringart': 9.0, 'paddenstoel': 5.0,
                'lampion': 8.0, 'vuur': 10.0, 'podium': 25.0}


def render(alleen=(), snel=False, mist=True):
    sc = bpy.context.scene
    col = collectie('Alleen_render')
    renderlicht(col)
    if not mist:
        bpy.data.objects.remove(bpy.data.objects['R_mist'])
    figuranten(col)
    sc.frame_set(1)
    uitmap = HIER
    if os.environ.get('RAVE_DAG'):          # controlebeeld bij daglicht (alleen voor ontwikkeling)
        uitmap = os.environ['RAVE_DAG']
        bpy.data.objects['R_maan'].data.energy = 3.0
        sc.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 25.0
    for m in bpy.data.materials:
        if m.name.startswith('gloed_'):
            groep = m.name.split('_')[1]
            m.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value = RENDER_GLOED.get(groep, 3)
    cam_d = bpy.data.cameras.new('Camera')
    cam = bpy.data.objects.new('Camera', cam_d)
    col.objects.link(cam)
    sc.camera = cam
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 24 if snel else 64
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 4
    sc.cycles.volume_bounces = 0
    sc.cycles.volume_step_rate = 4.0 if snel else 2.0
    sc.cycles.volume_max_steps = 256
    sc.render.resolution_x, sc.render.resolution_y = (480, 270) if snel else (960, 540)
    sc.render.image_settings.file_format = 'PNG'
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.view_settings.look = 'AgX - Punchy'
    except TypeError:
        pass
    sc.view_settings.exposure = 0.0
    beelden = [('totaal', (0, -30, 1.7), (0, 20, 5.0), 30, 1.0),
               ('boom', (-1.0, -15.0, 1.7), (-19, 6, 6.0), 22, 0.8),
               ('chill', (13.5, -12.5, 1.6), (24.5, -5.5, 1.3), 28, 0.3),
               ('vuur', (-20.0, -28.5, 1.5), (-12.5, -20.5, 0.9), 30, 0.45)]
    for naam, pos, doel, lens, mistf in beelden:
        if mist:
            bpy.data.materials['R_mist'].node_tree.nodes['mistfactor'].inputs[1].default_value = mistf
        if alleen and naam not in alleen:
            continue
        cam_d.lens = lens
        richt(cam, pos, doel)
        sc.render.filepath = os.path.join(uitmap, f'voorbeeld-{naam}.png')
        bpy.ops.render.render(write_still=True)
        print('Gerenderd:', sc.render.filepath)


# =====================================================================
def schrijf_botsing():
    def r2(v):
        return round(v, 2)
    data = {
        'versie': 1,
        'grens': GRENS,
        'start': {'x': 0, 'z': 30, 'richting': 0},
        'vakken': [[r2(x0), r2(-y1), r2(x1), r2(-y0), r2(h)] for x0, y0, x1, y1, h in vakken],
        'rondjes': [[r2(x), r2(-y), r2(r), r2(h)] for x, y, r, h in rondjes],
        'zitplaatsen': [{'x': r2(x), 'z': r2(-y), 'y': r2(z), 'h': h} for x, y, z, h in zitplaatsen],
        'dansers': [dict({'x': r2(x), 'z': r2(-y), 'h': h, 'zone': zone}, **({'y': z} if z else {}))
                    for x, y, h, zone, z in dansers],
        'dansvloer': {'x': 0, 'z': 0, 'r': 16},
        'podium': {'x0': -8, 'z0': -28, 'x1': 8, 'z1': -20, 'y': 1.2},
    }
    with open(os.path.join(UIT, 'botsing.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'))
    return data


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    doe_render = '--render' in argv
    snel = '--snel' in argv
    alleen = [a for a in argv if not a.startswith('--')]

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    print('Materialen en texturen ...')
    maak_materialen()

    rave = collectie('Rave')
    ac = collectie('Lichtankers', rave)
    print('Grond ...')
    bouw_grond(collectie('Grond', rave))
    print('Bos ...')
    bomen = bouw_bos(rave)
    bouw_onderbegroei(rave, bomen)
    bouw_reuzenboom(rave, ac)
    print('Podium ...')
    bouw_podium(rave, ac)
    bouw_doeken(rave)
    bouw_led(rave)
    print('Zones ...')
    bouw_chill(rave, ac)
    bouw_vuur(rave, ac)
    bouw_kraam(rave, ac)
    bouw_muur(rave, ac)
    werken = bouw_stringart(rave)
    plekken = bouw_paddenstoelen(rave, bomen, werken)
    kies_dansers(plekken, werken)
    maak_wereld()

    blend = os.path.join(HIER, 'rave.blend')
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True, relative_remap=True)

    for o in bpy.context.view_layer.objects:
        o.select_set(o.type in ('MESH', 'EMPTY'))
    bpy.ops.export_scene.gltf(filepath=os.path.join(UIT, 'rave.glb'), export_format='GLB',
                              use_selection=True, export_yup=True, export_apply=True,
                              export_lights=False, export_cameras=False, export_extras=True,
                              export_gpu_instances=True, export_vertex_color='ACTIVE',
                              export_image_format='AUTO', export_jpeg_quality=82,
                              export_draco_mesh_compression_enable=True, export_draco_position_quantization=14,
                              export_draco_normal_quantization=8, export_draco_texcoord_quantization=12,
                              export_draco_color_quantization=8)
    data = schrijf_botsing()

    # totaal aantal driehoeken zoals de viewer ze tekent (instanties meegeteld)
    tri = 0
    for o in bpy.data.objects:
        if o.type == 'MESH':
            o.data.calc_loop_triangles()
            tri += len(o.data.loop_triangles)
    print(f'Rave klaar: {tri} driehoeken, {len(data["vakken"])} vakken, {len(data["rondjes"])} rondjes, '
          f'{len(data["zitplaatsen"])} zitplaatsen, {len(data["dansers"])} dansers, {len(ankers)} lichtankers, '
          f'rave.glb {os.path.getsize(os.path.join(UIT, "rave.glb")) / 1e6:.2f} MB')

    if doe_render:
        render(alleen, snel, '--zondermist' not in argv)


if __name__ == '__main__':
    main()
