// Wereld Ruimte: traag vliegen door sterrenvelden, nevels en verre planeten.
import * as THREE from 'three';

export const info = {
  id: 'ruimte',
  naam: 'Ruimte',
  muziek: 'materiaal/audio/ruimte/ruimte.mp3',
  snelheid: 7,
  stuurbereik: { x: 6, y: 3 },
  achtergrond: '#03040a'
};

// Het pad: trage sinussen, helling < 0.25 (max. 0.125 + 0.087 in x, ~0.08 in y).
export function pad(s, uit) {
  const x = 50 * Math.sin(s / 400) + 20 * Math.sin(s / 230 + 1.3);
  const y = 14 * Math.sin(s / 310 + 0.7) + 6 * Math.sin(s / 170);
  return uit.set(x, y, -s);
}

// ---------- toestand op moduleniveau ----------
let scene = null;
let opt = null;
let objecten = [];       // alles wat in de scene hangt
let geos = [];
let mats = [];
let textures = [];
let lagen = [];          // sterrenlagen { punten, aantal }
let sky = null;
let nevels = [];         // { sprite, basis, p, anker }
let planeten = [];       // { mesh, p, anker, draai }
let lichtZon = null;
let lichtOm = null;
let lichaam = null;      // passerend hemellichaam
let lichaamMat = null;
let lichaamTex = null;
let lichaamActief = false;
let lichaamLeeftijd = 0;
let volgendeSpawn = 0;
let rotatieMul = 1;
let laag = false;
let ademS = 1;
let helderS = 1;
let laagS = 0;
let rng = null;
const tmp = new THREE.Vector3();
const tmp2 = new THREE.Vector2();

const KLEUREN = [
  [1.0, 1.0, 1.0], [0.75, 0.85, 1.0], [0.6, 0.75, 1.0],
  [1.0, 0.92, 0.78], [1.0, 0.82, 0.62]
];

function maakRng(zaad) {
  let a = zaad >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function canvasTex(b, h) {
  const c = document.createElement('canvas');
  c.width = b; c.height = h;
  return c;
}

function naarTextuur(c) {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 1;
  textures.push(t);
  return t;
}

// ---------- sterren ----------
const sterVS = `
uniform vec3 uCam;
uniform vec3 uBox;
uniform float uScale;
uniform float uAdem;
uniform float uHelder;
uniform float uMin;
uniform float uMax;
attribute vec3 aColor;
attribute float aSize;
varying vec3 vColor;
varying float vAlpha;
void main() {
  vec3 b = position * uBox;
  float rx = mod(b.x - uCam.x, uBox.x) - 0.5 * uBox.x;
  float ry = mod(b.y - uCam.y, uBox.y) - 0.5 * uBox.y;
  float d = mod(uCam.z - b.z, uBox.z);
  vec3 wp = vec3(uCam.x + rx, uCam.y + ry, uCam.z - d);
  vec4 mv = modelViewMatrix * vec4(wp, 1.0);
  gl_Position = projectionMatrix * mv;
  float dist = max(-mv.z, 1.0);
  float px = aSize * uScale * uAdem / dist;
  gl_PointSize = clamp(px, uMin, uMax);
  float fade = smoothstep(0.0, uBox.z * 0.08, d) * (1.0 - smoothstep(uBox.z * 0.75, uBox.z, d));
  fade *= 1.0 - smoothstep(0.38, 0.5, abs(rx) / uBox.x);
  fade *= 1.0 - smoothstep(0.38, 0.5, abs(ry) / uBox.y);
  float dim = clamp(px / uMin, 0.35, 1.0);
  vAlpha = fade * dim * uHelder;
  vColor = aColor;
}`;

const sterFS = `
varying vec3 vColor;
varying float vAlpha;
void main() {
  float r = length(gl_PointCoord - 0.5) * 2.0;
  if (r > 1.0) discard;
  float a = pow(1.0 - r, 2.0);
  gl_FragColor = vec4(vColor, a * vAlpha);
}`;

const skyVS = `
uniform float uPix;
uniform float uHelder;
attribute vec3 aColor;
attribute float aSize;
varying vec3 vColor;
varying float vAlpha;
void main() {
  vec4 mv = modelViewMatrix * vec4(position * 1000.0, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = max(aSize * uPix, 1.0);
  vAlpha = clamp(aSize * uPix, 0.4, 1.0) * uHelder;
  vColor = aColor;
}`;

function sterGeo(n, bx, by, bz, grootte) {
  const pos = new Float32Array(n * 3);
  const kl = new Float32Array(n * 3);
  const gr = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    pos[i * 3] = rng(); pos[i * 3 + 1] = rng(); pos[i * 3 + 2] = rng();
    const k = KLEUREN[Math.floor(rng() * KLEUREN.length)];
    const h = 0.45 + 0.55 * Math.pow(rng(), 1.6);
    kl[i * 3] = k[0] * h; kl[i * 3 + 1] = k[1] * h; kl[i * 3 + 2] = k[2] * h;
    gr[i] = grootte * (0.5 + 1.5 * Math.pow(rng(), 3));
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('aColor', new THREE.BufferAttribute(kl, 3));
  g.setAttribute('aSize', new THREE.BufferAttribute(gr, 1));
  geos.push(g);
  return g;
}

function maakLaag(n, bx, by, bz, grootte, min, max) {
  const g = sterGeo(n, bx, by, bz, grootte);
  const m = new THREE.ShaderMaterial({
    vertexShader: sterVS,
    fragmentShader: sterFS,
    uniforms: {
      uCam: { value: new THREE.Vector3() },
      uBox: { value: new THREE.Vector3(bx, by, bz) },
      uScale: { value: 700 },
      uAdem: { value: 1 },
      uHelder: { value: 1 },
      uMin: { value: min },
      uMax: { value: max }
    },
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending
  });
  mats.push(m);
  const p = new THREE.Points(g, m);
  p.frustumCulled = false;
  p.renderOrder = -4;
  scene.add(p);
  objecten.push(p);
  lagen.push({ punten: p, aantal: n });
}

function maakSky(n) {
  const pos = new Float32Array(n * 3);
  const kl = new Float32Array(n * 3);
  const gr = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const u = rng() * 2 - 1, a = rng() * Math.PI * 2;
    const r = Math.sqrt(1 - u * u);
    pos[i * 3] = r * Math.cos(a); pos[i * 3 + 1] = u; pos[i * 3 + 2] = r * Math.sin(a);
    const k = KLEUREN[Math.floor(rng() * KLEUREN.length)];
    const h = 0.35 + 0.5 * rng();
    kl[i * 3] = k[0] * h; kl[i * 3 + 1] = k[1] * h; kl[i * 3 + 2] = k[2] * h;
    gr[i] = 0.8 + 1.4 * Math.pow(rng(), 3);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('aColor', new THREE.BufferAttribute(kl, 3));
  g.setAttribute('aSize', new THREE.BufferAttribute(gr, 1));
  geos.push(g);
  const m = new THREE.ShaderMaterial({
    vertexShader: skyVS,
    fragmentShader: sterFS,
    uniforms: { uPix: { value: 1 }, uHelder: { value: 1 } },
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending
  });
  mats.push(m);
  const p = new THREE.Points(g, m);
  p.frustumCulled = false;
  p.renderOrder = -10;
  scene.add(p);
  objecten.push(p);
  sky = { punten: p, aantal: n };
}

// ---------- nevels ----------
function nevelTextuur(rgb) {
  const c = canvasTex(256, 256);
  const x = c.getContext('2d');
  x.clearRect(0, 0, 256, 256);
  for (let i = 0; i < 14; i++) {
    const cx = 128 + (rng() - 0.5) * 120;
    const cy = 128 + (rng() - 0.5) * 120;
    const r = 40 + rng() * 70;
    const v = 0.8 + rng() * 0.4;
    const kl = rgb.map(w => Math.min(255, Math.round(w * v)));
    const gr = x.createRadialGradient(cx, cy, 0, cx, cy, r);
    gr.addColorStop(0, `rgba(${kl[0]},${kl[1]},${kl[2]},0.30)`);
    gr.addColorStop(0.5, `rgba(${kl[0]},${kl[1]},${kl[2]},0.10)`);
    gr.addColorStop(1, `rgba(${kl[0]},${kl[1]},${kl[2]},0)`);
    x.fillStyle = gr;
    x.fillRect(0, 0, 256, 256);
  }
  // rand zacht uitfaden
  const rand = x.createRadialGradient(128, 128, 60, 128, 128, 128);
  rand.addColorStop(0, 'rgba(0,0,0,1)');
  rand.addColorStop(1, 'rgba(0,0,0,0)');
  x.globalCompositeOperation = 'destination-in';
  x.fillStyle = rand;
  x.fillRect(0, 0, 256, 256);
  return naarTextuur(c);
}

function maakNevels() {
  const def = [
    { rgb: [150, 90, 230], x: -380, y: 160, z: -900, g: 900, o: 0.30, p: 0.985 },
    { rgb: [70, 120, 230], x: 420, y: -120, z: -1000, g: 1000, o: 0.26, p: 0.99 },
    { rgb: [50, 190, 190], x: 60, y: 300, z: -1100, g: 800, o: 0.22, p: 0.99 },
    { rgb: [120, 80, 200], x: -200, y: -260, z: -850, g: 700, o: 0.20, p: 0.985 }
  ];
  for (const d of def) {
    const m = new THREE.SpriteMaterial({
      map: nevelTextuur(d.rgb),
      transparent: true,
      opacity: d.o,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      fog: false
    });
    mats.push(m);
    const s = new THREE.Sprite(m);
    s.scale.set(d.g, d.g, 1);
    s.renderOrder = -6;
    s.frustumCulled = false;
    scene.add(s);
    objecten.push(s);
    nevels.push({ sprite: s, basis: d.o, p: d.p, anker: new THREE.Vector3(d.x, d.y, d.z) });
  }
}

// ---------- planeten ----------
function bandenTextuur(paletten, zaad) {
  const r = maakRng(zaad);
  const c = canvasTex(512, 256);
  const x = c.getContext('2d');
  const f1 = 2 + r() * 3, f2 = 5 + r() * 6, f3 = 13 + r() * 9;
  const p1 = r() * 6, p2 = r() * 6, p3 = r() * 6;
  for (let y = 0; y < 256; y += 2) {
    const t = y / 256;
    const w = 0.5 + 0.25 * Math.sin(t * f1 * 6.28 + p1) + 0.18 * Math.sin(t * f2 * 6.28 + p2) + 0.07 * Math.sin(t * f3 * 6.28 + p3);
    const k = Math.min(1, Math.max(0, w)) * (paletten.length - 1);
    const i = Math.floor(k), fr = k - i;
    const a = paletten[i], b = paletten[Math.min(i + 1, paletten.length - 1)];
    x.fillStyle = `rgb(${Math.round(a[0] + (b[0] - a[0]) * fr)},${Math.round(a[1] + (b[1] - a[1]) * fr)},${Math.round(a[2] + (b[2] - a[2]) * fr)})`;
    x.fillRect(0, y, 512, 2);
  }
  // zachte vlekken
  for (let i = 0; i < 18; i++) {
    const cx = r() * 512, cy = r() * 256, rr = 10 + r() * 30;
    const gr = x.createRadialGradient(cx, cy, 0, cx, cy, rr);
    const l = r() < 0.5 ? '255,255,255' : '0,0,0';
    gr.addColorStop(0, `rgba(${l},0.10)`);
    gr.addColorStop(1, `rgba(${l},0)`);
    x.fillStyle = gr;
    x.fillRect(cx - rr, cy - rr, rr * 2, rr * 2);
  }
  return naarTextuur(c);
}

function maakPlaneten() {
  const geo = new THREE.SphereGeometry(1, 32, 24);
  geos.push(geo);

  // reuzenplaneet, blauwgroen
  const mA = new THREE.MeshLambertMaterial({
    map: bandenTextuur([[28, 60, 78], [60, 120, 135], [120, 170, 165], [70, 100, 140], [200, 215, 200]], 11)
  });
  mats.push(mA);
  const A = new THREE.Mesh(geo, mA);
  A.scale.setScalar(95);
  A.rotation.z = 0.25;
  A.renderOrder = -2;
  A.frustumCulled = false;
  scene.add(A);
  objecten.push(A);
  planeten.push({ mesh: A, p: 0.995, anker: new THREE.Vector3(-300, 70, -820), draai: 0.004 });

  // warme planeet met ring
  const mB = new THREE.MeshLambertMaterial({
    map: bandenTextuur([[90, 50, 38], [170, 110, 70], [225, 180, 125], [140, 80, 60]], 29)
  });
  mats.push(mB);
  const B = new THREE.Mesh(geo, mB);
  B.scale.setScalar(42);
  B.rotation.z = 0.35;
  B.renderOrder = -2;
  B.frustumCulled = false;
  scene.add(B);
  objecten.push(B);

  const ringGeo = new THREE.RingGeometry(1.5, 2.3, 64);
  geos.push(ringGeo);
  const ringMat = new THREE.MeshBasicMaterial({
    color: 0xd8c3a0,
    transparent: true,
    opacity: 0.32,
    side: THREE.DoubleSide,
    depthWrite: false
  });
  mats.push(ringMat);
  const ring = new THREE.Mesh(ringGeo, ringMat);
  ring.rotation.x = Math.PI / 2 - 0.35;
  ring.frustumCulled = false;
  B.add(ring);
  planeten.push({ mesh: B, p: 0.995, anker: new THREE.Vector3(360, -80, -640), draai: 0.006 });
}

// ---------- passerend hemellichaam ----------
function maakLichaam() {
  const c = canvasTex(256, 128);
  const x = c.getContext('2d');
  x.fillStyle = '#9aa3b0';
  x.fillRect(0, 0, 256, 128);
  for (let i = 0; i < 40; i++) {
    const cx = rng() * 256, cy = rng() * 128, r = 4 + rng() * 22;
    const gr = x.createRadialGradient(cx, cy, 0, cx, cy, r);
    const donker = rng() < 0.6;
    gr.addColorStop(0, donker ? 'rgba(40,45,60,0.45)' : 'rgba(240,245,255,0.35)');
    gr.addColorStop(1, 'rgba(0,0,0,0)');
    x.fillStyle = gr;
    x.fillRect(cx - r, cy - r, r * 2, r * 2);
  }
  lichaamTex = naarTextuur(c);
  lichaamMat = new THREE.MeshLambertMaterial({ map: lichaamTex, transparent: true, opacity: 0 });
  mats.push(lichaamMat);
  const g = new THREE.SphereGeometry(1, 20, 14);
  geos.push(g);
  lichaam = new THREE.Mesh(g, lichaamMat);
  lichaam.visible = false;
  lichaam.frustumCulled = false;
  scene.add(lichaam);
  objecten.push(lichaam);
}

const LICHAAMKLEUREN = [0xffffff, 0xcfe4ff, 0xe8cfb8, 0xb8c8d8];

function spawnLichaam(cam) {
  const zijde = rng() < 0.5 ? -1 : 1;
  pad(cam.s + 300, tmp);
  lichaam.position.set(
    tmp.x + zijde * (22 + rng() * 12),
    tmp.y + (rng() < 0.5 ? -1 : 1) * (6 + rng() * 10),
    tmp.z
  );
  lichaam.scale.setScalar(3 + rng() * 3);
  lichaamMat.color.setHex(LICHAAMKLEUREN[Math.floor(rng() * LICHAAMKLEUREN.length)]);
  lichaamMat.opacity = 0;
  lichaam.visible = true;
  lichaamActief = true;
  lichaamLeeftijd = 0;
}

// ---------- interface ----------
export function create(sc, analyser, opties) {
  scene = sc;
  opt = opties || {};
  rng = maakRng(20240607);
  objecten = []; geos = []; mats = []; textures = [];
  lagen = []; nevels = []; planeten = [];
  lichaamActief = false;
  volgendeSpawn = 6;
  ademS = 1; helderS = 1; laagS = 0;
  rotatieMul = opt.minderBeweging ? 0 : 1;

  scene.background = new THREE.Color(info.achtergrond);
  scene.fog = null;

  maakSky(900);
  maakLaag(2600, 500, 300, 400, 2.2, 1.5, 7);     // dichtbij
  maakLaag(2800, 1200, 700, 900, 5, 1.4, 6);      // midden
  maakLaag(2000, 2400, 1400, 1400, 9, 1.3, 5);    // ver
  maakNevels();
  maakPlaneten();
  maakLichaam();

  lichtZon = new THREE.DirectionalLight(0xfff2e0, 1.6);
  lichtZon.position.set(-0.6, 0.35, 1);
  lichtOm = new THREE.AmbientLight(0x303a5c, 0.9);
  scene.add(lichtZon, lichtOm);
  objecten.push(lichtZon, lichtOm);

  laag = false;
  setKwaliteit(opt.kwaliteit === 'laag' ? 'laag' : 'hoog');
}

export function update(tijd, audio, cam) {
  if (!scene) return;
  const dt = Math.min(cam.dt || 0.016, 0.1);
  const cp = cam.positie;

  // zachte, kleine reactie op de muziek
  const k = 1 - Math.exp(-dt * 3);
  ademS += ((1 + 0.14 * audio.niveau) - ademS) * k;
  helderS += ((0.92 + 0.2 * audio.hoog) - helderS) * k;
  laagS += (audio.laag - laagS) * k;

  // schaal voor puntgroottes (pixels per wereldeenheid op 1 eenheid afstand)
  let h = 800;
  if (opt.renderer) { opt.renderer.getDrawingBufferSize(tmp2); h = tmp2.y || 800; }
  const fov = (cam.camera && cam.camera.fov) || 60;
  const schaal = 0.5 * h / Math.tan(fov * Math.PI / 360);

  for (const l of lagen) {
    const u = l.punten.material.uniforms;
    u.uCam.value.copy(cp);
    u.uScale.value = schaal;
    u.uAdem.value = ademS;
    u.uHelder.value = helderS;
  }
  if (sky) {
    sky.punten.position.copy(cp);
    sky.punten.material.uniforms.uPix.value = h / 800;
    sky.punten.material.uniforms.uHelder.value = helderS;
  }

  for (const n of nevels) {
    n.sprite.position.copy(cp).multiplyScalar(n.p).add(n.anker);
    n.sprite.material.opacity = n.basis + 0.1 * laagS;
  }
  for (const p of planeten) {
    p.mesh.position.copy(cp).multiplyScalar(p.p).add(p.anker);
    p.mesh.rotation.y += p.draai * dt * rotatieMul;
  }

  // passerend lichaam
  if (!lichaamActief) {
    if (tijd >= volgendeSpawn) spawnLichaam(cam);
  } else {
    lichaamLeeftijd += dt;
    lichaamMat.opacity = Math.min(1, lichaamLeeftijd / 4);
    lichaam.rotation.y += 0.05 * dt * rotatieMul;
    if (lichaam.position.z > cp.z + 40) {
      lichaam.visible = false;
      lichaamActief = false;
      volgendeSpawn = tijd + 5 + rng() * 25;
    }
  }
}

export function setKwaliteit(niveau) {
  laag = niveau === 'laag';
  for (const l of lagen) l.punten.geometry.setDrawRange(0, laag ? Math.floor(l.aantal / 2) : l.aantal);
  if (sky) sky.punten.geometry.setDrawRange(0, laag ? Math.floor(sky.aantal / 2) : sky.aantal);
  if (nevels[3]) nevels[3].sprite.visible = !laag;
}

export function dispose() {
  if (scene) {
    for (const o of objecten) scene.remove(o);
    scene.background = null;
    scene.fog = null;
  }
  for (const g of geos) g.dispose();
  for (const m of mats) m.dispose();
  for (const t of textures) t.dispose();
  scene = null; opt = null;
  objecten = []; geos = []; mats = []; textures = [];
  lagen = []; sky = null; nevels = []; planeten = [];
  lichtZon = null; lichtOm = null;
  lichaam = null; lichaamMat = null; lichaamTex = null;
  lichaamActief = false;
  rng = null;
}
