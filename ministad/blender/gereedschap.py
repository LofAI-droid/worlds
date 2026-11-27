"""Gedeeld gereedschap voor bouw_stad.py en bouw_figuren.py:
texturen tekenen, materialen maken en geometrie opbouwen met bmesh."""
import math
import os

import bpy  # eerst bpy: dan worden ook bmesh en mathutils beschikbaar
import bmesh
import numpy as np
from mathutils import Matrix, Vector

HIER = os.path.dirname(os.path.abspath(__file__))
TEX_MAP = os.path.join(HIER, 'texturen')


# =====================================================================
#  Texturen (numpy -> PNG)
# =====================================================================
def srgb(hexkleur):
    h = hexkleur.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)


def lineair(hexkleur):
    return tuple(float(c) for c in srgb(hexkleur) ** 2.2)


def ruis(n, korrel, sterkte, zaad):
    g = np.random.default_rng(zaad)
    klein = g.random((max(2, n // korrel), max(2, n // korrel))).astype(np.float32)
    groot = np.kron(klein, np.ones((korrel, korrel), dtype=np.float32))[:n, :n]
    fijn = g.random((n, n)).astype(np.float32)
    return ((groot * 0.6 + fijn * 0.4) - 0.5) * sterkte


def bewaar_png(naam, rgb):
    """rgb: (h, w, 3) float in sRGB, rij 0 = boven. Geeft het bpy-beeld terug."""
    os.makedirs(TEX_MAP, exist_ok=True)
    h, w, _ = rgb.shape
    rgba = np.ones((h, w, 4), dtype=np.float32)
    rgba[..., :3] = np.clip(rgb, 0, 1)
    rgba = np.flipud(rgba)                       # Blender begint onderaan
    img = bpy.data.images.new(naam, w, h, alpha=False)
    img.pixels.foreach_set(rgba.ravel())
    pad = os.path.join(TEX_MAP, naam + '.png')
    img.filepath_raw = pad
    img.file_format = 'PNG'
    img.save()
    img.filepath = '//texturen/' + naam + '.png'
    return img


def tex_gevel(naam, muur, zaad, raam='#3d4c5c', kader='#f2efe8'):
    """Eén tegel = 3 m breed x 3 m hoog, met één raam."""
    n = 256
    rgb = np.empty((n, n, 3), dtype=np.float32)
    rgb[:] = srgb(muur)
    rgb += ruis(n, 8, 0.06, zaad)[..., None]
    voeg = (np.arange(n) % 12 == 0)
    rgb[voeg, :, :] *= 0.94
    y, x = np.mgrid[0:n, 0:n] / n
    kx0, kx1, ky0, ky1 = 0.24, 0.76, 0.16, 0.78
    kader_m = (x > kx0) & (x < kx1) & (y > ky0) & (y < ky1)
    rgb[kader_m] = srgb(kader)
    b = 0.035
    glas = (x > kx0 + b) & (x < kx1 - b) & (y > ky0 + b) & (y < ky1 - b)
    glas_kleur = srgb(raam)
    weerkaats = (0.25 * (1 - (y - ky0) / (ky1 - ky0)))[..., None]
    rgb[glas] = (glas_kleur + weerkaats * np.array([0.7, 0.8, 0.9], dtype=np.float32))[glas]
    stijl = (np.abs(x - 0.5) < 0.012) & glas
    rgb[stijl] = srgb(kader)
    dorpel = (x > kx0 - 0.03) & (x < kx1 + 0.03) & (y > ky1) & (y < ky1 + 0.035)
    rgb[dorpel] = srgb('#d9d4c8')
    return bewaar_png(naam, rgb)


def tex_kantoor(naam, zaad):
    """Glazen gevel: tegel = 3 x 3 m met twee panelen."""
    n = 256
    y, x = np.mgrid[0:n, 0:n] / n
    rgb = np.empty((n, n, 3), dtype=np.float32)
    rgb[:] = np.stack([0.45 + 0.25 * (1 - y), 0.58 + 0.22 * (1 - y), 0.72 + 0.15 * (1 - y)], -1)
    rgb += ruis(n, 32, 0.08, zaad)[..., None]
    balk = (y > 0.9) | (np.abs(x - 0.5) < 0.012) | (x < 0.012) | (x > 0.988)
    rgb[balk] = srgb('#c9ced4')
    return bewaar_png(naam, rgb)


def tex_dak(naam, kleur, zaad):
    """Dakpannen: tegel = 2 x 2 m."""
    n = 256
    rgb = np.empty((n, n, 3), dtype=np.float32)
    rgb[:] = srgb(kleur)
    rgb += ruis(n, 4, 0.08, zaad)[..., None]
    y = np.arange(n) % 16
    rgb[y < 2] *= 0.7
    for r in range(n // 16):
        verschuif = 8 if r % 2 else 0
        kol = (np.arange(n) + verschuif) % 16 == 0
        rgb[r * 16:(r + 1) * 16, kol] *= 0.8
    return bewaar_png(naam, rgb)


def tex_vlak(naam, kleur, sterkte, korrel, zaad, tegels=0, voeg=1.0):
    n = 256
    rgb = np.empty((n, n, 3), dtype=np.float32)
    rgb[:] = srgb(kleur)
    rgb += ruis(n, korrel, sterkte, zaad)[..., None]
    if tegels:
        stap = n // tegels
        lijn = (np.arange(n) % stap) < 2
        rgb[lijn, :] *= voeg
        rgb[:, lijn] *= voeg
    return bewaar_png(naam, rgb)


def tex_steen(naam, zaad):
    """Natuursteen in blokken: tegel = 3 x 3 m."""
    n = 256
    rgb = np.empty((n, n, 3), dtype=np.float32)
    rgb[:] = srgb('#cbbfa6')
    rgb += ruis(n, 16, 0.10, zaad)[..., None]
    for r in range(8):
        rgb[r * 32:r * 32 + 2] *= 0.78
        verschuif = 32 if r % 2 else 0
        for k in range(0, n, 64):
            kx = (k + verschuif) % n
            rgb[r * 32:(r + 1) * 32, kx:kx + 2] *= 0.78
    return bewaar_png(naam, rgb)


def tex_streep(naam, kleur, zaad):
    """Gestreept zonnescherm: tegel = 1 m, vijf banen."""
    n = 128
    x = np.arange(n)[None, :].repeat(n, 0)
    rgb = np.empty((n, n, 3), dtype=np.float32)
    baan = (x // (n // 6)) % 2 == 0
    rgb[:] = srgb('#f4f0e6')
    rgb[baan] = srgb(kleur)
    rgb += ruis(n, 4, 0.04, zaad)[..., None]
    return bewaar_png(naam, rgb)


def tex_interieur(naam, muur, zaad, horeca=False):
    """Achterwand van een winkel of café: tegel = 3 x 3 m, rekken met spulletjes."""
    n = 256
    g = np.random.default_rng(zaad)
    rgb = np.empty((n, n, 3), dtype=np.float32)
    rgb[:] = srgb(muur)
    rgb += ruis(n, 16, 0.05, zaad)[..., None]
    kleuren = ['#c0392b', '#e67e22', '#f1c40f', '#27ae60', '#2980b9', '#8e44ad', '#ecf0f1', '#d35400']
    if horeca:
        kleuren = ['#2e7d32', '#6d4c41', '#c62828', '#f9a825', '#e0e0e0', '#1b5e20', '#4e342e']
    planken = [60, 110, 160] if not horeca else [70, 120]
    for py in planken:
        rgb[py:py + 4, 10:n - 10] = srgb('#6b4b33')
        x = 14
        while x < n - 20:
            w = int(g.integers(5, 14)) if not horeca else int(g.integers(4, 7))
            h = int(g.integers(10, 30)) if not horeca else int(g.integers(18, 30))
            rgb[py - h:py, x:x + w] = srgb(g.choice(kleuren)) * float(g.uniform(0.8, 1.05))
            x += w + int(g.integers(1, 4))
    if horeca:
        # spiegel en een toog
        rgb[175:n, :] = srgb('#5a3a26')
        rgb[175:180, :] = srgb('#c9a46b')
    return bewaar_png(naam, rgb)


# =====================================================================
#  Materialen
# =====================================================================
MAT = {}


def materiaal(naam, kleur='#ffffff', ruwheid=0.85, beeld=None, emissie=None, metaal=0.0,
              sterkte=2.0, alfa=None):
    if naam in MAT:
        return MAT[naam]
    m = bpy.data.materials.new(naam)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get('Principled BSDF')
    bsdf.inputs['Roughness'].default_value = ruwheid
    bsdf.inputs['Metallic'].default_value = metaal
    lin = lineair(kleur)
    if beeld is not None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = beeld
        t.location = (-350, 250)
        nt.links.new(t.outputs['Color'], bsdf.inputs['Base Color'])
    else:
        bsdf.inputs['Base Color'].default_value = (*lin, 1)
    m.diffuse_color = (*lin, 1)
    if emissie:
        bsdf.inputs['Emission Color'].default_value = (*lineair(emissie), 1)
        bsdf.inputs['Emission Strength'].default_value = sterkte
    if alfa is not None:
        bsdf.inputs['Alpha'].default_value = alfa
        try:
            m.surface_render_method = 'BLENDED'
        except AttributeError:
            m.blend_method = 'BLEND'
    MAT[naam] = m
    return m


def kop(fx, fy):
    """Kijkrichting (fx, fy) in Blender -> draaihoek rond de verticale as in three.js
    (een model kijkt naar -Z; hoek h kijkt naar (-sin h, -cos h))."""
    return round(math.atan2(-fx, fy), 4)


# =====================================================================
#  Bouwer: verzamelt geometrie voor één object
# =====================================================================
UIT = {'n': (0, 1), 'z': (0, -1), 'o': (1, 0), 'w': (-1, 0)}


class Bouwer:
    def __init__(self, naam, collectie):
        self.naam = naam
        self.col = collectie
        self.bm = bmesh.new()
        self.uv = self.bm.loops.layers.uv.new('UVMap')
        self.mats = []

    def mi(self, naam):
        m = MAT[naam]
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def vlak(self, punten, mat, uvs=None):
        vs = [self.bm.verts.new(p) for p in punten]
        f = self.bm.faces.new(vs)
        f.material_index = self.mi(mat)
        if uvs is None:
            uvs = [(0, 0)] * len(punten)
        for lus, uv in zip(f.loops, uvs):
            lus[self.uv].uv = uv
        return f

    def projecteer(self, faces, schaal=1.0):
        """Vlakke projectie per vlak, volgens de dominante normaal."""
        for f in faces:
            n = f.normal
            ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
            for lus in f.loops:
                x, y, z = lus.vert.co
                if az >= ax and az >= ay:
                    uv = (x, y)
                elif ax >= ay:
                    uv = (y if n.x > 0 else -y, z)
                else:
                    uv = (-x if n.y > 0 else x, z)
                lus[self.uv].uv = (uv[0] / schaal, uv[1] / schaal)

    def doos(self, x0, y0, z0, x1, y1, z1, zij, top=None, bodem=False, raster=None, schaal=1.0, mats=None):
        """Balk. raster = tegelgrootte voor gevels (ramen passen precies op elke zijde).
        mats: ander materiaal per zijde, bv. {'n': 'interieur'}."""
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6 or z1 - z0 < 1e-6:
            raise ValueError(f'platte doos: {(x0, y0, z0, x1, y1, z1)}')
        top = top or zij
        mats = mats or {}
        P = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        vlakken = [((0, 1, 5, 4), 'z'), ((1, 2, 6, 5), 'o'), ((2, 3, 7, 6), 'n'),
                   ((3, 0, 4, 7), 'w'), ((4, 5, 6, 7), 't')]
        if bodem:
            vlakken.append(((3, 2, 1, 0), 'b'))
        uit = []
        for idx, kant in vlakken:
            pts = [P[i] for i in idx]
            mat = mats.get(kant, top if kant in 'tb' else zij)
            if kant in 'zn':
                breedte = x1 - x0
            elif kant in 'ow':
                breedte = y1 - y0
            else:
                breedte = None
            if breedte is not None and raster and mat == zij:
                su = breedte / max(1, round(breedte / raster))
                u = [0, breedte / su, breedte / su, 0]
                v = [0, 0, (z1 - z0) / raster, (z1 - z0) / raster]
                uvs = list(zip(u, v))
            elif breedte is not None:
                h = z1 - z0
                uvs = [(0, 0), (breedte / schaal, 0), (breedte / schaal, h / schaal), (0, h / schaal)]
            else:
                uvs = [(p[0] / schaal, p[1] / schaal) for p in pts]
            uit.append(self.vlak(pts, mat, uvs))
        return uit

    def zadeldak(self, x0, y0, x1, y1, h, nok, dak, muur, langs_x=True, raster=3.0):
        """Zadeldak; de nok loopt evenwijdig aan x (langs_x) of aan y."""
        b = [(x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h)]
        if langs_x:
            ym = (y0 + y1) / 2
            r0, r1 = (x0, ym, h + nok), (x1, ym, h + nok)
            helling = math.hypot((y1 - y0) / 2, nok)
            L = x1 - x0
            uv = [(0, 0), (L / 2, 0), (L / 2, helling / 2), (0, helling / 2)]
            self.vlak([b[0], b[1], r1, r0], dak, uv)
            self.vlak([b[2], b[3], r0, r1], dak, uv)
            d = y1 - y0
            su = d / max(1, round(d / raster))
            self.vlak([b[3], b[0], r0], muur, [(0, 0.0), (d / su, 0.0), (d / su / 2, nok / raster)])
            self.vlak([b[1], b[2], r1], muur, [(0, 0.0), (d / su, 0.0), (d / su / 2, nok / raster)])
        else:
            xm = (x0 + x1) / 2
            r0, r1 = (xm, y0, h + nok), (xm, y1, h + nok)
            helling = math.hypot((x1 - x0) / 2, nok)
            L = y1 - y0
            uv = [(0, 0), (L / 2, 0), (L / 2, helling / 2), (0, helling / 2)]
            self.vlak([b[1], b[2], r1, r0], dak, uv)
            self.vlak([b[3], b[0], r0, r1], dak, uv)
            d = x1 - x0
            su = d / max(1, round(d / raster))
            self.vlak([b[0], b[1], r0], muur, [(0, 0.0), (d / su, 0.0), (d / su / 2, nok / raster)])
            self.vlak([b[2], b[3], r1], muur, [(0, 0.0), (d / su, 0.0), (d / su / 2, nok / raster)])

    def piramide(self, x0, y0, x1, y1, h, top, mat):
        b = [(x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h)]
        t = ((x0 + x1) / 2, (y0 + y1) / 2, h + top)
        for i in range(4):
            self.vlak([b[i], b[(i + 1) % 4], t], mat, [(0, 0), (1.5, 0), (0.75, top / 2)])

    def _na(self, verts, mat, schaal=1.0):
        faces = {f for v in verts for f in v.link_faces}
        for f in faces:
            f.material_index = self.mi(mat)
        self.bm.normal_update()
        self.projecteer(faces, schaal)
        return faces

    def cilinder(self, x, y, z, r, h, mat, seg=8, r_top=None, schaal=1.0, matrix=None):
        m = Matrix.Translation((x, y, z + h / 2))
        if matrix is not None:
            m = matrix @ Matrix.Translation((0, 0, h / 2))
        res = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=seg,
                                    radius1=r, radius2=r if r_top is None else r_top, depth=h, matrix=m)
        return self._na(res['verts'], mat, schaal)

    def bol(self, x, y, z, r, mat, schaal=(1, 1, 1), sub=1, rnd=None):
        m = Matrix.Translation((x, y, z)) @ Matrix.Diagonal((*schaal, 1))
        res = bmesh.ops.create_icosphere(self.bm, subdivisions=sub, radius=r, matrix=m)
        if rnd is not None:
            for v in res['verts']:
                v.co += Vector(((rnd.random() - 0.5) * r * 0.15, (rnd.random() - 0.5) * r * 0.15, 0))
        return self._na(res['verts'], mat)

    def staaf(self, p0, p1, dikte, mat, diepte=None):
        """Balk met vierkante doorsnede van p0 naar p1 (voor fietskaders, leuningen...)."""
        p0, p1 = Vector(p0), Vector(p1)
        as_ = p1 - p0
        lengte = as_.length
        rot = as_.to_track_quat('Z', 'Y').to_matrix().to_4x4()
        m = Matrix.Translation(p0) @ rot
        d = diepte or dikte
        res = bmesh.ops.create_cube(self.bm, size=1.0,
                                    matrix=m @ Matrix.Translation((0, 0, lengte / 2)) @ Matrix.Diagonal((dikte, d, lengte, 1)))
        return self._na(res['verts'], mat)

    def torus(self, midden, R, r, mat, as_='X', seg=18, seg_r=6):
        """Ring (wiel) rond de gegeven as."""
        verts = []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            rij = []
            for j in range(seg_r):
                b = 2 * math.pi * j / seg_r
                q = (R + r * math.cos(b))
                lok = Vector((q * math.cos(a), q * math.sin(a), r * math.sin(b)))
                rij.append(lok)
            verts.append(rij)
        rot = {'X': Matrix.Rotation(math.pi / 2, 4, 'Y'), 'Y': Matrix.Rotation(math.pi / 2, 4, 'X'),
               'Z': Matrix.Identity(4)}[as_]
        m = Matrix.Translation(midden) @ rot
        bv = [[self.bm.verts.new(m @ p) for p in rij] for rij in verts]
        nieuw = []
        for i in range(seg):
            for j in range(seg_r):
                a, b = bv[i][j], bv[(i + 1) % seg][j]
                c, d = bv[(i + 1) % seg][(j + 1) % seg_r], bv[i][(j + 1) % seg_r]
                nieuw += [a, b, c, d]
                self.bm.faces.new((a, b, c, d))
        return self._na(set(nieuw), mat)

    def tekst(self, txt, matrix, grootte, mat, uitlijn='CENTER', dik=0.0):
        """Tekst als echte geometrie. matrix plaatst het tekstvlak (x = leesrichting, y = omhoog,
        z = naar de lezer)."""
        cu = bpy.data.curves.new('tekst', 'FONT')
        cu.body = txt
        cu.size = grootte
        cu.align_x = uitlijn
        cu.align_y = 'CENTER'
        cu.extrude = dik
        cu.resolution_u = 2           # weinig punten per bocht: lichte letters
        ob = bpy.data.objects.new('tekst_tijdelijk', cu)
        bpy.context.scene.collection.objects.link(ob)
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        me.transform(matrix)
        n0 = len(self.bm.faces)
        self.bm.from_mesh(me)
        self.bm.faces.ensure_lookup_table()
        idx = self.mi(mat)
        for f in self.bm.faces[n0:]:
            f.material_index = idx
        bpy.data.objects.remove(ob)
        bpy.data.curves.remove(cu)
        bpy.data.meshes.remove(me)

    def klaar(self, oorsprong='midden', ouder=None, plaats=None):
        """oorsprong: 'midden' (onderaan in het midden), 'wereld' (0,0,0) of een punt."""
        bm = self.bm
        if not bm.verts:
            bm.free()
            return None
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
        bm.normal_update()
        me = bpy.data.meshes.new(self.naam)
        bm.to_mesh(me)
        bm.free()
        for m in self.mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(self.naam, me)
        self.col.objects.link(ob)
        if oorsprong == 'midden':
            pts = [v.co for v in me.vertices]
            mid = Vector(((min(p.x for p in pts) + max(p.x for p in pts)) / 2,
                          (min(p.y for p in pts) + max(p.y for p in pts)) / 2,
                          min(p.z for p in pts)))
            me.transform(Matrix.Translation(-mid))
            ob.location = mid
        elif oorsprong != 'wereld':
            o = Vector(oorsprong)
            me.transform(Matrix.Translation(-o))
            ob.location = o
        if ouder is not None:
            wereld = ob.location.copy()
            ob.parent = ouder
            ob.location = wereld - ouder.matrix_world.translation if plaats is None else Vector(plaats)
        return ob


class Gevel:
    """Lokaal assenstelsel voor een gevel: u loopt naar rechts zoals een voorbijganger
    de gevel ziet, v wijst naar buiten (de straat op), z omhoog."""

    def __init__(self, kant, x0, y0, x1, y1):
        self.kant = kant
        ox, oy = UIT[kant]
        self.out = Vector((ox, oy, 0))
        self.r = Vector((-oy, ox, 0))
        if kant == 'n':
            eind = [(x0, y1), (x1, y1)]
        elif kant == 'z':
            eind = [(x0, y0), (x1, y0)]
        elif kant == 'o':
            eind = [(x1, y0), (x1, y1)]
        else:
            eind = [(x0, y0), (x0, y1)]
        eind.sort(key=lambda p: p[0] * self.r.x + p[1] * self.r.y)
        self.f0 = Vector((*eind[0], 0))
        self.breedte = (Vector((*eind[1], 0)) - self.f0).length
        self.achter = {'n': 'z', 'z': 'n', 'o': 'w', 'w': 'o'}[kant]

    @staticmethod
    def kant_van(vec):
        """De zijde ('n','z','o','w') waar een horizontale richting naar wijst."""
        if abs(vec.x) > abs(vec.y):
            return 'o' if vec.x > 0 else 'w'
        return 'n' if vec.y > 0 else 'z'

    def p(self, u, v, z=0.0):
        q = self.f0 + self.r * u + self.out * v
        return (q.x, q.y, z)

    def doos(self, b, u0, v0, u1, v1, z0, z1, mat, voor=None, **kw):
        """Balk in gevelcoördinaten: u0..u1 langs de gevel, v0..v1 naar buiten, z0..z1 hoogte."""
        a = self.p(u0, v0)
        c = self.p(u1, v1)
        mats = dict(kw.pop('mats', {}) or {})
        if voor:
            mats[self.kant] = voor
        return b.doos(a[0], a[1], z0, c[0], c[1], z1, mat, mats=mats, **kw)

    def matrix(self, u, v, z):
        m = Matrix.Identity(4)
        m.col[0][:3] = self.r
        m.col[1][:3] = (0, 0, 1)
        m.col[2][:3] = self.out
        m.col[3][:3] = self.p(u, v, z)
        return m

    def richting(self, kijk_naar_gevel=True):
        """Kijkhoek (three.js) van iemand die naar de gevel kijkt, of er net van weg."""
        s = -1 if kijk_naar_gevel else 1
        return kop(self.out.x * s, self.out.y * s)


def tekst_matrix(x, y, z, nx, ny):
    """Plaatsing voor rechtopstaande tekst op (x, y, z) die naar (nx, ny) kijkt."""
    hoek = math.atan2(nx, -ny)
    return Matrix.Translation((x, y, z)) @ Matrix.Rotation(hoek, 4, 'Z') @ Matrix.Rotation(math.pi / 2, 4, 'X')
