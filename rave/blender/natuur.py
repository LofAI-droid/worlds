"""Hulpmiddelen voor bouw_rave.py: echte CC0-texturen van Poly Haven ophalen (met cache),
PBR-materialen, en organische geometrie (buizen, vertakte bomen, bladkaarten, rotsen,
golvende doeken, afgeronde blokken).

Geometrie wordt eerst in een `Geo` verzameld (punten, vlakken, uv's, materiaal per vlak,
eventueel puntkleuren) en dan in één keer een Blender-mesh."""
import math
import os
import random
import urllib.request

import bpy  # eerst bpy: dan worden ook bmesh en mathutils beschikbaar
import bmesh
import numpy as np
from mathutils import Matrix, Vector, noise

HIER = os.path.dirname(os.path.abspath(__file__))
BRON = os.path.join(HIER, 'bronnen', 'polyhaven')     # ruwe downloads (gitignored)
TEX = os.path.join(HIER, 'texturen')                   # gebruikte, verkleinde texturen
PH = 'https://dl.polyhaven.org/file/ph-assets'


# =====================================================================
#  Downloads en texturen
# =====================================================================
def haal(url, pad):
    """Download één bestand naar pad (cache: bestaat het al, dan niets doen)."""
    if os.path.exists(pad) and os.path.getsize(pad) > 0:
        return pad
    os.makedirs(os.path.dirname(pad), exist_ok=True)
    q = urllib.request.Request(url, headers={'User-Agent': 'rave-terrein-bouw/1.0'})
    for poging in range(3):
        try:
            with urllib.request.urlopen(q, timeout=60) as r:
                data = r.read()
            with open(pad + '.deel', 'wb') as f:
                f.write(data)
            os.replace(pad + '.deel', pad)
            print('  gedownload:', os.path.basename(pad), len(data) // 1024, 'kB')
            return pad
        except Exception as e:        # noqa: BLE001
            print('  download mislukt, opnieuw:', url, e)
    raise RuntimeError('kon niet downloaden: ' + url)


def ph_bron(asset, kaart, soort='Textures'):
    """Pad naar de ruwe 1k-JPG van een Poly Haven-asset (bv. kaart 'diff', 'nor_gl', 'rough')."""
    naam = f'{asset}_{kaart}_1k.jpg'
    return haal(f'{PH}/{soort}/jpg/1k/{asset}/{naam}', os.path.join(BRON, naam))


def _pixels(img):
    w, h = img.size
    a = np.empty(w * h * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


def _laad_tex(bestand, kleurruimte):
    pad = os.path.join(TEX, bestand)
    for im in bpy.data.images:
        if im.filepath == '//texturen/' + bestand:
            return im
    img = bpy.data.images.load(pad)
    img.filepath = '//texturen/' + bestand
    img.colorspace_settings.name = kleurruimte
    return img


def ph_tex(asset, kaart, px=512, soort='Textures', bewerk=None, naam=None):
    """Haalt een kaart op, verkleint ze tot px en bewaart ze als texturen/<naam>.jpg.
    bewerk(rgba) -> rgba mag de pixels aanpassen (tint, contrast)."""
    naam = naam or f'{asset}_{kaart}'
    doel = os.path.join(TEX, naam + '.jpg')
    if not os.path.exists(doel):
        os.makedirs(TEX, exist_ok=True)
        img = bpy.data.images.load(ph_bron(asset, kaart, soort))
        if img.size[0] != px:
            img.scale(px, px)
        if bewerk is not None:
            p = bewerk(_pixels(img))
            img.pixels.foreach_set(np.clip(p, 0, 1).ravel())
        img.save(filepath=doel, quality=84)
        bpy.data.images.remove(img)
    kr = 'sRGB' if kaart == 'diff' else 'Non-Color'
    return _laad_tex(naam + '.jpg', kr)


def bewaar_rgba(naam, rgba, jpg=False):
    """rgba: (h, w, 4) float, rij 0 = BOVEN. Schrijft texturen/<naam>.png (of .jpg)."""
    os.makedirs(TEX, exist_ok=True)
    h, w, _ = rgba.shape
    ext = '.jpg' if jpg else '.png'
    pad = os.path.join(TEX, naam + ext)
    img = bpy.data.images.new(naam, w, h, alpha=not jpg)
    img.pixels.foreach_set(np.clip(np.flipud(rgba), 0, 1).astype(np.float32).ravel())
    img.filepath_raw = pad
    img.file_format = 'JPEG' if jpg else 'PNG'
    if jpg:
        img.save(filepath=pad, quality=86)
    else:
        img.save()
    bpy.data.images.remove(img)
    return _laad_tex(naam + ext, 'sRGB')


def bladatlas():
    """Jacaranda-bladveren (Poly Haven, CC0) met alfakanaal in één PNG van 512 px."""
    doel = 'blad_jacaranda.png'
    if not os.path.exists(os.path.join(TEX, doel)):
        d = bpy.data.images.load(ph_bron('jacaranda_tree', 'leaves_diff', 'Models'))
        a = bpy.data.images.load(ph_bron('jacaranda_tree', 'leaves_alpha', 'Models'))
        d.scale(512, 512)
        a.scale(512, 512)
        pd, pa = _pixels(d), _pixels(a)
        rgba = pd.copy()
        rgba[..., 3] = np.clip((pa[..., 0] - 0.35) * 3.0, 0, 1)
        # groener en iets donkerder: nachtbos
        rgba[..., :3] *= np.array([0.80, 0.95, 0.80], dtype=np.float32)
        img = bpy.data.images.new('blad_jacaranda', 512, 512, alpha=True)
        img.pixels.foreach_set(rgba.ravel())
        img.filepath_raw = os.path.join(TEX, doel)
        img.file_format = 'PNG'
        img.save()
        for i in (d, a, img):
            bpy.data.images.remove(i)
    return _laad_tex(doel, 'sRGB')


# rechthoeken (u0, v0, u1, v1) van de drie veren in de atlas (Blender-uv: v = 1 - beeldrij),
# en of de steel links (False) of rechts (True) zit
VEREN = [((0.160, 1 - 0.465, 0.985, 1 - 0.027), False),
         ((0.000, 1 - 0.691, 0.422, 1 - 0.324), False),
         ((0.246, 1 - 0.988, 0.996, 1 - 0.590), True)]


# =====================================================================
#  Materialen
# =====================================================================
MAT = {}


def lin(hexkleur):
    h = hexkleur.lstrip('#')
    return tuple((int(h[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4))


def _bsdf(naam):
    m = bpy.data.materials.new(naam)
    m.use_nodes = True
    nt = m.node_tree
    return m, nt, nt.nodes.get('Principled BSDF')


def pbr(naam, diff=None, nor=None, rough=None, kleur='#808080', ruwheid=0.9, metaal=0.0,
        normaal=1.0, puntkleur=False, dubbel=False):
    """PBR-materiaal met (optioneel) diffuse-, normal- en ruwheidstextuur."""
    if naam in MAT:
        return MAT[naam]
    m, nt, b = _bsdf(naam)
    b.inputs['Roughness'].default_value = ruwheid
    b.inputs['Metallic'].default_value = metaal
    if diff is not None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = diff
        t.location = (-600, 300)
        bron = t.outputs['Color']
        if puntkleur:
            ca = nt.nodes.new('ShaderNodeVertexColor')
            ca.layer_name = 'Kleur'
            ca.location = (-600, 520)
            mx = nt.nodes.new('ShaderNodeMix')
            mx.data_type = 'RGBA'
            mx.blend_type = 'MULTIPLY'
            mx.inputs['Factor'].default_value = 1.0
            mx.location = (-300, 400)
            nt.links.new(bron, mx.inputs['A'])
            nt.links.new(ca.outputs['Color'], mx.inputs['B'])
            bron = mx.outputs['Result']
        nt.links.new(bron, b.inputs['Base Color'])
    else:
        b.inputs['Base Color'].default_value = (*lin(kleur), 1)
    if nor is not None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = nor
        t.location = (-600, -200)
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nm.inputs['Strength'].default_value = normaal
        nm.location = (-300, -200)
        nt.links.new(t.outputs['Color'], nm.inputs['Color'])
        nt.links.new(nm.outputs['Normal'], b.inputs['Normal'])
    if rough is not None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = rough
        t.location = (-600, 50)
        nt.links.new(t.outputs['Color'], b.inputs['Roughness'])
    m.diffuse_color = (*lin(kleur), 1)
    m.use_backface_culling = not dubbel
    MAT[naam] = m
    return m


def blad_mat(naam, atlas):
    """Bladkaarten: alfa-uitknippen (glTF alphaMode MASK), dubbelzijdig."""
    if naam in MAT:
        return MAT[naam]
    m, nt, b = _bsdf(naam)
    t = nt.nodes.new('ShaderNodeTexImage')
    t.image = atlas
    t.location = (-600, 200)
    nt.links.new(t.outputs['Color'], b.inputs['Base Color'])
    r = nt.nodes.new('ShaderNodeMath')
    r.operation = 'ROUND'
    r.location = (-300, 0)
    nt.links.new(t.outputs['Alpha'], r.inputs[0])
    nt.links.new(r.outputs[0], b.inputs['Alpha'])
    b.inputs['Roughness'].default_value = 0.65
    try:
        m.surface_render_method = 'DITHERED'
    except AttributeError:
        pass
    m.use_backface_culling = False
    MAT[naam] = m
    return m


def gloed(naam, kleur, beeld=None, alfa=False, basis='#050505'):
    """Gloeiend materiaal gloed_<groep>[_<kleur>]: emissie-kleur (of -textuur), sterkte 1."""
    if naam in MAT:
        return MAT[naam]
    m, nt, b = _bsdf(naam)
    b.inputs['Base Color'].default_value = (*lin(basis), 1)
    b.inputs['Roughness'].default_value = 0.5
    b.inputs['Emission Strength'].default_value = 1.0
    if beeld is not None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = beeld
        t.location = (-600, 0)
        nt.links.new(t.outputs['Color'], b.inputs['Emission Color'])
        if alfa:
            nt.links.new(t.outputs['Alpha'], b.inputs['Alpha'])
            try:
                m.surface_render_method = 'BLENDED'
            except AttributeError:
                pass
    else:
        b.inputs['Emission Color'].default_value = (*lin(kleur), 1)
    m.diffuse_color = (*lin(kleur), 1)
    m.use_backface_culling = False
    m['gloed_kleur'] = kleur
    MAT[naam] = m
    return m


# =====================================================================
#  Geo: geometrie verzamelen
# =====================================================================
class Geo:
    def __init__(self):
        self.v = []
        self.f = []
        self.uv = []
        self.m = []
        self.glad = []
        self.mats = []
        self.kleur = None          # optioneel: kleur per punt (r, g, b)

    def mi(self, mat):
        if isinstance(mat, str):
            mat = MAT[mat]
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def p(self, co):
        self.v.append(tuple(co))
        return len(self.v) - 1

    def vlak(self, idx, mat, uvs, glad=True):
        self.f.append(tuple(idx))
        self.uv.append(list(uvs))
        self.m.append(self.mi(mat))
        self.glad.append(glad)

    def voeg(self, ander, matrix=None):
        """Voegt een andere Geo toe (eventueel getransformeerd)."""
        n0 = len(self.v)
        if matrix is None:
            self.v += ander.v
        else:
            self.v += [tuple(matrix @ Vector(c)) for c in ander.v]
        for f, uv, mi, gl in zip(ander.f, ander.uv, ander.m, ander.glad):
            self.vlak([i + n0 for i in f], ander.mats[mi], uv, gl)

    def mesh(self, naam):
        me = bpy.data.meshes.new(naam)
        me.from_pydata(self.v, [], self.f)
        uvl = me.uv_layers.new(name='UVMap')
        plat = [c for uvs in self.uv for uv in uvs for c in uv]
        uvl.data.foreach_set('uv', plat)
        me.polygons.foreach_set('material_index', self.m)
        me.polygons.foreach_set('use_smooth', self.glad)
        for m in self.mats:
            me.materials.append(m)
        if self.kleur is not None:
            ca = me.color_attributes.new('Kleur', 'BYTE_COLOR', 'POINT')
            ca.data.foreach_set('color', [c for k in self.kleur for c in (*k, 1.0)])
        me.validate(clean_customdata=False)
        me.update()
        return me

    def object(self, naam, col, plaats=None):
        me = self.mesh(naam)
        ob = bpy.data.objects.new(naam, me)
        col.objects.link(ob)
        if plaats is not None:
            ob.location = plaats
        return ob

    def tris(self):
        return sum(len(f) - 2 for f in self.f)


def assenstelsel(d):
    """Twee loodrechte vectoren op richting d."""
    d = Vector(d).normalized()
    a = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    x = d.cross(a).normalized()
    y = d.cross(x).normalized()
    return x, y


def buis(g, pts, radii, mat, n=8, tegel=1.0, dop=False, glad=True, v0=0.0, ruw=None):
    """Buis langs de punten met de gegeven stralen (parallel transport, naadloze uv).
    tegel = textuurgrootte in meter. ruw(i, j) -> factor voor knoestige schors."""
    pts = [Vector(p) for p in pts]
    rijen = []
    d0 = (pts[1] - pts[0]).normalized()
    x, y = assenstelsel(d0)
    vorige = d0
    omtrek = 2 * math.pi * max(radii[0], 0.01)
    U = max(1, round(omtrek / tegel))
    v = v0
    for i, p in enumerate(pts):
        if i < len(pts) - 1:
            d = (pts[i + 1] - p).normalized()
            if i > 0:
                d = ((pts[i + 1] - p).normalized() + (p - pts[i - 1]).normalized()).normalized()
        else:
            d = (p - pts[i - 1]).normalized()
        q = vorige.rotation_difference(d)
        x, y = q @ x, q @ y
        vorige = d
        if i > 0:
            v += (p - pts[i - 1]).length / tegel
        rij = []
        for j in range(n + 1):
            a = 2 * math.pi * (j % n) / n
            r = radii[i] * (ruw(i, j % n) if ruw else 1.0)
            rij.append((g.p(p + (x * math.cos(a) + y * math.sin(a)) * r), (U * j / n, v)))
        rijen.append(rij)
    for i in range(len(rijen) - 1):
        for j in range(n):
            a, b = rijen[i][j], rijen[i][j + 1]
            c, d = rijen[i + 1][j + 1], rijen[i + 1][j]
            g.vlak([a[0], b[0], c[0], d[0]], mat, [a[1], b[1], c[1], d[1]], glad)
    if dop:
        for rij, om in ((rijen[0], True), (rijen[-1], False)):
            idx = [r[0] for r in rij[:n]]
            uvs = [(0.5 + 0.5 * math.cos(2 * math.pi * j / n), 0.5 + 0.5 * math.sin(2 * math.pi * j / n))
                   for j in range(n)]
            if om:
                idx, uvs = idx[::-1], uvs[::-1]
            g.vlak(idx, dop if isinstance(dop, str) else mat, uvs, False)
    return v


def staaf(g, a, b, r, mat, n=6, dop=False, tegel=1.0):
    buis(g, [a, b], [r, r], mat, n=n, tegel=tegel, dop=dop)


def bm_in_geo(g, bm, mat, matrix=None, tegel=1.0, glad=False):
    """Zet een bmesh om naar Geo-vlakken met kubusprojectie-uv (wereldmaat / tegel)."""
    bm.normal_update()
    if matrix is not None:
        bm.transform(matrix)
        bm.normal_update()
    idx = {}
    for vt in bm.verts:
        idx[vt] = g.p(vt.co)
    for f in bm.faces:
        n = f.normal
        ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
        uvs = []
        for lus in f.loops:
            x, y, z = lus.vert.co
            if az >= ax and az >= ay:
                uv = (x, y)
            elif ax >= ay:
                uv = (y if n.x > 0 else -y, z)
            else:
                uv = (-x if n.y > 0 else x, z)
            uvs.append((uv[0] / tegel, uv[1] / tegel))
        g.vlak([idx[l.vert] for l in f.loops], mat, uvs, glad)
    bm.free()


def rond_blok(g, midden, half, r, mat, rot=0.0, seg=2, tegel=1.0, bol=0.0, glad=True, kantel=None):
    """Afgeschuind/afgerond blok (bevel op alle randen). bol > 0 laat de boven- en
    onderkant bol staan (kussens). kantel = extra rotatiematrix."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    for vt in bm.verts:
        vt.co = Vector((vt.co.x * half[0], vt.co.y * half[1], vt.co.z * half[2]))
    r = min(r, *[h * 0.95 for h in half])
    bmesh.ops.bevel(bm, geom=list(bm.edges) + list(bm.verts), offset=r, segments=seg,
                    profile=0.5, affect='EDGES', clamp_overlap=True)
    if bol:
        bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if e.calc_length() > max(half) * 0.9],
                                  cuts=2, use_grid_fill=True)
        for vt in bm.verts:
            fx = 1 - min(1, abs(vt.co.x) / half[0]) ** 2
            fy = 1 - min(1, abs(vt.co.y) / half[1]) ** 2
            vt.co.z *= 1 + bol * fx * fy
    m = Matrix.Translation(midden) @ Matrix.Rotation(rot, 4, 'Z')
    if kantel is not None:
        m = m @ kantel
    bm_in_geo(g, bm, mat, m, tegel, glad)


# =====================================================================
#  Bladkaarten en bomen
# =====================================================================
def veer(g, basis, richting, lengte, mat, rnd, rol=None, knik=0.18):
    """Eén blad-/veerkaart: een licht geplooide kaart (4 driehoeken) met een veer uit de atlas."""
    (u0, v0, u1, v1), rechts = VEREN[rnd.randrange(3)]
    asp = (v1 - v0) / (u1 - u0) * 1.0
    b = lengte * asp
    d = Vector(richting).normalized()
    zij = d.cross(Vector((0, 0, 1)))
    if zij.length < 1e-3:
        zij = Vector((1, 0, 0))
    zij.normalize()
    hoek = rol if rol is not None else rnd.uniform(-0.6, 0.6)
    zij = Matrix.Rotation(hoek, 3, d) @ zij
    nrm = zij.cross(d).normalized()
    if nrm.z < 0:
        nrm = -nrm
    basis = Vector(basis)
    # licht doorhangend: de punt zakt
    punt = basis + d * lengte - Vector((0, 0, lengte * rnd.uniform(0.05, 0.25)))
    mid = (basis + punt) / 2 + nrm * b * knik
    ub, ut = (u1, u0) if rechts else (u0, u1)
    vm = (v0 + v1) / 2
    P = [basis, mid + zij * b / 2, punt, mid - zij * b / 2, mid]
    i = [g.p(q) for q in P]
    uvm = ((ub + ut) / 2, vm)
    # vier driehoeken rond het midden
    g.vlak([i[0], i[1], i[4]], mat, [(ub, vm), (uvm[0], v1 if not rechts else v0), uvm], True)
    g.vlak([i[1], i[2], i[4]], mat, [(uvm[0], v1 if not rechts else v0), (ut, vm), uvm], True)
    g.vlak([i[2], i[3], i[4]], mat, [(ut, vm), (uvm[0], v0 if not rechts else v1), uvm], True)
    g.vlak([i[3], i[0], i[4]], mat, [(uvm[0], v0 if not rechts else v1), (ub, vm), uvm], True)


def _draai_weg(d, hoek, azimut):
    x, y = assenstelsel(d)
    as_ = x * math.cos(azimut) + y * math.sin(azimut)
    return (Matrix.Rotation(hoek, 3, as_) @ Vector(d)).normalized()


def boom(rnd, p):
    """Vertakte boom. p: dict met parameters. Geeft (schors-Geo, blad-Geo)."""
    gs, gb = Geo(), Geo()
    schors, blad = p['schors'], p['blad']
    eindpunten = []

    def tak(start, d, L, r, niv, v0=0.0):
        nseg = p['seg'][niv]
        pts, radii = [Vector(start)], [r]
        cur, dr = Vector(start), Vector(d)
        for i in range(nseg):
            buig = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * p['buig'][niv]
            dr = (dr + buig + Vector((0, 0, p['tropisme'][niv]))).normalized()
            cur = cur + dr * (L / nseg)
            pts.append(cur.copy())
            radii.append(r * (1 - (1 - p['eind'][niv]) * (i + 1) / nseg))
        ruw = None
        if niv == 0 and p.get('knoest'):
            k = p['knoest']
            zaad = rnd.random() * 100

            def ruw(i, j, k=k, zaad=zaad):
                return 1 + k * noise.noise(Vector((i * 0.7, j * 0.9, zaad)))
        buis(gs, pts, radii, schors, n=p['zijden'][niv], tegel=p['tegel'], ruw=ruw, v0=v0)
        if niv < len(p['aantal']):
            n = p['aantal'][niv]
            t0, t1 = p['vanaf'][niv], 1.0
            az = rnd.uniform(0, 6.28)
            for k in range(n):
                t = t0 + (t1 - t0) * (k + rnd.uniform(0.2, 0.8)) / n
                f = t * nseg
                i = min(int(f), nseg - 1)
                q = pts[i].lerp(pts[i + 1], f - i)
                rr = radii[i] + (radii[i + 1] - radii[i]) * (f - i)
                az += 2.39996 + rnd.uniform(-0.4, 0.4)
                hoek = math.radians(rnd.uniform(*p['hoek'][niv]))
                dk = _draai_weg((pts[i + 1] - pts[i]).normalized(), hoek, az)
                Lk = L * rnd.uniform(*p['lengte'][niv]) * (1.15 - 0.4 * t if niv == 0 else 1)
                tak(q, dk, Lk, max(rr * p['dikte'][niv], 0.015), niv + 1)
        else:
            eindpunten.append((pts, dr))
        return pts

    if p.get('wortels'):
        for k in range(p['wortels']):
            a = 2 * math.pi * k / p['wortels'] + rnd.uniform(-0.25, 0.25)
            R = p['stam_r']
            L = rnd.uniform(2.0, 3.5) * R
            pts = [Vector((math.cos(a) * R * 0.2, math.sin(a) * R * 0.2, R * 1.6)),
                   Vector((math.cos(a) * R * 0.9, math.sin(a) * R * 0.9, R * 0.45)),
                   Vector((math.cos(a) * L, math.sin(a) * L, -0.15))]
            buis(gs, pts, [R * 0.55, R * 0.42, R * 0.12], schors, n=7, tegel=p['tegel'])
    tak((0, 0, -0.2), (0, 0, 1), p['hoogte'], p['stam_r'], 0)

    # bladkaarten aan de uiteinden
    for pts, dr in eindpunten:
        L = sum((pts[i + 1] - pts[i]).length for i in range(len(pts) - 1))
        n = p['kaarten']
        for k in range(n):
            t = rnd.uniform(0.25, 1.0)
            f = t * (len(pts) - 1)
            i = min(int(f), len(pts) - 2)
            q = pts[i].lerp(pts[i + 1], f - i)
            d = _draai_weg(dr, math.radians(rnd.uniform(20, 85)), rnd.uniform(0, 6.28))
            d.z = d.z * 0.5 - 0.1
            veer(gb, q, d, rnd.uniform(*p['kaart']), blad, rnd)
    return gs, gb


def rots(rnd, r, mat, sub=2, plat=0.6, tegel=1.0):
    """Onregelmatige rots: icosfeer met ruis, onderaan afgevlakt."""
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
    z = rnd.random() * 50
    for vt in bm.verts:
        c = vt.co.normalized()
        f = 1 + 0.28 * noise.noise(c * 1.3 + Vector((z, 0, 0))) + 0.1 * noise.noise(c * 3.5 + Vector((0, z, 0)))
        vt.co = c * r * f
        vt.co.x *= rnd.uniform(0.9, 1.25)
        vt.co.z *= plat
        if vt.co.z < -r * 0.15:
            vt.co.z = -r * 0.15 + (vt.co.z + r * 0.15) * 0.15
    g = Geo()
    bm_in_geo(g, bm, mat, tegel=tegel, glad=True)
    return g


def doek(g, hoeken, mat, nu=14, nv=10, zak=0.6, golf=0.08, rnd=None, uvschaal=1.0, zaad=0.0):
    """Gespannen doek tussen vier hoekpunten (bilineair) met doorzakking en golving."""
    P = [Vector(h) for h in hoeken]
    idx = []
    for i in range(nu + 1):
        u = i / nu
        rij = []
        for j in range(nv + 1):
            v = j / nv
            q = (P[0] * (1 - u) * (1 - v) + P[1] * u * (1 - v) + P[2] * u * v + P[3] * (1 - u) * v)
            s = math.sin(math.pi * u) * math.sin(math.pi * v)
            q.z -= zak * s
            q.z += golf * s * noise.noise(Vector((u * 3 + zaad, v * 3, zaad)))
            rij.append(g.p(q))
        idx.append(rij)
    for i in range(nu):
        for j in range(nv):
            uvs = [(i / nu * uvschaal, j / nv * uvschaal), ((i + 1) / nu * uvschaal, j / nv * uvschaal),
                   ((i + 1) / nu * uvschaal, (j + 1) / nv * uvschaal), (i / nu * uvschaal, (j + 1) / nv * uvschaal)]
            g.vlak([idx[i][j], idx[i + 1][j], idx[i + 1][j + 1], idx[i][j + 1]], mat, uvs, True)


def zeil(g, a, b, c, mat, n=12, zak=0.5, uvschaal=1.0, zaad=0.0):
    """Driehoekig schaduwzeil a-b-c met holle randen en doorzakking (zoals UV-doeken op festivals)."""
    A, B, C = Vector(a), Vector(b), Vector(c)
    M = (A + B + C) / 3
    idx = {}
    for i in range(n + 1):
        for j in range(n + 1 - i):
            k = n - i - j
            wa, wb, wc = i / n, j / n, k / n
            q = A * wa + B * wb + C * wc
            # holle randen: trek randpunten naar het midden
            rand = min(wa, wb, wc)
            hoek = max(wa, wb, wc)
            if rand < 1e-6 and hoek < 1 - 1e-6:
                ws = sorted((wa, wb, wc))
                s = 4 * ws[1] * ws[2]
                q = q.lerp(M, 0.12 * s)
            s = 27 * wa * wb * wc
            q.z -= zak * s
            q.z += 0.06 * s * noise.noise(Vector((wa * 4 + zaad, wb * 4, zaad)))
            idx[(i, j)] = (g.p(q), ((wb + wc * 0.5) * uvschaal, wc * 0.866 * uvschaal))
    for i in range(n):
        for j in range(n - i):
            a1, b1, c1 = idx[(i, j)], idx[(i + 1, j)], idx[(i, j + 1)]
            g.vlak([a1[0], b1[0], c1[0]], mat, [a1[1], b1[1], c1[1]], True)
            if j + i + 1 < n:
                d1 = idx[(i + 1, j + 1)]
                g.vlak([b1[0], d1[0], c1[0]], mat, [b1[1], d1[1], c1[1]], True)


def kop(fx, fy):
    """Kijkrichting (fx, fy) in Blender -> hoek h in three.js (zoals Ministad):
    h kijkt naar (-sin h, -cos h) in three.js, h = 0 kijkt naar -z (naar het podium)."""
    return round(math.atan2(-fx, fy), 4)
