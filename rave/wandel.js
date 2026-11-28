// Rave against the machine — rondlopen op een psytrance-feest bij nacht.
// Vertrekt van ministad/wandel.js: lopen, botsen, camera, kaart, pauze en aanraakbediening.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { maakHoogteMist, maakLucht, NACHT, MAAN_RICHTING } from './lucht.js';
import { Lichtshow } from './licht.js';
import { ritme, stapRitme, tik, dropNu, startMicrofoon, stopMicrofoon, microfoonAan } from './ritme.js';
import { FigurenBron, Dansers } from './dansers.js';

const DRACO = 'https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/gltf/';
const WANDEL = 2.0;          // m/s
const LOOP = 5.2;            // m/s met Shift
const STRAAL = 0.3;
const STAP = 0.35;           // zo hoog stap je zonder springen
const SPRONG = 4.6;
const ZWAARTE = 13;
const MUIS = 0.0024;
const VEEG = 0.0055;
const OOG = 1.62;

const $ = (id) => document.getElementById(id);
const el = {
  doek: $('doek'), intro: $('intro'), wandel: $('wandel'), voortgang: $('voortgang'),
  pauze: $('pauze'), kaart: $('kaart'), stok: $('stok'), vizier: $('vizier'), zicht: $('zicht'),
  hud: $('hud'), lamp: $('ritmeLamp'), lampTekst: $('ritmeTekst'), tikKnop: $('tikKnop'), dansKnop: $('dansKnop'),
  muziek: $('muziek'), muziekKop: $('muziekKop'), muziekKnop: $('muziekKnop'), spotify: $('spotify'),
  micKnop: $('micKnop'), kwaliteitKnop: $('kwaliteitKnop')
};
const params = new URLSearchParams(location.search);
const aanraak = matchMedia('(pointer: coarse)').matches && !matchMedia('(pointer: fine)').matches;
document.documentElement.classList.toggle('is-aanraak', aanraak);
const minderBeweging = matchMedia('(prefers-reduced-motion: reduce)').matches;

// ---------- kwaliteit: 'hoog' of 'licht' (automatisch op telefoon) ----------
function beginKwaliteit() {
  const p = params.get('kwaliteit');
  if (p === 'hoog' || p === 'licht') return p;
  try { const k = localStorage.getItem('rave-kwaliteit'); if (k === 'hoog' || k === 'licht') return k; } catch (e) { /* geen opslag */ }
  const klein = Math.min(innerWidth, innerHeight) < 700;
  const zwak = (navigator.deviceMemory && navigator.deviceMemory <= 4) || (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4);
  return aanraak || (klein && zwak) ? 'licht' : 'hoog';
}
let kwaliteit = beginKwaliteit();

// ---------- renderer en scène ----------
maakHoogteMist();
const renderer = new THREE.WebGLRenderer({ canvas: el.doek, antialias: false, powerPreference: 'high-performance' });
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
scene.background = NACHT.clone();
scene.fog = new THREE.FogExp2(NACHT.clone(), 0.024);

const camera = new THREE.PerspectiveCamera(62, 1, 0.1, 700);
camera.rotation.order = 'YXZ';

const lucht = maakLucht(camera);
scene.add(lucht.mesh);

// zwak maanlicht en hemellicht; de rest komt van het feest zelf
scene.add(new THREE.HemisphereLight('#26306a', '#0b0806', 0.55));
const maan = new THREE.DirectionalLight('#9fb4ff', 0.32);
maan.position.copy(MAAN_RICHTING).multiplyScalar(100);
scene.add(maan, maan.target);

// nabewerking: bloom op alles wat gloeit
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.85, 0.55, 0.62);
composer.addPass(bloom);
composer.addPass(new OutputPass());

// ---------- toestand ----------
const speler = { x: 0, z: 0, y: 0, vy: 0, opGrond: true, vx: 0, vz: 0, kop: 0, snel: false };
const cam = { yaw: 0, pitch: 0.12, afstand: 4.2, huidig: 4.2, ik: false };
let data = null;
let licht = null;
let dansers = null;
let mannetje = null;          // { obj, figuur, mixer, acties, speel, botten }
let camVakken = [];
let bezig = false;
const toets = new Set();
let kaartAan = true;
const dans = { aan: false, keuze: 0, stil: 0 };
const vasteBlik = params.get('kijk') ? params.get('kijk').split(',').map(Number) : null;   // debug: x,y,z,tx,ty,tz

// ---------- laden ----------
function laadGltf(url, draco, voortgang) {
  const loader = new GLTFLoader();
  if (draco) loader.setDRACOLoader(new DRACOLoader().setDecoderPath(DRACO));
  return loader.loadAsync(url, voortgang);
}

async function laad() {
  const deel = { wereld: 0, figuren: 0 };
  const toon = () => {
    el.voortgang.textContent = 'Feest opbouwen: ' + Math.round((deel.wereld * 0.75 + deel.figuren * 0.25) * 100) + '%';
  };
  const [json, wereldGltf, figGltf] = await Promise.all([
    fetch('botsing.json').then((r) => { if (!r.ok) throw new Error('botsing.json'); return r.json(); }),
    laadGltf('rave.glb', true, (e) => { if (e.total) { deel.wereld = e.loaded / e.total; toon(); } }),
    laadGltf('figuren.glb', true, (e) => { if (e.total) { deel.figuren = e.loaded / e.total; toon(); } })
  ]);
  data = json;
  data.vakken = data.vakken || [];
  data.rondjes = data.rondjes || [];
  data.podium = data.podium || { x0: -8, z0: -28, x1: 8, z1: -20, y: 1.2 };
  data.dansvloer = data.dansvloer || { x: 0, z: 0, r: 16 };

  const wereld = voegSamen(wereldGltf.scene);
  scene.add(wereld);
  camVakken = data.vakken.filter((v) => (v[2] - v[0]) * (v[3] - v[1]) > 1.5 && v[4] > 2.2)
    .concat(data.rondjes.filter((r) => r[3] > 2.2 && r[2] > 0.3).map(([x, z, r, h]) => [x - r * 0.8, z - r * 0.8, x + r * 0.8, z + r * 0.8, h]));

  licht = new Lichtshow({ scene, wereld: wereldGltf.scene, gloedWortel: wereld, data, kwaliteit });
  lucht.uniforms.feestRichting.value.set(licht.podiumMidden.x, 0, licht.podiumMidden.z - 30).normalize();

  const bron = new FigurenBron(figGltf);
  dansers = new Dansers(scene, bron, data, { kwaliteit });
  maakMannetje(bron);

  speler.x = data.start?.x ?? 0;
  speler.z = data.start?.z ?? 30;
  speler.kop = data.start?.richting || 0;
  speler.y = grondHoogte(speler.x, speler.z, 0);
  cam.yaw = speler.kop;
  tekenKaartBasis();
  zetKwaliteit(kwaliteit);
  // alle shaders vooraf compileren: geen haperingen bij de eerste drop
  renderer.compile(scene, camera);
}

/** Voegt de terreinonderdelen met hetzelfde materiaal samen; instanced meshes blijven zoals ze zijn. */
function voegSamen(wortel) {
  wortel.updateMatrixWorld(true);
  const perSleutel = new Map();
  const groep = new THREE.Group();
  groep.name = 'wereld';
  const apart = [];
  const anisotroop = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  wortel.traverse((o) => {
    if (!o.isMesh) return;
    if (o.isInstancedMesh || o.isSkinnedMesh || Array.isArray(o.material)) { apart.push(o); return; }
    const g = o.geometry.clone().applyMatrix4(o.matrixWorld);
    if (!g.index) g.setIndex([...Array(g.attributes.position.count).keys()]);
    const sleutel = o.material.uuid + '|' + Object.keys(g.attributes).sort().join(',');
    if (!perSleutel.has(sleutel)) perSleutel.set(sleutel, { mat: o.material, geos: [] });
    perSleutel.get(sleutel).geos.push(g);
  });
  const instelMesh = (mesh, mat) => {
    const naam = mat.name || '';
    if (mat.map) { mat.map.anisotropy = anisotroop; mat.map.needsUpdate = true; }
    if (/blad|loof|kroon|naald/.test(naam)) doorzichtigDichtbij(mat);
    if (!mesh.geometry.boundingBox) mesh.geometry.computeBoundingBox();
    const bb = mesh.geometry.boundingBox;
    const hoog = mesh.isInstancedMesh || bb.max.y - bb.min.y > 0.25;
    mesh.castShadow = hoog && !/^gloed_/.test(naam);
    mesh.receiveShadow = !/^gloed_/.test(naam);
  };
  for (const { mat, geos } of perSleutel.values()) {
    let geo = null;
    try { geo = geos.length > 1 ? mergeGeometries(geos, false) : geos[0]; } catch (e) { geo = null; }
    for (const g of geo ? [geo] : geos) {
      const mesh = new THREE.Mesh(g, mat);
      instelMesh(mesh, mat);
      groep.add(mesh);
    }
    if (geo && geos.length > 1) geos.forEach((g) => g.dispose());
  }
  for (const o of apart) {
    const m = o.clone();
    o.matrixWorld.decompose(m.position, m.quaternion, m.scale);
    instelMesh(m, Array.isArray(m.material) ? m.material[0] : m.material);
    groep.add(m);
  }
  return groep;
}

/** Bladeren vlak voor de camera lossen op in een korrelpatroon. */
function doorzichtigDichtbij(mat) {
  mat.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWereld;')
      .replace('#include <project_vertex>', '#include <project_vertex>\nvWereld = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWereld;')
      .replace('#include <clipping_planes_fragment>', `#include <clipping_planes_fragment>
        float dCam = distance(vWereld, cameraPosition);
        if (dCam < 4.5) {
          float zicht = clamp((dCam - 2.0) / 2.5, 0.0, 1.0);
          float korrel = fract(sin(dot(floor(gl_FragCoord.xy), vec2(12.9898, 78.233))) * 43758.5453);
          if (korrel > zicht) discard;
        }`);
  };
  mat.customProgramCacheKey = () => 'blad';
}

// ---------- het mannetje (de speler) ----------
function maakMannetje(bron) {
  const f = bron.kloon({ accessoires: ['glowstick'] }, () => 0.37);
  const botten = {};
  const zoek = { heup: /Hips$/, bovenL: /LeftUpLeg$/, bovenR: /RightUpLeg$/, knieL: /LeftLeg$/, knieR: /RightLeg$/,
    armL: /LeftArm$/, armR: /RightArm$/, elleL: /LeftForeArm$/, elleR: /RightForeArm$/, rug: /Spine1?$/ };
  f.figuur.traverse((o) => {
    if (!o.isBone) return;
    for (const [k, re] of Object.entries(zoek)) if (!botten[k] && re.test(o.name)) botten[k] = o;
  });
  f.botten = botten;
  f.fase = 0;
  f.mixer.addEventListener('finished', (e) => {
    if (e.action === f.acties.backflip) f.speel(dans.aan ? huisClip() : 'staan', 0.3);
  });
  f.speel('staan', 0, 0);
  scene.add(f.obj);
  mannetje = f;
}
const huisClip = () => ['house_1', 'house_2', 'house_3'][dans.keuze % 3];

const tmpQ = new THREE.Quaternion(), tmpQ2 = new THREE.Quaternion(), tmpV = new THREE.Vector3();
/** Draai een bot rond een as in wereldruimte (na de animatie). */
function draaiBot(bot, asWereld, hoek) {
  if (!bot || !bot.parent || Math.abs(hoek) < 1e-4) return;
  bot.parent.getWorldQuaternion(tmpQ).invert();
  tmpV.copy(asWereld).applyQuaternion(tmpQ).normalize();
  tmpQ2.setFromAxisAngle(tmpV, hoek);
  bot.quaternion.premultiply(tmpQ2);
  bot.updateMatrixWorld(true);
}

/** Eenvoudige procedurele stap bovenop 'staan' (figuren.glb heeft geen loopclip). */
function procedureelLopen(m, sterkte, rennen) {
  const b = m.botten;
  m.figuur.updateMatrixWorld(true);
  const rechts = tmpV.set(-1, 0, 0).applyQuaternion(m.obj.quaternion).clone();     // figuur kijkt naar +z
  const f = m.fase;
  const amp = (rennen ? 0.75 : 0.45) * sterkte;
  const zwaai = Math.sin(f) * amp;
  draaiBot(b.bovenL, rechts, -zwaai);
  draaiBot(b.bovenR, rechts, zwaai);
  const buig = rennen ? 1.3 : 0.6;
  draaiBot(b.knieL, rechts, Math.max(0, Math.sin(f + 1.6)) * buig * sterkte);
  draaiBot(b.knieR, rechts, Math.max(0, Math.sin(f + 1.6 + Math.PI)) * buig * sterkte);
  draaiBot(b.armL, rechts, zwaai * 0.8);
  draaiBot(b.armR, rechts, -zwaai * 0.8);
  if (rennen) { draaiBot(b.elleL, rechts, -0.9 * sterkte); draaiBot(b.elleR, rechts, -0.9 * sterkte); }
  draaiBot(b.rug, rechts, (rennen ? -0.15 : -0.04) * sterkte);
}

// ---------- botsen en grond ----------
/** Grondhoogte: 0, of de bovenkant van een laag vak/rondje waar je op kan stappen. */
function grondHoogte(x, z, y) {
  let g = 0;
  for (const v of data.vakken) {
    if (v[4] > y + STAP || v[4] <= g) continue;
    if (x >= v[0] && x <= v[2] && z >= v[1] && z <= v[3]) g = v[4];
  }
  for (const r of data.rondjes) {
    if (r[3] > y + STAP || r[3] <= g) continue;
    if ((x - r[0]) ** 2 + (z - r[1]) ** 2 <= r[2] * r[2]) g = r[3];
  }
  return g;
}

function duwUitCirkel(p, cx, cz, r) {
  const dx = p.x - cx, dz = p.z - cz;
  const d = Math.hypot(dx, dz), min = r + STRAAL;
  if (d < min && d > 1e-6) { p.x = cx + dx / d * min; p.z = cz + dz / d * min; }
}

function botsUit(p, dynamisch) {
  const voet = speler.y + STAP;
  for (let ronde = 0; ronde < 2; ronde++) {
    for (const v of data.vakken) {
      const [x0, z0, x1, z1] = v;
      if (p.x < x0 - STRAAL || p.x > x1 + STRAAL || p.z < z0 - STRAAL || p.z > z1 + STRAAL) continue;
      if (v[4] <= voet) continue;                         // daar stap of spring je op
      const nx = Math.max(x0, Math.min(p.x, x1));
      const nz = Math.max(z0, Math.min(p.z, z1));
      const dx = p.x - nx, dz = p.z - nz;
      const d2 = dx * dx + dz * dz;
      if (d2 > STRAAL * STRAAL) continue;
      if (d2 > 1e-10) {
        const d = Math.sqrt(d2);
        p.x = nx + dx / d * STRAAL;
        p.z = nz + dz / d * STRAAL;
      } else {
        const uit = [[p.x - x0 + STRAAL, -1, 0], [x1 - p.x + STRAAL, 1, 0], [p.z - z0 + STRAAL, 0, -1], [z1 - p.z + STRAAL, 0, 1]]
          .sort((a, b) => a[0] - b[0])[0];
        p.x += uit[1] * uit[0];
        p.z += uit[2] * uit[0];
      }
    }
    for (const r of data.rondjes) if (r[3] > voet) duwUitCirkel(p, r[0], r[1], r[2]);
    for (const c of dynamisch) if (Math.abs((c.y || 0) - speler.y) < 1.5) duwUitCirkel(p, c.x, c.z, c.r);
  }
  const g = data.grens || 44;
  const d = Math.hypot(p.x, p.z);
  if (d > g) { p.x *= g / d; p.z *= g / d; }
}

/** Hoe ver kan de camera vanaf het doel in richting d, voor ze iets raakt? */
function camVrij(o, d, max) {
  let t = max;
  if (d.y < -1e-4) t = Math.min(t, (o.y - 0.35) / -d.y);
  for (const v of camVakken) {
    const lo = [v[0] - 0.25, -1, v[1] - 0.25], hi = [v[2] + 0.25, v[4] + 0.25, v[3] + 0.25];
    let t0 = 0, t1 = t;
    const oo = [o.x, o.y, o.z], dd = [d.x, d.y, d.z];
    let raak = true;
    for (let a = 0; a < 3 && raak; a++) {
      if (Math.abs(dd[a]) < 1e-9) { if (oo[a] < lo[a] || oo[a] > hi[a]) raak = false; continue; }
      let ta = (lo[a] - oo[a]) / dd[a], tb = (hi[a] - oo[a]) / dd[a];
      if (ta > tb) [ta, tb] = [tb, ta];
      t0 = Math.max(t0, ta); t1 = Math.min(t1, tb);
      if (t0 > t1) raak = false;
    }
    if (raak && t0 > 0) t = Math.min(t, t0);
  }
  return t;
}

// ---------- invoer: toetsenbord en muis ----------
const BEWEEG = { KeyW: 'v', ArrowUp: 'v', KeyS: 'a', ArrowDown: 'a', KeyA: 'l', ArrowLeft: 'l', KeyD: 'r', ArrowRight: 'r' };
addEventListener('keydown', (e) => {
  if (!bezig) return;
  if (BEWEEG[e.code]) { toets.add(BEWEEG[e.code]); e.preventDefault(); }
  if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') toets.add('loop');
  if (e.code === 'Space') { spring(); e.preventDefault(); }
  if (e.repeat) return;
  if (e.code === 'KeyM') { kaartAan = !kaartAan; el.kaart.hidden = !kaartAan; }
  if (e.code === 'KeyV') wisselZicht();
  if (e.code === 'KeyT') doeTik();
  if (e.code === 'KeyX') dropNu();
  if (e.code === 'KeyE') wisselDans();
  if (e.code === 'KeyR') salto();
});
addEventListener('keyup', (e) => {
  if (BEWEEG[e.code]) toets.delete(BEWEEG[e.code]);
  if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') toets.delete('loop');
});
addEventListener('blur', () => toets.clear());
addEventListener('wheel', (e) => {
  if (!bezig || cam.ik) return;
  cam.afstand = Math.max(1.8, Math.min(14, cam.afstand * (e.deltaY > 0 ? 1.12 : 0.89)));
}, { passive: true });

function wisselZicht() {
  cam.ik = !cam.ik;
  if (cam.ik) cam.pitch = Math.min(cam.pitch, 0.3);
  el.vizier.hidden = !cam.ik || aanraak;
  el.zicht.textContent = cam.ik ? 'Achter het mannetje' : 'Door zijn ogen';
}
function spring() {
  if (speler.opGrond) { speler.vy = SPRONG; speler.opGrond = false; }
}
function draai(dx, dy, gevoel) {
  cam.yaw -= dx * gevoel;
  cam.pitch = Math.max(cam.ik ? -1.35 : -0.35, Math.min(1.35, cam.pitch + dy * gevoel));
}
function doeTik() {
  const bpm = tik();
  el.tikKnop.classList.add('tik');
  setTimeout(() => el.tikKnop.classList.remove('tik'), 90);
  toonLamp(true, bpm);
}
function wisselDans() {
  if (!mannetje) return;
  dans.aan = !dans.aan;
  if (dans.aan) dans.keuze++;
  el.dansKnop.setAttribute('aria-pressed', String(dans.aan));
}
function salto() {
  if (!mannetje || !mannetje.acties.backflip || !speler.opGrond) return;
  if (Math.hypot(speler.vx, speler.vz) > 1) return;
  mannetje.speel('backflip', 0.15);
}

document.addEventListener('mousemove', (e) => {
  if (!bezig || document.pointerLockElement !== el.doek) return;
  if (Math.abs(e.movementX) > 250 || Math.abs(e.movementY) > 250) return;
  draai(e.movementX, e.movementY, MUIS);
});
document.addEventListener('pointerlockchange', () => {
  if (document.pointerLockElement !== el.doek && bezig && !aanraak && !vrijeMuis) pauzeer();
});
let vrijeMuis = false;
let sleep = null;
el.doek.addEventListener('mousedown', (e) => {
  if (!bezig) return;
  if (vrijeMuis) sleep = { x: e.clientX, y: e.clientY };
  else if (document.pointerLockElement !== el.doek) vergrendel();
});
addEventListener('mouseup', () => { sleep = null; });
addEventListener('mousemove', (e) => {
  if (!sleep) return;
  draai(e.clientX - sleep.x, e.clientY - sleep.y, MUIS * 1.5);
  sleep = { x: e.clientX, y: e.clientY };
});
function vergrendel() {
  try {
    const p = el.doek.requestPointerLock();
    if (p && p.catch) p.catch(() => { vrijeMuis = true; });
  } catch (e) { vrijeMuis = true; }
}

// ---------- invoer: aanraken ----------
const stok = { id: null, x0: 0, y0: 0, dx: 0, dy: 0 };
const kijk = { id: null, x: 0, y: 0 };
let laatsteTik = 0;
el.doek.addEventListener('touchstart', (e) => {
  if (!bezig) return;
  for (const t of e.changedTouches) {
    if (t.clientX < innerWidth / 2 && stok.id === null) {
      Object.assign(stok, { id: t.identifier, x0: t.clientX, y0: t.clientY, dx: 0, dy: 0 });
      el.stok.style.left = t.clientX + 'px';
      el.stok.style.top = t.clientY + 'px';
      el.stok.classList.add('actief');
      zetStok();
    } else if (kijk.id === null) {
      Object.assign(kijk, { id: t.identifier, x: t.clientX, y: t.clientY });
      const nu = performance.now();
      if (nu - laatsteTik < 300) spring();
      laatsteTik = nu;
    }
  }
  e.preventDefault();
}, { passive: false });
el.doek.addEventListener('touchmove', (e) => {
  for (const t of e.changedTouches) {
    if (t.identifier === stok.id) {
      stok.dx = t.clientX - stok.x0;
      stok.dy = t.clientY - stok.y0;
      zetStok();
    } else if (t.identifier === kijk.id) {
      draai(t.clientX - kijk.x, t.clientY - kijk.y, VEEG);
      kijk.x = t.clientX;
      kijk.y = t.clientY;
    }
  }
  e.preventDefault();
}, { passive: false });
function eindAanraak(e) {
  for (const t of e.changedTouches) {
    if (t.identifier === stok.id) { stok.id = null; stok.dx = stok.dy = 0; el.stok.classList.remove('actief'); }
    if (t.identifier === kijk.id) kijk.id = null;
  }
}
el.doek.addEventListener('touchend', eindAanraak);
el.doek.addEventListener('touchcancel', eindAanraak);
function zetStok() {
  const max = 50;
  const d = Math.hypot(stok.dx, stok.dy);
  const f = d > max ? max / d : 1;
  el.stok.firstElementChild.style.transform = `translate(${stok.dx * f}px, ${stok.dy * f}px)`;
}
// knoppen reageren op pointerdown: snel genoeg om mee te tikken
el.tikKnop.addEventListener('pointerdown', (e) => { e.preventDefault(); doeTik(); });
el.dansKnop.addEventListener('click', wisselDans);

// ---------- muziek, microfoon, kwaliteit ----------
function zetMuziek(open) {
  if (open && !el.spotify.src) el.spotify.src = el.spotify.dataset.src;
  el.muziek.classList.remove('verborgen');
  el.muziek.classList.toggle('dicht', !open);
  document.body.classList.add('muziek-open');
  el.muziekKop.setAttribute('aria-expanded', String(open));
  el.muziekKnop.setAttribute('aria-expanded', String(open));
}
el.muziekKnop.addEventListener('click', () => zetMuziek(el.muziek.classList.contains('dicht')));
el.muziekKop.addEventListener('click', () => zetMuziek(el.muziek.classList.contains('dicht')));

el.micKnop.addEventListener('click', async () => {
  if (microfoonAan()) {
    stopMicrofoon();
    el.micKnop.setAttribute('aria-pressed', 'false');
    el.micKnop.textContent = 'Laat de wereld meeluisteren';
    el.voortgang.textContent = 'De wereld luistert niet meer mee: eigen tempo, ' + Math.round(ritme.bpm) + ' BPM.';
    return;
  }
  el.micKnop.disabled = true;
  el.micKnop.textContent = 'Even toestemming vragen…';
  try {
    await startMicrofoon();
    el.micKnop.setAttribute('aria-pressed', 'true');
    el.micKnop.textContent = 'Luistert mee';
    el.voortgang.textContent = 'De wereld luistert mee via je microfoon. Het geluid blijft op je toestel.';
  } catch (fout) {
    el.micKnop.textContent = 'Laat de wereld meeluisteren';
    el.voortgang.textContent = 'Geen microfoon: het feest tikt zelf op ' + Math.round(ritme.bpm) + ' BPM. Tik mee met T of de Tik-knop.';
  }
  el.micKnop.disabled = false;
});

function zetKwaliteit(k) {
  kwaliteit = k;
  const licht_ = k === 'licht';
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, licht_ ? 1 : 1.75) * (licht_ && aanraak ? 0.8 : 1));
  bloom.strength = licht_ ? 0.6 : 0.85;
  bloom.radius = licht_ ? 0.4 : 0.55;
  maat();
  if (licht) licht.zetKwaliteit(k);
  if (dansers) dansers.zetKwaliteit(k);
  el.kwaliteitKnop.textContent = 'Beeld: ' + (licht_ ? 'licht' : 'hoog');
}
el.kwaliteitKnop.addEventListener('click', () => {
  zetKwaliteit(kwaliteit === 'hoog' ? 'licht' : 'hoog');
  try { localStorage.setItem('rave-kwaliteit', kwaliteit); } catch (e) { /* geen opslag */ }
});

// ---------- starten en pauzeren ----------
function start() {
  if (!data) return;
  el.intro.hidden = true;
  bezig = true;
  el.hud.hidden = false;
  el.pauze.hidden = !aanraak;
  el.zicht.hidden = !aanraak;
  el.kaart.hidden = !kaartAan;
  el.vizier.hidden = !cam.ik || aanraak;
  if (!el.muziek.classList.contains('verborgen')) zetMuziek(false);
  if (!aanraak && !vrijeMuis && el.doek.requestPointerLock && !params.has('auto')) vergrendel();
}
function pauzeer() {
  bezig = false;
  toets.clear();
  sleep = null;
  stok.id = kijk.id = null;
  el.stok.classList.remove('actief');
  el.intro.hidden = false;
  el.pauze.hidden = true;
  el.zicht.hidden = true;
  el.vizier.hidden = true;
  el.wandel.textContent = 'Verder feesten';
  el.wandel.focus();
}
el.wandel.addEventListener('click', start);
el.pauze.addEventListener('click', pauzeer);
el.zicht.addEventListener('click', wisselZicht);
addEventListener('keydown', (e) => {
  if (e.code === 'Escape' && bezig && (vrijeMuis || document.pointerLockElement !== el.doek)) pauzeer();
});

// ---------- statuslampje ----------
let lampKlok = 0;
function toonLamp(meteen, bpm) {
  if (!meteen && lampKlok > 0) return;
  lampKlok = 0.4;
  const bron = ritme.bron === 'microfoon' ? 'microfoon' : 'tempo';
  el.lampTekst.textContent = `${bron} · ${Math.round(bpm || ritme.bpm)} BPM · ${ritme.fase}`;
  el.lamp.classList.toggle('microfoon', ritme.bron === 'microfoon');
  el.lamp.classList.toggle('drop', ritme.fase === 'drop');
}

// ---------- kaart ----------
const kaartBasis = document.createElement('canvas');
function tekenKaartBasis() {
  const n = 400;
  kaartBasis.width = kaartBasis.height = n;
  const c = kaartBasis.getContext('2d');
  const g = 60;
  const s = n / (2 * g);
  const px = (x) => (x + g) * s;
  c.fillStyle = '#0c1410';
  c.fillRect(0, 0, n, n);
  // open plek
  c.fillStyle = '#1d1a16';
  c.beginPath(); c.arc(px(0), px(0), 44 * s, 0, Math.PI * 2); c.fill();
  // dansvloer
  const v = data.dansvloer;
  c.fillStyle = '#2a2230';
  c.beginPath(); c.arc(px(v.x), px(v.z), v.r * s, 0, Math.PI * 2); c.fill();
  c.strokeStyle = '#2ee6ff'; c.lineWidth = 2;
  c.stroke();
  // podium
  const p = data.podium;
  c.fillStyle = '#ff3fd2';
  c.fillRect(px(p.x0), px(p.z0), (p.x1 - p.x0) * s, (p.z1 - p.z0) * s);
  c.fillStyle = '#6d6a75';
  for (const [x0, z0, x1, z1] of data.vakken) {
    if ((x1 - x0) * (z1 - z0) < 0.5) continue;
    c.fillRect(px(x0), px(z0), Math.max(1, (x1 - x0) * s), Math.max(1, (z1 - z0) * s));
  }
  c.fillStyle = '#3c5a32';
  for (const [x, z, r] of data.rondjes) {
    c.beginPath(); c.arc(px(x), px(z), Math.max(1.2, r * s), 0, Math.PI * 2); c.fill();
  }
  kaartBasis.g = g;
}
function tekenKaart() {
  const c = el.kaart.getContext('2d');
  const w = el.kaart.width;
  const zicht = 34;
  const g = kaartBasis.g;
  const s = kaartBasis.width / (2 * g);
  const m = w / (2 * zicht);
  c.clearRect(0, 0, w, w);
  c.save();
  c.beginPath();
  c.arc(w / 2, w / 2, w / 2, 0, Math.PI * 2);
  c.clip();
  c.globalAlpha = 0.9;
  c.drawImage(kaartBasis, (speler.x - zicht + g) * s, (speler.z - zicht + g) * s, 2 * zicht * s, 2 * zicht * s, 0, 0, w, w);
  c.globalAlpha = 0.55 + ritme.beat * 0.45;
  c.fillStyle = '#d9c8ff';
  for (const d of dansers.lijst) {
    const x = (d.obj.position.x - speler.x) * m + w / 2, y = (d.obj.position.z - speler.z) * m + w / 2;
    if (x < -3 || y < -3 || x > w + 3 || y > w + 3) continue;
    c.fillRect(x - 1.5, y - 1.5, 3, 3);
  }
  c.globalAlpha = 1;
  c.translate(w / 2, w / 2);
  c.rotate(-(cam.ik ? cam.yaw : speler.kop));
  c.fillStyle = '#a6ff3a';
  c.strokeStyle = '#0a1400';
  c.lineWidth = 1.5;
  c.beginPath();
  c.moveTo(0, -9); c.lineTo(6, 6); c.lineTo(0, 3); c.lineTo(-6, 6); c.closePath();
  c.fill(); c.stroke();
  c.restore();
}

// ---------- lus ----------
const klok = new THREE.Clock();
const doelV = new THREE.Vector2();
const doelPunt = new THREE.Vector3();
const richting = new THREE.Vector3();
let tijd = 0;

function stap(dt) {
  let vooruit = 0, opzij = 0;
  if (bezig) {
    if (toets.has('v')) vooruit += 1;
    if (toets.has('a')) vooruit -= 1;
    if (toets.has('r')) opzij += 1;
    if (toets.has('l')) opzij -= 1;
  }
  let snel = toets.has('loop') ? LOOP : WANDEL;
  if (bezig && stok.id !== null) {
    const d = Math.hypot(stok.dx, stok.dy);
    if (d > 8) {
      const f = Math.min(1, d / 50);
      vooruit = -stok.dy / d * f;
      opzij = stok.dx / d * f;
      snel = f > 0.95 ? LOOP * 0.85 : WANDEL;
    }
  }
  const lengte = Math.hypot(vooruit, opzij);
  if (lengte > 1) { vooruit /= lengte; opzij /= lengte; }
  const flip = mannetje.huidigNaam === 'backflip';
  if (flip) { vooruit = opzij = 0; }
  const sin = Math.sin(cam.yaw), cos = Math.cos(cam.yaw);
  doelV.set((-sin * vooruit + cos * opzij) * snel, (-cos * vooruit - sin * opzij) * snel);
  const k = 1 - Math.exp(-(speler.opGrond ? 10 : 2.5) * dt);
  speler.vx += (doelV.x - speler.vx) * k;
  speler.vz += (doelV.y - speler.vz) * k;

  const p = { x: speler.x + speler.vx * dt, z: speler.z + speler.vz * dt };
  botsUit(p, dansers.botsers());
  const verplaatst = Math.hypot(p.x - speler.x, p.z - speler.z);
  const snelheid = verplaatst / Math.max(dt, 1e-4);
  speler.x = p.x;
  speler.z = p.z;

  const grond = grondHoogte(speler.x, speler.z, speler.y);
  speler.vy -= ZWAARTE * dt;
  speler.y += speler.vy * dt;
  if (speler.y <= grond) {
    if (speler.opGrond && grond > speler.y) speler.y += (grond - speler.y) * Math.min(1, dt * 18);
    else speler.y = grond;
    speler.vy = 0;
    speler.opGrond = true;
  } else if (speler.opGrond && speler.y - grond < 0.2 && speler.vy <= 0) {
    speler.y = Math.max(grond, speler.y - dt * 2.5);
    speler.vy = 0;
  } else {
    speler.opGrond = false;
  }

  if (cam.ik) speler.kop = cam.yaw;
  else if (Math.hypot(speler.vx, speler.vz) > 0.3) {
    let v = Math.atan2(-speler.vx, -speler.vz) - speler.kop;
    v = Math.atan2(Math.sin(v), Math.cos(v));
    speler.kop += v * Math.min(1, dt * 12);
  }

  // animatie: staan, wiegen op de vloer, dansen (E), salto (R), procedureel lopen
  const m = mannetje;
  m.obj.position.set(speler.x, speler.y, speler.z);
  m.obj.rotation.y = speler.kop + Math.PI;
  const beweegt = snelheid > 0.25;
  if (beweegt) { dans.stil = 0; if (dans.aan) wisselDans(); } else dans.stil += dt;
  if (!flip) {
    let clip = 'staan';
    if (dans.aan) clip = huisClip();
    else if (!beweegt && dans.stil > 1.5 && Math.hypot(speler.x - data.dansvloer.x, speler.z - data.dansvloer.z) < data.dansvloer.r) clip = 'wiegen';
    if (beweegt && m.acties.lopen) clip = 'lopen';
    m.speel(clip, 0.35);
  }
  const bpmSchaal = Math.max(0.88, Math.min(1.2, ritme.bpm / 125));
  m.mixer.timeScale = m.huidigNaam === 'lopen' ? snelheid / WANDEL : m.huidigNaam?.startsWith('house') ? bpmSchaal : 1;
  m.mixer.update(dt);
  if (!m.acties.lopen && !flip && (beweegt || !speler.opGrond)) {
    const rennen = snelheid > 3.4;
    m.fase += verplaatst * Math.PI * 2 / (rennen ? 2.3 : 1.4);
    procedureelLopen(m, speler.opGrond ? Math.min(1, snelheid / (rennen ? 4 : 1.6)) : 0.6, rennen);
  }

  // camera
  if (vasteBlik) {
    camera.position.set(vasteBlik[0], vasteBlik[1], vasteBlik[2]);
    camera.lookAt(vasteBlik[3], vasteBlik[4], vasteBlik[5]);
    m.obj.visible = true;
  } else if (cam.ik) {
    m.obj.visible = false;
    camera.position.set(speler.x, speler.y + OOG, speler.z);
    camera.rotation.set(-cam.pitch, cam.yaw, 0);
  } else {
    doelPunt.set(speler.x, speler.y + 1.5, speler.z);
    richting.set(Math.sin(cam.yaw) * Math.cos(cam.pitch), Math.sin(cam.pitch), Math.cos(cam.yaw) * Math.cos(cam.pitch));
    const vrij = camVrij(doelPunt, richting, cam.afstand) - 0.2;
    const doel = Math.max(0.4, Math.min(cam.afstand, vrij));
    cam.huidig = doel < cam.huidig ? doel : cam.huidig + (doel - cam.huidig) * Math.min(1, dt * 3);
    camera.position.copy(doelPunt).addScaledVector(richting, cam.huidig);
    camera.lookAt(doelPunt);
    m.obj.visible = cam.huidig > 0.9;
  }
  camera.updateMatrixWorld();
}

function maat() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false);
  composer.setPixelRatio(renderer.getPixelRatio());
  composer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
addEventListener('resize', maat);
maat();

function lus() {
  const dt = Math.min(klok.getDelta(), 0.05);
  if (data) {
    tijd += dt;
    if (!bezig && !minderBeweging && !vasteBlik) cam.yaw += dt * 0.04;
    stapRitme(dt);
    stap(dt);
    licht.update(dt, ritme, camera);
    dansers.update(dt, ritme, camera);
    lucht.uniforms.tijd.value = tijd;
    lucht.uniforms.feest.value.copy(licht.dominant).multiplyScalar(0.25 + ritme.drop * 0.25 + ritme.beat * 0.1);
    composer.render(dt);
    if (kaartAan && !el.kaart.hidden) tekenKaart();
    el.lamp.style.setProperty('--beat', ritme.beat.toFixed(2));
    lampKlok -= dt;
    toonLamp(false);
  }
  requestAnimationFrame(lus);
}

// voor wie wil meekijken in de console
window.rave = {
  speler, cam, ritme, camera, scene, renderer,
  get licht() { return licht; }, get dansers() { return dansers; }, get info() { return renderer.info.render; },
  zetKwaliteit, start
};

laad().then(() => {
  el.wandel.disabled = false;
  el.wandel.textContent = 'Naar het feest';
  el.voortgang.textContent = '';
  requestAnimationFrame(lus);
  if (params.has('auto')) start();
}).catch((fout) => {
  console.error(fout);
  el.wandel.textContent = 'Laden mislukt';
  el.voortgang.textContent = 'Het feest kon niet geladen worden. Herlaad de pagina.';
});
