// Ministad — figuren uit figuren.glb klonen, inkleuren en laten bewegen.
// Alle figuren kijken naar -Z; draaihoek h kijkt naar (-sin h, -cos h).
import * as THREE from 'three';

export const KLEUREN = {
  huid: ['#f1c7a5', '#e0ac88', '#d49a74', '#c68863', '#a0663f', '#7a4a2c', '#5c3a22'],
  shirt: ['#3a78c2', '#c0392b', '#27ae60', '#f1c40f', '#8e44ad', '#e67e22', '#ecf0f1', '#2c3e50', '#d35400',
    '#16a085', '#e84393', '#95a5a6', '#6ab04c', '#f8a5c2', '#273c75'],
  broek: ['#2f3640', '#34495e', '#3d5a80', '#5d4037', '#7f8c8d', '#1e272e', '#b8a07e', '#40407a'],
  haar: ['#2b1d14', '#4a3222', '#7a5230', '#c9a35b', '#e8d18c', '#8a8a8a', '#b5442c', '#111111', '#d9d9d9'],
  schoen: ['#262626', '#5d4037', '#ecf0f1', '#c0392b', '#2c3e50'],
  helm: ['#f2f2f2', '#2c3e50', '#e74c3c', '#f1c40f', '#27ae60'],
  rugzak: ['#e0a823', '#2e86de', '#c0392b', '#27ae60', '#2f3640'],
  hond: [['#a8743f', '#6e4a2a'], ['#1f1f1f', '#111111'], ['#e8dcc0', '#c9b48f'], ['#d9a441', '#b07a2a'],
    ['#7a7a7a', '#4a4a4a'], ['#ffffff', '#3a2a20']],
  kat: ['#d9883b', '#2a2a2a', '#9b9b9b', '#f0e6d8', '#7a5230'],
  auto: ['#c0392b', '#2e5d9a', '#e9e9e6', '#26272b', '#e5b62c', '#3b7a57', '#8e9aa6', '#6c3483', '#d35400'],
  fiets: ['#2c5d8f', '#b23b35', '#2f2f33', '#27ae60', '#e9e9e6', '#f1c40f', '#8e44ad'],
  bak: ['#2f6b4f', '#2c5d8f', '#c0392b', '#3b3b3b'],
  scooter: ['#e9e2d0', '#c0392b', '#7fb3d5', '#2f2f33', '#a3c586']
};

export const kies = (lijst, rnd = Math.random) => lijst[Math.floor(rnd() * lijst.length)];

const PERSOON = {
  romp: 'Persoon_romp', hoofd: 'Persoon_hoofd', armL: 'Persoon_armL', armR: 'Persoon_armR',
  beenL: 'Persoon_beenL', beenR: 'Persoon_beenR', knieL: 'Persoon_knieL', knieR: 'Persoon_knieR',
  haarKort: 'Persoon_haar_kort', haarLang: 'Persoon_haar_lang', pet: 'Persoon_pet', helm: 'Persoon_helm',
  rugzak: 'Persoon_rugzak'
};
const HOND = {
  lijf: 'Hond_lijf', kop: 'Hond_kop', staart: 'Hond_staart', lv: 'Hond_poot_lv', rv: 'Hond_poot_rv',
  la: 'Hond_poot_la', ra: 'Hond_poot_ra', lijn: 'Hond_lijn'
};
const KAT = {
  lijf: 'Kat_lijf', kop: 'Kat_kop', staart: 'Kat_staart', lv: 'Kat_poot_lv', rv: 'Kat_poot_rv',
  la: 'Kat_poot_la', ra: 'Kat_poot_ra'
};
const DUIF = { lijf: 'Duif_lijf', kop: 'Duif_kop', vL: 'Duif_vleugelL', vR: 'Duif_vleugelR' };

// Waar de berijder zit, in het assenstelsel van het voertuig (wortel van de persoon).
export const ZADEL = {
  Fiets: { pos: [0, 0.07, 0.24], soort: 'trappen' },
  Bakfiets: { pos: [0, 0.09, 0.31], soort: 'trappen' },
  Scooter: { pos: [0, -0.1, 0.47], soort: 'zitten' }
};

export class Figuren {
  constructor(gltfScene) {
    this.proto = {};
    for (const naam of ['Persoon', 'Hond', 'Kat', 'Duif', 'Fiets', 'Bakfiets', 'Scooter', 'Auto', 'Taxi', 'Bus']) {
      const o = gltfScene.getObjectByName(naam);
      if (!o) throw new Error('figuur ontbreekt: ' + naam);
      o.removeFromParent();
      o.position.set(0, 0, 0);
      o.rotation.set(0, 0, 0);
      o.traverse((m) => {
        if (m.isMesh) {
          m.castShadow = !/oog|snavel/.test(m.material.name);
          m.receiveShadow = false;
        }
      });
      this.proto[naam] = o;
    }
    this.cache = new Map();
  }

  materiaal(basis, kleur) {
    const sleutel = basis.name + kleur;
    let m = this.cache.get(sleutel);
    if (!m) {
      m = basis.clone();
      m.color.set(kleur);
      this.cache.set(sleutel, m);
    }
    return m;
  }

  kloon(naam, kleuren = {}) {
    const o = this.proto[naam].clone(true);
    o.traverse((m) => {
      if (m.isMesh && kleuren[m.material.name]) m.material = this.materiaal(m.material, kleuren[m.material.name]);
    });
    return o;
  }

  delen(o, namen) {
    const d = {};
    for (const [k, n] of Object.entries(namen)) d[k] = o.getObjectByName(n);
    return d;
  }

  /** Een mens. opties: { kleuren, haar: 'kort'|'lang'|'geen', pet, helm, rugzak, schaal } */
  persoon(opties = {}, rnd = Math.random) {
    const k = opties.kleuren || {};
    const kleuren = {
      p_huid: k.huid || kies(KLEUREN.huid, rnd),
      p_shirt: k.shirt || kies(KLEUREN.shirt, rnd),
      p_broek: k.broek || kies(KLEUREN.broek, rnd),
      p_haar: k.haar || kies(KLEUREN.haar, rnd),
      p_schoen: k.schoen || kies(KLEUREN.schoen, rnd),
      p_helm: k.helm || kies(KLEUREN.helm, rnd),
      p_rugzak: k.rugzak || kies(KLEUREN.rugzak, rnd),
      p_pet: k.pet || kies(KLEUREN.shirt, rnd)
    };
    const obj = this.kloon('Persoon', kleuren);
    const d = this.delen(obj, PERSOON);
    const haar = opties.haar || (rnd() < 0.45 ? 'lang' : rnd() < 0.9 ? 'kort' : 'geen');
    d.haarKort.visible = haar === 'kort' && !opties.helm;
    d.haarLang.visible = haar === 'lang' && !opties.helm;
    d.pet.visible = !!opties.pet && !opties.helm;
    d.helm.visible = !!opties.helm;
    d.rugzak.visible = opties.rugzak ?? rnd() < 0.15;
    const schaal = opties.schaal || 1;
    obj.scale.setScalar(schaal);
    return { obj, d, schaal, fase: rnd() * 6.28, kijk: 0 };
  }

  hond(rnd = Math.random) {
    const [vacht, oor] = kies(KLEUREN.hond, rnd);
    const obj = this.kloon('Hond', { h_vacht: vacht, h_oor: oor });
    const s = 0.75 + rnd() * 0.5;
    obj.scale.setScalar(s);
    return { obj, d: this.delen(obj, HOND), schaal: s, fase: rnd() * 6.28 };
  }

  kat(rnd = Math.random) {
    const obj = this.kloon('Kat', { k_vacht: kies(KLEUREN.kat, rnd) });
    return { obj, d: this.delen(obj, KAT), fase: rnd() * 6.28 };
  }

  duif() {
    const obj = this.kloon('Duif');
    return { obj, d: this.delen(obj, DUIF), fase: Math.random() * 6.28 };
  }

  voertuig(type, rnd = Math.random) {
    const kleuren = {};
    if (type === 'Auto') kleuren.v_lak = kies(KLEUREN.auto, rnd);
    if (type === 'Fiets' || type === 'Bakfiets') kleuren.f_kader = kies(KLEUREN.fiets, rnd);
    if (type === 'Bakfiets') kleuren.bak = kies(KLEUREN.bak, rnd);
    if (type === 'Scooter') kleuren.s_lak = kies(KLEUREN.scooter, rnd);
    return this.kloon(type, kleuren);
  }
}

// ---------- houdingen ----------
const lerp = (a, b, t) => a + (b - a) * t;

/** Stappen of lopen. sterkte 0..1 (0 = stilstaan), rennen = joggen. */
export function poseLopen(p, sterkte, rennen = false) {
  const { d } = p;
  const f = p.fase;
  const amp = (rennen ? 0.85 : 0.5) * sterkte;
  const zwaai = Math.sin(f) * amp;
  d.beenL.rotation.x = zwaai;
  d.beenR.rotation.x = -zwaai;
  const buig = rennen ? 1.2 : 0.55;
  d.knieL.rotation.x = -Math.max(0, Math.sin(f + 1.6)) * buig * sterkte - 0.05;
  d.knieR.rotation.x = -Math.max(0, Math.sin(f + 1.6 + Math.PI)) * buig * sterkte - 0.05;
  d.armL.rotation.x = -zwaai * (rennen ? 1.0 : 0.8);
  d.armR.rotation.x = zwaai * (rennen ? 1.0 : 0.8);
  d.armL.rotation.z = -0.06;
  d.armR.rotation.z = 0.06;
  d.romp.rotation.x = rennen ? -0.18 * sterkte : -0.03 * sterkte;
  d.romp.rotation.y = Math.sin(f) * 0.08 * sterkte;
  d.romp.position.y = 0.9 + Math.abs(Math.cos(f)) * (rennen ? 0.05 : 0.025) * sterkte - 0.02 * sterkte;
  d.hoofd.rotation.y = lerp(d.hoofd.rotation.y, p.kijk || 0, 0.1);
  d.hoofd.rotation.x = 0;
}

/** Stilstaan met een beetje ademen; gebaren = 0..1 voor praten. */
export function poseStaan(p, t, gebaren = 0) {
  const { d } = p;
  d.beenL.rotation.x = 0; d.beenR.rotation.x = 0;
  d.knieL.rotation.x = 0; d.knieR.rotation.x = 0;
  d.romp.rotation.set(0, 0, 0);
  d.romp.position.y = 0.9 + Math.sin(t * 1.7 + p.fase) * 0.006;
  const g = gebaren * Math.max(0, Math.sin(t * 1.3 + p.fase));
  d.armR.rotation.x = 0.1 + g * (0.9 + Math.sin(t * 6 + p.fase) * 0.25);
  d.armR.rotation.z = 0.08 + g * 0.2;
  d.armL.rotation.x = 0.05 + gebaren * Math.max(0, Math.sin(t * 0.9 + p.fase + 2)) * 0.6;
  d.armL.rotation.z = -0.08;
  d.hoofd.rotation.y = lerp(d.hoofd.rotation.y, p.kijk || 0, 0.06);
  d.hoofd.rotation.x = gebaren ? Math.sin(t * 2.1 + p.fase) * 0.06 : 0;
}

/** Zitten op een stoel of bank; zithoogte wordt door de beller gezet. */
export function poseZitten(p, t) {
  const { d } = p;
  d.beenL.rotation.x = Math.PI / 2; d.beenR.rotation.x = Math.PI / 2;
  d.knieL.rotation.x = -Math.PI / 2; d.knieR.rotation.x = -Math.PI / 2;
  d.beenL.rotation.z = -0.05; d.beenR.rotation.z = 0.05;
  d.romp.rotation.set(0.04, 0, 0);
  d.romp.position.y = 0.9;
  const drink = Math.max(0, Math.sin(t * 0.35 + p.fase) - 0.85) * 6;          // af en toe iets drinken
  d.armR.rotation.x = 0.5 + drink * 1.3;
  d.armL.rotation.x = 0.45;
  d.armR.rotation.z = 0.12; d.armL.rotation.z = -0.12;
  d.hoofd.rotation.y = lerp(d.hoofd.rotation.y, (p.kijk || 0) + Math.sin(t * 0.25 + p.fase) * 0.5, 0.05);
  d.hoofd.rotation.x = -drink * 0.25;
}

/** Fietsen (trappen) of op een scooter zitten. */
export function poseRijden(p, soort) {
  const { d } = p;
  d.romp.position.y = 0.9;
  if (soort === 'trappen') {
    const f = p.fase;
    d.romp.rotation.set(-0.32, 0, 0);
    d.beenL.rotation.x = 1.0 + Math.sin(f) * 0.38;
    d.beenR.rotation.x = 1.0 + Math.sin(f + Math.PI) * 0.38;
    d.knieL.rotation.x = -1.2 + Math.cos(f) * 0.45;
    d.knieR.rotation.x = -1.2 + Math.cos(f + Math.PI) * 0.45;
    d.armL.rotation.set(1.05, 0, -0.18);
    d.armR.rotation.set(1.05, 0, 0.18);
  } else {
    d.romp.rotation.set(-0.08, 0, 0);
    d.beenL.rotation.x = 1.35; d.beenR.rotation.x = 1.35;
    d.knieL.rotation.x = -1.1; d.knieR.rotation.x = -1.1;
    d.beenL.rotation.z = -0.12; d.beenR.rotation.z = 0.12;
    d.armL.rotation.set(1.05, 0, -0.25);
    d.armR.rotation.set(1.05, 0, 0.25);
  }
  d.hoofd.rotation.set(soort === 'trappen' ? 0.25 : 0.05, 0, 0);
}

export function poseHond(h, sterkte, t, snuffel = 0) {
  const { d } = h;
  const z = Math.sin(h.fase) * 0.6 * sterkte;
  d.lv.rotation.x = z; d.ra.rotation.x = z;
  d.rv.rotation.x = -z; d.la.rotation.x = -z;
  d.staart.rotation.y = Math.sin(t * (sterkte > 0.1 ? 14 : 6) + h.fase) * 0.6;
  d.staart.rotation.x = 0.2;
  d.kop.rotation.x = snuffel * 0.6 + Math.sin(h.fase * 2) * 0.05 * sterkte;
  d.lijf.position.y = 0.42 + Math.abs(Math.sin(h.fase)) * 0.025 * sterkte;
}

export function poseKat(k, t, kijk = 0, onrustig = 0) {
  const { d } = k;
  d.lijf.rotation.x = 0.55;
  d.lijf.position.y = 0.17;
  d.lv.rotation.x = -0.55; d.rv.rotation.x = -0.55;
  d.la.rotation.x = -0.55 - 1.0; d.ra.rotation.x = -0.55 - 1.0;
  d.kop.rotation.x = -0.55;
  d.kop.rotation.y = lerp(d.kop.rotation.y, kijk, 0.08);
  d.staart.rotation.x = 1.35;
  d.staart.rotation.y = Math.sin(t * (1.2 + onrustig * 5) + k.fase) * (0.3 + onrustig * 0.4);
}

export function poseDuif(du, vliegen, t) {
  const { d } = du;
  if (vliegen) {
    const s = Math.sin(t * 24 + du.fase) * 0.9;
    d.vL.rotation.z = s; d.vR.rotation.z = -s;
    d.kop.rotation.x = 0;
  } else {
    d.vL.rotation.z = 1.35; d.vR.rotation.z = -1.35;
    const pik = Math.max(0, Math.sin(t * 3 + du.fase * 3)) ** 4;
    d.kop.rotation.x = pik * 1.1;
    d.kop.position.z = -0.085 + Math.sin(t * 9 + du.fase) * 0.008;
  }
}
