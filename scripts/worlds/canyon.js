// Wereld Canyon: traag vliegen tussen rode canyonwanden, laag boven een rivier.
import * as THREE from 'three';

export const info = {
  id: 'canyon',
  naam: 'Canyon',
  muziek: 'materiaal/audio/canyon/canyon.mp3',
  snelheid: 6,
  stuurbereik: { x: 4, y: 1.5 },
  achtergrond: '#c98f66'
};

// Het pad: rivier met trage bochten (helling max. 0.1 + 0.066), vaste hoogte boven het water.
export function pad(s, uit) {
  const x = 6 * Math.sin(s / 60) + 2.5 * Math.sin(s / 38 + 1.3);
  const y = 4.5 + 0.25 * Math.sin(s / 45);
  return uit.set(x, y, -s);
}

// ---------- constanten ----------
const L = 60;            // lengte van een segment
const N = 10;            // aantal segmenten: k-1 .. k+8 rond de camera
const HALF = 16;         // profielpunten per kant (0 = midden van de rivier)
const COL = HALF * 2 - 1;
const WAND = [0.06, 0.14, 0.24, 0.35, 0.46, 0.58, 0.7, 0.82, 0.92, 1.0];
const TEX_H = 96;        // hoogte die de bandentextuur dekt
const ZON = 2.3;
const BEAM_N = 4;
const BEAM_AFSTAND = 55;
const STOF_N = 1500;

// ---------- toestand op moduleniveau ----------
let scene = null;
let opt = null;
let objecten = [];
let geos = [];
let mats = [];
let textures = [];
let segs = [];           // { k, rows, geo, wgeo, mesh, water }
let wandMat = null;
let waterMat = null;
let waterTex = null;
let waterOff = 0;
let sky = null;
let stof = null;
let stofTijd = 0;
let beams = [];
let zon = null;
let laag = false;
let niveauS = 0;
let hoogS = 0;
let laagS = 0;
let rng = null;
const tmp = new THREE.Vector3();
const tmp2 = new THREE.Vector2();

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

function klem(v, a, b) { return v < a ? a : (v > b ? b : v); }

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

// ---------- ruis op wereldcoördinaten (naadloos tussen segmenten) ----------
function hash(i, j) {
  const n = Math.sin(i * 127.1 + j * 311.7) * 43758.5453;
  return n - Math.floor(n);
}

function vnoise(x, y) {
  const xi = Math.floor(x), yi = Math.floor(y);
  let fx = x - xi, fy = y - yi;
  fx = fx * fx * (3 - 2 * fx);
  fy = fy * fy * (3 - 2 * fy);
  const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
  return a + (b - a) * fx + (c - a) * fy + (a - b - c + d) * fx * fy;
}

// ---------- profiel van de canyon ----------
let pU = 0, pY = 0, pT = 0;   // resultaat van profiel(): zijwaarts, hoogte, schaduw

// z = -1 (links) of 1 (rechts); i = 0 (rivier) .. HALF-1 (bovenrand)
function profiel(s, z, i) {
  const zi = z * 7.3;
  const wr = 4.5 + 1.0 * Math.sin(s / 55);
  const w = z < 0
    ? 21 + 3 * Math.sin(s / 70 + 0.5) + 2 * Math.sin(s / 37)
    : 21 + 3 * Math.sin(s / 83 + 2) + 2 * Math.sin(s / 41 + 1);
  const nb = vnoise(s * 0.08, 3 + zi) - 0.5;
  let u, y, t;
  if (i <= 5) {
    if (i === 0) { u = 0; y = -1.0; }
    else if (i === 1) { u = wr * 0.8; y = -0.5; }
    else if (i === 2) { u = wr * 1.05; y = 0.35; }
    else if (i === 3) { u = wr + (w - wr) * 0.4; y = 0.8 + nb; }
    else if (i === 4) { u = wr + (w - wr) * 0.75; y = 1.5 + nb * 1.2; }
    else { u = w; y = 2.5 + nb * 0.6; }
    t = 0.92 + 0.25 * nb;
  } else {
    const hoog = 45 + 20 * vnoise(s * 0.02, 11 + zi) + 8 * vnoise(s * 0.09, 5 + zi);
    const f = WAND[i - 6];
    y = 2.5 + (hoog - 2.5) * f + (vnoise(s * 0.15, i * 3.1 + zi) - 0.5) * hoog * 0.04;
    u = w + y * 0.12
      + (vnoise(s * 0.09, y * 0.12 + zi * 2) - 0.5) * 5
      + (vnoise(s * 0.3, y * 0.4 + zi) - 0.5) * 1.6;
    t = (0.72 + 0.5 * vnoise(s * 0.05, y * 0.06 + zi)) * (0.75 + 0.25 * Math.min(1, y / 12));
  }
  pU = u; pY = y; pT = t;
}

// ---------- segmenten ----------
function rijen() { return laag ? 12 : 24; }

function bouwGeos(seg) {
  const R = rijen();
  const nv = (R + 3) * COL;
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(nv * 3), 3));
  g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(nv * 3), 3));
  g.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(nv * 2), 2));
  const idx = new Uint16Array((R + 2) * (COL - 1) * 6);
  let n = 0;
  for (let j = 0; j < R + 2; j++) {
    for (let c = 0; c < COL - 1; c++) {
      const a = j * COL + c, b = a + 1, cc = a + COL, d = cc + 1;
      idx[n++] = a; idx[n++] = b; idx[n++] = cc;
      idx[n++] = b; idx[n++] = d; idx[n++] = cc;
    }
  }
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  // alleen de binnenste rijen tekenen: de extra rijen dienen voor naadloze normalen
  g.setDrawRange((COL - 1) * 6, R * (COL - 1) * 6);

  const wv = (R + 1) * 3;
  const wg = new THREE.BufferGeometry();
  const wn = new Float32Array(wv * 3);
  for (let i = 0; i < wv; i++) wn[i * 3 + 1] = 1;
  wg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(wv * 3), 3));
  wg.setAttribute('normal', new THREE.BufferAttribute(wn, 3));
  wg.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(wv * 2), 2));
  const widx = new Uint16Array(R * 2 * 6);
  n = 0;
  for (let j = 0; j < R; j++) {
    for (let c = 0; c < 2; c++) {
      const a = j * 3 + c, b = a + 1, cc = a + 3, d = cc + 1;
      widx[n++] = a; widx[n++] = b; widx[n++] = cc;
      widx[n++] = b; widx[n++] = d; widx[n++] = cc;
    }
  }
  wg.setIndex(new THREE.BufferAttribute(widx, 1));

  if (seg.geo) seg.geo.dispose();
  if (seg.wgeo) seg.wgeo.dispose();
  seg.geo = g; seg.wgeo = wg; seg.rows = R;
  seg.mesh.geometry = g;
  seg.water.geometry = wg;
}

function vulSegment(seg, k) {
  if (seg.rows !== rijen()) bouwGeos(seg);
  seg.k = k;
  const R = seg.rows, dr = L / R;
  const pos = seg.geo.attributes.position.array;
  const kl = seg.geo.attributes.color.array;
  const uv = seg.geo.attributes.uv.array;
  let p = 0, q = 0;
  for (let j = 0; j < R + 3; j++) {
    const s = k * L + (j - 1) * dr;
    pad(s, tmp);
    for (let c = 0; c < COL; c++) {
      const i = Math.abs(c - (HALF - 1));
      const z = c < HALF - 1 ? -1 : 1;
      profiel(s, z, i);
      pos[p] = tmp.x + z * pU;
      pos[p + 1] = pY;
      pos[p + 2] = -s;
      kl[p] = pT;
      kl[p + 1] = pT * 0.97;
      kl[p + 2] = pT * 0.94;
      uv[q] = 0.5;
      uv[q + 1] = pY / TEX_H;
      p += 3; q += 2;
    }
  }
  seg.geo.attributes.position.needsUpdate = true;
  seg.geo.attributes.color.needsUpdate = true;
  seg.geo.attributes.uv.needsUpdate = true;
  seg.geo.computeVertexNormals();

  // water: strook langs het pad
  const wp = seg.wgeo.attributes.position.array;
  const wuv = seg.wgeo.attributes.uv.array;
  p = 0; q = 0;
  for (let j = 0; j <= R; j++) {
    const s = k * L + j * dr;
    pad(s, tmp);
    const wr = 4.5 + 1.0 * Math.sin(s / 55);
    for (let c = 0; c < 3; c++) {
      wp[p] = tmp.x + (c - 1) * wr;
      wp[p + 1] = 0;
      wp[p + 2] = -s;
      wuv[q] = c * 0.5;
      wuv[q + 1] = s / 14;
      p += 3; q += 2;
    }
  }
  seg.wgeo.attributes.position.needsUpdate = true;
  seg.wgeo.attributes.uv.needsUpdate = true;
  seg.wgeo.computeBoundingSphere();
}

// ---------- texturen ----------
function wandTextuur() {
  const r = maakRng(77);
  const c = canvasTex(16, 512);
  const x = c.getContext('2d');
  const pal = ['#6f2c1e', '#8a3a24', '#a64a2c', '#b85a32', '#c8703c', '#d4833f', '#d99a52', '#d6ad6c', '#e0bd85'];
  const pxPerEenheid = 512 / TEX_H;
  x.fillStyle = '#c9a374';
  x.fillRect(0, 0, 16, 512);
  // van onder (hoogte 0) naar boven; canvas-y loopt omgekeerd
  let h = 3;
  while (h < TEX_H) {
    const dik = 0.8 + r() * r() * 5;
    const top = Math.min(TEX_H, h + dik);
    const idx = Math.floor(klem(r() * 0.7 + (h / TEX_H) * 0.5, 0, 0.999) * pal.length);
    const yTop = 512 - top * pxPerEenheid;
    x.fillStyle = pal[idx];
    x.fillRect(0, yTop, 16, Math.max(1, (top - h) * pxPerEenheid));
    x.fillStyle = 'rgba(40,15,10,0.35)';
    x.fillRect(0, 512 - (h + 0.12) * pxPerEenheid, 16, Math.max(1, 0.12 * pxPerEenheid));
    h += dik;
  }
  return naarTextuur(c);
}

const waterVS = `
varying vec3 vW;
varying vec2 vUv;
void main() {
  vUv = uv;
  vec4 w = modelMatrix * vec4(position, 1.0);
  vW = w.xyz;
  gl_Position = projectionMatrix * viewMatrix * w;
}`;

const waterFS = `
uniform sampler2D uMap;
uniform float uOff;
uniform vec3 uDiep;
uniform vec3 uMidden;
uniform vec3 uWarm;
uniform vec3 uZon;
uniform vec3 uZonRicht;
uniform vec3 uMist;
uniform float uMistN;
uniform float uMistF;
varying vec3 vW;
varying vec2 vUv;
void main() {
  vec2 uv = vUv + vec2(0.0, uOff);
  vec3 t = texture2D(uMap, uv).rgb;
  vec3 t2 = texture2D(uMap, uv * 1.7 + vec2(0.3, -uOff * 0.7)).rgb;
  vec3 toCam = cameraPosition - vW;
  float dist = length(toCam);
  vec3 V = toCam / dist;
  vec3 kleur = mix(uDiep, uMidden, smoothstep(10.0, 120.0, dist));
  vec3 c = kleur * (0.85 + 0.3 * t.r);
  c = mix(c, uWarm, 0.75 * smoothstep(0.7 * uMistF, uMistF, dist));
  vec3 n = normalize(vec3((t.r - 0.6) * 1.2, 1.0, (t2.g - 0.6) * 1.2));
  vec3 H = normalize(uZonRicht + V);
  float sp = pow(max(dot(n, H), 0.0), 60.0);
  c += uZon * sp * 0.8;
  float f = smoothstep(uMistN, uMistF, dist);
  c = mix(c, uMist, f);
  gl_FragColor = vec4(c, 1.0);
  #include <colorspace_fragment>
}`;

function waterTextuur() {
  const r = maakRng(5);
  const c = canvasTex(256, 256);
  const x = c.getContext('2d');
  x.fillStyle = '#9bb7b4';
  x.fillRect(0, 0, 256, 256);
  x.lineCap = 'round';
  for (let i = 0; i < 140; i++) {
    const x0 = r() * 256, y0 = r() * 256;
    const len = 20 + r() * 60, bw = 1 + r() * 2.5, kink = (r() - 0.5) * 8;
    x.strokeStyle = r() < 0.5 ? 'rgba(255,240,210,0.20)' : 'rgba(20,50,60,0.22)';
    x.lineWidth = bw;
    for (const dx of [-256, 0, 256]) {
      for (const dy of [-256, 0, 256]) {
        x.beginPath();
        x.moveTo(x0 + dx, y0 + dy);
        x.lineTo(x0 + dx + kink, y0 + dy + len);
        x.stroke();
      }
    }
  }
  const t = naarTextuur(c);
  t.wrapS = THREE.RepeatWrapping;
  t.wrapT = THREE.RepeatWrapping;
  return t;
}

function bundelTextuur() {
  const c = canvasTex(64, 256);
  const x = c.getContext('2d');
  const gh = x.createLinearGradient(0, 0, 64, 0);
  gh.addColorStop(0, 'rgba(255,255,255,0)');
  gh.addColorStop(0.5, 'rgba(255,255,255,1)');
  gh.addColorStop(1, 'rgba(255,255,255,0)');
  x.fillStyle = gh;
  x.fillRect(0, 0, 64, 256);
  const gv = x.createLinearGradient(0, 0, 0, 256);
  gv.addColorStop(0, 'rgba(0,0,0,0)');
  gv.addColorStop(0.5, 'rgba(0,0,0,1)');
  gv.addColorStop(1, 'rgba(0,0,0,0)');
  x.globalCompositeOperation = 'destination-in';
  x.fillStyle = gv;
  x.fillRect(0, 0, 64, 256);
  return naarTextuur(c);
}

// ---------- hemel ----------
const hemelVS = `
varying vec3 vDir;
void main() {
  vDir = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const hemelFS = `
uniform vec3 uHor;
uniform vec3 uTop;
uniform vec3 uZon;
uniform vec3 uZonRicht;
varying vec3 vDir;
void main() {
  vec3 d = normalize(vDir);
  float h = clamp(d.y, 0.0, 1.0);
  vec3 c = mix(uHor, uTop, pow(h, 0.55));
  float g = pow(max(dot(d, uZonRicht), 0.0), 6.0);
  c += uZon * g * 0.35;
  gl_FragColor = vec4(c, 1.0);
  #include <colorspace_fragment>
}`;

function maakHemel() {
  const g = new THREE.SphereGeometry(1000, 24, 16);
  geos.push(g);
  const m = new THREE.ShaderMaterial({
    vertexShader: hemelVS,
    fragmentShader: hemelFS,
    uniforms: {
      uHor: { value: new THREE.Color(0xf2b57a) },
      uTop: { value: new THREE.Color(0x6fb8c4) },
      uZon: { value: new THREE.Color(0xffb866) },
      uZonRicht: { value: new THREE.Vector3(-0.8, 0.45, -0.5).normalize() }
    },
    side: THREE.BackSide,
    depthWrite: false,
    fog: false
  });
  mats.push(m);
  sky = new THREE.Mesh(g, m);
  sky.renderOrder = -10;
  sky.frustumCulled = false;
  scene.add(sky);
  objecten.push(sky);
}

// ---------- stof ----------
const stofVS = `
uniform vec3 uCam;
uniform vec3 uBox;
uniform float uScale;
uniform float uTijd;
uniform float uAdem;
uniform float uHelder;
attribute float aSize;
attribute float aFase;
varying float vAlpha;
varying float vLit;
void main() {
  vec3 b = position * uBox;
  b.x += sin(uTijd * 0.12 + aFase * 6.2832) * 2.0;
  b.y += uTijd * (0.15 + 0.2 * aFase);
  float rx = mod(b.x - uCam.x, uBox.x) - 0.5 * uBox.x;
  float ry = mod(b.y - uCam.y, uBox.y) - 0.5 * uBox.y;
  float d = mod(uCam.z - b.z, uBox.z);
  vec3 wp = vec3(uCam.x + rx, uCam.y + ry, uCam.z - d);
  vec4 mv = modelViewMatrix * vec4(wp, 1.0);
  gl_Position = projectionMatrix * mv;
  float dist = max(-mv.z, 1.0);
  float px = aSize * uScale * uAdem / dist;
  gl_PointSize = clamp(px, 2.0, 24.0);
  float fade = smoothstep(0.0, 6.0, d) * (1.0 - smoothstep(0.5 * uBox.z, uBox.z, d));
  fade *= 1.0 - smoothstep(0.38, 0.5, abs(rx) / uBox.x);
  fade *= 1.0 - smoothstep(0.38, 0.5, abs(ry) / uBox.y);
  float lit = 0.25 + 0.65 * smoothstep(0.2, 0.8, 0.5 + 0.5 * sin(wp.x * 0.12 - wp.y * 0.08 + 0.6 * sin(wp.z * 0.03)));
  vAlpha = fade * lit * uHelder * clamp(px / 3.0, 0.4, 1.0) * 1.0;
  vLit = lit;
}`;

const stofFS = `
varying float vAlpha;
varying float vLit;
void main() {
  float r = length(gl_PointCoord - 0.5) * 2.0;
  if (r > 1.0) discard;
  float a = pow(1.0 - r, 2.0);
  gl_FragColor = vec4(mix(vec3(0.8, 0.55, 0.35), vec3(1.0, 0.85, 0.45), vLit), a * vAlpha);
}`;

function maakStof() {
  const pos = new Float32Array(STOF_N * 3);
  const gr = new Float32Array(STOF_N);
  const fa = new Float32Array(STOF_N);
  for (let i = 0; i < STOF_N; i++) {
    pos[i * 3] = rng(); pos[i * 3 + 1] = rng(); pos[i * 3 + 2] = rng();
    gr[i] = 0.1 + 0.18 * Math.pow(rng(), 2);
    fa[i] = rng();
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setAttribute('aSize', new THREE.BufferAttribute(gr, 1));
  g.setAttribute('aFase', new THREE.BufferAttribute(fa, 1));
  geos.push(g);
  const m = new THREE.ShaderMaterial({
    vertexShader: stofVS,
    fragmentShader: stofFS,
    uniforms: {
      uCam: { value: new THREE.Vector3() },
      uBox: { value: new THREE.Vector3(44, 22, 80) },
      uScale: { value: 700 },
      uTijd: { value: 0 },
      uAdem: { value: 1 },
      uHelder: { value: 1 }
    },
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending
  });
  mats.push(m);
  const p = new THREE.Points(g, m);
  p.frustumCulled = false;
  p.renderOrder = 2;
  scene.add(p);
  objecten.push(p);
  stof = p;
}

// ---------- lichtbundels ----------
function maakBundels() {
  const g = new THREE.PlaneGeometry(10, 70);
  geos.push(g);
  const tex = bundelTextuur();
  for (let i = 0; i < BEAM_N; i++) {
    const m = new THREE.MeshBasicMaterial({
      map: tex,
      color: 0xffc27a,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      fog: false
    });
    mats.push(m);
    const mesh = new THREE.Mesh(g, m);
    mesh.rotation.z = 0.45 + rng() * 0.15;
    mesh.frustumCulled = false;
    mesh.renderOrder = 1;
    scene.add(mesh);
    objecten.push(mesh);
    beams.push({ mesh, mat: m, bs: 30 + i * BEAM_AFSTAND, ox: -4 + rng() * 10 });
  }
}

// ---------- interface ----------
export function create(sc, analyser, opties) {
  scene = sc;
  opt = opties || {};
  rng = maakRng(20240611);
  objecten = []; geos = []; mats = []; textures = [];
  segs = []; beams = [];
  stofTijd = 0; waterOff = 0;
  niveauS = 0; hoogS = 0; laagS = 0;
  laag = opt.kwaliteit === 'laag';

  scene.background = new THREE.Color(info.achtergrond);
  scene.fog = new THREE.Fog(0xf2b57a, 25, 300);

  maakHemel();

  wandMat = new THREE.MeshLambertMaterial({ map: wandTextuur(), vertexColors: true });
  mats.push(wandMat);
  waterTex = waterTextuur();
  waterMat = new THREE.ShaderMaterial({
    vertexShader: waterVS,
    fragmentShader: waterFS,
    uniforms: {
      uMap: { value: waterTex },
      uOff: { value: 0 },
      uDiep: { value: new THREE.Color(0x3f8f8c) },
      uMidden: { value: new THREE.Color(0x5aa7a0) },
      uWarm: { value: new THREE.Color(0xf5b47c) },
      uZon: { value: new THREE.Color(0xffd699) },
      uZonRicht: { value: new THREE.Vector3(-0.8, 0.45, -0.5).normalize() },
      uMist: { value: new THREE.Color(0xf2b57a) },
      uMistN: { value: 25 },
      uMistF: { value: 300 }
    }
  });
  mats.push(waterMat);

  for (let i = 0; i < N; i++) {
    const seg = { k: 0, rows: 0, geo: null, wgeo: null, mesh: new THREE.Mesh(undefined, wandMat), water: new THREE.Mesh(undefined, waterMat) };
    seg.mesh.frustumCulled = false;
    seg.water.frustumCulled = false;
    bouwGeos(seg);
    vulSegment(seg, i - 1);
    scene.add(seg.mesh, seg.water);
    objecten.push(seg.mesh, seg.water);
    segs.push(seg);
  }

  maakStof();
  maakBundels();

  zon = new THREE.DirectionalLight(0xffb866, ZON);
  zon.position.set(-0.8, 0.45, -0.5);
  const koel = new THREE.DirectionalLight(0x6f86b8, 0.6);
  koel.position.set(1, 0.3, 0.2);
  const hemel = new THREE.HemisphereLight(0xffd2a8, 0xa04a2c, 0.9);
  scene.add(zon, koel, hemel);
  objecten.push(zon, koel, hemel);

  setKwaliteit(laag ? 'laag' : 'hoog');
}

export function update(tijd, audio, cam) {
  if (!scene) return;
  const dt = Math.min(cam.dt || 0.016, 0.1);
  const cp = cam.positie;
  const beweging = opt.minderBeweging ? 0 : 1;

  // zachte, kleine reactie op de muziek
  const k = 1 - Math.exp(-dt * 3);
  niveauS += (audio.niveau - niveauS) * k;
  hoogS += (audio.hoog - hoogS) * k;
  laagS += (audio.laag - laagS) * k;
  zon.intensity = ZON + 0.35 * laagS;

  // segmenten recyclen, hooguit één per frame
  const kc = Math.floor(cam.s / L);
  let oud = segs[0], max = segs[0].k;
  for (let i = 1; i < segs.length; i++) {
    if (segs[i].k < oud.k) oud = segs[i];
    if (segs[i].k > max) max = segs[i].k;
  }
  if (oud.k < kc - 1) vulSegment(oud, max + 1);

  // hemel volgt de camera
  sky.position.copy(cp);

  // water stroomt langzaam naar ons toe
  waterOff += dt * 0.03 * beweging;
  waterMat.uniforms.uOff.value = waterOff;

  // stof
  stofTijd += dt * beweging;
  let h = 800;
  if (opt.renderer) { opt.renderer.getDrawingBufferSize(tmp2); h = tmp2.y || 800; }
  const fov = (cam.camera && cam.camera.fov) || 60;
  const u = stof.material.uniforms;
  u.uCam.value.copy(cp);
  u.uScale.value = 0.5 * h / Math.tan(fov * Math.PI / 360);
  u.uTijd.value = stofTijd;
  u.uAdem.value = 1 + 0.15 * niveauS;
  u.uHelder.value = 0.85 + 0.35 * hoogS;

  // lichtbundels
  for (const b of beams) {
    if (b.bs < cam.s - 30) b.bs += BEAM_N * BEAM_AFSTAND;
    const voor = b.bs - cam.s;
    pad(b.bs, tmp);
    b.mesh.position.set(tmp.x + b.ox, 20, tmp.z);
    const f = klem((230 - voor) / 60, 0, 1) * klem((voor - 10) / 40, 0, 1);
    b.mat.opacity = f * (0.17 + 0.06 * laagS);
  }
}

export function setKwaliteit(niveau) {
  laag = niveau === 'laag';
  if (stof) stof.geometry.setDrawRange(0, laag ? 700 : STOF_N);
  for (const b of beams) b.mesh.visible = !laag;
}

export function dispose() {
  if (scene) {
    for (const o of objecten) scene.remove(o);
    scene.background = null;
    scene.fog = null;
  }
  for (const s of segs) {
    if (s.geo) s.geo.dispose();
    if (s.wgeo) s.wgeo.dispose();
  }
  for (const g of geos) g.dispose();
  for (const m of mats) m.dispose();
  for (const t of textures) t.dispose();
  scene = null; opt = null;
  objecten = []; geos = []; mats = []; textures = [];
  segs = []; beams = [];
  wandMat = null; waterMat = null; waterTex = null;
  sky = null; stof = null; zon = null;
  stofTijd = 0;
  rng = null;
}
