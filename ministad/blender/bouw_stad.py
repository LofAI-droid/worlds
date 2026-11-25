"""Ministad — bouwt met Blender een kleine stad waarin je kan rondwandelen.

Gebruik (vanuit de map ministad/):

    blender --background --python blender/bouw_stad.py
    # of met de bpy-module:  python3.11 blender/bouw_stad.py

Optioneel: `-- --render` om ook voorbeeldbeelden te renderen (Cycles, CPU).

Het script maakt:
    blender/ministad.blend   het bewerkbare Blender-bestand
    ministad.glb             de stad voor de wandelpagina (index.html)
    botsing.json             muren en obstakels voor de wandelaar + startpunt
    blender/texturen/*.png   de zelfgemaakte texturen
    blender/voorbeeld-*.png  (met --render) gerenderde voorbeeldbeelden

Alles wordt procedureel opgebouwd met een vaste toevalszaad, dus elke run geeft
dezelfde stad. Verander ZAAD voor een andere stad.
"""
import json
import math
import os
import random
import sys

import bpy  # eerst bpy: dan worden ook bmesh en mathutils beschikbaar
import bmesh
import numpy as np
from mathutils import Matrix, Vector

ZAAD = 7
HIER = os.path.dirname(os.path.abspath(__file__))
UIT = os.path.dirname(HIER)                    # ministad/
TEX_MAP = os.path.join(HIER, 'texturen')

# ---------- stadsplan ----------
BLOKKEN = 5            # 5 x 5 bouwblokken
BLOK = 30.0            # breedte van een bouwblok (m)
WEG = 10.0             # breedte van een straat (m)
STEEK = BLOK + WEG     # afstand tussen straatassen
RAND = BLOKKEN * BLOK + (BLOKKEN + 1) * WEG     # 210 m: stad inclusief buitenste straten
HALF = RAND / 2
STOEP_H = 0.15         # hoogte van de stoeprand
STOEP_B = 3.0          # breedte van de stoep
DIEPTE = 8.0           # diepte van de huizenrijen
VERDIEP = 3.0          # hoogte van één verdieping

# Bijzondere blokken (kolom, rij)
PARK = (2, 2)
PLEIN = (1, 3)
ZAKEN = (3, 1)

rnd = random.Random(ZAAD)
botsers = []           # [x0, y0, x1, y1] in Blender-coördinaten


def weg_as(i):
    """x (of y) van straatas i, i = 0..BLOKKEN."""
    return -HALF + WEG / 2 + i * STEEK


def blok_bereik(j):
    a = -HALF + WEG + j * STEEK
    return a, a + BLOK


# =====================================================================
#  Texturen (numpy -> PNG)
# =====================================================================
def srgb(hexkleur):
    h = hexkleur.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)], dtype=np.float32)


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
    # baksteenvoegen, heel licht
    voeg = (np.arange(n) % 12 == 0)
    rgb[voeg, :, :] *= 0.94
    y, x = np.mgrid[0:n, 0:n] / n
    # kader en raam (rij 0 = boven)
    kx0, kx1, ky0, ky1 = 0.24, 0.76, 0.16, 0.78
    kader_m = (x > kx0) & (x < kx1) & (y > ky0) & (y < ky1)
    rgb[kader_m] = srgb(kader)
    b = 0.035
    glas = (x > kx0 + b) & (x < kx1 - b) & (y > ky0 + b) & (y < ky1 - b)
    glas_kleur = srgb(raam)
    weerkaats = (0.25 * (1 - (y - ky0) / (ky1 - ky0)))[..., None]
    rgb[glas] = (glas_kleur + weerkaats * np.array([0.7, 0.8, 0.9], dtype=np.float32))[glas]
    # middenstijl en dorpel
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
    lucht = np.stack([0.45 + 0.25 * (1 - y), 0.58 + 0.22 * (1 - y), 0.72 + 0.15 * (1 - y)], -1)
    rgb[:] = lucht
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
    rij = np.arange(n) // 16
    y = np.arange(n) % 16
    rgb[y < 2] *= 0.7                                       # schaduwlijn per rij
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
    """Natuursteen in blokken voor de kerk: tegel = 3 x 3 m."""
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


# =====================================================================
#  Materialen
# =====================================================================
MAT = {}


def materiaal(naam, kleur='#ffffff', ruwheid=0.85, beeld=None, emissie=None, metaal=0.0):
    m = bpy.data.materials.new(naam)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get('Principled BSDF')
    bsdf.inputs['Roughness'].default_value = ruwheid
    bsdf.inputs['Metallic'].default_value = metaal
    if beeld is not None:
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = beeld
        t.location = (-350, 250)
        nt.links.new(t.outputs['Color'], bsdf.inputs['Base Color'])
        m.diffuse_color = (*srgb(kleur) ** 2.2, 1)
    else:
        lin = srgb(kleur) ** 2.2
        bsdf.inputs['Base Color'].default_value = (*lin, 1)
        m.diffuse_color = (*lin, 1)
    if emissie:
        bsdf.inputs['Emission Color'].default_value = (*srgb(emissie) ** 2.2, 1)
        bsdf.inputs['Emission Strength'].default_value = 2.0
    MAT[naam] = m
    return m


GEVELKLEUREN = {
    'baksteen': '#9c4a36', 'rood': '#b5654a', 'oker': '#d1a25e', 'creme': '#e8dcc0',
    'wit': '#efece4', 'grijs': '#a3a19c', 'blauw': '#8aa3b5', 'groen': '#97a88a',
}


def maak_materialen():
    for i, (naam, kleur) in enumerate(GEVELKLEUREN.items()):
        raam = '#33424f' if naam not in ('baksteen', 'rood') else '#2e3a44'
        kader = '#f4f1ea' if naam != 'wit' else '#4a5560'
        materiaal('gevel_' + naam, kleur, 0.9, tex_gevel('gevel_' + naam, kleur, 10 + i, raam, kader))
    materiaal('kantoor', '#8fb0c8', 0.15, tex_kantoor('kantoor', 30), metaal=0.3)
    materiaal('dak_rood', '#8a3b2b', 0.8, tex_dak('dak_rood', '#8a3b2b', 40))
    materiaal('dak_grijs', '#4d5157', 0.8, tex_dak('dak_grijs', '#4d5157', 41))
    materiaal('plat_dak', '#8b8a86', 0.95, tex_vlak('grind', '#8b8a86', 0.18, 2, 42))
    materiaal('asfalt', '#4a4b4e', 0.95, tex_vlak('asfalt', '#4a4b4e', 0.12, 2, 43))
    materiaal('stoep', '#b9b4aa', 0.9, tex_vlak('stoep', '#b9b4aa', 0.06, 8, 44, tegels=4, voeg=0.8))
    materiaal('gras', '#5f8a3e', 1.0, tex_vlak('gras', '#5f8a3e', 0.22, 2, 45))
    materiaal('steen', '#cbbfa6', 0.9, tex_steen('steen', 46))
    materiaal('markering', '#f1f1ea', 0.7)
    materiaal('boomstam', '#5b4331', 0.9)
    materiaal('blad_1', '#4f7f35', 0.85)
    materiaal('blad_2', '#6b9440', 0.85)
    materiaal('blad_3', '#3f6b3a', 0.85)
    materiaal('metaal', '#3a3d42', 0.5, metaal=0.6)
    materiaal('lamp', '#fff3d0', 0.4, emissie='#ffe9b0')
    materiaal('water', '#4f8fb3', 0.05)
    materiaal('hout', '#8a6440', 0.8)
    materiaal('band', '#1d1e21', 0.8)
    materiaal('ruit', '#27323c', 0.1)
    materiaal('luifel_rood', '#b23b35', 0.8)
    materiaal('luifel_groen', '#2f6b4f', 0.8)
    materiaal('luifel_geel', '#d9a62e', 0.8)
    materiaal('deur', '#5a3b2a', 0.7)
    for naam, kleur in [('auto_rood', '#c0392b'), ('auto_blauw', '#2e5d9a'), ('auto_wit', '#e9e9e6'),
                        ('auto_zwart', '#26272b'), ('auto_geel', '#e5b62c'), ('auto_groen', '#3b7a57')]:
        materiaal(naam, kleur, 0.35, metaal=0.2)


# =====================================================================
#  Geometrie-hulpjes
# =====================================================================
class Bouwer:
    """Verzamelt geometrie (in wereldcoördinaten) voor één object."""

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

    def vlak(self, punten, mat, uvs):
        vs = [self.bm.verts.new(p) for p in punten]
        f = self.bm.faces.new(vs)
        f.material_index = self.mi(mat)
        for lus, uv in zip(f.loops, uvs):
            lus[self.uv].uv = uv
        return f

    def projecteer(self, faces, schaal=1.0, oorsprong=(0, 0, 0)):
        """Vlakke projectie per vlak, volgens de dominante normaal."""
        ox, oy, oz = oorsprong
        for f in faces:
            n = f.normal
            ax, ay, az = abs(n.x), abs(n.y), abs(n.z)
            for lus in f.loops:
                x, y, z = lus.vert.co.x - ox, lus.vert.co.y - oy, lus.vert.co.z - oz
                if az >= ax and az >= ay:
                    uv = (x, y)
                elif ax >= ay:
                    uv = (y if n.x > 0 else -y, z)
                else:
                    uv = (-x if n.y > 0 else x, z)
                lus[self.uv].uv = (uv[0] / schaal, uv[1] / schaal)

    def doos(self, x0, y0, z0, x1, y1, z1, zij, top=None, bodem=False, raster=None, schaal=1.0):
        """Balk. raster = tegelgrootte voor gevels: ramen passen dan precies op elke zijde."""
        top = top or zij
        P = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        vlakken = [((0, 1, 5, 4), 'z'), ((1, 2, 6, 5), 'o'), ((2, 3, 7, 6), 'n'),
                   ((3, 0, 4, 7), 'w'), ((4, 5, 6, 7), 't')]
        if bodem:
            vlakken.append(((3, 2, 1, 0), 'b'))
        uit = []
        for idx, kant in vlakken:
            pts = [P[i] for i in idx]
            mat = top if kant in 't' else zij
            if kant in 'zn':
                breedte = x1 - x0
            elif kant in 'ow':
                breedte = y1 - y0
            else:
                breedte = None
            if breedte is not None and raster:
                su = breedte / max(1, round(breedte / raster))
                sv = raster
                u = [0, breedte / su, breedte / su, 0]
                v = [0, 0, (z1 - z0) / sv, (z1 - z0) / sv]
                uvs = list(zip(u, v))
            elif breedte is not None:
                h = z1 - z0
                uvs = [(0, 0), (breedte / schaal, 0), (breedte / schaal, h / schaal), (0, h / schaal)]
            else:
                uvs = [(p[0] / schaal, p[1] / schaal) for p in pts]
            uit.append(self.vlak(pts, mat, uvs))
        return uit

    def zadeldak(self, x0, y0, x1, y1, h, nok, dak, muur, langs_x=True, raster=VERDIEP):
        """Zadeldak; de nok loopt evenwijdig aan x (langs_x) of aan y."""
        if langs_x:
            ym = (y0 + y1) / 2
            b = [(x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h)]
            r0, r1 = (x0, ym, h + nok), (x1, ym, h + nok)
            helling = math.hypot((y1 - y0) / 2, nok)
            L = x1 - x0
            self.vlak([b[0], b[1], r1, r0], dak, [(0, 0), (L / 2, 0), (L / 2, helling / 2), (0, helling / 2)])
            self.vlak([b[2], b[3], r0, r1], dak, [(0, 0), (L / 2, 0), (L / 2, helling / 2), (0, helling / 2)])
            d = y1 - y0
            su = d / max(1, round(d / raster))
            self.vlak([b[3], b[0], r0], muur, [(0, 0.0), (d / su, 0.0), (d / su / 2, nok / raster)])
            self.vlak([b[1], b[2], r1], muur, [(0, 0.0), (d / su, 0.0), (d / su / 2, nok / raster)])
        else:
            xm = (x0 + x1) / 2
            b = [(x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h)]
            r0, r1 = (xm, y0, h + nok), (xm, y1, h + nok)
            helling = math.hypot((x1 - x0) / 2, nok)
            L = y1 - y0
            self.vlak([b[1], b[2], r1, r0], dak, [(0, 0), (L / 2, 0), (L / 2, helling / 2), (0, helling / 2)])
            self.vlak([b[3], b[0], r0, r1], dak, [(0, 0), (L / 2, 0), (L / 2, helling / 2), (0, helling / 2)])
            d = x1 - x0
            su = d / max(1, round(d / raster))
            self.vlak([b[0], b[1], r0], muur, [(0, 0.0), (d / su, 0.0), (d / su / 2, nok / raster)])
            self.vlak([b[2], b[3], r1], muur, [(0, 0.0), (d / su, 0.0), (d / su / 2, nok / raster)])

    def piramide(self, x0, y0, x1, y1, h, top, mat):
        b = [(x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h)]
        t = ((x0 + x1) / 2, (y0 + y1) / 2, h + top)
        for i in range(4):
            self.vlak([b[i], b[(i + 1) % 4], t], mat, [(0, 0), (1.5, 0), (0.75, top / 2)])

    def cilinder(self, x, y, z, r, h, mat, seg=8, r_top=None, schaal=1.0):
        res = bmesh.ops.create_cone(self.bm, cap_ends=True, cap_tris=False, segments=seg,
                                    radius1=r, radius2=r if r_top is None else r_top, depth=h,
                                    matrix=Matrix.Translation((x, y, z + h / 2)))
        faces = {f for v in res['verts'] for f in v.link_faces}
        for f in faces:
            f.material_index = self.mi(mat)
        self.bm.normal_update()
        self.projecteer(faces, schaal)

    def bol(self, x, y, z, r, mat, schaal_z=1.0, sub=1):
        res = bmesh.ops.create_icosphere(self.bm, subdivisions=sub, radius=r,
                                         matrix=Matrix.Translation((x, y, z)) @ Matrix.Diagonal((1, 1, schaal_z, 1)))
        faces = {f for v in res['verts'] for f in v.link_faces}
        for v in res['verts']:
            v.co += Vector(((rnd.random() - 0.5) * r * 0.15, (rnd.random() - 0.5) * r * 0.15, 0))
        for f in faces:
            f.material_index = self.mi(mat)
        self.bm.normal_update()
        self.projecteer(faces, 1.0)

    def klaar(self, oorsprong_midden=True):
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
        if oorsprong_midden:
            pts = [v.co for v in me.vertices]
            mid = Vector(((min(p.x for p in pts) + max(p.x for p in pts)) / 2,
                          (min(p.y for p in pts) + max(p.y for p in pts)) / 2,
                          min(p.z for p in pts)))
            me.transform(Matrix.Translation(-mid))
            ob.location = mid
        return ob


def botser(x0, y0, x1, y1):
    botsers.append([round(min(x0, x1), 3), round(min(y0, y1), 3), round(max(x0, x1), 3), round(max(y0, y1), 3)])


def collectie(naam, ouder=None):
    c = bpy.data.collections.new(naam)
    (ouder or bpy.context.scene.collection).children.link(c)
    return c


# =====================================================================
#  Stadsonderdelen
# =====================================================================
def bouw_grond(col):
    b = Bouwer('Weiland', col)
    G = 320
    b.vlak([(-G, -G, -0.02), (G, -G, -0.02), (G, G, -0.02), (-G, G, -0.02)], 'gras',
           [(-G / 4, -G / 4), (G / 4, -G / 4), (G / 4, G / 4), (-G / 4, G / 4)])
    b.klaar(False)

    b = Bouwer('Straten', col)
    H = HALF
    b.vlak([(-H, -H, 0), (H, -H, 0), (H, H, 0), (-H, H, 0)], 'asfalt',
           [(-H / 6, -H / 6), (H / 6, -H / 6), (H / 6, H / 6), (-H / 6, H / 6)])
    b.klaar(False)

    # wegmarkeringen: onderbroken middenlijn + zebrapaden
    b = Bouwer('Wegmarkering', col)
    z = 0.012
    for i in range(BLOKKEN + 1):
        as_ = weg_as(i)
        for j in range(BLOKKEN):
            a, e = blok_bereik(j)
            s = a + 4.5
            while s + 2.5 < e - 4.5:
                b.doos(as_ - 0.08, s, 0, as_ + 0.08, s + 2.5, z, 'markering')
                b.doos(s, as_ - 0.08, 0, s + 2.5, as_ + 0.08, z, 'markering')
                s += 5.0
            # zebrapaden aan beide uiteinden van elk wegvak
            for y0 in (a + 0.6, e - 3.6):
                for k in range(6):
                    xs = as_ - WEG / 2 + 0.9 + k * 1.5
                    b.doos(xs, y0, 0, xs + 0.8, y0 + 3.0, z, 'markering')
                    b.doos(y0, xs, 0, y0 + 3.0, xs + 0.8, z, 'markering')
    b.klaar(False)


def bouw_huizenrij(col, naam, x0, y0, x1, y1, straatkant, hoogtes, langs_x):
    """Een rij aaneengesloten huizen. straatkant: 'n','z','o','w'."""
    lengte = (x1 - x0) if langs_x else (y1 - y0)
    breedtes = []
    rest = lengte
    while rest > 0.01:
        if rest <= 10.5:
            w = rest
        else:
            w = rnd.choice([4.5, 5.5, 6.0, 7.5, 9.0])
            if rest - w < 4.5:
                w = rest
        breedtes.append(w)
        rest -= w
    pos = x0 if langs_x else y0
    for k, w in enumerate(breedtes):
        verd = rnd.randint(*hoogtes)
        h = verd * VERDIEP
        gevel = 'gevel_' + rnd.choice(list(GEVELKLEUREN))
        b = Bouwer(f'{naam}_{k + 1}', col)
        if langs_x:
            bx0, by0, bx1, by1 = pos, y0, pos + w, y1
        else:
            bx0, by0, bx1, by1 = x0, pos, x1, pos + w
        hellend = verd <= 3 and rnd.random() < 0.7
        b.doos(bx0, by0, STOEP_H, bx1, by1, STOEP_H + h, gevel, 'plat_dak', raster=VERDIEP, schaal=3)
        if hellend:
            dak = rnd.choice(['dak_rood', 'dak_rood', 'dak_grijs'])
            b.zadeldak(bx0, by0, bx1, by1, STOEP_H + h, rnd.uniform(2.6, 3.6), dak, gevel, langs_x=langs_x)
        else:
            # dakrand en soms een technische kast
            r = 0.25
            hz = STOEP_H + h
            b.doos(bx0, by0, hz, bx1, by0 + r, hz + 0.5, 'plat_dak', schaal=2)
            b.doos(bx0, by1 - r, hz, bx1, by1, hz + 0.5, 'plat_dak', schaal=2)
            if rnd.random() < 0.4:
                cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
                b.doos(cx - 1, cy - 1, hz, cx + 1, cy + 1, hz + 1.6, 'metaal', schaal=2)
        # voordeur en luifel aan de straatkant
        mid = pos + w / 2
        if straatkant in 'nz':
            yv = by1 if straatkant == 'n' else by0
            s = 1 if straatkant == 'n' else -1
            b.doos(mid - 0.55, min(yv, yv + s * 0.06), STOEP_H, mid + 0.55, max(yv, yv + s * 0.06), STOEP_H + 2.2, 'deur')
            if rnd.random() < 0.3:
                b.doos(bx0 + 0.3, min(yv, yv + s * 1.4), STOEP_H + 2.6, bx1 - 0.3, max(yv, yv + s * 1.4), STOEP_H + 2.8,
                       rnd.choice(['luifel_rood', 'luifel_groen', 'luifel_geel']))
        else:
            xv = bx1 if straatkant == 'o' else bx0
            s = 1 if straatkant == 'o' else -1
            b.doos(min(xv, xv + s * 0.06), mid - 0.55, STOEP_H, max(xv, xv + s * 0.06), mid + 0.55, STOEP_H + 2.2, 'deur')
            if rnd.random() < 0.3:
                b.doos(min(xv, xv + s * 1.4), by0 + 0.3, STOEP_H + 2.6, max(xv, xv + s * 1.4), by1 - 0.3, STOEP_H + 2.8,
                       rnd.choice(['luifel_rood', 'luifel_groen', 'luifel_geel']))
        b.klaar()
        pos += w
    botser(x0, y0, x1, y1)


def stoepblok(col, naam, a0, b0, a1, b1, binnen='gras'):
    b = Bouwer(naam, col)
    b.doos(a0, b0, 0, a1, b1, STOEP_H, 'stoep', schaal=2)
    if binnen:
        i = STOEP_B + DIEPTE
        b.doos(a0 + i, b0 + i, STOEP_H, a1 - i, b1 - i, STOEP_H + 0.02, binnen, schaal=4)
    b.klaar()


def gewoon_blok(col, j, i, hoogtes):
    x0, x1 = blok_bereik(j)
    y0, y1 = blok_bereik(i)
    c = collectie(f'Blok {j + 1}-{i + 1}', col)
    stoepblok(c, f'Stoep {j + 1}-{i + 1}', x0, y0, x1, y1)
    s, d = STOEP_B, DIEPTE
    n = f'Huis {j + 1}-{i + 1}'
    bouw_huizenrij(c, n + 'n', x0 + s, y1 - s - d, x1 - s, y1 - s, 'n', hoogtes, True)
    bouw_huizenrij(c, n + 'z', x0 + s, y0 + s, x1 - s, y0 + s + d, 'z', hoogtes, True)
    bouw_huizenrij(c, n + 'o', x1 - s - d, y0 + s + d, x1 - s, y1 - s - d, 'o', hoogtes, False)
    bouw_huizenrij(c, n + 'w', x0 + s, y0 + s + d, x0 + s + d, y1 - s - d, 'w', hoogtes, False)
    # boom op de binnenkoer
    boom(c, (x0 + x1) / 2, (y0 + y1) / 2, STOEP_H, rnd.uniform(0.9, 1.2), botsing=False)


def boom(col, x, y, z, grootte=1.0, botsing=True, naam='Boom'):
    b = Bouwer(naam, col)
    h = 2.4 * grootte
    b.cilinder(x, y, z, 0.18 * grootte, h, 'boomstam', seg=7)
    blad = rnd.choice(['blad_1', 'blad_2', 'blad_3'])
    r = 1.7 * grootte
    b.bol(x, y, z + h + r * 0.55, r, blad, schaal_z=1.1)
    if rnd.random() < 0.6:
        b.bol(x + rnd.uniform(-0.7, 0.7) * grootte, y + rnd.uniform(-0.7, 0.7) * grootte,
              z + h + r * 1.25, r * 0.7, blad)
    b.klaar()
    if botsing:
        botser(x - 0.3, y - 0.3, x + 0.3, y + 0.3)


def lantaarn(col, x, y, richting):
    b = Bouwer('Lantaarn', col)
    z = STOEP_H
    b.cilinder(x, y, z, 0.12, 0.5, 'metaal', seg=8)
    b.cilinder(x, y, z, 0.07, 5.2, 'metaal', seg=8)
    dx, dy = richting
    hx, hy = x + dx * 0.9, y + dy * 0.9
    b.doos(min(x, hx) - 0.05, min(y, hy) - 0.05, z + 5.0, max(x, hx) + 0.05, max(y, hy) + 0.05, z + 5.12, 'metaal')
    b.doos(hx - 0.25, hy - 0.25, z + 4.75, hx + 0.25, hy + 0.25, z + 5.0, 'lamp')
    b.doos(hx - 0.3, hy - 0.3, z + 5.0, hx + 0.3, hy + 0.3, z + 5.1, 'metaal')
    b.klaar()
    botser(x - 0.15, y - 0.15, x + 0.15, y + 0.15)


def bank(col, x, y, langs_x=True):
    b = Bouwer('Bank', col)
    z = STOEP_H
    L, D = 1.8, 0.5
    if langs_x:
        b.doos(x - L / 2, y - D / 2, z + 0.42, x + L / 2, y + D / 2, z + 0.5, 'hout')
        b.doos(x - L / 2, y + D / 2 - 0.06, z + 0.5, x + L / 2, y + D / 2, z + 0.95, 'hout')
        for px in (x - L / 2 + 0.1, x + L / 2 - 0.15):
            b.doos(px, y - D / 2, z, px + 0.05, y + D / 2, z + 0.42, 'metaal')
        botser(x - L / 2, y - D / 2, x + L / 2, y + D / 2)
    else:
        b.doos(x - D / 2, y - L / 2, z + 0.42, x + D / 2, y + L / 2, z + 0.5, 'hout')
        b.doos(x + D / 2 - 0.06, y - L / 2, z + 0.5, x + D / 2, y + L / 2, z + 0.95, 'hout')
        for py in (y - L / 2 + 0.1, y + L / 2 - 0.15):
            b.doos(x - D / 2, py, z, x + D / 2, py + 0.05, z + 0.42, 'metaal')
        botser(x - D / 2, y - L / 2, x + D / 2, y + L / 2)
    b.klaar()


def auto(col, x, y, langs_x):
    b = Bouwer('Auto', col)
    kleur = rnd.choice(['auto_rood', 'auto_blauw', 'auto_wit', 'auto_zwart', 'auto_geel', 'auto_groen'])
    L, B = 4.2, 1.8
    if langs_x:
        hx, hy = L / 2, B / 2
    else:
        hx, hy = B / 2, L / 2
    b.doos(x - hx, y - hy, 0.35, x + hx, y + hy, 1.0, kleur)
    # cabine iets naar achter, met ramen in de zijvlakken
    if langs_x:
        b.doos(x - hx * 0.55, y - hy * 0.9, 1.0, x + hx * 0.35, y + hy * 0.9, 1.5, 'ruit', kleur)
        wielen = [(x + sx * hx * 0.62, y + sy * (hy - 0.1)) for sx in (-1, 1) for sy in (-1, 1)]
        for wx, wy in wielen:
            res = bmesh.ops.create_cone(b.bm, cap_ends=True, segments=10, radius1=0.34, radius2=0.34, depth=0.24,
                                        matrix=Matrix.Translation((wx, wy, 0.34)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
            for f in {f for v in res['verts'] for f in v.link_faces}:
                f.material_index = b.mi('band')
    else:
        b.doos(x - hx * 0.9, y - hy * 0.55, 1.0, x + hx * 0.9, y + hy * 0.35, 1.5, 'ruit', kleur)
        wielen = [(x + sx * (hx - 0.1), y + sy * hy * 0.62) for sx in (-1, 1) for sy in (-1, 1)]
        for wx, wy in wielen:
            res = bmesh.ops.create_cone(b.bm, cap_ends=True, segments=10, radius1=0.34, radius2=0.34, depth=0.24,
                                        matrix=Matrix.Translation((wx, wy, 0.34)) @ Matrix.Rotation(math.pi / 2, 4, 'Y'))
            for f in {f for v in res['verts'] for f in v.link_faces}:
                f.material_index = b.mi('band')
    b.bm.normal_update()
    b.klaar()
    botser(x - hx, y - hy, x + hx, y + hy)


def bouw_park(col):
    j, i = PARK
    x0, x1 = blok_bereik(j)
    y0, y1 = blok_bereik(i)
    c = collectie('Park', col)
    stoepblok(c, 'Parkrand', x0, y0, x1, y1, binnen=None)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    b = Bouwer('Parkgazon', c)
    r = BLOK / 2 - 1.5
    b.doos(cx - r, cy - r, STOEP_H, cx + r, cy + r, STOEP_H + 0.04, 'gras', schaal=4)
    # paden in een kruis + rond de fontein
    p = 1.6
    b.doos(cx - r, cy - p, STOEP_H, cx + r, cy + p, STOEP_H + 0.06, 'stoep', schaal=2)
    b.doos(cx - p, cy - r, STOEP_H, cx + p, cy + r, STOEP_H + 0.06, 'stoep', schaal=2)
    b.cilinder(cx, cy, STOEP_H, 6.5, 0.06, 'stoep', seg=32, schaal=2)
    b.klaar()

    f = Bouwer('Fontein', c)
    z = STOEP_H + 0.06
    f.cilinder(cx, cy, z, 3.6, 0.55, 'steen', seg=24, schaal=3)
    f.cilinder(cx, cy, z, 3.25, 0.5, 'water', seg=24)
    f.cilinder(cx, cy, z, 0.45, 1.8, 'steen', seg=12, schaal=3)
    f.cilinder(cx, cy, z + 1.8, 1.3, 0.25, 'steen', seg=16, r_top=0.9, schaal=3)
    f.cilinder(cx, cy, z + 2.05, 0.85, 0.15, 'water', seg=16)
    f.cilinder(cx, cy, z + 2.05, 0.15, 0.9, 'steen', seg=8, schaal=3)
    f.bol(cx, cy, z + 3.0, 0.22, 'water', sub=2)
    f.klaar()
    botser(cx - 3.5, cy - 3.5, cx + 3.5, cy + 3.5)

    for dx, dy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
        for k in range(2):
            boom(c, cx + dx * rnd.uniform(6.5, 11.5), cy + dy * rnd.uniform(6.5, 11.5), STOEP_H, rnd.uniform(0.9, 1.3))
    for sx in (-1, 1):
        for sy in (-1, 1):
            bank(c, cx + sx * 9.5, cy + sy * 2.4, True)
            bank(c, cx + sx * 2.4, cy + sy * 9.5, False)


def bouw_plein(col):
    """Marktplein met een kerk aan de noordkant."""
    j, i = PLEIN
    x0, x1 = blok_bereik(j)
    y0, y1 = blok_bereik(i)
    c = collectie('Kerkplein', col)
    stoepblok(c, 'Plein', x0, y0, x1, y1, binnen=None)
    cx = (x0 + x1) / 2

    k = Bouwer('Kerk', c)
    z = STOEP_H
    # schip
    sx0, sx1, sy0, sy1 = cx - 5, cx + 5, y1 - 22, y1 - 3
    k.doos(sx0, sy0, z, sx1, sy1, z + 11, 'steen', 'steen', schaal=3)
    k.zadeldak(sx0 - 0.3, sy0, sx1 + 0.3, sy1, z + 11, 6.5, 'dak_grijs', 'steen', langs_x=False, raster=3)
    # toren aan de pleinkant
    tx0, tx1, ty0, ty1 = cx - 2.8, cx + 2.8, sy0 - 4.5, sy0 + 1.0
    k.doos(tx0, ty0, z, tx1, ty1, z + 26, 'steen', 'steen', schaal=3)
    k.doos(tx0 - 0.3, ty0 - 0.3, z + 26, tx1 + 0.3, ty1 + 0.3, z + 27, 'steen', schaal=3)
    k.piramide(tx0 - 0.3, ty0 - 0.3, tx1 + 0.3, ty1 + 0.3, z + 27, 13, 'dak_grijs')
    # galmgaten, wijzerplaat en portaal
    for zz in (z + 21.5,):
        k.doos(cx - 0.7, ty0 - 0.05, zz, cx + 0.7, ty0, zz + 2.6, 'ruit')
        k.doos(tx0 - 0.05, (ty0 + ty1) / 2 - 0.7, zz, tx0, (ty0 + ty1) / 2 + 0.7, zz + 2.6, 'ruit')
        k.doos(tx1, (ty0 + ty1) / 2 - 0.7, zz, tx1 + 0.05, (ty0 + ty1) / 2 + 0.7, zz + 2.6, 'ruit')
    # wijzerplaat met twee wijzers
    k.doos(cx - 1.1, ty0 - 0.06, z + 16.4, cx + 1.1, ty0, z + 18.6, 'markering')
    k.doos(cx - 0.06, ty0 - 0.1, z + 17.5, cx + 0.06, ty0 - 0.06, z + 18.35, 'metaal')
    k.doos(cx, ty0 - 0.1, z + 17.44, cx + 0.65, ty0 - 0.06, z + 17.56, 'metaal')
    k.doos(cx - 1.2, ty0 - 0.08, z, cx + 1.2, ty0, z + 3.6, 'deur')
    for yy in range(4):
        wy = sy0 + 3 + yy * 4
        for wx, s in ((sx0, -1), (sx1, 1)):
            k.doos(min(wx, wx + s * 0.05), wy, z + 3.5, max(wx, wx + s * 0.05), wy + 1.4, z + 8.5, 'ruit')
    k.klaar()
    botser(sx0, sy0, sx1, sy1)
    botser(tx0, ty0, tx1, ty1)

    # pleinbomen en banken
    for bx in (x0 + 4, x1 - 4):
        for by in (y0 + 4, y0 + 11, y1 - 6):
            boom(c, bx, by, STOEP_H, 0.85)
    for bx in (x0 + 8, x1 - 8):
        bank(c, bx, y0 + 7.5, True)
    # standbeeld
    s = Bouwer('Standbeeld', c)
    s.doos(cx - 0.9, y0 + 4.1, z, cx + 0.9, y0 + 5.9, z + 1.6, 'steen', schaal=3)
    s.cilinder(cx, y0 + 5, z + 1.6, 0.35, 1.3, 'metaal', seg=10, r_top=0.25)
    s.bol(cx, y0 + 5, z + 3.15, 0.3, 'metaal', sub=2)
    s.klaar()
    botser(cx - 0.9, y0 + 4.1, cx + 0.9, y0 + 5.9)


def bouw_zakenwijk(col):
    j, i = ZAKEN
    x0, x1 = blok_bereik(j)
    y0, y1 = blok_bereik(i)
    c = collectie('Zakenwijk', col)
    stoepblok(c, 'Zakenplein', x0, y0, x1, y1, binnen=None)
    for naam, (a0, b0, a1, b1, h) in {'Toren Noord': (x0 + 3, y1 - 15, x1 - 13, y1 - 3, 57),
                                      'Toren Zuid': (x1 - 11, y0 + 3, x1 - 3, y0 + 14, 39)}.items():
        t = Bouwer(naam, c)
        t.doos(a0, b0, STOEP_H, a1, b1, STOEP_H + 4.5, 'steen', schaal=3)            # sokkel
        t.doos(a0 + 0.3, b0 + 0.3, STOEP_H + 4.5, a1 - 0.3, b1 - 0.3, STOEP_H + h, 'kantoor', 'plat_dak', raster=3)
        t.doos(a0 + 0.1, b0 + 0.1, STOEP_H + h, a1 - 0.1, b1 - 0.1, STOEP_H + h + 0.6, 'steen', schaal=3)
        t.doos((a0 + a1) / 2 - 1.5, (b0 + b1) / 2 - 1.5, STOEP_H + h + 0.6, (a0 + a1) / 2 + 1.5, (b0 + b1) / 2 + 1.5,
               STOEP_H + h + 3.5, 'metaal', schaal=2)
        t.cilinder((a0 + a1) / 2, (b0 + b1) / 2, STOEP_H + h + 3.5, 0.08, 6, 'metaal')
        t.klaar()
        botser(a0, b0, a1, b1)
    for bx, by in [(x0 + 5, y0 + 5), (x0 + 11, y0 + 5), (x0 + 5, y0 + 11)]:
        boom(c, bx, by, STOEP_H, 0.8)
    bank(c, x0 + 8, y0 + 8.5, True)


def bouw_straatmeubilair(col):
    c_l = collectie('Lantaarns', col)
    c_b = collectie('Straatbomen', col)
    c_a = collectie('Autos', col)
    # lantaarns op de blokhoeken, lamp naar de straat gericht
    for j in range(BLOKKEN):
        for i in range(BLOKKEN):
            x0, x1 = blok_bereik(j)
            y0, y1 = blok_bereik(i)
            for (x, y, d) in [(x0 + 0.6, y0 + 0.6, (-0.7, -0.7)), (x1 - 0.6, y1 - 0.6, (0.7, 0.7)),
                              (x1 - 0.6, y0 + 0.6, (0.7, -0.7)), (x0 + 0.6, y1 - 0.6, (-0.7, 0.7))]:
                lantaarn(c_l, x, y, d)
    # bomen langs de twee middelste lanen
    for k in (2, 3):
        as_ = weg_as(k)
        for j in range(BLOKKEN):
            a, e = blok_bereik(j)
            for t in (a + 8, a + 15, a + 22):
                for zij in (-1, 1):
                    boom(c_b, as_ + zij * (WEG / 2 + 1.1), t, STOEP_H, rnd.uniform(0.75, 0.95), naam='Laanboom')
    # geparkeerde auto's
    for i in range(BLOKKEN + 1):
        as_ = weg_as(i)
        for j in range(BLOKKEN):
            a, e = blok_bereik(j)
            for zij in (-1, 1):
                for t in (a + 7.5, a + 13, a + 18.5):
                    if rnd.random() < 0.28:
                        auto(c_a, as_ + zij * 3.7, t + rnd.uniform(-0.6, 0.6), False)
                    if rnd.random() < 0.28:
                        auto(c_a, t + rnd.uniform(-0.6, 0.6), as_ + zij * 3.7, True)


def bouw_bos(col):
    """Een gordel bomen rondom de stad."""
    c = collectie('Bosrand', col)
    n = 0
    while n < 170:
        x, y = rnd.uniform(-175, 175), rnd.uniform(-175, 175)
        m = max(abs(x), abs(y))
        if m < HALF + 8 or m > 175:
            continue
        boom(c, x, y, 0, rnd.uniform(1.0, 1.8), botsing=True, naam='Bosboom')
        n += 1


# =====================================================================
#  Licht, camera, render
# =====================================================================
def zet_licht_en_camera():
    sc = bpy.context.scene
    zon = bpy.data.lights.new('Zon', 'SUN')
    zon.energy = 4.0
    zon.angle = math.radians(1.5)
    zon.color = (1.0, 0.95, 0.88)
    o = bpy.data.objects.new('Zon', zon)
    o.rotation_euler = (math.radians(50), math.radians(10), math.radians(35))
    sc.collection.objects.link(o)

    w = bpy.data.worlds.new('Lucht')
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes['Background']
    try:
        sky = nt.nodes.new('ShaderNodeTexSky')
        for t in ('MULTIPLE_SCATTERING', 'SINGLE_SCATTERING', 'NISHITA'):
            try:
                sky.sky_type = t
                break
            except TypeError:
                continue
        try:
            sky.sun_elevation = math.radians(40)
            sky.sun_rotation = math.radians(215)
        except AttributeError:
            pass
        nt.links.new(sky.outputs['Color'], bg.inputs['Color'])
        bg.inputs['Strength'].default_value = 0.35
    except Exception:
        bg.inputs['Color'].default_value = (0.55, 0.7, 0.9, 1)

    cam = bpy.data.cameras.new('Camera')
    cam.lens = 30
    co = bpy.data.objects.new('Camera', cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return co


def richt(obj, positie, doel):
    obj.location = positie
    d = Vector(doel) - Vector(positie)
    obj.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()


def render(cam):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.samples = 48
    try:
        sc.cycles.use_denoising = True
    except AttributeError:
        pass
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    sc.render.image_settings.file_format = 'PNG'
    for naam, pos, doel in [('lucht', (150, -170, 110), (0, 0, 0)),
                            ('straat', (weg_as(2) + 1.5, blok_bereik(2)[0] - 22, 1.7),
                             (weg_as(2) - 2, blok_bereik(2)[1] + 10, 6))]:
        richt(cam, pos, doel)
        sc.render.filepath = os.path.join(HIER, f'voorbeeld-{naam}.png')
        bpy.ops.render.render(write_still=True)
        print('Gerenderd:', sc.render.filepath)


# =====================================================================
def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    doe_render = '--render' in argv

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0      # geen .blend1-reservekopie
    sc = bpy.context.scene
    sc.unit_settings.system = 'METRIC'
    maak_materialen()

    stad = collectie('Ministad')
    bouw_grond(collectie('Grond', stad))
    gebouwen = collectie('Bouwblokken', stad)
    for j in range(BLOKKEN):
        for i in range(BLOKKEN):
            if (j, i) in (PARK, PLEIN, ZAKEN):
                continue
            afstand = max(abs(j - 2), abs(i - 2))
            hoogtes = (3, 6) if afstand == 1 else (2, 4)
            gewoon_blok(gebouwen, j, i, hoogtes)
    bouw_park(stad)
    bouw_plein(stad)
    bouw_zakenwijk(stad)
    bouw_straatmeubilair(collectie('Straatmeubilair', stad))
    bouw_bos(stad)

    cam = zet_licht_en_camera()
    richt(cam, (150, -170, 110), (0, 0, 0))

    # ---- bewaren ----
    os.makedirs(UIT, exist_ok=True)
    blend = os.path.join(HIER, 'ministad.blend')
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)

    # ---- glTF-export: alleen de stad (geen licht of camera) ----
    for o in bpy.context.view_layer.objects:
        o.select_set(o.type == 'MESH')
    bpy.ops.export_scene.gltf(filepath=os.path.join(UIT, 'ministad.glb'), export_format='GLB',
                              use_selection=True, export_yup=True, export_apply=True,
                              export_lights=False, export_cameras=False, export_extras=False)

    # ---- botsvakken en startpunt (glTF-assen: x = x, z = -y) ----
    vakken = [[b[0], -b[3], b[2], -b[1]] for b in botsers]
    start_x, start_y = weg_as(2) + 1.5, blok_bereik(2)[0] - 18
    data = {
        'versie': 1,
        'grens': HALF + 40,
        'ooghoogte': 1.65,
        'start': {'x': start_x, 'z': -start_y, 'richting': 0},
        'vakken': vakken,
        'straten': [weg_as(i) for i in range(BLOKKEN + 1)],
        'blokken': [list(blok_bereik(j)) for j in range(BLOKKEN)],
    }
    with open(os.path.join(UIT, 'botsing.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'))

    n_obj = sum(1 for o in bpy.data.objects if o.type == 'MESH')
    n_drie = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == 'MESH')
    print(f'Ministad klaar: {n_obj} objecten, {n_drie} vlakken, {len(vakken)} botsvakken')

    if doe_render:
        render(cam)
        bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)


if __name__ == '__main__':
    main()
