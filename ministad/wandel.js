// Ministad — wandelen door de stad die blender/bouw_stad.py heeft gebouwd.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const WANDEL = 4.2;          // m/s
const LOOP = 8.0;            // m/s met Shift
const STRAAL = 0.35;         // breedte van de wandelaar
const SPRONG = 4.6;          // beginsnelheid omhoog
const ZWAARTE = 13;
const STOEP_H = 0.15;
const MUIS = 0.0022;         // rad per pixel
const VEEG = 0.0055;         // rad per pixel bij aanraken
const ZON_RICHTING = new THREE.Vector3(-0.45, 0.8, 0.4).normalize();

const $ = (id) => document.getElementById(id);
const el = {
  doek: $('doek'), intro: $('intro'), wandel: $('wandel'), voortgang: $('voortgang'),
  pauze: $('pauze'), kaart: $('kaart'), stok: $('stok'), vizier: $('vizier')
};
const aanraak = matchMedia('(pointer: coarse)').matches && !matchMedia('(pointer: fine)').matches;
document.documentElement.classList.toggle('is-aanraak', aanraak);
const minderBeweging = matchMedia('(prefers-reduced-motion: reduce)').matches;

// ---------- renderer en scène ----------
const renderer = new THREE.WebGLRenderer({ canvas: el.doek, antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;

const scene = new THREE.Scene();
const HORIZON = new THREE.Color('#dce7ef');
scene.fog = new THREE.Fog(HORIZON, 90, 430);
scene.background = HORIZON;

const camera = new THREE.PerspectiveCamera(70, 1, 0.1, 1200);
camera.rotation.order = 'YXZ';

// lucht: verloop van horizon naar zenit, ook zonder textuur
{
  const geo = new THREE.SphereGeometry(900, 32, 16);
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false,
    uniforms: {
      zenit: { value: new THREE.Color('#5d93cf') },
      horizon: { value: HORIZON },
      zon: { value: ZON_RICHTING }
    },
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
  const lucht = new THREE.Mesh(geo, mat);
  lucht.renderOrder = -1;
  lucht.frustumCulled = false;
  lucht.onBeforeRender = () => lucht.position.copy(camera.position);
  scene.add(lucht);
}

scene.add(new THREE.HemisphereLight('#cfe2f5', '#7a7f5c', 1.25));
const zon = new THREE.DirectionalLight('#fff0d8', 2.6);
zon.castShadow = true;
zon.shadow.mapSize.set(2048, 2048);
Object.assign(zon.shadow.camera, { left: -55, right: 55, top: 55, bottom: -55, near: 1, far: 300 });
zon.shadow.bias = -0.0004;
zon.shadow.normalBias = 0.04;
scene.add(zon, zon.target);

// ---------- toestand van de wandelaar ----------
const speler = {
  x: 0, z: 0, y: 0,          // y = hoogte van de voeten
  vy: 0, opGrond: true,
  yaw: 0, pitch: 0,
  vx: 0, vz: 0,
  stap: 0
};
let stad = null;              // gegevens uit botsing.json
let bezig = false;            // wandelen (niet gepauzeerd)
const toets = new Set();
let kaartAan = true;

// ---------- laden ----------
async function laad() {
  const [data, gltf] = await Promise.all([
    fetch('botsing.json').then((r) => { if (!r.ok) throw new Error('botsing.json'); return r.json(); }),
    new GLTFLoader().loadAsync('ministad.glb', (e) => {
      if (e.total) el.voortgang.textContent = 'Stad laden: ' + Math.round(e.loaded / e.total * 100) + '%';
    })
  ]);
  stad = data;
  scene.add(voegSamen(gltf.scene));
  speler.x = data.start.x;
  speler.z = data.start.z;
  speler.yaw = data.start.richting || 0;
  speler.y = grondHoogte(speler.x, speler.z);
  tekenKaartBasis();
}

/** Voegt alle meshes met hetzelfde materiaal samen: van ~1400 naar ~40 tekenopdrachten. */
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
    if (!g.index) g.setIndex([...Array(g.attributes.position.count).keys()]);
    const m = o.material;
    if (!perMat.has(m)) perMat.set(m, []);
    perMat.get(m).push(g);
  });
  const groep = new THREE.Group();
  for (const [mat, geos] of perMat) {
    if (mat.map) {
      mat.map.anisotropy = anisotroop;
      mat.map.needsUpdate = true;
    }
    let geo = null;
    try { geo = mergeGeometries(geos, false); } catch (e) { geo = null; }
    const stukken = geo ? [geo] : geos;
    for (const g of stukken) {
      const mesh = new THREE.Mesh(g, mat);
      const naam = mat.name || '';
      mesh.castShadow = !['gras', 'asfalt', 'markering', 'stoep', 'water'].includes(naam);
      mesh.receiveShadow = true;
      groep.add(mesh);
    }
    if (geo) geos.forEach((g) => g.dispose());
  }
  return groep;
}

// ---------- botsen en grond ----------
function opStoep(x, z) {
  const binnen = (v) => stad.blokken.some(([a, b]) => v >= a && v <= b);
  return binnen(x) && binnen(z);
}
function grondHoogte(x, z) { return opStoep(x, z) ? STOEP_H : 0; }

/** Duwt een cirkel uit alle botsvakken; geeft glijden langs muren. */
function botsUit(p) {
  for (let ronde = 0; ronde < 2; ronde++) {
    for (const [x0, z0, x1, z1] of stad.vakken) {
      if (p.x < x0 - STRAAL || p.x > x1 + STRAAL || p.z < z0 - STRAAL || p.z > z1 + STRAAL) continue;
      const nx = Math.max(x0, Math.min(p.x, x1));
      const nz = Math.max(z0, Math.min(p.z, z1));
      let dx = p.x - nx, dz = p.z - nz;
      const d2 = dx * dx + dz * dz;
      if (d2 > STRAAL * STRAAL) continue;
      if (d2 > 1e-10) {
        const d = Math.sqrt(d2);
        p.x = nx + dx / d * STRAAL;
        p.z = nz + dz / d * STRAAL;
      } else {
        // middelpunt in het vak: langs de kortste weg naar buiten
        const uit = [[p.x - x0 + STRAAL, -1, 0], [x1 - p.x + STRAAL, 1, 0], [p.z - z0 + STRAAL, 0, -1], [z1 - p.z + STRAAL, 0, 1]]
          .sort((a, b) => a[0] - b[0])[0];
        p.x += uit[1] * uit[0];
        p.z += uit[2] * uit[0];
      }
    }
  }
  const g = stad.grens;
  p.x = Math.max(-g, Math.min(g, p.x));
  p.z = Math.max(-g, Math.min(g, p.z));
}

// ---------- invoer: toetsenbord en muis ----------
const BEWEEG = { KeyW: 'v', ArrowUp: 'v', KeyS: 'a', ArrowDown: 'a', KeyA: 'l', ArrowLeft: 'l', KeyD: 'r', ArrowRight: 'r' };
addEventListener('keydown', (e) => {
  if (!bezig) return;
  if (BEWEEG[e.code]) { toets.add(BEWEEG[e.code]); e.preventDefault(); }
  if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') toets.add('loop');
  if (e.code === 'Space') { spring(); e.preventDefault(); }
  if (e.code === 'KeyM') { kaartAan = !kaartAan; el.kaart.hidden = !kaartAan; }
});
addEventListener('keyup', (e) => {
  if (BEWEEG[e.code]) toets.delete(BEWEEG[e.code]);
  if (e.code === 'ShiftLeft' || e.code === 'ShiftRight') toets.delete('loop');
});
addEventListener('blur', () => toets.clear());

function spring() {
  if (speler.opGrond) { speler.vy = SPRONG; speler.opGrond = false; }
}

function draai(dx, dy, gevoel) {
  speler.yaw -= dx * gevoel;
  speler.pitch = Math.max(-1.45, Math.min(1.45, speler.pitch - dy * gevoel));
}

document.addEventListener('mousemove', (e) => {
  if (!bezig || document.pointerLockElement !== el.doek) return;
  // sommige browsers sturen bij het vergrendelen één enorme sprong: negeren
  if (Math.abs(e.movementX) > 250 || Math.abs(e.movementY) > 250) return;
  draai(e.movementX, e.movementY, MUIS);
});
document.addEventListener('pointerlockchange', () => {
  if (document.pointerLockElement !== el.doek && bezig && !aanraak) pauzeer();
});
document.addEventListener('pointerlockerror', () => {
  // zonder pointer lock: slepen met de muis om rond te kijken
  vrijeMuis = true;
});
let vrijeMuis = false;
let sleep = null;
el.doek.addEventListener('mousedown', (e) => { if (bezig && vrijeMuis) sleep = { x: e.clientX, y: e.clientY }; });
addEventListener('mouseup', () => { sleep = null; });
addEventListener('mousemove', (e) => {
  if (!sleep) return;
  draai(e.clientX - sleep.x, e.clientY - sleep.y, MUIS * 1.5);
  sleep = { x: e.clientX, y: e.clientY };
});

// ---------- invoer: aanraken (links wandelen, rechts kijken) ----------
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
      if (nu - laatsteTik < 300) spring();       // dubbeltik rechts = springen
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
  el.kaart.hidden = !kaartAan;
  el.vizier.hidden = aanraak;
  if (!aanraak && el.doek.requestPointerLock) {
    try {
      const p = el.doek.requestPointerLock();
      if (p && p.catch) p.catch(() => { vrijeMuis = true; });
    } catch (e) { vrijeMuis = true; }
  }
}
function pauzeer() {
  bezig = false;
  toets.clear();
  sleep = null;
  stok.id = kijk.id = null;
  el.stok.classList.remove('actief');
  el.intro.hidden = false;
  el.pauze.hidden = true;
  el.vizier.hidden = true;
  el.wandel.textContent = 'Verder wandelen';
  el.wandel.focus();
}
el.wandel.addEventListener('click', start);
el.pauze.addEventListener('click', pauzeer);
addEventListener('keydown', (e) => {
  if (e.code === 'Escape' && bezig && vrijeMuis) pauzeer();
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
  c.fillStyle = '#e9e4d8';
  for (const [x0, z0, x1, z1] of stad.vakken) {
    if ((x1 - x0) * (z1 - z0) < 3) continue;           // kleine dingen weglaten
    c.fillRect(px(x0), px(z0), Math.max(1, (x1 - x0) * s), Math.max(1, (z1 - z0) * s));
  }
}
function tekenKaart() {
  const c = el.kaart.getContext('2d');
  const w = el.kaart.width;
  const zicht = 90;                                       // meter rondom de wandelaar
  const g = stad.grens;
  const s = kaartBasis.width / (2 * g);
  c.clearRect(0, 0, w, w);
  c.save();
  c.beginPath();
  c.roundRect ? c.roundRect(0, 0, w, w, 14) : c.rect(0, 0, w, w);
  c.clip();
  c.globalAlpha = 0.92;
  c.drawImage(kaartBasis, (speler.x - zicht + g) * s, (speler.z - zicht + g) * s, 2 * zicht * s, 2 * zicht * s, 0, 0, w, w);
  c.globalAlpha = 1;
  c.translate(w / 2, w / 2);
  c.rotate(-speler.yaw);
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

function stap(dt) {
  // gewenste richting
  let vooruit = 0, opzij = 0;
  if (toets.has('v')) vooruit += 1;
  if (toets.has('a')) vooruit -= 1;
  if (toets.has('r')) opzij += 1;
  if (toets.has('l')) opzij -= 1;
  let snel = toets.has('loop') ? LOOP : WANDEL;
  if (stok.id !== null) {
    const d = Math.hypot(stok.dx, stok.dy);
    if (d > 8) {
      const f = Math.min(1, d / 50);
      vooruit = -stok.dy / d * f;
      opzij = stok.dx / d * f;
      snel = f > 0.95 ? LOOP * 0.8 : WANDEL;
    }
  }
  const lengte = Math.hypot(vooruit, opzij);
  if (lengte > 1) { vooruit /= lengte; opzij /= lengte; }
  const sin = Math.sin(speler.yaw), cos = Math.cos(speler.yaw);
  doelV.set((-sin * vooruit + cos * opzij) * snel, (-cos * vooruit - sin * opzij) * snel);
  const k = 1 - Math.exp(-(speler.opGrond ? 12 : 3) * dt);
  speler.vx += (doelV.x - speler.vx) * k;
  speler.vz += (doelV.y - speler.vz) * k;

  const p = { x: speler.x + speler.vx * dt, z: speler.z + speler.vz * dt };
  botsUit(p);
  const verplaatst = Math.hypot(p.x - speler.x, p.z - speler.z);
  speler.x = p.x;
  speler.z = p.z;

  // hoogte: zwaartekracht, springen en de stoeprand opstappen
  const grond = grondHoogte(speler.x, speler.z);
  speler.vy -= ZWAARTE * dt;
  speler.y += speler.vy * dt;
  if (speler.y <= grond) {
    if (speler.opGrond && grond > speler.y) speler.y += (grond - speler.y) * Math.min(1, dt * 18);
    else speler.y = grond;
    speler.vy = 0;
    speler.opGrond = true;
  } else if (speler.opGrond && speler.y - grond < 0.2 && speler.vy <= 0) {
    speler.y = Math.max(grond, speler.y - dt * 2.5);     // stoep af
    speler.vy = 0;
  } else {
    speler.opGrond = false;
  }

  // camera, met een lichte stapbeweging
  speler.stap += verplaatst * 1.9;
  const deining = speler.opGrond && !minderBeweging ? Math.sin(speler.stap) * 0.035 * Math.min(1, verplaatst / (dt * WANDEL + 1e-6)) : 0;
  camera.position.set(speler.x, speler.y + stad.ooghoogte + deining, speler.z);
  camera.rotation.set(speler.pitch, speler.yaw, 0);

  // de zon volgt de wandelaar zodat de schaduwen scherp blijven
  const t = 110 / 2048;                                    // één schaduwtexel: afronden tegen flikkeren
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
    if (bezig) stap(dt);
    else {
      // in de pauze traag rondkijken
      if (!minderBeweging) speler.yaw += dt * 0.04;
      stap(0.0001);
    }
    renderer.render(scene, camera);
    if (kaartAan && !el.kaart.hidden) tekenKaart();
  }
  requestAnimationFrame(lus);
}

// voor wie wil meekijken in de console
window.ministad = { speler };

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
