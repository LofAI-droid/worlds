// Rave against the machine — de menigte. Kloont `danser_xbot` uit figuren.glb voor elke
// plaats in botsing.json → `dansers`, met een AnimationMixer per figuur die luistert naar `ritme`.
import * as THREE from 'three';
import { clone as kloonSkelet } from 'three/addons/utils/SkeletonUtils.js';
import { randLicht } from './licht.js';

const CLIPS = ['house_1', 'house_2', 'house_3', 'backflip', 'staan', 'wiegen'];
const HOUSE = ['house_1', 'house_2', 'house_3'];
const CLIP_BPM = 125;              // aangenomen tempo van de Mixamo-dansjes (schaal ten opzichte hiervan)
const GLOW_KLEUREN = ['#22e6ff', '#ff2fd0', '#9dff2a', '#ff8a1a', '#b44dff'];
const BOTTEN = { hand: /RightHand$/, nek: /Neck$/, hoofd: /Head$/ };
const ACC = { glowstick: 'hand', halsband: 'nek', koptelefoon: 'hoofd', masker: 'hoofd' };

const klem = (v, a, b) => Math.max(a, Math.min(b, v));

/** Wat uit figuren.glb komt: het prototype, de clips en de accessoires. */
export class FigurenBron {
  constructor(gltf) {
    const scene = gltf.scene;
    scene.updateMatrixWorld(true);
    const node = scene.getObjectByName('danser_xbot');
    if (!node) throw new Error('figuren.glb: danser_xbot ontbreekt');
    let wortel = node;
    while (wortel.parent && wortel.parent !== scene) wortel = wortel.parent;
    // als het skelet ergens anders hangt dan de mesh: samen in één groep
    const extra = new Set();
    wortel.traverse((o) => {
      if (!o.isSkinnedMesh) return;
      let b = o.skeleton.bones[0];
      while (b.parent && b.parent !== scene) b = b.parent;
      if (b !== wortel) extra.add(b);
    });
    let proto = wortel;
    if (extra.size) {
      proto = new THREE.Group();
      proto.add(wortel, ...extra);
    }
    // accessoires apart houden
    this.acc = {};
    scene.traverse((o) => {
      const m = /^acc_([a-z]+)/.exec(o.name || '');
      if (m && ACC[m[1]] && !this.acc[m[1]]) this.acc[m[1]] = o;
    });
    for (const a of Object.values(this.acc)) {
      a.userData.wereld = a.matrixWorld.clone();
    }
    for (const a of Object.values(this.acc)) a.removeFromParent();
    proto.removeFromParent();
    proto.updateMatrixWorld(true);

    this.botNamen = {};
    proto.traverse((o) => {
      if (!o.isBone) return;
      for (const [k, re] of Object.entries(BOTTEN)) if (!this.botNamen[k] && re.test(o.name)) this.botNamen[k] = o.name;
    });
    // waar elk accessoire op zijn bot komt (rustpose)
    this.accLokaal = {};
    for (const [soort, a] of Object.entries(this.acc)) {
      const bot = proto.getObjectByName(this.botNamen[ACC[soort]] || '');
      if (!bot) continue;
      const botW = bot.matrixWorld;
      let accW;
      const p = new THREE.Vector3().setFromMatrixPosition(a.userData.wereld);
      if (a.userData.offset && Array.isArray(a.userData.offset)) {
        // afspraak van de figuren-agent: offset (en rotatie) in het assenstelsel van het bot
        const lok = new THREE.Matrix4().compose(
          new THREE.Vector3(...a.userData.offset),
          new THREE.Quaternion().setFromEuler(new THREE.Euler(...(a.userData.rotatie || [0, 0, 0]))),
          new THREE.Vector3(1, 1, 1));
        const s = new THREE.Vector3().setFromMatrixScale(botW);
        lok.scale(new THREE.Vector3(1 / s.x, 1 / s.y, 1 / s.z));
        this.accLokaal[soort] = lok;
        continue;
      }
      if (Math.hypot(p.x, p.z) < 1.2 && p.y > 0.2 && p.y < 2.2) {
        accW = a.userData.wereld.clone();                       // staat al op zijn plaats op de figuur
      } else {
        const s = new THREE.Vector3().setFromMatrixScale(a.userData.wereld);
        accW = new THREE.Matrix4().compose(new THREE.Vector3().setFromMatrixPosition(botW), new THREE.Quaternion(), s);
      }
      this.accLokaal[soort] = new THREE.Matrix4().copy(botW).invert().multiply(accW);
    }

    // clips: op naam, zonder wortelbeweging
    this.clips = {};
    for (const c of gltf.animations) {
      const naam = CLIPS.find((n) => c.name === n || c.name.endsWith('|' + n) || c.name.endsWith('_' + n) && c.name.length < n.length + 14) || c.name;
      this.clips[naam] = this.zonderWortelbeweging(c, proto);
    }
    this.proto = proto;

    // huidvarianten: donker en mat met lichte glans, telkens een tikje anders
    this.huid = [];
    const basis = [];
    proto.traverse((o) => { if (o.isMesh && !basis.includes(o.material)) basis.push(o.material); });
    for (let v = 0; v < 8; v++) {
      const map = new Map();
      for (const m of basis) {
        const k = m.clone();
        if (/figuur_huid/.test(m.name) && k.color) {
          const hsl = {};
          k.color.getHSL(hsl);
          const tint = [0.62, 0.75, 0.05, 0.08, 0.85, 0.55, 0.0, 0.7][v];
          k.color.setHSL(tint, 0.12 + Math.random() * 0.15, klem(hsl.l * (0.8 + Math.random() * 0.6), 0.012, 0.09));
          k.roughness = 0.4 + Math.random() * 0.2;
        }
        randLicht(k);
        map.set(m, k);
      }
      this.huid.push(map);
    }
    this.glowMat = GLOW_KLEUREN.map((kl) => {
      const basisMat = this.acc.glowstick?.material || new THREE.MeshStandardMaterial();
      const m = basisMat.clone();
      m.color = new THREE.Color(kl).multiplyScalar(0.3);
      m.emissive = new THREE.Color(kl);
      m.emissiveIntensity = 2.5;
      m.name = 'gloed_glowstick';
      return m;
    });
  }

  zonderWortelbeweging(clip, proto) {
    const c = clip.clone();
    for (const tr of c.tracks) {
      if (!/Hips\.position$/.test(tr.name)) continue;
      const botNaam = tr.name.replace(/\.position$/, '');
      const bot = proto.getObjectByName(botNaam);
      // welke lokale as is 'omhoog' voor de heup?
      let as = 1;
      if (bot && bot.parent) {
        const q = bot.parent.getWorldQuaternion(new THREE.Quaternion()).invert();
        const op = new THREE.Vector3(0, 1, 0).applyQuaternion(q);
        const a = [Math.abs(op.x), Math.abs(op.y), Math.abs(op.z)];
        as = a.indexOf(Math.max(...a));
      }
      const v = tr.values;
      const v0 = [v[0], v[1], v[2]];
      for (let i = 0; i < v.length; i += 3) {
        for (let k = 0; k < 3; k++) if (k !== as) v[i + k] = v0[k];
      }
    }
    return c;
  }

  /** Eén figuur: { obj, mixer, acties, speel(naam) }. */
  kloon(opties = {}, rnd = Math.random) {
    const figuur = kloonSkelet(this.proto);
    const huid = this.huid[Math.floor(rnd() * this.huid.length)];
    figuur.traverse((o) => {
      if (!o.isMesh) return;
      o.material = huid.get(o.material) || o.material;
      o.frustumCulled = false;            // eigen culling per figuur (dansen gaat buiten de rustpose)
      o.castShadow = true;
      o.receiveShadow = false;
    });
    const obj = new THREE.Group();
    obj.add(figuur);
    // accessoires
    const hang = (soort, mat) => {
      const bron = this.acc[soort];
      const lok = this.accLokaal[soort];
      if (!bron || !lok) return null;
      const bot = figuur.getObjectByName(this.botNamen[ACC[soort]]);
      if (!bot) return null;
      const a = bron.clone();
      a.matrixAutoUpdate = true;
      lok.decompose(a.position, a.quaternion, a.scale);
      if (mat) a.traverse((o) => { if (o.isMesh) o.material = mat; });
      a.traverse((o) => { if (o.isMesh) { o.castShadow = false; o.frustumCulled = false; } });
      bot.add(a);
      return a;
    };
    // opties.accessoires: lijst met soorten (vast), of weglaten voor een willekeurige keuze
    const vast = opties.accessoires;
    const kies = (soort, p) => (vast ? vast.includes(soort) : rnd() < p);
    const glow = () => this.glowMat[Math.floor(rnd() * this.glowMat.length)];
    if (kies('glowstick', 0.4)) hang('glowstick', glow());
    if (kies('halsband', 0.22)) hang('halsband', glow());
    const hoofd = rnd();
    if (vast ? vast.includes('koptelefoon') : hoofd < 0.15) hang('koptelefoon');
    else if (vast ? vast.includes('masker') : hoofd < 0.3) hang('masker');

    const mixer = new THREE.AnimationMixer(figuur);
    const acties = {};
    for (const [naam, clip] of Object.entries(this.clips)) acties[naam] = mixer.clipAction(clip);
    if (acties.backflip) {
      acties.backflip.setLoop(THREE.LoopOnce, 1);
      acties.backflip.clampWhenFinished = false;
    }
    const f = { obj, figuur, mixer, acties, huidig: null };
    f.speel = (naam, overgang = 0.5, offset = null) => {
      const nieuw = acties[naam] || acties.staan || acties[Object.keys(acties)[0]];
      if (!nieuw || nieuw === f.huidig) return;
      nieuw.reset();
      nieuw.enabled = true;
      nieuw.setEffectiveWeight(1);
      if (offset !== null) nieuw.time = offset * nieuw.getClip().duration;
      nieuw.play();
      if (f.huidig && overgang > 0) f.huidig.crossFadeTo(nieuw, overgang, false);
      else if (f.huidig) f.huidig.stop();
      f.huidig = nieuw;
      f.huidigNaam = naam;
    };
    return f;
  }
}

// =====================================================================
export class Dansers {
  constructor(scene, bron, data, { kwaliteit = 'hoog' } = {}) {
    this.bron = bron;
    this.groep = new THREE.Group();
    this.groep.name = 'dansers';
    scene.add(this.groep);
    this.kwaliteit = kwaliteit;
    this.lijst = [];
    this.vorigeFase = null;
    this.flipKlok = 6;
    this.frustum = new THREE.Frustum();
    this.pm = new THREE.Matrix4();
    this.bol = new THREE.Sphere(new THREE.Vector3(), 1.7);
    let i = 0;
    for (const plaats of data.dansers || []) {
      const f = bron.kloon();
      const zone = plaats.zone || 'vloer';
      const y = plaats.y ?? (zone === 'podium' ? data.podium.y : 0);
      f.obj.position.set(plaats.x, y, plaats.z);
      f.obj.rotation.y = (plaats.h || 0) + Math.PI;           // figuur kijkt naar +z, h volgt Ministad
      this.groep.add(f.obj);
      Object.assign(f, {
        zone, i, dj: zone === 'podium' && !this.lijst.some((d) => d.zone === 'podium'),
        temperament: Math.random(), wacht: Math.random() * 2, opgeteld: 0, wissel: 8 + Math.random() * 14
      });
      f.mixer.addEventListener('finished', (e) => {
        if (e.action === f.acties.backflip) f.speel(HOUSE[Math.floor(Math.random() * 3)], 0.35);
      });
      f.speel(this.keuze(f, 'basis'), 0, Math.random());
      this.lijst.push(f);
      i++;
    }
    this.botsersLijst = this.lijst.map((f) => ({ x: f.obj.position.x, z: f.obj.position.z, r: 0.32, y: f.obj.position.y }));
  }

  keuze(f, fase) {
    if (f.dj) return f.acties.wiegen ? 'wiegen' : 'staan';
    const kansen = {
      vloer: { basis: 0.3, opbouw: 0.55, drop: 1 },
      podium: { basis: 0.6, opbouw: 0.8, drop: 1 },
      rand: { basis: 0.2, opbouw: 0.3, drop: 0.6 },
      vuur: { basis: 0.06, opbouw: 0.1, drop: 0.3 },
      chill: { basis: 0.04, opbouw: 0.08, drop: 0.25 }
    }[f.zone] || { basis: 0.3, opbouw: 0.5, drop: 0.9 };
    const p = kansen[fase] * (fase === 'drop' ? 1 : 0.55 + f.temperament * 0.9);
    if (Math.random() < p) return HOUSE[Math.floor(Math.random() * HOUSE.length)];
    return Math.random() < 0.7 ? 'wiegen' : 'staan';
  }

  zetKwaliteit(k) { this.kwaliteit = k; }

  botsers() { return this.botsersLijst; }

  update(dt, ritme, camera) {
    const licht = this.kwaliteit === 'licht';
    // fasewissel: iedereen kiest opnieuw, gespreid in de tijd (bij de drop vlug)
    if (ritme.fase !== this.vorigeFase) {
      const spreid = ritme.fase === 'drop' ? 0.5 : 3.5;
      for (const f of this.lijst) f.wacht = Math.random() * spreid;
      this.vorigeFase = ritme.fase;
    }
    const tempo = klem(ritme.bpm / CLIP_BPM, 0.88, 1.2);
    const rustig = klem(ritme.bpm / 142, 0.85, 1.15);

    // af en toe een backflip in de drop
    this.flipKlok -= dt;
    if (ritme.fase === 'drop' && this.flipKlok < 0) {
      this.flipKlok = 6 + Math.random() * 9;
      const kandidaten = this.lijst.filter((f) => f.zone === 'vloer' && f.zichtbaar && f.huidigNaam !== 'backflip' &&
        f.obj.position.distanceTo(camera.position) < 28);
      const f = kandidaten[Math.floor(Math.random() * kandidaten.length)];
      if (f && f.acties.backflip) f.speel('backflip', 0.2);
    }

    this.pm.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    this.frustum.setFromProjectionMatrix(this.pm);
    const cam = camera.position;
    for (const f of this.lijst) {
      if (f.wacht > 0) {
        f.wacht -= dt;
        if (f.wacht <= 0) f.speel(this.keuze(f, ritme.fase), ritme.fase === 'drop' ? 0.3 : 0.8);
      }
      f.wissel -= dt;
      if (f.wissel < 0) {
        f.wissel = 10 + Math.random() * 16;
        if (f.huidigNaam !== 'backflip') f.speel(this.keuze(f, ritme.fase), 0.9);
      }
      this.bol.center.set(f.obj.position.x, f.obj.position.y + 0.9, f.obj.position.z);
      f.zichtbaar = this.frustum.intersectsSphere(this.bol);
      f.obj.visible = f.zichtbaar;
      f.opgeteld += dt;
      if (!f.zichtbaar) { f.opgeteld = Math.min(f.opgeteld, 3); continue; }
      const d = Math.hypot(this.bol.center.x - cam.x, this.bol.center.z - cam.z);
      const interval = d < 14 ? 0 : d < 30 ? (licht ? 1 / 15 : 1 / 30) : (licht ? 1 / 6 : 1 / 12);
      if (f.opgeteld < interval) continue;
      const n = f.huidigNaam;
      f.mixer.timeScale = n === 'backflip' ? 1 : HOUSE.includes(n) ? tempo : rustig;
      f.mixer.update(f.opgeteld);
      f.opgeteld = 0;
    }
    // glowsticks pulseren mee
    const g = 2.2 + ritme.beat * (0.6 + ritme.drop * 1.2);
    for (const m of this.bron.glowMat) m.emissiveIntensity = g;
  }
}
