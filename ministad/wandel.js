// Ministad — rondlopen als een mannetje in de stad die Blender heeft gebouwd.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { Figuren, poseLopen, poseStaan } from './figuren.js';
import { Leven } from './leven.js';

const DRACO = 'https://cdn.jsdelivr.net/npm/three@0.170.0/examples/jsm/libs/draco/gltf/';
const WANDEL = 2.2;          // m/s
const LOOP = 5.8;            // m/s met Shift
const STRAAL = 0.32;
const SPRONG = 4.6;
const ZWAARTE = 13;
const MUIS = 0.0024;
const VEEG = 0.0055;
const OOG = 1.62;
const ZON_RICHTING = new THREE.Vector3(-0.45, 0.8, 0.4).normalize();

const $ = (id) => document.getElementById(id);
const el = {
  doek: $('doek'), intro: $('intro'), wandel: $('wandel'), voortgang: $('voortgang'),
  pauze: $('pauze'), kaart: $('kaart'), stok: $('stok'), vizier: $('vizier'), zicht: $('zicht')
};
const aanraak = matchMedia('(pointer: coarse)').matches && !matchMedia('(pointer: fine)').matches;
document.documentElement.classList.toggle('is-aanraak', aanraak);
const minderBeweging = matchMedia('(prefers-reduced-motion: reduce)').matches;

// ---------- renderer en scène ----------
const renderer = new THREE.WebGLRenderer({ canvas: el.doek, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, aanraak ? 1.5 : 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
const HORIZON = new THREE.Color('#dce7ef');
scene.fog = new THREE.Fog(HORIZON, 90, 430);
scene.background = HORIZON;

const camera = new THREE.PerspectiveCamera(62, 1, 0.1, 1200);
camera.rotation.order = 'YXZ';

{
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: { zenit: { value: new THREE.Color('#5d93cf') }, horizon: { value: HORIZON }, zon: { value: ZON_RICHTING } },
    vertexShader: `varying vec3 vRicht;
      void main() { vRicht = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`,
    fragmentShader: `uniform vec3 zenit; uniform vec3 horizon; uniform vec3 zon; varying vec3 vRicht;
      void main() {
        float h = clamp(vRicht.y, 0.0, 1.0);
        vec3 k = mix(horizon, zenit, pow(h, 0.55));
        float s = max(dot(normalize(vRicht), zon), 0.0);
        k += vec3(1.0, 0.92, 0.75) * (pow(s, 600.0) * 2.0 + pow(s, 12.0) * 0.18);
        gl_FragColor = vec4(k, 1.0);
      }`
  });
  const lucht = new THREE.Mesh(new THREE.SphereGeometry(900, 32, 16), mat);
  lucht.frustumCulled = false;
  lucht.onBeforeRender = () => lucht.position.copy(camera.position);
  scene.add(lucht);
}

scene.add(new THREE.HemisphereLight('#cfe2f5', '#7a7f5c', 1.25));
const zon = new THREE.DirectionalLight('#fff0d8', 2.6);
zon.castShadow = true;
zon.shadow.mapSize.set(2048, 2048);
Object.assign(zon.shadow.camera, { left: -45, right: 45, top: 45, bottom: -45, near: 1, far: 300 });
zon.shadow.bias = -0.0004;
zon.shadow.normalBias = 0.04;
scene.add(zon, zon.target);

// ---------- toestand ----------
const speler = {
  x: 0, z: 0, y: 0, vy: 0, opGrond: true,
  vx: 0, vz: 0, kop: 0,
  snel: false, opStraat: false
};
const cam = { yaw: 0, pitch: 0.3, afstand: 4.5, huidig: 4.5, ik: false };
let stad = null;
let leven = null;
let mannetje = null;
let camVakken = [];
let bezig = false;
const toets = new Set();
let kaartAan = true;

// ---------- laden ----------
function laadGltf(url, draco, voortgang) {
  const loader = new GLTFLoader();
  if (draco) loader.setDRACOLoader(new DRACOLoader().setDecoderPath(DRACO));
  return loader.loadAsync(url, voortgang);
}

async function laad() {
  let geladen = 0;
  const [data, stadGltf, figGltf] = await Promise.all([
    fetch('botsing.json').then((r) => { if (!r.ok) throw new Error('botsing.json'); return r.json(); }),
    laadGltf('ministad.glb', true, (e) => {
      if (e.total) {
        geladen = e.loaded / e.total;
        el.voortgang.textContent = 'Stad laden: ' + Math.round(geladen * 100) + '%';
      }
    }),
    laadGltf('figuren.glb', false)
  ]);
  stad = data;
  scene.add(voegSamen(stadGltf.scene));
  camVakken = stad.vakken.filter((v) => (v[2] - v[0]) * (v[3] - v[1]) > 1.5 && v[4] > 2.2);

  const figuren = new Figuren(figGltf.scene);
  mannetje = figuren.persoon({
    kleuren: { shirt: '#e85d3f', broek: '#2c3e50', pet: '#f1c40f', rugzak: '#2e86de', huid: '#e0ac88', haar: '#4a3222', schoen: '#f4f4f0' },
    haar: 'kort', pet: true, rugzak: true
  });
  scene.add(mannetje.obj);
  leven = new Leven(scene, figuren, stad, { minder: aanraak });

  speler.x = stad.start.x;
  speler.z = stad.start.z;
  speler.kop = stad.start.richting || 0;
  speler.y = grondHoogte(speler.x, speler.z);
  cam.yaw = speler.kop;
  tekenKaartBasis();
}

/** Voegt alle stadsonderdelen met hetzelfde materiaal samen: honderden objecten, een veertigtal tekenopdrachten. */
function voegSamen(wortel) {
  wortel.updateMatrixWorld(true);
  const perMat = new Map();
  const anisotroop = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  wortel.traverse((o) => {
    if (!o.isMesh) return;
    const g = o.geometry.clone().applyMatrix4(o.matrixWorld);
    for (const naam of Object.keys(g.attributes)) {
      if (!['position', 'normal', 'uv'].includes(naam)) g.deleteAttribute(naam);
    }
    if (!g.attributes.uv) g.setAttribute('uv', new THREE.Float32BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2));
    if (!g.index) g.setIndex([...Array(g.attributes.position.count).keys()]);
    const m = o.material;
    if (!perMat.has(m)) perMat.set(m, []);
    perMat.get(m).push(g);
  });
  const groep = new THREE.Group();
  for (const [mat, geos] of perMat) {
    if (mat.map) { mat.map.anisotropy = anisotroop; mat.map.needsUpdate = true; }
    if (/^blad_/.test(mat.name)) doorzichtigDichtbij(mat);
    let geo = null;
    try { geo = mergeGeometries(geos, false); } catch (e) { geo = null; }
    for (const g of geo ? [geo] : geos) {
      const mesh = new THREE.Mesh(g, mat);
      const naam = mat.name || '';
      mesh.castShadow = !['gras', 'asfalt', 'markering', 'stoep', 'water', 'glas', 'zand'].includes(naam);
      mesh.receiveShadow = naam !== 'glas';
      if (naam === 'glas') mesh.renderOrder = 2;
      groep.add(mesh);
    }
    if (geo) geos.forEach((g) => g.dispose());
  }
  return groep;
}

/** Bladeren vlak voor de camera lossen op in een korrelpatroon, zodat een boom het zicht niet wegneemt. */
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
}

// ---------- botsen en grond ----------
function opStoep(x, z) {
  const binnen = (v) => stad.blokken.some(([a, b]) => v >= a && v <= b);
  return binnen(x) && binnen(z);
}
function grondHoogte(x, z) { return opStoep(x, z) ? stad.stoephoogte : 0; }

function duwUitCirkel(p, cx, cz, r) {
  const dx = p.x - cx, dz = p.z - cz;
  const d = Math.hypot(dx, dz), min = r + STRAAL;
  if (d < min && d > 1e-6) { p.x = cx + dx / d * min; p.z = cz + dz / d * min; }
}

function botsUit(p, dynamisch) {
  for (let ronde = 0; ronde < 2; ronde++) {
    for (const v of stad.vakken) {
      const [x0, z0, x1, z1] = v;
      if (p.x < x0 - STRAAL || p.x > x1 + STRAAL || p.z < z0 - STRAAL || p.z > z1 + STRAAL) continue;
      if (v[4] < 1.0 && speler.y > v[4] + 0.05) continue;             // over lage dingen heen springen
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
    for (const c of dynamisch) duwUitCirkel(p, c.x, c.z, c.r);
  }
  const g = stad.grens;
  p.x = Math.max(-g, Math.min(g, p.x));
  p.z = Math.max(-g, Math.min(g, p.z));
}

/** Hoe ver kan de camera vanaf het doel in richting d, voor ze een gebouw raakt? */
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
  if (e.code === 'KeyM') { kaartAan = !kaartAan; el.kaart.hidden = !kaartAan; }
  if (e.code === 'KeyV') wisselZicht();
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

// ---------- starten en pauzeren ----------
function start() {
  if (!stad) return;
  el.intro.hidden = true;
  bezig = true;
  el.pauze.hidden = !aanraak;
  el.zicht.hidden = !aanraak;
  el.kaart.hidden = !kaartAan;
  el.vizier.hidden = !cam.ik || aanraak;
  if (!aanraak && !vrijeMuis && el.doek.requestPointerLock) vergrendel();
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
  el.wandel.textContent = 'Verder wandelen';
  el.wandel.focus();
}
el.wandel.addEventListener('click', start);
el.pauze.addEventListener('click', pauzeer);
el.zicht.addEventListener('click', wisselZicht);
addEventListener('keydown', (e) => {
  if (e.code === 'Escape' && bezig && (vrijeMuis || document.pointerLockElement !== el.doek)) pauzeer();
});

// ---------- kaart ----------
const kaartBasis = document.createElement('canvas');
function tekenKaartBasis() {
  const n = 360;
  kaartBasis.width = kaartBasis.height = n;
  const c = kaartBasis.getContext('2d');
  const g = stad.grens;
  const s = n / (2 * g);
  const px = (x) => (x + g) * s;
  c.fillStyle = '#4c6b3a';
  c.fillRect(0, 0, n, n);
  const r = stad.straten;
  const half = (r[r.length - 1] - r[0]) / 2 + 5;
  c.fillStyle = '#55575c';
  c.fillRect(px(-half), px(-half), 2 * half * s, 2 * half * s);
  c.fillStyle = '#a7a39a';
  for (const [a0, a1] of stad.blokken) for (const [b0, b1] of stad.blokken) c.fillRect(px(a0), px(b0), (a1 - a0) * s, (b1 - b0) * s);
  const p = stad.park;
  c.fillStyle = '#6f9a4e';
  c.fillRect(px(p.x0), px(p.z0), (p.x1 - p.x0) * s, (p.z1 - p.z0) * s);
  c.fillStyle = '#e9e4d8';
  for (const [x0, z0, x1, z1] of stad.vakken) {
    if ((x1 - x0) * (z1 - z0) < 3) continue;
    c.fillRect(px(x0), px(z0), Math.max(1, (x1 - x0) * s), Math.max(1, (z1 - z0) * s));
  }
}
function tekenKaart() {
  const c = el.kaart.getContext('2d');
  const w = el.kaart.width;
  const zicht = 70;
  const g = stad.grens;
  const s = kaartBasis.width / (2 * g);
  const m = w / (2 * zicht);
  c.clearRect(0, 0, w, w);
  c.save();
  c.beginPath();
  if (c.roundRect) c.roundRect(0, 0, w, w, 14); else c.rect(0, 0, w, w);
  c.clip();
  c.globalAlpha = 0.92;
  c.drawImage(kaartBasis, (speler.x - zicht + g) * s, (speler.z - zicht + g) * s, 2 * zicht * s, 2 * zicht * s, 0, 0, w, w);
  c.globalAlpha = 1;
  for (const v of leven.voertuigen) {
    const x = (v.pos[0] - speler.x) * m + w / 2, y = (v.pos[1] - speler.z) * m + w / 2;
    if (x < -5 || y < -5 || x > w + 5 || y > w + 5) continue;
    c.fillStyle = v.type === 'Bus' ? '#2b6cb0' : v.type === 'Taxi' ? '#f5c518' : v.B < 1 ? '#7ec8e3' : '#f4f4f0';
    const r = v.type === 'Bus' ? 4 : v.B < 1 ? 1.6 : 2.6;
    c.fillRect(x - r, y - r, 2 * r, 2 * r);
  }
  c.translate(w / 2, w / 2);
  c.rotate(-(cam.ik ? cam.yaw : speler.kop));
  c.fillStyle = '#f1c27d';
  c.strokeStyle = '#1a1408';
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
  const sin = Math.sin(cam.yaw), cos = Math.cos(cam.yaw);
  doelV.set((-sin * vooruit + cos * opzij) * snel, (-cos * vooruit - sin * opzij) * snel);
  const k = 1 - Math.exp(-(speler.opGrond ? 10 : 2.5) * dt);
  speler.vx += (doelV.x - speler.vx) * k;
  speler.vz += (doelV.y - speler.vz) * k;

  const p = { x: speler.x + speler.vx * dt, z: speler.z + speler.vz * dt };
  botsUit(p, leven.botsers());
  const verplaatst = Math.hypot(p.x - speler.x, p.z - speler.z);
  const snelheid = verplaatst / Math.max(dt, 1e-4);
  speler.x = p.x;
  speler.z = p.z;

  const grond = grondHoogte(speler.x, speler.z);
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
  speler.snel = snelheid > 3.5;
  speler.opStraat = !opStoep(speler.x, speler.z);

  // het mannetje draait mee met waar hij heen loopt
  if (cam.ik) speler.kop = cam.yaw;
  else if (Math.hypot(speler.vx, speler.vz) > 0.3) {
    let v = Math.atan2(-speler.vx, -speler.vz) - speler.kop;
    v = Math.atan2(Math.sin(v), Math.cos(v));
    speler.kop += v * Math.min(1, dt * 12);
  }
  const m = mannetje;
  m.obj.position.set(speler.x, speler.y, speler.z);
  m.obj.rotation.y = speler.kop;
  if (!speler.opGrond) {
    m.d.beenL.rotation.x = 0.6; m.d.beenR.rotation.x = -0.25;
    m.d.knieL.rotation.x = -0.9; m.d.knieR.rotation.x = -0.3;
    m.d.armL.rotation.x = -0.4; m.d.armR.rotation.x = 0.9;
  } else {
    const rennen = snelheid > 3.5;
    m.fase += verplaatst * Math.PI * 2 / (rennen ? 2.3 : 1.35);
    const sterkte = Math.min(1, snelheid / (rennen ? 4 : 1.6));
    if (sterkte < 0.05) poseStaan(m, tijd); else poseLopen(m, sterkte, rennen);
  }

  // camera
  if (cam.ik) {
    m.obj.visible = false;
    camera.position.set(speler.x, speler.y + OOG, speler.z);
    camera.rotation.set(-cam.pitch, cam.yaw, 0);
  } else {
    doelPunt.set(speler.x, speler.y + 1.45, speler.z);
    richting.set(Math.sin(cam.yaw) * Math.cos(cam.pitch), Math.sin(cam.pitch), Math.cos(cam.yaw) * Math.cos(cam.pitch));
    const vrij = camVrij(doelPunt, richting, cam.afstand) - 0.2;
    const doel = Math.max(0.4, Math.min(cam.afstand, vrij));
    cam.huidig = doel < cam.huidig ? doel : cam.huidig + (doel - cam.huidig) * Math.min(1, dt * 3);
    camera.position.copy(doelPunt).addScaledVector(richting, cam.huidig);
    camera.lookAt(doelPunt);
    m.obj.visible = cam.huidig > 0.9;
  }

  const t = 90 / 2048;
  const sx = Math.round(speler.x / t) * t, sz = Math.round(speler.z / t) * t;
  zon.position.set(sx + ZON_RICHTING.x * 150, ZON_RICHTING.y * 150, sz + ZON_RICHTING.z * 150);
  zon.target.position.set(sx, 0, sz);
}

function maat() {
  const w = innerWidth, h = innerHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
addEventListener('resize', maat);
maat();

function lus() {
  const dt = Math.min(klok.getDelta(), 0.05);
  if (stad) {
    tijd += dt;
    if (!bezig && !minderBeweging) cam.yaw += dt * 0.05;
    leven.update(dt, tijd, speler);
    stap(dt);
    renderer.render(scene, camera);
    if (kaartAan && !el.kaart.hidden) tekenKaart();
  }
  requestAnimationFrame(lus);
}

// voor wie wil meekijken in de console
window.ministad = { speler, cam, get leven() { return leven; }, get info() { return renderer.info.render; } };

laad().then(() => {
  el.wandel.disabled = false;
  el.wandel.textContent = 'Wandel';
  el.voortgang.textContent = '';
  requestAnimationFrame(lus);
}).catch((fout) => {
  console.error(fout);
  el.wandel.textContent = 'Laden mislukt';
  el.voortgang.textContent = 'De stad kon niet geladen worden. Herlaad de pagina.';
});
