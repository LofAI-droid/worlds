"""Ministad — de bewoners: mensen, dieren en voertuigen, gebouwd met Blender.

Gebruik (vanuit de map ministad/):

    blender --background --python blender/bouw_figuren.py
    # of:  python3.11 blender/bouw_figuren.py   (met -- --render voor een voorbeeldbeeld)

Elk figuur is een lege 'wortel' met onderdelen die rond hun gewricht kunnen draaien
(benen rond de heup, knieën, armen rond de schouder, kop, staart, vleugels...).
De wandelpagina kloont ze, geeft ze andere kleuren en laat ze bewegen.

Het script maakt blender/figuren.blend en figuren.glb.
Alle figuren kijken in Blender naar +Y (in three.js naar -Z); +X is hun rechterkant.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from gereedschap import Bouwer, materiaal, tekst_matrix  # noqa: E402

HIER = os.path.dirname(os.path.abspath(__file__))
UIT = os.path.dirname(HIER)


def materialen():
    m = materiaal
    # mensen (de kleuren worden in de browser per persoon gevarieerd)
    m('p_huid', '#e0ac88', 0.7)
    m('p_shirt', '#3a78c2', 0.85)
    m('p_broek', '#2f3640', 0.85)
    m('p_haar', '#4a3222', 0.9)
    m('p_schoen', '#262626', 0.6)
    m('p_oog', '#1b1b1b', 0.4)
    m('p_pet', '#c0392b', 0.7)
    m('p_helm', '#f2f2f2', 0.4)
    m('p_rugzak', '#e0a823', 0.8)
    m('p_rok', '#e84393', 0.85)
    # dieren
    m('h_vacht', '#a8743f', 0.95)
    m('h_oor', '#6e4a2a', 0.95)
    m('h_donker', '#1e1a18', 0.5)
    m('h_halsband', '#c0392b', 0.6)
    m('k_vacht', '#d9883b', 0.95)
    m('k_oog', '#8bc34a', 0.3)
    m('d_veren', '#8d93a0', 0.9)
    m('d_kop', '#5e6b73', 0.6)
    m('d_snavel', '#3a3a3a', 0.6)
    m('d_poot', '#c76b6b', 0.7)
    # voertuigen
    m('v_lak', '#c0392b', 0.3, metaal=0.3)
    m('v_ruit', '#28343e', 0.08)
    m('v_zwart', '#1c1c1e', 0.6)
    m('v_band', '#1a1a1c', 0.85)
    m('v_velg', '#c4c8cc', 0.3, metaal=0.8)
    m('v_licht', '#fffbe8', 0.2, emissie='#fff6d6', sterkte=1.5)
    m('v_achter', '#c0221f', 0.3, emissie='#ff2a1f', sterkte=1.0)
    m('wit', '#f4f4f0', 0.6)
    m('taxi_lak', '#22252a', 0.3, metaal=0.3)
    m('taxi_bord', '#f5c518', 0.4, emissie='#f5c518', sterkte=0.4)
    m('bus_lak', '#2b6cb0', 0.35, metaal=0.2)
    m('bus_wit', '#eef2f5', 0.5)
    m('bus_deur', '#3b4650', 0.3)
    m('bus_tekst', '#ffa31a', 0.4, emissie='#ffa31a', sterkte=2.0)
    m('f_kader', '#2c5d8f', 0.4, metaal=0.3)
    m('bak', '#2f6b4f', 0.6)
    m('hout', '#8a6440', 0.8)
    m('s_lak', '#e9e2d0', 0.35, metaal=0.2)
    m('metaal', '#3a3d42', 0.5, metaal=0.6)
    m('vloer', '#9aa0a6', 0.9)


def wortel(naam, col, x):
    ob = bpy.data.objects.new(naam, None)
    ob.empty_display_size = 0.3
    col.objects.link(ob)
    ob.location = (x, 0, 0)
    return ob


def deel(naam, col, ouder, plaats, bouw):
    """Een onderdeel: geometrie rond het gewricht (0,0,0), op 'plaats' t.o.v. de ouder."""
    b = Bouwer(naam, col)
    bouw(b)
    ob = b.klaar('wereld')
    ob.parent = ouder
    ob.location = plaats
    return ob


def leeg(naam, col, ouder, plaats):
    ob = bpy.data.objects.new(naam, None)
    ob.empty_display_size = 0.05
    col.objects.link(ob)
    ob.parent = ouder
    ob.location = plaats
    return ob


# =====================================================================
#  Mens
# =====================================================================
def persoon(col, x):
    w = wortel('Persoon', col, x)

    def romp(b):
        b.doos(-0.17, -0.1, 0.0, 0.17, 0.1, 0.14, 'p_broek')
        b.doos(-0.19, -0.11, 0.12, 0.19, 0.11, 0.55, 'p_shirt')
    r = deel('Persoon_romp', col, w, (0, 0, 0.9), romp)

    deel('Persoon_rok', col, r, (0, 0, 0),
         lambda b: b.cilinder(0, 0, -0.36, 0.27, 0.5, 'p_rok', seg=10, r_top=0.195))

    deel('Persoon_rugzak', col, r, (0, -0.11, 0.33),
         lambda b: b.doos(-0.15, -0.15, -0.18, 0.15, 0.0, 0.17, 'p_rugzak'))

    def hoofd(b):
        b.cilinder(0, 0, 0, 0.05, 0.07, 'p_huid', seg=8)
        b.doos(-0.1, -0.11, 0.05, 0.1, 0.11, 0.29, 'p_huid')
        for s in (-1, 1):
            b.doos(s * 0.045 - 0.016, 0.105, 0.17, s * 0.045 + 0.016, 0.116, 0.2, 'p_oog')
        b.doos(-0.015, 0.11, 0.12, 0.015, 0.135, 0.16, 'p_huid')
    h = deel('Persoon_hoofd', col, r, (0, 0, 0.55), hoofd)

    def kort(b):
        b.doos(-0.106, -0.12, 0.24, 0.106, 0.1, 0.32, 'p_haar')
        b.doos(-0.106, -0.12, 0.1, 0.106, -0.08, 0.26, 'p_haar')
        for s in (-1, 1):
            b.doos(s * 0.1 - 0.008, -0.1, 0.18, s * 0.1 + 0.008, 0.03, 0.26, 'p_haar')
    deel('Persoon_haar_kort', col, h, (0, 0, 0), kort)

    def lang(b):
        b.doos(-0.108, -0.122, 0.24, 0.108, 0.1, 0.325, 'p_haar')
        b.doos(-0.11, -0.13, -0.1, 0.11, -0.07, 0.3, 'p_haar')
        for s in (-1, 1):
            b.doos(s * 0.104 - 0.01, -0.1, 0.04, s * 0.104 + 0.01, 0.06, 0.3, 'p_haar')
    deel('Persoon_haar_lang', col, h, (0, 0, 0), lang)

    def pet(b):
        b.doos(-0.112, -0.122, 0.25, 0.112, 0.112, 0.34, 'p_pet')
        b.doos(-0.09, 0.11, 0.25, 0.09, 0.23, 0.27, 'p_pet')
    deel('Persoon_pet', col, h, (0, 0, 0), pet)

    deel('Persoon_helm', col, h, (0, 0, 0),
         lambda b: b.bol(0, -0.005, 0.22, 0.155, 'p_helm', schaal=(0.95, 1.05, 0.8), sub=2))

    for kant, s in (('L', -1), ('R', 1)):
        def arm(b):
            b.doos(-0.055, -0.055, -0.3, 0.055, 0.055, 0.04, 'p_shirt')
            b.doos(-0.045, -0.045, -0.57, 0.045, 0.045, -0.3, 'p_huid')
        deel('Persoon_arm' + kant, col, r, (s * 0.25, 0, 0.5), arm)

        been = deel('Persoon_been' + kant, col, w, (s * 0.095, 0, 0.9),
                    lambda b: b.doos(-0.075, -0.08, -0.45, 0.075, 0.08, 0.0, 'p_broek'))

        def onder(b):
            b.doos(-0.07, -0.075, -0.39, 0.07, 0.075, 0.0, 'p_broek')
            b.doos(-0.075, -0.09, -0.45, 0.075, 0.15, -0.38, 'p_schoen')
        deel('Persoon_knie' + kant, col, been, (0, 0, -0.45), onder)
    return w


# =====================================================================
#  Dieren
# =====================================================================
def hond(col, x):
    w = wortel('Hond', col, x)

    def lijf(b):
        b.doos(-0.11, -0.3, -0.11, 0.11, 0.25, 0.1, 'h_vacht')
        b.doos(-0.115, 0.17, -0.1, 0.115, 0.22, 0.105, 'h_halsband')
    l_ = deel('Hond_lijf', col, w, (0, 0, 0.42), lijf)

    def kop(b):
        b.doos(-0.09, -0.05, -0.06, 0.09, 0.13, 0.11, 'h_vacht')
        b.doos(-0.05, 0.13, -0.05, 0.05, 0.25, 0.03, 'h_vacht')
        b.doos(-0.025, 0.245, -0.01, 0.025, 0.26, 0.035, 'h_donker')
        for s in (-1, 1):
            b.doos(s * 0.045 - 0.015, 0.125, 0.04, s * 0.045 + 0.015, 0.135, 0.07, 'h_donker')
            b.doos(s * 0.095 - 0.012, -0.03, -0.08, s * 0.095 + 0.012, 0.06, 0.1, 'h_oor')
    deel('Hond_kop', col, l_, (0, 0.25, 0.07), kop)
    deel('Hond_staart', col, l_, (0, -0.29, 0.07),
         lambda b: b.staaf((0, 0, 0), (0, -0.07, 0.2), 0.04, 'h_vacht'))
    for naam, (px, py) in {'lv': (-0.07, 0.17), 'rv': (0.07, 0.17), 'la': (-0.07, -0.22), 'ra': (0.07, -0.22)}.items():
        deel('Hond_poot_' + naam, col, l_, (px, py, -0.06),
             lambda b: b.doos(-0.035, -0.035, -0.36, 0.035, 0.035, 0.0, 'h_vacht'))
    leeg('Hond_lijn', col, l_, (0, 0.21, 0.1))           # hier hangt de leiband
    return w


def kat(col, x):
    w = wortel('Kat', col, x)
    l_ = deel('Kat_lijf', col, w, (0, 0, 0.2),
              lambda b: b.doos(-0.07, -0.17, -0.06, 0.07, 0.15, 0.07, 'k_vacht'))

    def kop(b):
        b.doos(-0.065, -0.03, -0.05, 0.065, 0.08, 0.07, 'k_vacht')
        b.doos(-0.02, 0.08, -0.03, 0.02, 0.095, 0.0, 'p_oog')
        for s in (-1, 1):
            b.staaf((s * 0.045, 0.01, 0.06), (s * 0.05, 0.015, 0.13), 0.035, 'k_vacht', diepte=0.02)
            b.doos(s * 0.03 - 0.012, 0.078, 0.015, s * 0.03 + 0.012, 0.086, 0.035, 'k_oog')
    deel('Kat_kop', col, l_, (0, 0.15, 0.06), kop)
    deel('Kat_staart', col, l_, (0, -0.16, 0.04),
         lambda b: b.staaf((0, 0, 0), (0, -0.06, 0.28), 0.03, 'k_vacht'))
    for naam, (px, py) in {'lv': (-0.04, 0.11), 'rv': (0.04, 0.11), 'la': (-0.04, -0.13), 'ra': (0.04, -0.13)}.items():
        deel('Kat_poot_' + naam, col, l_, (px, py, -0.05),
             lambda b: b.doos(-0.02, -0.02, -0.15, 0.02, 0.02, 0.0, 'k_vacht'))
    return w


def duif(col, x):
    w = wortel('Duif', col, x)

    def lijf(b):
        b.bol(0, 0, 0, 0.075, 'd_veren', schaal=(0.8, 1.35, 0.8), sub=1)
        b.doos(-0.04, -0.2, -0.01, 0.04, -0.08, 0.02, 'd_veren')
        for s in (-1, 1):
            b.staaf((s * 0.025, 0, -0.05), (s * 0.025, 0.01, -0.11), 0.012, 'd_poot')
    l_ = deel('Duif_lijf', col, w, (0, 0, 0.11), lijf)

    def kop(b):
        b.bol(0, 0, 0, 0.04, 'd_kop', sub=1)
        b.doos(-0.008, 0.03, -0.008, 0.008, 0.06, 0.004, 'd_snavel')
        for s in (-1, 1):
            b.doos(s * 0.03 - 0.006, 0.015, 0.005, s * 0.03 + 0.006, 0.025, 0.017, 'p_oog')
    deel('Duif_kop', col, l_, (0, 0.085, 0.06), kop)
    for kant, s in (('L', -1), ('R', 1)):
        deel('Duif_vleugel' + kant, col, l_, (s * 0.05, 0, 0.03),
             lambda b, s=s: b.doos(min(0, s * 0.2), -0.07, -0.006, max(0, s * 0.2), 0.06, 0.006, 'd_veren'))
    return w


# =====================================================================
#  Voertuigen
# =====================================================================
def wiel(b, x, y, z, r, breed, band='v_band', velg='v_velg'):
    m = Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.pi / 2, 4, 'Y') @ Matrix.Translation((0, 0, -breed / 2))
    b.cilinder(0, 0, 0, r, breed, band, seg=14, matrix=m)
    m2 = Matrix.Translation((x, y, z)) @ Matrix.Rotation(math.pi / 2, 4, 'Y') @ Matrix.Translation((0, 0, -breed / 2 - 0.01))
    b.cilinder(0, 0, 0, r * 0.55, breed + 0.02, velg, seg=10, matrix=m2)


def auto(col, x, naam='Auto', lak='v_lak', taxi=False):
    w = wortel(naam, col, x)

    def romp(b):
        b.doos(-0.9, -2.1, 0.3, 0.9, 2.1, 0.88, lak)
        b.doos(-0.88, -2.0, 0.88, 0.88, 1.2, 0.95, lak)
        b.doos(-0.82, -1.25, 0.95, 0.82, 0.72, 1.42, 'v_ruit', top=lak)
        b.doos(-0.84, -1.2, 1.42, 0.84, 0.68, 1.47, lak)
        for s in (-1, 1):
            b.doos(s * 0.83 - 0.02, -0.3, 0.95, s * 0.83 + 0.02, -0.2, 1.42, lak)       # middenstijl
            b.doos(s * 0.9, 0.55, 0.9, s * 1.02, 0.65, 1.0, lak)                        # spiegel
            b.doos(s * 0.65 - 0.15, 2.1, 0.62, s * 0.65 + 0.15, 2.13, 0.78, 'v_licht')
            b.doos(s * 0.68 - 0.12, -2.13, 0.68, s * 0.68 + 0.12, -2.1, 0.82, 'v_achter')
        for y0, y1 in ((2.08, 2.18), (-2.18, -2.08)):
            b.doos(-0.92, y0, 0.3, 0.92, y1, 0.48, 'v_zwart')                           # bumpers
        b.doos(-0.25, 2.18, 0.34, 0.25, 2.2, 0.44, 'wit')                                # nummerplaten
        b.doos(-0.25, -2.2, 0.34, 0.25, -2.18, 0.44, 'wit')
        for sx in (-0.8, 0.8):
            for sy in (-1.35, 1.35):
                wiel(b, sx, sy, 0.34, 0.34, 0.24)
        if taxi:
            b.doos(-0.32, -0.3, 1.47, 0.32, 0.2, 1.68, 'taxi_bord')
            b.tekst('TAXI', tekst_matrix(0, 0.205, 1.575, 0, 1), 0.15, 'v_zwart')
            b.tekst('TAXI', tekst_matrix(0, -0.305, 1.575, 0, -1), 0.15, 'v_zwart')
    deel(naam + '_romp', col, w, (0, 0, 0), romp)
    return w


def bus(col, x):
    w = wortel('Bus', col, x)

    def romp(b):
        b.doos(-1.25, -5.5, 0.35, 1.25, 5.5, 1.2, 'bus_lak')
        b.doos(-1.24, -5.45, 1.2, 1.24, 5.45, 2.6, 'v_ruit')
        b.doos(-1.25, -5.5, 2.6, 1.25, 5.5, 3.05, 'bus_wit')
        b.doos(-1.25, -5.5, 1.2, 1.25, -5.0, 2.6, 'bus_wit')
        for t in range(8):
            y = -4.4 + t * 1.35
            for s in (-1, 1):
                b.doos(s * 1.25 - 0.02, y, 1.2, s * 1.25 + 0.02, y + 0.12, 2.6, 'bus_wit')
        # deuren rechts (+x)
        for y0 in (3.5, -0.7):
            b.doos(1.25, y0, 0.3, 1.28, y0 + 1.2, 2.5, 'bus_deur')
            b.doos(1.27, y0 + 0.58, 0.3, 1.29, y0 + 0.62, 2.5, 'v_zwart')
        # bestemming voor en achter
        b.doos(-0.95, 5.45, 2.62, 0.95, 5.53, 2.98, 'v_zwart')
        b.tekst('12  Centrum', tekst_matrix(0, 5.535, 2.8, 0, 1), 0.22, 'bus_tekst')
        b.doos(-0.4, -5.53, 2.62, 0.4, -5.45, 2.98, 'v_zwart')
        b.tekst('12', tekst_matrix(0, -5.535, 2.8, 0, -1), 0.25, 'bus_tekst')
        for s in (-1, 1):
            b.doos(s * 0.95 - 0.18, 5.5, 0.6, s * 0.95 + 0.18, 5.53, 0.78, 'v_licht')
            b.doos(s * 1.0 - 0.12, -5.53, 0.6, s * 1.0 + 0.12, -5.5, 0.9, 'v_achter')
            b.doos(s * 1.28 - 0.04, 5.3, 2.0, s * 1.28 + 0.06, 5.45, 2.4, 'v_zwart')
        b.doos(-1.27, 5.45, 0.3, 1.27, 5.6, 0.5, 'v_zwart')
        b.doos(-1.27, -5.6, 0.3, 1.27, -5.45, 0.5, 'v_zwart')
        for sx in (-1.1, 1.1):
            for sy in (-3.6, 3.4):
                wiel(b, sx, sy, 0.5, 0.5, 0.32)
    deel('Bus_romp', col, w, (0, 0, 0), romp)
    return w


def fietswielen(b, y_achter, y_voor, r_achter=0.34, r_voor=0.34):
    b.torus((0, y_achter, r_achter), r_achter - 0.03, 0.025, 'v_band', as_='X', seg=16, seg_r=4)
    b.torus((0, y_voor, r_voor), r_voor - 0.03, 0.025, 'v_band', as_='X', seg=16, seg_r=4)
    for y, r in ((y_achter, r_achter), (y_voor, r_voor)):
        for k in range(3):
            a = k * math.pi / 3
            b.staaf((0, y - math.cos(a) * (r - 0.04), r - math.sin(a) * (r - 0.04)),
                    (0, y + math.cos(a) * (r - 0.04), r + math.sin(a) * (r - 0.04)), 0.012, 'v_velg')


def fiets(col, x):
    w = wortel('Fiets', col, x)

    def kader(b):
        fietswielen(b, -0.52, 0.52)
        k = 'f_kader'
        b.staaf((0, -0.52, 0.34), (0, -0.05, 0.3), 0.035, k)
        b.staaf((0, -0.05, 0.3), (0, -0.2, 0.86), 0.035, k)
        b.staaf((0, -0.2, 0.82), (0, 0.38, 0.82), 0.035, k)
        b.staaf((0, -0.05, 0.3), (0, 0.38, 0.82), 0.04, k)
        b.staaf((0, -0.52, 0.34), (0, -0.2, 0.82), 0.025, k)
        b.staaf((0, 0.38, 0.82), (0, 0.52, 0.34), 0.03, k)
        b.staaf((0, 0.38, 0.82), (0, 0.42, 1.02), 0.03, 'metaal')
        b.staaf((-0.27, 0.42, 1.02), (0.27, 0.42, 1.02), 0.03, 'metaal')
        b.doos(-0.07, -0.33, 0.88, 0.07, -0.08, 0.95, 'v_zwart')                         # zadel
        b.doos(-0.06, -0.62, 0.62, 0.06, -0.3, 0.65, 'metaal')                           # bagagedrager
        b.doos(-0.05, 0.54, 0.62, 0.05, 0.57, 0.7, 'v_licht')
        b.cilinder(0, -0.05, 0.3, 0.1, 0.02, 'metaal', seg=10,
                   matrix=Matrix.Translation((0.03, -0.05, 0.3)) @ Matrix.Rotation(math.pi / 2, 4, 'Y'))
    deel('Fiets_kader', col, w, (0, 0, 0), kader)
    return w


def bakfiets(col, x):
    w = wortel('Bakfiets', col, x)

    def kader(b):
        fietswielen(b, -0.55, 1.35, 0.34, 0.25)
        k = 'f_kader'
        b.staaf((0, -0.55, 0.34), (0, -0.05, 0.3), 0.035, k)
        b.staaf((0, -0.05, 0.3), (0, -0.27, 0.88), 0.035, k)
        b.staaf((0, -0.27, 0.82), (0, 0.22, 0.86), 0.035, k)
        b.staaf((0, -0.05, 0.3), (0, 0.32, 0.3), 0.04, k)
        b.staaf((0, 0.22, 0.86), (0, 0.3, 0.32), 0.04, k)
        b.staaf((0, 1.12, 0.3), (0, 1.35, 0.25), 0.04, k)
        b.staaf((0, 0.22, 0.86), (0, 0.18, 1.05), 0.03, 'metaal')
        b.staaf((-0.3, 0.18, 1.05), (0.3, 0.18, 1.05), 0.03, 'metaal')
        b.doos(-0.07, -0.4, 0.9, 0.07, -0.15, 0.97, 'v_zwart')
        # de bak
        b.doos(-0.38, 0.32, 0.28, 0.38, 1.15, 0.32, 'hout')
        b.doos(-0.38, 0.32, 0.32, 0.38, 0.35, 0.8, 'bak')
        b.doos(-0.38, 1.12, 0.32, 0.38, 1.15, 0.7, 'bak')
        for s in (-1, 1):
            b.doos(s * 0.38 - 0.015, 0.35, 0.32, s * 0.38 + 0.015, 1.12, 0.75, 'bak')
        b.doos(-0.35, 0.36, 0.32, 0.35, 0.58, 0.5, 'hout')                              # bankje
    deel('Bakfiets_kader', col, w, (0, 0, 0), kader)
    return w


def scooter(col, x):
    w = wortel('Scooter', col, x)

    def romp(b):
        for y in (-0.62, 0.62):
            m = Matrix.Translation((0, y, 0.22)) @ Matrix.Rotation(math.pi / 2, 4, 'Y') @ Matrix.Translation((0, 0, -0.05))
            b.cilinder(0, 0, 0, 0.22, 0.1, 'v_band', seg=14, matrix=m)
        b.doos(-0.17, -0.25, 0.2, 0.17, 0.38, 0.28, 's_lak')
        b.doos(-0.2, -0.78, 0.28, 0.2, -0.15, 0.68, 's_lak')
        b.doos(-0.16, -0.72, 0.68, 0.16, -0.15, 0.78, 'v_zwart')
        b.doos(-0.2, 0.36, 0.22, 0.2, 0.48, 0.95, 's_lak')
        b.staaf((0, 0.45, 0.9), (0, 0.42, 1.1), 0.07, 's_lak')
        b.staaf((-0.33, 0.42, 1.08), (0.33, 0.42, 1.08), 0.035, 'v_zwart')
        b.doos(-0.08, 0.48, 0.74, 0.08, 0.5, 0.86, 'v_licht')
        b.doos(-0.06, -0.8, 0.5, 0.06, -0.78, 0.58, 'v_achter')
        b.staaf((0, 0.45, 0.3), (0, 0.62, 0.22), 0.05, 'metaal')
        b.doos(-0.18, -0.8, 0.5, 0.18, -0.5, 0.52, 'metaal')
    deel('Scooter_romp', col, w, (0, 0, 0), romp)
    return w


# =====================================================================
def zet_licht_en_camera():
    sc = bpy.context.scene
    zon = bpy.data.lights.new('Zon', 'SUN')
    zon.energy = 3.5
    o = bpy.data.objects.new('Zon', zon)
    o.rotation_euler = (math.radians(45), math.radians(15), math.radians(30))
    sc.collection.objects.link(o)
    wrl = bpy.data.worlds.new('Lucht')
    sc.world = wrl
    wrl.use_nodes = True
    wrl.node_tree.nodes['Background'].inputs['Color'].default_value = (0.65, 0.75, 0.88, 1)
    wrl.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.8
    cam = bpy.data.cameras.new('Camera')
    cam.lens = 45
    co = bpy.data.objects.new('Camera', cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return co


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    materialen()
    col = bpy.data.collections.new('Figuren')
    bpy.context.scene.collection.children.link(col)

    # op een rij, zodat je ze in Blender naast elkaar ziet
    persoon(col, 0)
    hond(col, 1.2)
    kat(col, 2.0)
    duif(col, 2.6)
    fiets(col, 3.6)
    bakfiets(col, 5.0)
    scooter(col, 6.4)
    auto(col, 8.4)
    auto(col, 10.8, 'Taxi', 'taxi_lak', taxi=True)
    bus(col, 14.2)

    vloer = Bouwer('Vloer', bpy.context.scene.collection)
    vloer.doos(-3, -8, -0.05, 18, 8, 0, 'vloer')
    vloer_ob = vloer.klaar('wereld')

    cam = zet_licht_en_camera()
    cam.data.lens = 32
    cam.location = (6.5, 15.5, 4.2)
    d = Vector((6.6, 0, 0.6)) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HIER, 'figuren.blend'), compress=True)

    for o in bpy.context.view_layer.objects:
        o.select_set(o.users_collection[0] == col)
    bpy.ops.export_scene.gltf(filepath=os.path.join(UIT, 'figuren.glb'), export_format='GLB',
                              use_selection=True, export_yup=True, export_apply=True,
                              export_lights=False, export_cameras=False, export_extras=False)
    print('Figuren klaar:', ', '.join(o.name for o in col.objects if o.parent is None))

    if '--render' in argv:
        # in de browser draagt iedereen maar één ding op het hoofd; voor de foto ook
        for naam in ('Persoon_helm', 'Persoon_haar_lang', 'Persoon_rok'):
            bpy.data.objects[naam].hide_render = True
        sc = bpy.context.scene
        sc.render.engine = 'CYCLES'
        sc.cycles.device = 'CPU'
        sc.cycles.samples = 32
        sc.render.resolution_x, sc.render.resolution_y = 1280, 560
        sc.render.filepath = os.path.join(HIER, 'voorbeeld-figuren.png')
        bpy.ops.render.render(write_still=True)
        print('Gerenderd:', sc.render.filepath)
    del vloer_ob


if __name__ == '__main__':
    main()
