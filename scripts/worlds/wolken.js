// Wereld Wolken: vliegen boven een eindeloze wolkenzee bij gouden licht.
import * as THREE from 'three';

export const info = {
  id: 'wolken',
  naam: 'Wolken',
  muziek: 'materiaal/audio/wolken/wolken.mp3',
  snelheid: 7,
  stuurbereik: { x: 6, y: 2.5 },
  achtergrond: '#d99a55'
};

// Het pad: zeer brede bochten (golflengte 520 en 330), helling < 0.2; y rond 30 boven de zee.
export function pad(s, uit) {
  const x = 8 * Math.sin(s * 0.012083) + 4 * Math.sin(s * 0.019039 + 1.1);
  const y = 30 + 2 * Math.sin(s * 0.015708) + 1 * Math.sin(s * 0.027318 + 0.5);
  return uit.set(x, y, -s);
}

// ---------- toestand op moduleniveau ----------
const PERIODE = 7680;          // ruis herhaalt na deze afstand (voorkomt float-problemen)
const MAX_LOS = 12;
const DUUR_SLUIER = 4;         // seconden dat het beeld wit-goud wordt

let scene = null;
let opt = null;
let objecten = [];
let geos = [];
let mats = [];
let textures = [];
let rng = null;
let laag = false;
let begonnen = false;
let hemel = null;              // mesh
let zee = null;                // mesh
let zon = null;                // sprite
let sluier = null;             // mesh (fullscreen)
let sluierMat = null;
let zeeMat = null;
let wolkjes = [];              // { sprite, s, basis }
let kruis = null;              // { sprite, s, basis }
let kruisToestand = 0;         // 0 wacht, 1 onderweg, 2 sluier bezig
let volgendeKruis = 0;
let sluierTijd = 0;
let vorigeS = 0;
let snelheidS = 7;
let glowS = 0;
let hoogS = 0;
let uGemeen = null;            // gedeelde uniforms hemel/zee
const zonRichting = new THREE.Vector3(0.13, 0.07, -1).normalize();
const tmp = new THREE.Vector3();

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

function smooth(a, b, x) {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

function naarTextuur(c) {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 1;
  textures.push(t);
  return t;
}

// ---------- shaders ----------
// Hemelkleur per richting; ook gebruikt als horizonkleur van de zee.
const SKY_GLSL = `
uniform vec3 uSun;
uniform float uGlow;
vec3 skyCol(vec3 d) {
  float t = clamp(d.y, 0.0, 1.0);
  vec3 c = vec3(0.95, 0.70, 0.34);
  c = mix(c, vec3(0.94, 0.58, 0.38), smoothstep(0.0, 0.12, t));
  c = mix(c, vec3(0.48, 0.34, 0.56), smoothstep(0.08, 0.40, t));
  c = mix(c, vec3(0.24, 0.25, 0.48), smoothstep(0.3, 0.9, t));
  float sd = max(dot(d, uSun), 0.0);
  c += vec3(1.0, 0.72, 0.38) * (pow(sd, 30.0) * 0.14 + pow(sd, 300.0) * 0.30) * uGlow;
  c = mix(c, vec3(1.0, 0.92, 0.72), smoothstep(0.9990, 0.9996, sd) * 0.9);
  c = min(c, vec3(1.0));
  return c;
}`;

const hemelVS = `
varying vec3 vDir;
void main() {
  vDir = position;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const hemelFS = `
varying vec3 vDir;
${SKY_GLSL}
void main() {
  gl_FragColor = vec4(skyCol(normalize(vDir)), 1.0);
}`;

const zeeVS = `
varying vec2 vLocal;
void main() {
  vLocal = position.xz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

const zeeFS = `
precision highp float;
varying vec2 vLocal;
uniform vec2 uOff;
uniform float uOct;
uniform float uBright;
uniform float uSheen;
${SKY_GLSL}
float hash(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}
// value noise die zich herhaalt na n cellen (geen precisieproblemen)
float vnoise(vec2 p, float n) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  vec2 a = mod(i, n);
  vec2 b = mod(i + 1.0, n);
  float h00 = hash(a);
  float h10 = hash(vec2(b.x, a.y));
  float h01 = hash(vec2(a.x, b.y));
  float h11 = hash(b);
  return mix(mix(h00, h10, f.x), mix(h01, h11, f.x), f.y);
}
void main() {
  float dist = length(vLocal);
  vec2 q = vLocal + uOff;
  vec2 sunXZ = normalize(uSun.xz);
  float n1 = vnoise(q / 96.0, 80.0);
  float n2 = vnoise(q / 48.0, 160.0);
  float n2s = vnoise((q + sunXZ * 7.0) / 48.0, 160.0);
  float lit = (n2s - n2) * 7.0;
  float n = n1 * 0.38 + n2 * 0.30 * (1.0 - smoothstep(300.0, 900.0, dist));
  if (uOct > 0.5) {
    n += vnoise(q / 24.0, 320.0) * 0.17 * (1.0 - smoothstep(150.0, 500.0, dist));
    n += vnoise(q / 12.0, 640.0) * 0.15 * (1.0 - smoothstep(80.0, 300.0, dist));
  } else {
    n += 0.16;
  }
  n += 0.5 * (smoothstep(300.0, 900.0, dist)) * 0.35;
  float h = smoothstep(0.35, 0.75, n);
  vec3 col = mix(vec3(0.37, 0.32, 0.52), vec3(0.95, 0.84, 0.66), h);
  col *= 0.8 + 0.4 * clamp(lit * 0.5 + 0.5, 0.0, 1.0);
  col += vec3(0.12, 0.06, 0.0) * clamp(lit, 0.0, 1.0) * h;
  col = mix(col, vec3(0.38, 0.34, 0.56), clamp(-lit, 0.0, 1.0) * 0.6);
  vec2 dh = vLocal / max(dist, 1.0);
  float naarZon = max(dot(dh, sunXZ), 0.0);
  col *= 1.0 + 0.12 * pow(naarZon, 3.0);
  col = min(col * uBright + uSheen * h, vec3(0.95));
  vec3 hor = skyCol(normalize(vec3(dh.x, 0.0, dh.y)));
  float f = smoothstep(250.0, 1150.0, dist);
  gl_FragColor = vec4(mix(col, hor, f), 1.0);
}`;

const sluierVS = `
varying vec2 vP;
void main() {
  vP = position.xy;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}`;

const sluierFS = `
varying vec2 vP;
uniform float uA;
void main() {
  float v = length(vP);
  vec3 c = mix(vec3(1.0, 0.92, 0.76), vec3(0.97, 0.78, 0.48), smoothstep(0.0, 1.5, v));
  gl_FragColor = vec4(c, uA * (1.0 - 0.12 * smoothstep(0.3, 1.2, v)));
}`;

// ---------- texturen ----------
function wolkTextuur(zaad) {
  const r = maakRng(zaad);
  const c = document.createElement('canvas');
  c.width = 256; c.height = 128;
  const x = c.getContext('2d');
  for (let i = 0; i < 16; i++) {
    const cx = 128 + (r() - 0.5) * 150;
    const cy = 70 + (r() - 0.5) * 40 - (1 - Math.abs(cx - 128) / 128) * 8;
    const rad = 26 + r() * 34;
    const g = x.createRadialGradient(cx, cy, 0, cx, cy, rad);
    g.addColorStop(0, 'rgba(255,255,255,0.55)');
    g.addColorStop(0.55, 'rgba(255,255,255,0.22)');
    g.addColorStop(1, 'rgba(255,255,255,0)');
    x.fillStyle = g;
    x.fillRect(cx - rad, cy - rad, rad * 2, rad * 2);
  }
  // onderkant zacht lila, bovenkant blijft licht
  x.globalCompositeOperation = 'source-atop';
  const lg = x.createLinearGradient(0, 30, 0, 110);
  lg.addColorStop(0, 'rgba(255,240,215,0)');
  lg.addColorStop(1, 'rgba(190,160,215,0.55)');
  x.fillStyle = lg;
  x.fillRect(0, 0, 256, 128);
  // rand zacht uitfaden
  x.globalCompositeOperation = 'destination-in';
  const rand = x.createRadialGradient(128, 64, 20, 128, 64, 128);
  rand.addColorStop(0, 'rgba(0,0,0,1)');
  rand.addColorStop(1, 'rgba(0,0,0,0)');
  x.fillStyle = rand;
  x.fillRect(0, 0, 256, 128);
  return naarTextuur(c);
}

function zonTextuur() {
  const c = document.createElement('canvas');
  c.width = 256; c.height = 256;
  const x = c.getContext('2d');
  const g = x.createRadialGradient(128, 128, 0, 128, 128, 128);
  g.addColorStop(0, 'rgba(255,252,235,1)');
  g.addColorStop(0.05, 'rgba(255,235,185,0.7)');
  g.addColorStop(0.2, 'rgba(255,195,120,0.22)');
  g.addColorStop(0.5, 'rgba(255,170,100,0.05)');
  g.addColorStop(1, 'rgba(255,160,100,0)');
  x.fillStyle = g;
  x.fillRect(0, 0, 256, 256);
  return naarTextuur(c);
}

// ---------- wolken ----------
function maakSprite(tex, kleur, basis) {
  const m = new THREE.SpriteMaterial({
    map: tex,
    color: kleur,
    transparent: true,
    opacity: 0,
    depthWrite: false,
    fog: false
  });
  mats.push(m);
  const s = new THREE.Sprite(m);
  s.frustumCulled = false;
  s.visible = false;
  scene.add(s);
  objecten.push(s);
  return { sprite: s, s: 0, basis };
}

function plaatsWolk(w, s) {
  const breedte = 60 + rng() * 70;
  const hoogte = breedte * 0.4;
  const zijde = rng() < 0.5 ? -1 : 1;
  pad(s, tmp);
  w.s = s;
  w.sprite.scale.set(breedte, hoogte, 1);
  w.sprite.position.set(
    tmp.x + zijde * (30 + rng() * 110),
    hoogte * 0.5 + 3 + rng() * 32,
    tmp.z
  );
  w.basis = 0.35 + rng() * 0.2;
  w.sprite.visible = true;
}

// afstand-afhankelijke dekking: nooit hard in beeld
function wolkOpacity(w, cp) {
  const d = w.sprite.position.distanceTo(cp);
  return w.basis * smooth(40, 130, d) * (1 - smooth(520, 680, d));
}

// ---------- interface ----------
export function create(sc, analyser, opties) {
  scene = sc;
  opt = opties || {};
  rng = maakRng(8412027);
  objecten = []; geos = []; mats = []; textures = [];
  wolkjes = []; kruis = null;
  begonnen = false;
  kruisToestand = 0;
  sluierTijd = 0;
  volgendeKruis = 38 + rng() * 10;
  glowS = 0; hoogS = 0;
  snelheidS = info.snelheid * (opt.minderBeweging ? 0.5 : 1);

  scene.background = new THREE.Color(info.achtergrond);
  scene.fog = null;

  uGemeen = {
    uSun: { value: zonRichting.clone() },
    uGlow: { value: 1 }
  };

  // hemel
  const hg = new THREE.SphereGeometry(1000, 24, 16);
  geos.push(hg);
  const hm = new THREE.ShaderMaterial({
    vertexShader: hemelVS,
    fragmentShader: hemelFS,
    uniforms: { uSun: uGemeen.uSun, uGlow: uGemeen.uGlow },
    side: THREE.BackSide,
    depthTest: false,
    depthWrite: false
  });
  mats.push(hm);
  hemel = new THREE.Mesh(hg, hm);
  hemel.frustumCulled = false;
  hemel.renderOrder = -10;
  scene.add(hemel);
  objecten.push(hemel);

  // wolkenzee
  const zg = new THREE.PlaneGeometry(2600, 2600, 1, 1);
  zg.rotateX(-Math.PI / 2);
  geos.push(zg);
  zeeMat = new THREE.ShaderMaterial({
    vertexShader: zeeVS,
    fragmentShader: zeeFS,
    uniforms: {
      uSun: uGemeen.uSun,
      uGlow: uGemeen.uGlow,
      uOff: { value: new THREE.Vector2() },
      uOct: { value: 1 },
      uBright: { value: 1 },
      uSheen: { value: 0 }
    }
  });
  mats.push(zeeMat);
  zee = new THREE.Mesh(zg, zeeMat);
  zee.frustumCulled = false;
  scene.add(zee);
  objecten.push(zee);

  // zon
  const zm = new THREE.SpriteMaterial({
    map: zonTextuur(),
    transparent: true,
    opacity: 0.5,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    fog: false
  });
  mats.push(zm);
  zon = new THREE.Sprite(zm);
  zon.scale.set(170, 170, 1);
  zon.frustumCulled = false;
  zon.renderOrder = -9;
  scene.add(zon);
  objecten.push(zon);

  // losse wolken
  const texA = wolkTextuur(11);
  const texB = wolkTextuur(37);
  const kleurA = new THREE.Color(0.96, 0.86, 0.74);
  const kleurB = new THREE.Color(0.96, 0.76, 0.52);
  for (let i = 0; i < MAX_LOS; i++) {
    wolkjes.push(maakSprite(i % 2 ? texA : texB, i % 3 ? kleurA : kleurB, 0.4));
  }
  // de wolk die je doorkruist
  kruis = maakSprite(texA, new THREE.Color(1.0, 0.92, 0.78), 0.8);
  kruis.sprite.scale.set(190, 100, 1);

  // sluier (fullscreen, onafhankelijk van de camera)
  const sg = new THREE.PlaneGeometry(2, 2);
  geos.push(sg);
  sluierMat = new THREE.ShaderMaterial({
    vertexShader: sluierVS,
    fragmentShader: sluierFS,
    uniforms: { uA: { value: 0 } },
    transparent: true,
    depthTest: false,
    depthWrite: false
  });
  mats.push(sluierMat);
  sluier = new THREE.Mesh(sg, sluierMat);
  sluier.frustumCulled = false;
  sluier.renderOrder = 100;
  sluier.visible = false;
  scene.add(sluier);
  objecten.push(sluier);

  laag = false;
  setKwaliteit(opt.kwaliteit === 'laag' ? 'laag' : 'hoog');
}

export function update(tijd, audio, cam) {
  if (!scene) return;
  const dt = Math.min(cam.dt || 0.016, 0.1);
  const cp = cam.positie;

  // eerste frame: wolken verspreid voor je neerzetten
  if (!begonnen) {
    begonnen = true;
    vorigeS = cam.s;
    for (let i = 0; i < wolkjes.length; i++) {
      plaatsWolk(wolkjes[i], cam.s + 90 + (i / wolkjes.length) * 560 + rng() * 40);
    }
    applyAantal();
  }

  // snelheid schatten (voor het moment van de sluier)
  if (dt > 0) snelheidS += ((cam.s - vorigeS) / dt - snelheidS) * (1 - Math.exp(-dt * 2));
  vorigeS = cam.s;

  // zachte reactie op de muziek
  const k = 1 - Math.exp(-dt * 2);
  glowS += (audio.niveau * 0.6 + audio.laag * 0.4 - glowS) * k;
  hoogS += (audio.hoog - hoogS) * k;
  uGemeen.uGlow.value = 0.9 + 0.2 * glowS;
  zeeMat.uniforms.uBright.value = 1 + 0.10 * glowS;
  zeeMat.uniforms.uSheen.value = 0.04 * hoogS;
  zon.material.opacity = 0.45 + 0.1 * glowS;

  // hemel, zon en zee volgen de camera
  hemel.position.copy(cp);
  zon.position.copy(cp).addScaledVector(zonRichting, 900);
  zee.position.set(cp.x, 0, cp.z);
  zeeMat.uniforms.uOff.value.set(
    ((cp.x % PERIODE) + PERIODE) % PERIODE,
    ((cp.z % PERIODE) + PERIODE) % PERIODE
  );

  // losse wolken: recyclen als ze achter de camera vallen
  for (const w of wolkjes) {
    if (!w.sprite.visible) continue;
    if (cam.s > w.s + 30) plaatsWolk(w, cam.s + 450 + rng() * 250);
    w.sprite.material.opacity = wolkOpacity(w, cp);
  }

  // doorkruiste wolk en sluier
  const maxSluier = opt.minderBeweging ? 0.35 : 0.6;
  if (kruisToestand === 0) {
    if (tijd >= volgendeKruis) {
      const s = cam.s + Math.max(snelheidS, 1) * 25;
      pad(s, tmp);
      kruis.s = s;
      kruis.sprite.position.set(tmp.x, tmp.y, tmp.z);
      kruis.sprite.material.opacity = 0;
      kruis.sprite.visible = true;
      kruisToestand = 1;
    }
  } else if (kruisToestand === 1) {
    const d = kruis.sprite.position.distanceTo(cp);
    kruis.sprite.material.opacity = kruis.basis * (1 - smooth(200, 300, d));
    if (kruis.s - cam.s <= Math.max(snelheidS, 1) * DUUR_SLUIER * 0.5) {
      kruisToestand = 2;
      sluierTijd = 0;
    }
  } else {
    sluierTijd += dt;
    const u = Math.min(1, sluierTijd / DUUR_SLUIER);
    sluierMat.uniforms.uA.value = maxSluier * Math.sin(Math.PI * u);
    // de wolk zelf lost op terwijl de sluier opkomt
    const d = kruis.sprite.position.distanceTo(cp);
    kruis.sprite.material.opacity = kruis.basis * smooth(10, 70, d);
    if (u >= 1) {
      kruisToestand = 0;
      kruis.sprite.visible = false;
      sluierMat.uniforms.uA.value = 0;
      volgendeKruis = tijd + 15 + rng() * 30;
    }
  }
  sluier.visible = sluierMat.uniforms.uA.value > 0.002;
}

function applyAantal() {
  const n = laag ? 7 : MAX_LOS;
  for (let i = 0; i < wolkjes.length; i++) {
    const w = wolkjes[i];
    if (i >= n) { w.sprite.visible = false; }
    else if (begonnen && !w.sprite.visible) { w.sprite.visible = true; }
  }
}

export function setKwaliteit(niveau) {
  laag = niveau === 'laag';
  if (zeeMat) zeeMat.uniforms.uOct.value = laag ? 0 : 1;
  applyAantal();
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
  wolkjes = []; kruis = null;
  hemel = null; zee = null; zon = null; sluier = null;
  sluierMat = null; zeeMat = null; uGemeen = null;
  begonnen = false;
  kruisToestand = 0;
  rng = null;
}
