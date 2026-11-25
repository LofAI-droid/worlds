"""Ministad — bouwt met Blender een kleine stad waarin je kan rondwandelen.

Gebruik (vanuit de map ministad/):

    blender --background --python blender/bouw_stad.py
    # of met de bpy-module:  python3.11 blender/bouw_stad.py

Optioneel: `-- --render` om ook voorbeeldbeelden te renderen (Cycles, CPU).

Het script maakt:
    blender/ministad.blend   het bewerkbare Blender-bestand
    ministad.glb             de stad voor de wandelpagina (index.html)
    botsing.json             obstakels, zitplaatsen, busroute ... voor het leven in de stad
    blender/texturen/*.png   de zelfgemaakte texturen
    blender/voorbeeld-*.png  (met --render) gerenderde voorbeeldbeelden

De mensen, dieren en voertuigen komen uit bouw_figuren.py.
Alles wordt procedureel opgebouwd met een vaste toevalszaad: elke run geeft dezelfde stad.
"""
import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from gereedschap import (MAT, Bouwer, Gevel, kop, materiaal, tekst_matrix, tex_dak, tex_gevel,  # noqa: E402
                         tex_interieur, tex_kantoor, tex_steen, tex_streep, tex_vlak)

ZAAD = 7
HIER = os.path.dirname(os.path.abspath(__file__))
UIT = os.path.dirname(HIER)                    # ministad/

# ---------- stadsplan ----------
BLOKKEN = 5            # 5 x 5 bouwblokken
BLOK = 30.0            # breedte van een bouwblok (m)
WEG = 10.0             # breedte van een straat (m)
STEEK = BLOK + WEG     # afstand tussen straatassen
RAND = BLOKKEN * BLOK + (BLOKKEN + 1) * WEG     # 210 m: stad inclusief buitenste straten
HALF = RAND / 2
STOEP_H = 0.15         # hoogte van de stoeprand
STOEP_B = 4.0          # breedte van de stoep
DIEPTE = 8.0           # diepte van de huizenrijen
VERDIEP = 3.0          # hoogte van één verdieping
LOOPLIJN = 1.95        # voetgangers lopen zo ver van de stoeprand

# Bijzondere blokken (kolom, rij) in Blender-coördinaten
PARK = (2, 2)
PLEIN = (1, 3)
ZAKEN = (3, 1)

# Busroute in three.js-coördinaten: knooppunten (index x, index z) en haltes (segment, afstand)
BUSROUTE = [(1, 1), (1, 4), (4, 4), (4, 1)]
BUSHALTES = [(0, 20.0), (2, 20.0)]
RIJSTROOK = {'auto': 1.3, 'bus': 1.4, 'fiets': 2.55}

STRAATNAMEN_X = ['Westlaan', 'Bakkerstraat', 'Parklaan', 'Lindelaan', 'Molenstraat', 'Oostlaan']
STRAATNAMEN_Y = ['Zuidlaan', 'Schoolstraat', 'Marktstraat', 'Kerkstraat', 'Stationsstraat', 'Noordlaan']

# naam op het bord, soort, bordkleur, letterkleur, zonnescherm, terras
WINKELS = [
    ('Bakkerij', 'bakker', '#7a4a2a', '#f6e7c8', 'rood', False),
    ('Café De Hoek', 'cafe', '#1f3b2c', '#f1d08a', 'groen', True),
    ('Pizzeria Luna', 'resto', '#8c1c1c', '#ffffff', 'rood', True),
    ('Boekhandel', 'boeken', '#24344d', '#f4efe3', None, False),
    ('Bloemen', 'bloemen', '#f6f1e7', '#2f6b4f', 'groen', False),
    ('Apotheek', 'apotheek', '#ffffff', '#1d8a4a', None, False),
    ('Groenten & Fruit', 'groenten', '#2f6b4f', '#ffffff', 'groen', False),
    ('IJssalon', 'ijs', '#f7c6d9', '#7a2e4d', 'roze', True),
    ('Koffiebar', 'cafe', '#3b2a20', '#f1c27d', None, True),
    ('Frituur', 'frituur', '#f2c230', '#8c1c1c', 'geel', False),
    ('Kapper', 'kapper', '#1d1d1d', '#ffffff', None, False),
    ('Fietsen', 'fietsen', '#1f5f8b', '#ffffff', None, False),
    ('Speelgoed', 'speelgoed', '#f4d03f', '#1f3b8c', 'blauw', False),
    ('Mode', 'kledij', '#efe7dc', '#222222', None, False),
    ('Brasserie', 'resto', '#2b2b2b', '#e8d3a2', 'zwart', True),
    ('Chocolatier', 'choco', '#4a2c1d', '#f0d9b5', None, False),
    ('Wijnbar', 'cafe', '#5a1a2a', '#f0e0c0', 'rood', True),
    ('Krantenwinkel', 'kranten', '#c0392b', '#ffffff', None, False),
    ('Slagerij', 'slager', '#9b1c1c', '#ffffff', 'rood', False),
    ('Tearoom', 'cafe', '#a8c3b1', '#2f3b33', 'groen', True),
    ('Sushi', 'resto', '#111111', '#e74c3c', None, True),
    ('Optiek', 'optiek', '#ffffff', '#2c3e50', None, False),
    ('Bar Noord', 'cafe', '#14213d', '#fca311', 'blauw', True),
    ('Bloemenhoek', 'bloemen', '#d8e2dc', '#7a2e4d', 'roze', False),
]

rnd = random.Random(ZAAD)
botsers = []           # [x0, y0, x1, y1, hoogte] in Blender-coördinaten
zitplaatsen = []       # {x, z, y, h} in three.js-coördinaten
katplekken = []
bezet = []             # stukken stoeprand die al gebruikt zijn: (x0, y0, x1, y1)
winkel_rij = []
gebouwde_winkels = []  # (naam, soort, punt midden op de gevel, richting naar buiten, langs de gevel)


def weg_as(i):
    """x (of y) van straatas i, i = 0..BLOKKEN."""
    return -HALF + WEG / 2 + i * STEEK


def blok_bereik(j):
    a = -HALF + WEG + j * STEEK
    return a, a + BLOK


def botser(x0, y0, x1, y1, h=1.0):
    botsers.append([round(min(x0, x1), 3), round(min(y0, y1), 3), round(max(x0, x1), 3),
                    round(max(y0, y1), 3), round(h, 2)])


def zit(x, y, z, fx, fy):
    """Een zitplaats: positie van het zitvlak en de kijkrichting (in Blender)."""
    zitplaatsen.append({'x': round(x, 3), 'z': round(-y, 3), 'y': round(z, 3), 'h': kop(fx, fy)})


def vrij(x0, y0, x1, y1):
    for a in bezet:
        if x0 < a[2] and x1 > a[0] and y0 < a[3] and y1 > a[1]:
            return False
    return True


def neem(x0, y0, x1, y1):
    bezet.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))


def collectie(naam, ouder=None):
    c = bpy.data.collections.new(naam)
    (ouder or bpy.context.scene.collection).children.link(c)
    return c


# =====================================================================
#  Materialen
# =====================================================================
GEVELKLEUREN = {
    'baksteen': '#9c4a36', 'rood': '#b5654a', 'oker': '#d1a25e', 'creme': '#e8dcc0',
    'wit': '#efece4', 'grijs': '#a3a19c', 'blauw': '#8aa3b5', 'groen': '#97a88a',
}
LUIFELS = {'rood': '#b23b35', 'groen': '#2f6b4f', 'blauw': '#2c5d8f', 'roze': '#e38fb0',
           'zwart': '#2b2b2b', 'geel': '#e0a823'}
WAREN = {'waar_rood': '#d03a2f', 'waar_oranje': '#ec8a2b', 'waar_geel': '#f2c94c', 'waar_groen': '#4caf50',
         'waar_blauw': '#3a78c2', 'waar_paars': '#8e5bb5', 'waar_roze': '#f29bb8', 'waar_wit': '#f2f0ea',
         'waar_bruin': '#9a6436', 'waar_donker': '#3a2a22'}


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
    materiaal('zand', '#e2cf9c', 1.0, tex_vlak('zand', '#e2cf9c', 0.12, 2, 47))
    materiaal('interieur_winkel', '#f3e6cf', 0.9, tex_interieur('interieur_winkel', '#efe3cf', 48),
              emissie='#ffe9c4', sterkte=0.12)
    materiaal('interieur_horeca', '#c9a46b', 0.9, tex_interieur('interieur_horeca', '#b98a5a', 49, horeca=True),
              emissie='#ffcf8a', sterkte=0.12)
    for naam, kleur in LUIFELS.items():
        materiaal('luifel_' + naam, kleur, 0.85, tex_streep('luifel_' + naam, kleur, 50))
    for naam, kleur in WAREN.items():
        materiaal(naam, kleur, 0.6)
    materiaal('glas', '#a9c4d4', 0.05, alfa=0.22)
    materiaal('plint', '#3b3f45', 0.7)
    materiaal('kozijn', '#2a2d31', 0.5)
    materiaal('markering', '#f1f1ea', 0.7)
    materiaal('boomstam', '#5b4331', 0.9)
    materiaal('blad_1', '#4f7f35', 0.85)
    materiaal('blad_2', '#6b9440', 0.85)
    materiaal('blad_3', '#3f6b3a', 0.85)
    materiaal('metaal', '#3a3d42', 0.5, metaal=0.6)
    materiaal('inox', '#b9bec4', 0.3, metaal=0.8)
    materiaal('metaal_groen', '#2e5b47', 0.6, metaal=0.3)
    materiaal('lamp', '#fff3d0', 0.4, emissie='#ffe9b0')
    materiaal('water', '#4f8fb3', 0.05)
    materiaal('hout', '#8a6440', 0.8)
    materiaal('hout_licht', '#c49a6c', 0.8)
    materiaal('band', '#1d1e21', 0.8)
    materiaal('ruit', '#27323c', 0.1)
    materiaal('deur', '#5a3b2a', 0.7)
    materiaal('postrood', '#d0312d', 0.5)
    materiaal('bordblauw', '#1f4e9c', 0.5)
    materiaal('wit', '#f4f4f0', 0.6)
    materiaal('zwart', '#1c1c1e', 0.6)
    materiaal('beton', '#a9a59c', 0.95)
    materiaal('terracotta', '#b5643c', 0.85)
    materiaal('kussen_rood', '#c0392b', 0.8)
    for naam, kleur in [('auto_rood', '#c0392b'), ('auto_blauw', '#2e5d9a'), ('auto_wit', '#e9e9e6'),
                        ('auto_zwart', '#26272b'), ('auto_geel', '#e5b62c'), ('auto_groen', '#3b7a57')]:
        materiaal(naam, kleur, 0.35, metaal=0.2)
    materiaal('fiets_frame', '#2c5d8f', 0.4, metaal=0.3)
    materiaal('fiets_frame2', '#b23b35', 0.4, metaal=0.3)
    materiaal('fiets_frame3', '#2f2f33', 0.4, metaal=0.3)


def bordmateriaal(kleur):
    return materiaal('bord_' + kleur.lstrip('#'), kleur, 0.6).name


# =====================================================================
#  Kleine dingen
# =====================================================================
def fiets_vorm(b, x, y, z, langs_x, kader):
    """Een geparkeerde fiets, in de wereld geplaatst."""
    def p(u, h):           # u langs de fiets, h hoogte
        return (x + u, y, z + h) if langs_x else (x, y + u, z + h)
    as_ = 'Y' if langs_x else 'X'
    for u in (-0.52, 0.52):
        b.torus(p(u, 0.34), 0.31, 0.025, 'band', as_=as_, seg=12, seg_r=3)
    b.staaf(p(-0.52, 0.34), p(-0.05, 0.3), 0.035, kader)
    b.staaf(p(-0.05, 0.3), p(-0.2, 0.85), 0.035, kader)
    b.staaf(p(-0.2, 0.82), p(0.38, 0.82), 0.035, kader)
    b.staaf(p(-0.05, 0.3), p(0.38, 0.82), 0.035, kader)
    b.staaf(p(-0.52, 0.34), p(-0.2, 0.82), 0.025, kader)
    b.staaf(p(0.38, 0.82), p(0.52, 0.34), 0.03, kader)
    b.staaf(p(0.38, 0.82), p(0.42, 1.0), 0.03, 'metaal')
    if langs_x:
        b.doos(x - 0.32, y - 0.06, z + 0.88, x - 0.08, y + 0.06, z + 0.94, 'zwart')
        b.staaf((x + 0.42, y - 0.25, z + 1.0), (x + 0.42, y + 0.25, z + 1.0), 0.03, 'metaal')
    else:
        b.doos(x - 0.06, y - 0.32, z + 0.88, x + 0.06, y - 0.08, z + 0.94, 'zwart')
        b.staaf((x - 0.25, y + 0.42, z + 1.0), (x + 0.25, y + 0.42, z + 1.0), 0.03, 'metaal')


def boom(col, x, y, z, grootte=1.0, botsing=True, naam='Boom'):
    b = Bouwer(naam, col)
    h = 2.4 * grootte
    b.cilinder(x, y, z, 0.18 * grootte, h, 'boomstam', seg=7)
    blad = rnd.choice(['blad_1', 'blad_2', 'blad_3'])
    r = 1.7 * grootte
    b.bol(x, y, z + h + r * 0.55, r, blad, schaal=(1, 1, 1.1), rnd=rnd)
    if rnd.random() < 0.6:
        b.bol(x + rnd.uniform(-0.7, 0.7) * grootte, y + rnd.uniform(-0.7, 0.7) * grootte,
              z + h + r * 1.25, r * 0.7, blad, rnd=rnd)
    b.klaar()
    if botsing:
        botser(x - 0.3, y - 0.3, x + 0.3, y + 0.3, 2.0)


def lantaarn(col, x, y, richting, namen=None):
    b = Bouwer('Lantaarn', col)
    z = STOEP_H
    b.cilinder(x, y, z, 0.12, 0.5, 'metaal', seg=8)
    b.cilinder(x, y, z, 0.07, 5.2, 'metaal', seg=8)
    dx, dy = richting
    hx, hy = x + dx * 0.9, y + dy * 0.9
    b.doos(min(x, hx) - 0.05, min(y, hy) - 0.05, z + 5.0, max(x, hx) + 0.05, max(y, hy) + 0.05, z + 5.12, 'metaal')
    b.doos(hx - 0.25, hy - 0.25, z + 4.75, hx + 0.25, hy + 0.25, z + 5.0, 'lamp')
    b.doos(hx - 0.3, hy - 0.3, z + 5.0, hx + 0.3, hy + 0.3, z + 5.1, 'metaal')
    if namen:
        # straatnaambordjes: één evenwijdig met elke straat, leesbaar van beide kanten
        for k, (naam, langs_x) in enumerate(namen):
            hz = z + 2.55 + k * 0.32
            L = 0.15 * len(naam) + 0.3
            if langs_x:
                b.doos(x - L / 2, y - 0.02, hz - 0.13, x + L / 2, y + 0.02, hz + 0.13, 'bordblauw')
                for s in (1, -1):
                    b.tekst(naam, tekst_matrix(x, y + s * 0.025, hz, 0, s), 0.2, 'wit')
            else:
                b.doos(x - 0.02, y - L / 2, hz - 0.13, x + 0.02, y + L / 2, hz + 0.13, 'bordblauw')
                for s in (1, -1):
                    b.tekst(naam, tekst_matrix(x + s * 0.025, y, hz, s, 0), 0.2, 'wit')
    b.klaar()
    botser(x - 0.15, y - 0.15, x + 0.15, y + 0.15, 5.3)


def bank(col, x, y, langs_x=True, kijk=-1, z=STOEP_H, zitten=True):
    """Bank; kijk = +1/-1: de richting (langs y of x) waarin je zit te kijken."""
    b = Bouwer('Bank', col)
    L, D = 1.8, 0.5
    if langs_x:
        b.doos(x - L / 2, y - D / 2, z + 0.42, x + L / 2, y + D / 2, z + 0.5, 'hout')
        ry = y - kijk * (D / 2 - 0.03)
        b.doos(x - L / 2, ry - 0.03, z + 0.5, x + L / 2, ry + 0.03, z + 0.95, 'hout')
        for px in (x - L / 2 + 0.1, x + L / 2 - 0.15):
            b.doos(px, y - D / 2, z, px + 0.05, y + D / 2, z + 0.42, 'metaal')
        botser(x - L / 2, y - D / 2, x + L / 2, y + D / 2, 0.9)
        if zitten:
            for dx in (-0.45, 0.45):
                zit(x + dx, y + kijk * 0.05, z + 0.5, 0, kijk)
    else:
        b.doos(x - D / 2, y - L / 2, z + 0.42, x + D / 2, y + L / 2, z + 0.5, 'hout')
        rx = x - kijk * (D / 2 - 0.03)
        b.doos(rx - 0.03, y - L / 2, z + 0.5, rx + 0.03, y + L / 2, z + 0.95, 'hout')
        for py in (y - L / 2 + 0.1, y + L / 2 - 0.15):
            b.doos(x - D / 2, py, z, x + D / 2, py + 0.05, z + 0.42, 'metaal')
        botser(x - D / 2, y - L / 2, x + D / 2, y + L / 2, 0.9)
        if zitten:
            for dy in (-0.45, 0.45):
                zit(x + kijk * 0.05, y + dy, z + 0.5, kijk, 0)
    b.klaar()


def auto(col, x, y, langs_x):
    b = Bouwer('Auto', col)
    kleur = rnd.choice(['auto_rood', 'auto_blauw', 'auto_wit', 'auto_zwart', 'auto_geel', 'auto_groen'])
    L, B = 4.2, 1.8
    hx, hy = (L / 2, B / 2) if langs_x else (B / 2, L / 2)
    b.doos(x - hx, y - hy, 0.35, x + hx, y + hy, 1.0, kleur)
    if langs_x:
        b.doos(x - hx * 0.55, y - hy * 0.9, 1.0, x + hx * 0.35, y + hy * 0.9, 1.5, 'ruit', kleur)
        wielen = [(x + sx * hx * 0.62, y + sy * (hy - 0.1)) for sx in (-1, 1) for sy in (-1, 1)]
        rot = Matrix.Rotation(math.pi / 2, 4, 'X')
    else:
        b.doos(x - hx * 0.9, y - hy * 0.55, 1.0, x + hx * 0.9, y + hy * 0.35, 1.5, 'ruit', kleur)
        wielen = [(x + sx * (hx - 0.1), y + sy * hy * 0.62) for sx in (-1, 1) for sy in (-1, 1)]
        rot = Matrix.Rotation(math.pi / 2, 4, 'Y')
    for wx, wy in wielen:
        b.cilinder(0, 0, 0, 0.34, 0.24, 'band', seg=10,
                   matrix=Matrix.Translation((wx, wy, 0.34)) @ rot @ Matrix.Translation((0, 0, -0.12)))
    b.klaar()
    botser(x - hx, y - hy, x + hx, y + hy, 1.5)


def bloembak(b, x, y, z, lx, ly):
    b.doos(x - lx / 2, y - ly / 2, z, x + lx / 2, y + ly / 2, z + 0.5, 'beton', schaal=2)
    n = max(2, int(lx * ly * 6))
    for _ in range(n):
        px = x + rnd.uniform(-lx / 2 + 0.15, lx / 2 - 0.15)
        py = y + rnd.uniform(-ly / 2 + 0.15, ly / 2 - 0.15)
        b.bol(px, py, z + 0.6, rnd.uniform(0.14, 0.22), rnd.choice(['blad_1', 'blad_2', 'waar_roze', 'waar_geel',
                                                                     'waar_rood', 'waar_paars']))


def potplant(b, x, y, z, s=1.0):
    b.cilinder(x, y, z, 0.18 * s, 0.35 * s, 'terracotta', seg=8, r_top=0.22 * s)
    b.bol(x, y, z + 0.55 * s, 0.26 * s, rnd.choice(['blad_1', 'blad_2', 'blad_3']))


# =====================================================================
#  Grond en straten
# =====================================================================
def bouw_grond(col):
    b = Bouwer('Weiland', col)
    G = 320
    b.vlak([(-G, -G, -0.02), (G, -G, -0.02), (G, G, -0.02), (-G, G, -0.02)], 'gras',
           [(-G / 4, -G / 4), (G / 4, -G / 4), (G / 4, G / 4), (-G / 4, G / 4)])
    b.klaar('wereld')

    b = Bouwer('Straten', col)
    H = HALF
    b.vlak([(-H, -H, 0), (H, -H, 0), (H, H, 0), (-H, H, 0)], 'asfalt',
           [(-H / 6, -H / 6), (H / 6, -H / 6), (H / 6, H / 6), (-H / 6, H / 6)])
    # putdeksels
    for _ in range(40):
        i = rnd.randrange(BLOKKEN + 1)
        a, e = blok_bereik(rnd.randrange(BLOKKEN))
        t = rnd.uniform(a + 5, e - 5)
        zij = rnd.choice((-1.3, 1.3))
        x, y = (weg_as(i) + zij, t) if rnd.random() < 0.5 else (t, weg_as(i) + zij)
        b.cilinder(x, y, -0.01, 0.35, 0.025, 'metaal', seg=12)
    b.klaar('wereld')

    # wegmarkeringen: onderbroken middenlijn, zebrapaden en haaientanden
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
            for y0 in (a + 0.6, e - 3.6):
                for k in range(6):
                    xs = as_ - WEG / 2 + 0.9 + k * 1.5
                    b.doos(xs, y0, 0, xs + 0.8, y0 + 3.0, z, 'markering')
                    b.doos(y0, xs, 0, y0 + 3.0, xs + 0.8, z, 'markering')
    b.klaar('wereld')


# =====================================================================
#  Winkels
# =====================================================================
def etalage(b, g, u0, u1, z, soort):
    """Spulletjes achter het raam: op een plank tussen v = -0.95 en -0.3."""
    w = u1 - u0
    def p(u, v):
        return g.p(u, v)
    if soort in ('bakker', 'choco'):
        for k in range(int(w / 0.45)):
            u = u0 + 0.3 + k * 0.45
            x, y, _ = p(u, -0.6)
            if soort == 'bakker' and k % 3 == 2:
                b.cilinder(x, y, z, 0.17, 0.14, 'waar_wit', seg=12)
                b.cilinder(x, y, z + 0.14, 0.15, 0.05, 'waar_roze', seg=12)
            else:
                b.bol(x, y, z + 0.06, 0.16, 'waar_bruin' if soort == 'bakker' else 'waar_donker',
                      schaal=(1, 0.55, 0.45) if g.kant in 'nz' else (0.55, 1, 0.45))
    elif soort in ('boeken', 'kranten'):
        for rij, hoogte in ((-0.75, 0.0), (-0.45, 0.0)):
            u = u0 + 0.2
            while u < u1 - 0.3:
                d = rnd.uniform(0.05, 0.09)
                h = rnd.uniform(0.22, 0.32)
                kl = rnd.choice(list(WAREN))
                g.doos(b, u, rij - 0.1, u + d, rij + 0.1, z + hoogte, z + hoogte + h, kl)
                u += d + 0.01
    elif soort == 'kledij':
        for k in range(max(1, int(w / 1.1))):
            u = u0 + 0.6 + k * 1.1
            x, y, _ = p(u, -0.6)
            b.cilinder(x, y, z, 0.03, 0.8, 'metaal', seg=6)
            b.cilinder(x, y, z + 0.8, 0.17, 0.55, rnd.choice(['waar_rood', 'waar_blauw', 'waar_geel', 'waar_wit',
                                                                'waar_groen', 'waar_paars']), seg=10, r_top=0.2)
            b.bol(x, y, z + 1.5, 0.11, 'waar_wit', sub=2)
    elif soort in ('speelgoed',):
        for k in range(int(w / 0.35)):
            u = u0 + 0.25 + k * 0.35
            x, y, _ = p(u, rnd.uniform(-0.8, -0.4))
            if k % 2:
                b.bol(x, y, z + 0.12, 0.12, rnd.choice(list(WAREN)), sub=2)
            else:
                s = rnd.uniform(0.08, 0.14)
                b.doos(x - s, y - s, z, x + s, y + s, z + 2 * s, rnd.choice(list(WAREN)))
        x, y, _ = p(u0 + w * 0.5, -0.55)                    # teddybeer
        b.bol(x, y, z + 0.22, 0.2, 'waar_bruin', sub=2)
        b.bol(x, y, z + 0.52, 0.14, 'waar_bruin', sub=2)
    elif soort in ('bloemen', 'groenten'):
        for k in range(int(w / 0.5)):
            u = u0 + 0.3 + k * 0.5
            x, y, _ = p(u, -0.6)
            b.cilinder(x, y, z, 0.16, 0.3, 'inox' if soort == 'bloemen' else 'hout_licht', seg=10)
            for _ in range(5):
                b.bol(x + rnd.uniform(-0.1, 0.1), y + rnd.uniform(-0.1, 0.1), z + 0.4,
                      0.09, rnd.choice(['waar_rood', 'waar_roze', 'waar_geel', 'waar_paars', 'waar_wit'])
                      if soort == 'bloemen' else rnd.choice(['waar_rood', 'waar_oranje', 'waar_groen', 'waar_geel']))
    elif soort == 'ijs':
        g.doos(b, u0 + 0.2, -0.9, u1 - 0.2, -0.35, z, z + 0.4, 'inox')
        for k in range(int((w - 0.5) / 0.35)):
            u = u0 + 0.35 + k * 0.35
            g.doos(b, u, -0.8, u + 0.28, -0.45, z + 0.4, z + 0.46,
                   ['waar_roze', 'waar_wit', 'waar_bruin', 'waar_geel', 'waar_groen', 'waar_rood'][k % 6])
    elif soort in ('slager', 'apotheek', 'optiek'):
        for rij in (0.0, 0.45):
            u = u0 + 0.2
            while u < u1 - 0.3:
                g.doos(b, u, -0.85, u + 0.14, -0.7, z + rij, z + rij + 0.18,
                       rnd.choice(['waar_wit', 'waar_groen', 'waar_blauw']) if soort != 'slager'
                       else rnd.choice(['waar_rood', 'waar_roze']))
                u += 0.2
            g.doos(b, u0 + 0.1, -0.95, u1 - 0.1, -0.6, z + rij - 0.03, z + rij, 'wit')
    elif soort == 'fietsen':
        x, y, _ = p((u0 + u1) / 2, -0.55)
        fiets_vorm(b, x, y, z, g.kant in 'nz', rnd.choice(['fiets_frame', 'fiets_frame2']))
    elif soort in ('cafe', 'resto', 'frituur', 'kapper'):
        for k in range(max(1, int(w / 1.6))):
            u = u0 + 0.6 + k * 1.6
            x, y, _ = p(u, -0.6)
            potplant(b, x, y, z, 1.0)


def winkelpui(b, g, w, z0, gevel, winkel, hoog):
    """De benedenverdieping als winkel: inspringende etalage, uithangbord, zonnescherm, terras."""
    naam, soort, bord, letters, luifel, terras = winkel
    gebouwde_winkels.append((naam, soort, Vector(g.p(w / 2, 0, 0)), g.out.copy(), g.r.copy(), w))
    horeca = soort in ('cafe', 'resto', 'frituur', 'ijs')
    INSPRING = 1.0
    # binnenkant en zijmuren
    g.doos(b, 0, -DIEPTE, w, -INSPRING, z0, z0 + 3, gevel, voor='interieur_horeca' if horeca else 'interieur_winkel',
           raster=VERDIEP)
    g.doos(b, 0, -INSPRING, 0.3, 0, z0, z0 + 3, 'plint')
    g.doos(b, w - 0.3, -INSPRING, w, 0, z0, z0 + 3, 'plint')
    plank = 0.5 if not horeca else 0.35
    g.doos(b, 0.3, -INSPRING, w - 0.3, -0.05, z0, z0 + plank, 'plint')
    # glas met kozijnen en een deur
    g.doos(b, 0.3, -0.14, w - 0.3, -0.12, z0 + plank, z0 + 2.55, 'glas')
    g.doos(b, 0.3, -0.16, w - 0.3, -0.1, z0 + 2.5, z0 + 2.6, 'kozijn')
    deur = w - 1.4
    g.doos(b, deur - 0.05, -0.16, deur + 0.05, -0.1, z0 + plank, z0 + 2.5, 'kozijn')
    g.doos(b, deur + 0.85, -0.18, deur + 0.9, -0.12, z0 + 1.0, z0 + 1.3, 'inox')
    etalage(b, g, 0.4, deur - 0.15, z0 + plank, soort)
    # uithangbord met naam
    g.doos(b, 0.15, -0.02, w - 0.15, 0.12, z0 + 2.62, z0 + 3.15, bordmateriaal(bord))
    grootte = min(0.36, (w - 0.6) / (0.6 * len(naam)))
    materiaal('letters_' + letters.lstrip('#'), letters, 0.5)
    b.tekst(naam, g.matrix(w / 2, 0.125, z0 + 2.885), grootte, 'letters_' + letters.lstrip('#'))
    if soort == 'apotheek':
        # groen kruis dat uitsteekt
        x, y, _ = g.p(0.2, 0.55)
        g.doos(b, 0.17, 0.25, 0.23, 0.85, z0 + 3.4, z0 + 3.95, 'waar_groen', mats=None)
        g.doos(b, 0.17, 0.4, 0.23, 0.7, z0 + 3.25, z0 + 4.1, 'waar_groen')
        g.doos(b, 0.17, 0.0, 0.23, 0.25, z0 + 3.65, z0 + 3.7, 'metaal')
    if soort == 'kapper':
        x, y, _ = g.p(0.15, 0.25)
        for k in range(6):
            b.cilinder(x, y, z0 + 1.5 + k * 0.15, 0.08, 0.15, 'waar_rood' if k % 2 else 'waar_wit', seg=10)
    # zonnescherm (van boven en van onder zichtbaar)
    if luifel:
        m = 'luifel_' + luifel
        a0, a1 = g.p(0.2, 0.0, z0 + 2.58), g.p(w - 0.2, 0.0, z0 + 2.58)
        c0, c1 = g.p(0.2, 1.35, z0 + 2.2), g.p(w - 0.2, 1.35, z0 + 2.2)
        d0, d1 = g.p(0.2, 1.35, z0 + 1.98), g.p(w - 0.2, 1.35, z0 + 1.98)
        uv = [(0, 0), (w - 0.4, 0), (w - 0.4, 1.4), (0, 1.4)]
        b.vlak([a0, a1, c1, c0], m, uv)
        b.vlak([c0, c1, a1, a0], m, uv)
        b.vlak([c0, c1, d1, d0], m, [(0, 0.2), (w - 0.4, 0.2), (w - 0.4, 0), (0, 0)])
        b.vlak([d0, d1, c1, c0], m, [(0, 0), (w - 0.4, 0), (w - 0.4, 0.2), (0, 0.2)])
    # terras met tafeltjes, stoelen en parasols
    if terras and w >= 4.5:
        n = int((w - 0.6) / 2.2)
        start = (w - (n - 1) * 2.2) / 2
        for k in range(n):
            u = start + k * 2.2
            tx, ty, _ = g.p(u, 0.8)
            b.cilinder(tx, ty, STOEP_H, 0.04, 0.72, 'metaal', seg=6)
            b.cilinder(tx, ty, STOEP_H + 0.72, 0.36, 0.04, 'wit' if soort != 'resto' else 'hout_licht', seg=14)
            b.cilinder(tx + 0.1, ty + 0.05, STOEP_H + 0.76, 0.035, 0.14, 'glas', seg=6)
            if rnd.random() < 0.6:
                b.cilinder(tx - 0.1, ty - 0.08, STOEP_H + 0.76, 0.04, 0.09, 'wit', seg=6)
            botser(tx - 0.38, ty - 0.38, tx + 0.38, ty + 0.38, 0.8)
            for s in (-1, 1):
                cx, cy, _ = g.p(u + s * 0.62, 0.8)
                q = g.r * (-s)                    # stoel kijkt naar de tafel
                b.doos(cx - 0.2, cy - 0.2, STOEP_H + 0.42, cx + 0.2, cy + 0.2, STOEP_H + 0.46, 'zwart')
                for lx in (-0.17, 0.17):
                    for ly in (-0.17, 0.17):
                        b.doos(cx + lx - 0.015, cy + ly - 0.015, STOEP_H, cx + lx + 0.015, cy + ly + 0.015,
                               STOEP_H + 0.42, 'zwart')
                bx, by = cx - q.x * 0.19, cy - q.y * 0.19
                b.doos(bx - 0.2 * abs(q.y) - 0.02, by - 0.2 * abs(q.x) - 0.02, STOEP_H + 0.46,
                       bx + 0.2 * abs(q.y) + 0.02, by + 0.2 * abs(q.x) + 0.02, STOEP_H + 0.85, 'zwart')
                zit(cx, cy, STOEP_H + 0.46, q.x, q.y)
            if luifel is None and k % 2 == 0:
                b.cilinder(tx, ty, STOEP_H + 0.76, 0.025, 1.6, 'wit', seg=6)
                b.cilinder(tx, ty, STOEP_H + 2.2, 1.25, 0.35, 'wit', seg=8, r_top=0.05)
        # krijtbord op de stoep
        bx, by, _ = g.p(w - 0.35, 1.1)
        b.doos(bx - 0.25, by - 0.2, STOEP_H, bx + 0.25, by + 0.2, STOEP_H + 0.9, 'zwart')
    # waren buiten
    if soort in ('groenten', 'bloemen'):
        for k in range(int((w - 0.8) / 0.7)):
            u = 0.5 + k * 0.7
            g.doos(b, u, 0.1, u + 0.6, 0.6, STOEP_H, STOEP_H + 0.45, 'hout_licht')
            for _ in range(6):
                x, y, _ = g.p(u + rnd.uniform(0.1, 0.5), rnd.uniform(0.2, 0.5))
                b.bol(x, y, STOEP_H + 0.52, 0.08, rnd.choice(['waar_rood', 'waar_oranje', 'waar_groen', 'waar_geel'])
                      if soort == 'groenten' else rnd.choice(['waar_rood', 'waar_roze', 'waar_paars', 'waar_wit']))
        a, c = g.p(0.4, 0.05), g.p(w - 0.4, 0.7)
        botser(a[0], a[1], c[0], c[1], 0.6)
    if soort == 'fietsen':
        for k in range(2):
            x, y, _ = g.p(1.2 + k * 2.0, 0.45)
            fiets_vorm(b, x, y, STOEP_H, g.kant in 'nz', rnd.choice(['fiets_frame', 'fiets_frame2', 'fiets_frame3']))
        a, c = g.p(0.3, 0.1), g.p(4.0, 0.8)
        botser(a[0], a[1], c[0], c[1], 1.0)
    # bovenverdiepingen
    g.doos(b, 0, -DIEPTE, w, 0, z0 + 3, z0 + hoog, gevel, top='plat_dak', bodem=True, raster=VERDIEP)


def huisvoorkant(b, g, w, z0, verd):
    """Voordeur, soms een bloembak en balkons."""
    mid = w / 2 + rnd.uniform(-0.6, 0.6) * (w > 5)
    g.doos(b, mid - 0.55, -0.02, mid + 0.55, 0.05, z0, z0 + 2.2, 'deur')
    g.doos(b, mid - 0.7, 0.0, mid + 0.7, 0.35, z0, z0 + 0.15, 'steen')           # stoepje
    if rnd.random() < 0.45:
        u = mid + 1.2 if mid + 1.9 < w else mid - 1.9
        x, y, _ = g.p(u + 0.35, 0.3)
        potplant(b, x, y, z0, rnd.uniform(0.8, 1.2))
    elif rnd.random() < 0.5:
        x, y, _ = g.p(mid + 0.85, 0.25)
        katplekken.append({'x': round(x, 2), 'z': round(-y, 2), 'y': round(z0 + 0.15, 2), 'h': g.richting(False)})
    if verd >= 3 and w >= 4.5 and rnd.random() < 0.4:
        for k in range(1, verd):
            if rnd.random() < 0.6:
                zb = z0 + k * VERDIEP
                g.doos(b, 0.6, 0, w - 0.6, 0.9, zb - 0.15, zb, 'beton', schaal=2)
                g.doos(b, 0.6, 0.85, w - 0.6, 0.9, zb + 0.95, zb + 1.0, 'metaal')
                for u in [0.62 + t * 0.25 for t in range(int((w - 1.24) / 0.25) + 1)]:
                    g.doos(b, u, 0.86, u + 0.025, 0.89, zb, zb + 0.95, 'metaal')
                for u in (0.62, w - 0.65):
                    g.doos(b, u, 0, u + 0.03, 0.9, zb + 0.95, zb + 1.0, 'metaal')
                if rnd.random() < 0.7:
                    x, y, _ = g.p(rnd.uniform(1.0, w - 1.0), 0.4)
                    potplant(b, x, y, zb, 0.8)


def bouw_huizenrij(col, naam, x0, y0, x1, y1, straatkant, hoogtes, langs_x, winkelkans):
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
        g = Gevel(straatkant, bx0, by0, bx1, by1)
        winkel = None
        if w >= 4.4 and rnd.random() < winkelkans:
            if not winkel_rij:
                winkel_rij.extend(rnd.sample(WINKELS, len(WINKELS)))
            winkel = winkel_rij.pop()
        hellend = verd <= 3 and rnd.random() < 0.7
        if winkel:
            winkelpui(b, g, w, STOEP_H, gevel, winkel, h)
        else:
            b.doos(bx0, by0, STOEP_H, bx1, by1, STOEP_H + h, gevel, 'plat_dak', raster=VERDIEP, schaal=3)
            huisvoorkant(b, g, w, STOEP_H, verd)
        hz = STOEP_H + h
        nok = 0
        if hellend:
            dak = rnd.choice(['dak_rood', 'dak_rood', 'dak_grijs'])
            nok = rnd.uniform(2.6, 3.6)
            b.zadeldak(bx0, by0, bx1, by1, hz, nok, dak, gevel, langs_x=langs_x)
            # schoorsteen
            if rnd.random() < 0.6:
                cx = bx0 + (bx1 - bx0) * rnd.uniform(0.25, 0.75)
                cy = by0 + (by1 - by0) * rnd.uniform(0.25, 0.75)
                b.doos(cx - 0.3, cy - 0.3, hz + nok * 0.4, cx + 0.3, cy + 0.3, hz + nok + 0.6, 'gevel_baksteen', schaal=3)
        else:
            r = 0.25
            b.doos(bx0, by0, hz, bx1, by0 + r, hz + 0.5, 'plat_dak', schaal=2)
            b.doos(bx0, by1 - r, hz, bx1, by1, hz + 0.5, 'plat_dak', schaal=2)
            if rnd.random() < 0.4:
                cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
                b.doos(cx - 1, cy - 1, hz, cx + 1, cy + 1, hz + 1.6, 'metaal', schaal=2)
        b.klaar()
        botser(bx0, by0, bx1, by1, hz + nok)
        pos += w


def stoepblok(col, naam, a0, b0, a1, b1, binnen='gras'):
    b = Bouwer(naam, col)
    b.doos(a0, b0, 0, a1, b1, STOEP_H, 'stoep', schaal=2)
    if binnen:
        i = STOEP_B + DIEPTE
        b.doos(a0 + i, b0 + i, STOEP_H, a1 - i, b1 - i, STOEP_H + 0.02, binnen, schaal=4)
    b.klaar()


def gewoon_blok(col, j, i, hoogtes, winkelkans):
    x0, x1 = blok_bereik(j)
    y0, y1 = blok_bereik(i)
    c = collectie(f'Blok {j + 1}-{i + 1}', col)
    stoepblok(c, f'Stoep {j + 1}-{i + 1}', x0, y0, x1, y1)
    s, d = STOEP_B, DIEPTE
    n = f'Huis {j + 1}-{i + 1}'
    bouw_huizenrij(c, n + 'n', x0 + s, y1 - s - d, x1 - s, y1 - s, 'n', hoogtes, True, winkelkans)
    bouw_huizenrij(c, n + 'z', x0 + s, y0 + s, x1 - s, y0 + s + d, 'z', hoogtes, True, winkelkans)
    bouw_huizenrij(c, n + 'o', x1 - s - d, y0 + s + d, x1 - s, y1 - s - d, 'o', hoogtes, False, winkelkans)
    bouw_huizenrij(c, n + 'w', x0 + s, y0 + s + d, x0 + s + d, y1 - s - d, 'w', hoogtes, False, winkelkans)
    boom(c, (x0 + x1) / 2, (y0 + y1) / 2, STOEP_H, rnd.uniform(0.7, 0.9), botsing=False)


# =====================================================================
#  Park, plein en zakenwijk
# =====================================================================
def bouw_park(col):
    j, i = PARK
    x0, x1 = blok_bereik(j)
    y0, y1 = blok_bereik(i)
    c = collectie('Park', col)
    stoepblok(c, 'Parkrand', x0, y0, x1, y1, binnen=None)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    b = Bouwer('Parkgazon', c)
    r = BLOK / 2 - 3.0
    b.doos(cx - r, cy - r, STOEP_H, cx + r, cy + r, STOEP_H + 0.04, 'gras', schaal=4)
    p = 1.6
    b.doos(cx - r - 3, cy - p, STOEP_H, cx + r + 3, cy + p, STOEP_H + 0.06, 'stoep', schaal=2)
    b.doos(cx - p, cy - r - 3, STOEP_H, cx + p, cy + r + 3, STOEP_H + 0.06, 'stoep', schaal=2)
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
    botser(cx - 3.5, cy - 3.5, cx + 3.5, cy + 3.5, 0.6)

    # bomen in drie kwarten, een speeltuin in het vierde
    for dx, dy in [(-1, -1), (1, -1), (-1, 1)]:
        for k in range(2):
            boom(c, cx + dx * rnd.uniform(6.5, 10.5), cy + dy * rnd.uniform(6.5, 10.5), STOEP_H, rnd.uniform(0.9, 1.3))
    sx, sy = cx + 8.0, cy + 8.0
    s = Bouwer('Speeltuin', c)
    s.doos(sx - 3.2, sy - 3.2, STOEP_H, sx + 3.2, sy + 3.2, STOEP_H + 0.06, 'zand', schaal=3)
    # schommel
    for px in (sx - 2.4, sx - 0.2):
        s.staaf((px, sy + 1.6, STOEP_H), (px, sy + 2.2, STOEP_H + 2.2), 0.08, 'metaal_groen')
        s.staaf((px, sy + 2.8, STOEP_H), (px, sy + 2.2, STOEP_H + 2.2), 0.08, 'metaal_groen')
    s.staaf((sx - 2.4, sy + 2.2, STOEP_H + 2.2), (sx - 0.2, sy + 2.2, STOEP_H + 2.2), 0.08, 'metaal_groen')
    for px in (sx - 1.8, sx - 0.8):
        s.staaf((px - 0.2, sy + 2.2, STOEP_H + 2.2), (px - 0.2, sy + 2.2, STOEP_H + 0.5), 0.02, 'metaal')
        s.staaf((px + 0.2, sy + 2.2, STOEP_H + 2.2), (px + 0.2, sy + 2.2, STOEP_H + 0.5), 0.02, 'metaal')
        s.doos(px - 0.25, sy + 2.05, STOEP_H + 0.45, px + 0.25, sy + 2.35, STOEP_H + 0.5, 'waar_rood')
    botser(sx - 2.5, sy + 1.5, sx - 0.1, sy + 2.9, 2.3)
    # glijbaan
    s.doos(sx + 1.0, sy - 2.2, STOEP_H, sx + 2.0, sy - 1.2, STOEP_H + 1.5, 'hout_licht')
    s.staaf((sx + 1.5, sy - 1.2, STOEP_H + 1.5), (sx + 1.5, sy + 1.2, STOEP_H + 0.1), 0.6, 'waar_geel', diepte=0.05)
    s.staaf((sx + 1.0, sy - 2.4, STOEP_H), (sx + 1.0, sy - 2.2, STOEP_H + 1.5), 0.05, 'metaal_groen')
    botser(sx + 0.9, sy - 2.3, sx + 2.1, sy + 1.2, 1.6)
    # wipwap
    s.doos(sx - 1.7, sy - 1.6, STOEP_H, sx - 1.3, sy - 1.2, STOEP_H + 0.45, 'metaal_groen')
    s.staaf((sx - 3.0, sy - 1.4, STOEP_H + 0.2), (sx, sy - 1.4, STOEP_H + 0.65), 0.25, 'waar_blauw', diepte=0.05)
    botser(sx - 3.0, sy - 1.6, sx, sy - 1.2, 0.7)
    s.klaar()

    # banken langs de paden, met het gezicht naar het pad
    for sx_ in (-1, 1):
        for sy_ in (-1, 1):
            if sx_ > 0 and sy_ > 0:
                continue
            bank(c, cx + sx_ * 9.5, cy + sy_ * 2.4, True, kijk=-sy_)
            bank(c, cx + sx_ * 2.4, cy + sy_ * 9.5, False, kijk=-sx_)
    bank(c, sx - 1.2, sy - 3.8, True, kijk=1)

    # ijskar bij de fontein
    k = Bouwer('IJskar', c)
    kx, ky = cx - 5.0, cy - 5.0
    k.doos(kx - 0.8, ky - 0.45, STOEP_H + 0.35, kx + 0.8, ky + 0.45, STOEP_H + 1.1, 'waar_wit')
    k.doos(kx - 0.82, ky - 0.47, STOEP_H + 0.6, kx + 0.82, ky + 0.47, STOEP_H + 0.75, 'waar_roze')
    for wx in (-0.55, 0.55):
        k.cilinder(0, 0, 0, 0.3, 0.08, 'band', seg=12,
                   matrix=Matrix.Translation((kx + wx, ky - 0.5, STOEP_H + 0.3)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
    k.cilinder(kx, ky, STOEP_H + 1.1, 0.03, 1.2, 'metaal', seg=6)
    k.cilinder(kx, ky, STOEP_H + 2.2, 1.1, 0.3, 'luifel_roze', seg=10, r_top=0.05)
    materiaal('letters_7a2e4d', '#7a2e4d', 0.5)
    k.tekst('IJS', tekst_matrix(kx, ky - 0.48, STOEP_H + 0.9, 0, -1), 0.25,
            'letters_7a2e4d')
    k.klaar()
    botser(kx - 0.85, ky - 0.6, kx + 0.85, ky + 0.5, 1.2)

    return {'x0': cx - r, 'z0': -(cy + r), 'x1': cx + r, 'z1': -(cy - r),
            'fontein': {'x': cx, 'z': -cy, 'r': 4.2}, 'speeltuin': {'x': sx, 'z': -sy, 'r': 3.5}}


def marktkraam(c, x, y, kleur, waren):
    b = Bouwer('Marktkraam', c)
    z = STOEP_H
    b.doos(x - 1.5, y - 0.8, z + 0.8, x + 1.5, y + 0.8, z + 0.88, 'hout_licht')
    for px in (x - 1.45, x + 1.4):
        for py in (y - 0.75, y + 0.7):
            b.doos(px, py, z, px + 0.05, py + 0.05, z + 2.3, 'metaal')
    # dak in twee schuine vlakken
    m = 'luifel_' + kleur
    a = [(x - 1.65, y - 1.0, z + 2.1), (x + 1.65, y - 1.0, z + 2.1), (x + 1.65, y, z + 2.55), (x - 1.65, y, z + 2.55)]
    e = [(x - 1.65, y + 1.0, z + 2.1), (x + 1.65, y + 1.0, z + 2.1)]
    uv = [(0, 0), (3.3, 0), (3.3, 1.1), (0, 1.1)]
    b.vlak(a, m, uv)
    b.vlak(list(reversed(a)), m, uv)
    b.vlak([a[3], a[2], e[1], e[0]], m, uv)
    b.vlak([e[0], e[1], a[2], a[3]], m, uv)
    for k in range(5):
        px = x - 1.2 + k * 0.6
        b.doos(px - 0.25, y - 0.55, z + 0.88, px + 0.25, y + 0.1, z + 1.0, 'hout')
        for _ in range(5):
            b.bol(px + rnd.uniform(-0.18, 0.18), y + rnd.uniform(-0.45, 0.0), z + 1.07, 0.07, rnd.choice(waren))
    b.klaar()
    botser(x - 1.5, y - 0.8, x + 1.5, y + 0.8, 2.5)


def bouw_plein(col):
    """Marktplein met een kerk, marktkramen, een reclamezuil en duiven."""
    j, i = PLEIN
    x0, x1 = blok_bereik(j)
    y0, y1 = blok_bereik(i)
    c = collectie('Kerkplein', col)
    stoepblok(c, 'Plein', x0, y0, x1, y1, binnen=None)
    cx = (x0 + x1) / 2
    z = STOEP_H

    k = Bouwer('Kerk', c)
    sx0, sx1, sy0, sy1 = cx - 4, cx + 4, y1 - 15, y1 - 3
    k.doos(sx0, sy0, z, sx1, sy1, z + 10, 'steen', 'steen', schaal=3)
    k.zadeldak(sx0 - 0.3, sy0, sx1 + 0.3, sy1, z + 10, 5.5, 'dak_grijs', 'steen', langs_x=False, raster=3)
    tx0, tx1, ty0, ty1 = cx - 2.3, cx + 2.3, sy0 - 4.0, sy0 + 0.5
    k.doos(tx0, ty0, z, tx1, ty1, z + 22, 'steen', 'steen', schaal=3)
    k.doos(tx0 - 0.3, ty0 - 0.3, z + 22, tx1 + 0.3, ty1 + 0.3, z + 23, 'steen', schaal=3)
    k.piramide(tx0 - 0.3, ty0 - 0.3, tx1 + 0.3, ty1 + 0.3, z + 23, 11, 'dak_grijs')
    zz = z + 18.0
    k.doos(cx - 0.6, ty0 - 0.05, zz, cx + 0.6, ty0, zz + 2.4, 'ruit')
    k.doos(tx0 - 0.05, (ty0 + ty1) / 2 - 0.6, zz, tx0, (ty0 + ty1) / 2 + 0.6, zz + 2.4, 'ruit')
    k.doos(tx1, (ty0 + ty1) / 2 - 0.6, zz, tx1 + 0.05, (ty0 + ty1) / 2 + 0.6, zz + 2.4, 'ruit')
    k.doos(cx - 1.0, ty0 - 0.06, z + 13.4, cx + 1.0, ty0, z + 15.4, 'markering')
    k.doos(cx - 0.06, ty0 - 0.1, z + 14.4, cx + 0.06, ty0 - 0.06, z + 15.2, 'metaal')
    k.doos(cx, ty0 - 0.1, z + 14.34, cx + 0.6, ty0 - 0.06, z + 14.46, 'metaal')
    k.doos(cx - 1.1, ty0 - 0.08, z, cx + 1.1, ty0, z + 3.4, 'deur')
    for yy in range(3):
        wy = sy0 + 2.5 + yy * 3.5
        for wx, s in ((sx0, -1), (sx1, 1)):
            k.doos(min(wx, wx + s * 0.05), wy, z + 3.0, max(wx, wx + s * 0.05), wy + 1.3, z + 7.8, 'ruit')
    k.klaar()
    botser(sx0, sy0, sx1, sy1, z + 15.5)
    botser(tx0, ty0, tx1, ty1, z + 34)

    for bx in (x0 + 4.5, x1 - 4.5):
        for by in (y1 - 5, y1 - 12):
            boom(c, bx, by, STOEP_H, 0.85)
    bank(c, x0 + 7.2, y1 - 8.5, False, kijk=1)
    bank(c, x1 - 7.2, y1 - 8.5, False, kijk=-1)
    marktkraam(c, x0 + 6.8, y0 + 7.0, 'rood', ['waar_rood', 'waar_oranje', 'waar_groen', 'waar_geel'])
    marktkraam(c, x1 - 6.8, y0 + 7.0, 'blauw', ['waar_wit', 'waar_geel', 'waar_bruin'])
    marktkraam(c, x1 - 6.8, y0 + 11.5, 'groen', ['waar_roze', 'waar_paars', 'waar_rood', 'waar_wit'])
    # reclamezuil
    r = Bouwer('Reclamezuil', c)
    rx, ry = x0 + 6.0, y0 + 12.0
    r.cilinder(rx, ry, z, 0.6, 2.6, 'metaal_groen', seg=16)
    for k_, kl in enumerate(['waar_geel', 'waar_rood', 'waar_blauw', 'waar_wit']):
        a = k_ * math.pi / 2
        px, py = rx + math.cos(a) * 0.61, ry + math.sin(a) * 0.61
        r.doos(px - 0.3 * abs(math.sin(a)) - 0.02, py - 0.3 * abs(math.cos(a)) - 0.02, z + 0.8,
               px + 0.3 * abs(math.sin(a)) + 0.02, py + 0.3 * abs(math.cos(a)) + 0.02, z + 2.0, kl)
    r.cilinder(rx, ry, z + 2.6, 0.7, 0.2, 'metaal_groen', seg=16)
    r.cilinder(rx, ry, z + 2.8, 0.5, 0.35, 'metaal_groen', seg=16, r_top=0.05)
    r.klaar()
    botser(rx - 0.6, ry - 0.6, rx + 0.6, ry + 0.6, 3.0)
    # paaltjes langs de rand
    p = Bouwer('Paaltjes', c)
    for t in range(6):
        px = x0 + 9 + t * 2.4
        if abs(px - cx) < 1.5:
            continue
        p.cilinder(px, y0 + 0.5, z, 0.09, 0.8, 'metaal', seg=8)
        botser(px - 0.1, y0 + 0.4, px + 0.1, y0 + 0.6, 0.8)
    p.klaar()
    duiven = {'x0': cx - 5.5, 'z0': -(y0 + 11.0), 'x1': cx + 5.5, 'z1': -(y0 + 3.5)}
    praat = [{'x': x0 + 9.5, 'z': -(y0 + 9.5)}, {'x': x1 - 10.0, 'z': -(y0 + 14.5)}]
    return duiven, praat


def bouw_zakenwijk(col):
    j, i = ZAKEN
    x0, x1 = blok_bereik(j)
    y0, y1 = blok_bereik(i)
    c = collectie('Zakenwijk', col)
    stoepblok(c, 'Zakenplein', x0, y0, x1, y1, binnen=None)
    for naam, (a0, b0, a1, b1, h) in {'Toren Noord': (x0 + 4, y1 - 16, x1 - 14, y1 - 4, 57),
                                      'Toren Zuid': (x1 - 12, y0 + 4, x1 - 4, y0 + 15, 39)}.items():
        t = Bouwer(naam.replace(' ', '_'), c)
        t.doos(a0, b0, STOEP_H, a1, b1, STOEP_H + 4.5, 'steen', schaal=3)
        t.doos(a0 + 0.3, b0 + 0.3, STOEP_H + 4.5, a1 - 0.3, b1 - 0.3, STOEP_H + h, 'kantoor', 'plat_dak', raster=3)
        t.doos(a0 + 0.1, b0 + 0.1, STOEP_H + h, a1 - 0.1, b1 - 0.1, STOEP_H + h + 0.6, 'steen', schaal=3)
        t.doos((a0 + a1) / 2 - 1.5, (b0 + b1) / 2 - 1.5, STOEP_H + h + 0.6, (a0 + a1) / 2 + 1.5, (b0 + b1) / 2 + 1.5,
               STOEP_H + h + 3.5, 'metaal', schaal=2)
        t.cilinder((a0 + a1) / 2, (b0 + b1) / 2, STOEP_H + h + 3.5, 0.08, 6, 'metaal')
        t.klaar()
        botser(a0, b0, a1, b1, STOEP_H + h + 3.5)
    for bx, by in [(x0 + 6, y0 + 6), (x0 + 12, y0 + 6)]:
        boom(c, bx, by, STOEP_H, 0.8)
    bank(c, x0 + 9, y0 + 9.5, True, kijk=-1)
    # koffiekiosk
    k = Bouwer('Koffiekiosk', c)
    kx, ky = x0 + 8.0, y0 + 14.0
    k.doos(kx - 1.3, ky - 1.0, STOEP_H, kx + 1.3, ky + 1.0, STOEP_H + 2.5, 'hout', 'plat_dak')
    k.doos(kx - 1.1, ky - 1.05, STOEP_H + 1.0, kx + 1.1, ky - 1.0, STOEP_H + 2.0, 'interieur_horeca')
    k.doos(kx - 1.3, ky - 1.4, STOEP_H + 0.95, kx + 1.3, ky - 1.0, STOEP_H + 1.0, 'hout_licht')
    k.doos(kx - 1.4, ky - 1.1, STOEP_H + 2.5, kx + 1.4, ky + 1.1, STOEP_H + 2.6, 'zwart')
    materiaal('letters_f1c27d', '#f1c27d', 0.5)
    k.tekst('KOFFIE', tekst_matrix(kx, ky - 1.12, STOEP_H + 2.3, 0, -1), 0.3,
            'letters_f1c27d')
    k.klaar()
    botser(kx - 1.3, ky - 1.4, kx + 1.3, ky + 1.0, 2.6)
    # fietsenstalling
    f = Bouwer('Fietsenstalling', c)
    for t in range(4):
        fy = y0 + 18 + t * 0.9
        f.staaf((x0 + 5.0, fy, STOEP_H), (x0 + 5.0, fy, STOEP_H + 0.7), 0.04, 'inox')
        if t != 2:
            fiets_vorm(f, x0 + 5.0, fy, STOEP_H, True, rnd.choice(['fiets_frame', 'fiets_frame2', 'fiets_frame3']))
    f.klaar()
    botser(x0 + 4.3, y0 + 17.6, x0 + 5.7, y0 + 21.0, 1.1)
    return [{'x': x0 + 11.0, 'z': -(y0 + 10.5)}]


# =====================================================================
#  Straatmeubilair
# =====================================================================
def bushalte(c, x, y, langs_x, kijk):
    """Wachthuisje: kijk = richting naar de straat (+1/-1 langs de korte as)."""
    b = Bouwer('Bushalte', c)
    z = STOEP_H
    L, D = 3.6, 1.0
    if langs_x:
        x0, x1 = x - L / 2, x + L / 2
        yr = y - kijk * D / 2                   # achterwand
        b.doos(x0, yr - 0.03, z + 0.15, x1, yr + 0.03, z + 2.3, 'glas')
        for px in (x0, x1 - 0.06):
            b.doos(px, min(yr, y + kijk * D / 2), z, px + 0.06, max(yr, y + kijk * D / 2), z + 2.4, 'metaal')
            b.doos(px, min(yr, y), z + 0.15, px + 0.06, max(yr, y), z + 2.3, 'glas')
        b.doos(x0 - 0.1, y - D / 2 - 0.1, z + 2.4, x1 + 0.1, y + D / 2 + 0.1, z + 2.5, 'metaal')
        b.doos(x0 + 0.4, yr + kijk * 0.05, z + 0.42, x1 - 0.4, yr + kijk * 0.45, z + 0.48, 'hout')
        for t in (-0.9, 0.0, 0.9):
            zit(x + t, yr + kijk * 0.27, z + 0.48, 0, kijk)
        px, py = x1 + 0.6, y + kijk * (D / 2 - 0.1)
    else:
        y0, y1 = y - L / 2, y + L / 2
        xr = x - kijk * D / 2
        b.doos(xr - 0.03, y0, z + 0.15, xr + 0.03, y1, z + 2.3, 'glas')
        for py_ in (y0, y1 - 0.06):
            b.doos(min(xr, x + kijk * D / 2), py_, z, max(xr, x + kijk * D / 2), py_ + 0.06, z + 2.4, 'metaal')
            b.doos(min(xr, x), py_, z + 0.15, max(xr, x), py_ + 0.06, z + 2.3, 'glas')
        b.doos(x - D / 2 - 0.1, y0 - 0.1, z + 2.4, x + D / 2 + 0.1, y1 + 0.1, z + 2.5, 'metaal')
        b.doos(xr + kijk * 0.05, y0 + 0.4, z + 0.42, xr + kijk * 0.45, y1 - 0.4, z + 0.48, 'hout')
        for t in (-0.9, 0.0, 0.9):
            zit(xr + kijk * 0.27, y + t, z + 0.48, kijk, 0)
        px, py = x + kijk * (D / 2 - 0.1), y1 + 0.6
    # haltepaal met bord
    b.cilinder(px, py, z, 0.05, 2.9, 'metaal', seg=8)
    b.doos(px - 0.3, py - 0.3, z + 2.3, px + 0.3, py + 0.3, z + 2.9, 'waar_wit')
    for nx, ny in ((0, -1), (1, 0), (0, 1), (-1, 0)):
        b.tekst('BUS', tekst_matrix(px + nx * 0.305, py + ny * 0.305, z + 2.68, nx, ny), 0.17, 'bordblauw')
        b.tekst('12', tekst_matrix(px + nx * 0.305, py + ny * 0.305, z + 2.48, nx, ny), 0.16, 'waar_rood')
    b.klaar()
    if langs_x:
        botser(x - L / 2, y - D / 2, x + L / 2, y + D / 2, 2.5)
        neem(x - L / 2 - 1.2, y - D, x + L / 2 + 1.2, y + D)
    else:
        botser(x - D / 2, y - L / 2, x + D / 2, y + L / 2, 2.5)
        neem(x - D, y - L / 2 - 1.2, x + D, y + L / 2 + 1.2)
    botser(px - 0.1, py - 0.1, px + 0.1, py + 0.1, 2.9)


def stoeprand_ding(c, g, u, soort):
    """Iets op de stoeprand-strook (v tussen -1.3 en -0.3 van de stoeprand)."""
    v = -0.75
    x, y, _ = g.p(u, v)
    z = STOEP_H
    langs_x = g.kant in 'nz'
    half = {'prullenbak': 0.35, 'rek': 1.6, 'brandkraan': 0.25, 'brievenbus': 0.35, 'bloembak': 0.8,
            'parkeerbord': 0.2, 'zitbank': 1.0}[soort]
    a, e = g.p(u - half, v - 0.55), g.p(u + half, v + 0.55)
    if not vrij(min(a[0], e[0]), min(a[1], e[1]), max(a[0], e[0]), max(a[1], e[1])):
        return
    neem(a[0], a[1], e[0], e[1])
    b = Bouwer(soort.capitalize(), c)
    if soort == 'prullenbak':
        b.cilinder(x, y, z, 0.25, 0.85, 'metaal_groen', seg=12)
        b.cilinder(x, y, z + 0.85, 0.27, 0.08, 'metaal', seg=12)
        botser(x - 0.27, y - 0.27, x + 0.27, y + 0.27, 0.95)
    elif soort == 'rek':
        for t in (-1.2, -0.4, 0.4, 1.2):
            px, py, _ = g.p(u + t, v)
            q = g.out * 0.3
            b.staaf((px - q.x, py - q.y, z), (px - q.x, py - q.y, z + 0.75), 0.04, 'inox')
            b.staaf((px + q.x, py + q.y, z), (px + q.x, py + q.y, z + 0.75), 0.04, 'inox')
            b.staaf((px - q.x, py - q.y, z + 0.75), (px + q.x, py + q.y, z + 0.75), 0.04, 'inox')
        for t in (-1.2, 0.4) if rnd.random() < 0.5 else (-0.4, 0.4, 1.2):
            px, py, _ = g.p(u + t, v - 0.12)
            fiets_vorm(b, px, py, z, langs_x, rnd.choice(['fiets_frame', 'fiets_frame2', 'fiets_frame3']))
        botser(min(a[0], e[0]) + 0.1, min(a[1], e[1]) + 0.25, max(a[0], e[0]) - 0.1, max(a[1], e[1]) - 0.25, 1.1)
    elif soort == 'brandkraan':
        b.cilinder(x, y, z, 0.12, 0.55, 'postrood', seg=10)
        b.bol(x, y, z + 0.58, 0.12, 'postrood', sub=1)
        b.staaf((x - 0.18, y, z + 0.4), (x + 0.18, y, z + 0.4), 0.07, 'postrood')
        botser(x - 0.18, y - 0.18, x + 0.18, y + 0.18, 0.7)
    elif soort == 'brievenbus':
        b.doos(x - 0.06, y - 0.06, z, x + 0.06, y + 0.06, z + 0.8, 'metaal')
        b.doos(x - 0.27, y - 0.2, z + 0.8, x + 0.27, y + 0.2, z + 1.45, 'postrood')
        b.doos(x - 0.3, y - 0.23, z + 1.45, x + 0.3, y + 0.23, z + 1.5, 'postrood')
        botser(x - 0.3, y - 0.23, x + 0.3, y + 0.23, 1.5)
    elif soort == 'bloembak':
        bloembak(b, x, y, z, 1.5 if langs_x else 0.7, 0.7 if langs_x else 1.5)
        botser(x - (0.75 if langs_x else 0.35), y - (0.35 if langs_x else 0.75),
               x + (0.75 if langs_x else 0.35), y + (0.35 if langs_x else 0.75), 0.6)
    elif soort == 'parkeerbord':
        b.cilinder(x, y, z, 0.04, 2.6, 'metaal', seg=8)
        b.doos(x - 0.25, y - 0.25, z + 2.0, x + 0.25, y + 0.25, z + 2.5, 'bordblauw')
        for s in (1, -1):
            px, py, _ = g.p(u, v + s * 0.255)
            b.tekst('P', tekst_matrix(px, py, z + 2.25, g.out.x * s, g.out.y * s), 0.4, 'wit')
        botser(x - 0.08, y - 0.08, x + 0.08, y + 0.08, 2.6)
    b.klaar()


def bouw_straatmeubilair(col):
    c_l = collectie('Lantaarns', col)
    c_b = collectie('Straatbomen', col)
    c_a = collectie('Autos', col)
    c_s = collectie('Stoep', col)
    # lantaarns op de blokhoeken; op één hoek per blok de straatnaambordjes
    for j in range(BLOKKEN):
        for i in range(BLOKKEN):
            x0, x1 = blok_bereik(j)
            y0, y1 = blok_bereik(i)
            for (x, y, d) in [(x0 + 0.6, y0 + 0.6, (-0.7, -0.7)), (x1 - 0.6, y1 - 0.6, (0.7, 0.7)),
                              (x1 - 0.6, y0 + 0.6, (0.7, -0.7)), (x0 + 0.6, y1 - 0.6, (-0.7, 0.7))]:
                namen = None
                if x == x0 + 0.6 and y == y1 - 0.6:
                    namen = [(STRAATNAMEN_X[j], False), (STRAATNAMEN_Y[i + 1], True)]
                lantaarn(c_l, x, y, d, namen)
                neem(x - 0.8, y - 0.8, x + 0.8, y + 0.8)
    # laanbomen langs de twee middelste lanen
    for k in (2, 3):
        as_ = weg_as(k)
        for j in range(BLOKKEN):
            a, e = blok_bereik(j)
            for t in (a + 8, a + 15, a + 22):
                for zij in (-1, 1):
                    x = as_ + zij * (WEG / 2 + 1.1)
                    boom(c_b, x, t, STOEP_H, rnd.uniform(0.75, 0.95), naam='Laanboom')
                    neem(x - 0.9, t - 0.9, x + 0.9, t + 0.9)
    # bushaltes
    c_h = collectie('Bushaltes', col)
    haltes_blender = []
    for seg, s in BUSHALTES:
        a, e = BUSROUTE[seg], BUSROUTE[(seg + 1) % len(BUSROUTE)]
        ax, az = weg_as(a[0]), weg_as(a[1])
        dx, dz = (e[0] > a[0]) - (e[0] < a[0]), (e[1] > a[1]) - (e[1] < a[1])
        rx, rz = -dz, dx
        px, pz = ax + dx * s + rx * (WEG / 2 + 0.85), az + dz * s + rz * (WEG / 2 + 0.85)
        x, y = px, -pz
        if dz == 0:
            bushalte(c_h, x, y, True, dx)         # kijkt naar de straat
        else:
            bushalte(c_h, x, y, False, dz)
        haltes_blender.append((ax + dx * s + rx * 3.7, -(az + dz * s + rz * 3.7)))
    # geparkeerde auto's (niet bij de bushaltes)
    for i in range(BLOKKEN + 1):
        as_ = weg_as(i)
        for j in range(BLOKKEN):
            a, e = blok_bereik(j)
            for zij in (-1, 1):
                for t in (a + 7.5, a + 13, a + 18.5):
                    for langs_x in (False, True):
                        if rnd.random() >= 0.22:
                            continue
                        x, y = (as_ + zij * 3.7, t) if not langs_x else (t, as_ + zij * 3.7)
                        x += rnd.uniform(-0.6, 0.6) if langs_x else 0
                        y += rnd.uniform(-0.6, 0.6) if not langs_x else 0
                        if any(math.hypot(x - hx, y - hy) < 9 for hx, hy in haltes_blender):
                            continue
                        auto(c_a, x, y, langs_x)
    # dingen op de stoeprand: prullenbakken, fietsenrekken, brievenbussen ...
    soorten = ['prullenbak', 'rek', 'prullenbak', 'bloembak', 'brandkraan', 'rek', 'parkeerbord', 'brievenbus']
    for j in range(BLOKKEN):
        for i in range(BLOKKEN):
            x0, x1 = blok_bereik(j)
            y0, y1 = blok_bereik(i)
            for kant in 'nzow':
                g = Gevel(kant, x0, y0, x1, y1)
                for u in rnd.sample([5.0, 11.5, 18.5, 25.0], 2):
                    stoeprand_ding(c_s, g, u, rnd.choice(soorten))


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


def render(cam, alleen=()):
    """Rendert de voorbeeldbeelden; met namen achter --render alleen die (bv. --render winkels)."""
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
    # een terras in een blok naast het park, schuin van op de overkant van de stoep
    kandidaten = [w for w in gebouwde_winkels if w[1] in ('cafe', 'resto') and w[5] >= 5.5
                  and max(abs(w[2].x), abs(w[2].y)) < 45]
    naam_, soort_, mid, uit, r, w_ = (kandidaten or gebouwde_winkels)[0]
    oog = mid + uit * 7.5 - r * 6.0
    oog.z = 1.75
    kijk = mid + r * 1.0
    kijk.z = 2.1
    for naam, pos, doel in [('winkels', tuple(oog), tuple(kijk)),('lucht', (150, -170, 110), (0, 0, 0)),
                            ('straat', (weg_as(2) + 1.5, blok_bereik(2)[0] - 22, 1.7),
                             (weg_as(2) - 2, blok_bereik(2)[1] + 10, 6))]:
        if alleen and naam not in alleen:
            continue
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
    bouw_straatmeubilair(collectie('Straatmeubilair', stad))
    gebouwen = collectie('Bouwblokken', stad)
    for j in range(BLOKKEN):
        for i in range(BLOKKEN):
            if (j, i) in (PARK, PLEIN, ZAKEN):
                continue
            afstand = max(abs(j - 2), abs(i - 2))
            hoogtes = (3, 6) if afstand == 1 else (2, 4)
            gewoon_blok(gebouwen, j, i, hoogtes, 0.55 if afstand == 1 else 0.22)
    park = bouw_park(stad)
    duiven, praat = bouw_plein(stad)
    praat += bouw_zakenwijk(stad)
    bouw_bos(stad)

    cam = zet_licht_en_camera()
    richt(cam, (150, -170, 110), (0, 0, 0))

    blend = os.path.join(HIER, 'ministad.blend')
    bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)

    for o in bpy.context.view_layer.objects:
        o.select_set(o.type == 'MESH')
    bpy.ops.export_scene.gltf(filepath=os.path.join(UIT, 'ministad.glb'), export_format='GLB',
                              use_selection=True, export_yup=True, export_apply=True,
                              export_lights=False, export_cameras=False, export_extras=False,
                              export_draco_mesh_compression_enable=True, export_draco_position_quantization=16,
                              export_draco_normal_quantization=8, export_draco_texcoord_quantization=12)

    # ---- gegevens voor het leven in de stad (three.js-assen: x = x, z = -y) ----
    vakken = [[b[0], -b[3], b[2], -b[1], b[4]] for b in botsers]
    data = {
        'versie': 2,
        'grens': HALF + 40,
        'start': {'x': weg_as(2) + WEG / 2 + LOOPLIJN, 'z': 6.0, 'richting': 0},
        'vakken': vakken,
        'straten': [weg_as(i) for i in range(BLOKKEN + 1)],
        'blokken': [list(blok_bereik(j)) for j in range(BLOKKEN)],
        'stoephoogte': STOEP_H,
        'looplijn': LOOPLIJN,
        'rijstrook': RIJSTROOK,
        'busroute': [list(p) for p in BUSROUTE],
        'bushaltes': [{'seg': s, 's': d} for s, d in BUSHALTES],
        'zitplaatsen': zitplaatsen,
        'katplekken': katplekken,
        'park': park,
        'duiven': duiven,
        'praatplekken': praat,
    }
    with open(os.path.join(UIT, 'botsing.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'))

    n_obj = sum(1 for o in bpy.data.objects if o.type == 'MESH')
    n_vl = sum(len(o.data.polygons) for o in bpy.data.objects if o.type == 'MESH')
    print(f'Ministad klaar: {n_obj} objecten, {n_vl} vlakken, {len(vakken)} botsvakken, '
          f'{len(zitplaatsen)} zitplaatsen, {len(katplekken)} katplekken')

    if doe_render:
        render(cam, argv[argv.index('--render') + 1:])
        bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)


if __name__ == '__main__':
    main()
