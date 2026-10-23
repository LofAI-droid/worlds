// Zweef — navigatie, renderer, vliegcamera, besturing en kwaliteitsbewaking.
import * as THREE from 'three';
import { audio } from './audio.js';

const WERELDEN = ['ruimte', 'canyon', 'wolken'];
const PIXEL_STAPPEN = [1.5, 1.25, 1, 0.85, 0.7];
const KIJK_VOORUIT = 25;                       // afstand (eenheden) voor het kijkdoel
const MAX_PITCH = 6 * Math.PI / 180;
const KANTEL_BEREIK = 25;                      // graden voor volle uitslag

const $ = (id) => document.getElementById(id);
const el = {
  start: $('start'), keuze: $('keuze'), vlucht: $('vlucht'), doek: $('doek'),
  begin: $('begin'), terug: $('terug'), zwart: $('zwart'), laden: $('laden'),
  melding: $('melding'), minder: $('minder-beweging')
};

// ---------- Instellingen ----------
let minderBeweging = matchMedia('(prefers-reduced-motion: reduce)').matches;
try {
  const bewaard = localStorage.getItem('zweef-minder-beweging');
  if (bewaard !== null) minderBeweging = bewaard === '1';
} catch (e) { /* opslag niet beschikbaar */ }

function pasMinderBewegingToe() {
  el.minder.checked = minderBeweging;
  document.documentElement.classList.toggle('minder-beweging', minderBeweging);
}
pasMinderBewegingToe();
el.minder.addEventListener('change', () => {
  minderBeweging = el.minder.checked;
  pasMinderBewegingToe();
  try { localStorage.setItem('zweef-minder-beweging', minderBeweging ? '1' : '0'); } catch (e) { /* negeren */ }
});

// ---------- Toestand ----------
let scherm = 'start';        // 'start' | 'keuze' | 'vlucht'
let bezig = false;           // blokkeert dubbele klikken tijdens overgangen
let renderer = null;
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 1500);
camera.rotation.order = 'YXZ';
let wereld = null;
let info = null;
let wakeLock = null;

// Kwaliteit, onthouden binnen de sessie
const startRatio = Math.min(window.devicePixelRatio || 1, 1.5);
const stappen = [startRatio, ...PIXEL_STAPPEN.filter((r) => r < startRatio - 1e-6)];
let stapIndex = 0;
let laagGezet = navigator.hardwareConcurrency <= 4 || Math.min(innerWidth, innerHeight) < 340;

// ---------- Overgangen ----------
function fade(doel, seconden) {
  el.zwart.style.transition = 'opacity ' + seconden + 's ease';
  el.zwart.style.opacity = String(doel);
  el.zwart.classList.toggle('dicht', doel > 0);
  return new Promise((klaar) => setTimeout(klaar, seconden * 1000));
}

function toon(naam) {
  scherm = naam;
  for (const s of ['start', 'keuze', 'vlucht']) el[s].hidden = s !== naam;
  document.body.classList.toggle('in-vlucht', naam === 'vlucht');
}

function meld(tekst) { el.melding.textContent = tekst || ''; }

el.begin.addEventListener('click', async () => {
  if (bezig) return;
  bezig = true;
  audio.ontgrendel();
  await fade(1, 0.7);
  toon('keuze');
  await fade(0, 0.9);
  bezig = false;
});

for (const kaart of document.querySelectorAll('.kaart')) {
  kaart.addEventListener('click', () => kies(kaart.dataset.wereld));
}

// ---------- Vlucht starten ----------
async function kies(id) {
  if (bezig || !WERELDEN.includes(id)) return;
  bezig = true;
  meld('');
  // Binnen de tik: geluid ontgrendelen en (iOS) kantelrechten vragen
  audio.ontgrendel();
  let rechten = Promise.resolve('granted');
  if (typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function') {
    try { rechten = DeviceOrientationEvent.requestPermission().catch(() => 'denied'); } catch (e) { rechten = Promise.resolve('denied'); }
  }

  const [, toestemming] = await Promise.all([fade(1, 1.2), rechten]);
  el.laden.classList.add('zichtbaar');

  let module;
  try {
    module = await import('./worlds/' + id + '.js');
  } catch (e) {
    return mislukt('Deze wereld is er nog niet. Kies een andere.');
  }

  wereld = module;
  info = module.info;
  try {
    await audio.laad(info.muziek);
  } catch (e) { /* zonder muziek vliegen is nog steeds prettig */ }

  try {
    maakRenderer();
    toon('vlucht');
    el.vlucht.style.background = info.achtergrond || '#000';
    renderer.setClearColor(info.achtergrond || '#000');
    pasPixelRatioToe();
    maatAan();
    resetBesturing();
    zetCameraBegin();
    wereld.create(scene, audio.analyser, {
      kwaliteit: laagGezet ? 'laag' : 'hoog', minderBeweging, renderer, camera
    });
  } catch (e) {
    console.error(e);
    return mislukt('De wereld kon niet worden opgebouwd.');
  }

  if (toestemming === 'granted') window.addEventListener('deviceorientation', bijKanteling);
  audio.speel(info.muziek, { fadeIn: 4 }).catch(() => {});
  vraagWakeLock();
  start();
  el.laden.classList.remove('zichtbaar');
  toonTerug();
  fade(0, 3);
  bezig = false;
}

// Terug naar de keuze na een fout
async function mislukt(tekst) {
  opruimen();
  toon('keuze');
  meld(tekst);
  el.laden.classList.remove('zichtbaar');
  await fade(0, 1);
  bezig = false;
}

function maakRenderer() {
  if (renderer) return;
  renderer = new THREE.WebGLRenderer({
    canvas: el.doek,
    antialias: (window.devicePixelRatio || 1) <= 1,
    powerPreference: 'high-performance'
  });
}

function pasPixelRatioToe() { renderer.setPixelRatio(stappen[stapIndex]); }

function maatAan() {
  if (!renderer) return;
  const b = innerWidth, h = innerHeight;
  renderer.setSize(b, h, false);
  camera.aspect = b / h;
  camera.updateProjectionMatrix();
}
addEventListener('resize', maatAan);
addEventListener('orientationchange', () => { maatAan(); kalibratie = null; });

// ---------- Besturing ----------
const doel = { x: 0, y: 0 };
const waarde = { x: 0, y: 0 };
let aanraking = false;
let kanteling = null;        // { x, y } zodra er echte kantelgegevens zijn
let kalibratie = null;       // beginhouding { beta, gamma }
let muis = { x: 0, y: 0 };

const klem = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

function schermPositie(e) {
  return {
    x: klem((e.clientX - innerWidth / 2) / (innerWidth / 2), -1, 1),
    y: klem(-(e.clientY - innerHeight / 2) / (innerHeight / 2), -1, 1)
  };
}

function resetBesturing() {
  doel.x = doel.y = waarde.x = waarde.y = 0;
  aanraking = false; kanteling = null; kalibratie = null; muis = { x: 0, y: 0 };
}

el.doek.addEventListener('pointerdown', (e) => {
  if (e.pointerType === 'mouse') return;
  aanraking = true;
  Object.assign(doel, schermPositie(e));
});
el.doek.addEventListener('pointermove', (e) => {
  if (e.pointerType === 'mouse' || !aanraking) return;
  Object.assign(doel, schermPositie(e));
});
for (const naam of ['pointerup', 'pointercancel']) {
  addEventListener(naam, (e) => { if (e.pointerType !== 'mouse') aanraking = false; });
}
addEventListener('pointermove', (e) => {
  if (e.pointerType === 'mouse' && scherm === 'vlucht') muis = schermPositie(e);
});

function bijKanteling(e) {
  if (e.beta === null || e.gamma === null) return;
  if (!kalibratie) kalibratie = { beta: e.beta, gamma: e.gamma };
  const db = (e.beta - kalibratie.beta) / KANTEL_BEREIK;
  const dg = (e.gamma - kalibratie.gamma) / KANTEL_BEREIK;
  const hoek = ((screen.orientation && screen.orientation.angle) || window.orientation || 0);
  let x, y;
  if (hoek === 90) { x = db; y = dg; }
  else if (hoek === 270 || hoek === -90) { x = -db; y = -dg; }
  else if (hoek === 180) { x = -dg; y = db; }
  else { x = dg; y = -db; }
  kanteling = { x: klem(x, -1, 1), y: klem(y, -1, 1) };
}

function kiesDoel() {
  if (aanraking) return;                       // doel wordt door de vinger gezet
  const bron = kanteling || muis;
  doel.x = bron.x; doel.y = bron.y;
}
// Loslaten: de vinger zet het doel niet meer, dus terug naar het midden (tenzij kanteling/muis iets anders zeggen)

// ---------- Vliegcamera ----------
let s = 0, tijd = 0, laatste = 0;
let yaw = 0, pitch = 0, eersteFrame = true;
const basis = new THREE.Vector3();
const richting = new THREE.Vector3();

function zetCameraBegin() {
  s = 0; tijd = 0; laatste = 0; yaw = 0; pitch = 0; eersteFrame = true;
  camera.position.set(0, 0, 0);
  camera.rotation.set(0, 0, 0);
}

function volg(huidig, doelwaarde, dt, tau) {
  return huidig + (doelwaarde - huidig) * (1 - Math.exp(-dt / tau));
}

function frame(ms) {
  if (!wereld) return;
  const nu = ms / 1000;
  const dt = laatste ? Math.min(0.1, nu - laatste) : 0.016;
  laatste = nu;
  tijd += dt;
  s += info.snelheid * dt * (minderBeweging ? 0.5 : 1);

  // Besturing: doel kiezen en zacht volgen
  kiesDoel();
  const tau = minderBeweging ? 2.5 : 1.5;
  waarde.x = volg(waarde.x, doel.x, dt, tau);
  waarde.y = volg(waarde.y, doel.y, dt, tau);

  // Kijkrichting uit het pad, sterk afgevlakt, zonder roll
  wereld.pad(s, basis);
  wereld.pad(s + KIJK_VOORUIT, richting);
  const dx = richting.x - basis.x, dy = richting.y - basis.y, dz = richting.z - basis.z;
  const yawDoel = Math.atan2(-dx, -dz);
  const pitchDoel = klem(Math.atan2(dy, Math.hypot(dx, dz)), -MAX_PITCH, MAX_PITCH);
  if (eersteFrame) { yaw = yawDoel; pitch = pitchDoel; eersteFrame = false; }
  else { yaw = volg(yaw, yawDoel, dt, 1); pitch = volg(pitch, pitchDoel, dt, 1); }
  camera.rotation.set(pitch, yaw, 0);

  // Stuurverschuiving: zijwaarts loodrecht op de kijkrichting, verticaal omhoog
  const zij = waarde.x * info.stuurbereik.x;
  camera.position.set(
    basis.x + Math.cos(yaw) * zij,
    basis.y + waarde.y * info.stuurbereik.y,
    basis.z - Math.sin(yaw) * zij
  );

  const n = audio.niveaus();
  wereld.update(tijd, n, { positie: camera.position, s, dt, camera });
  renderer.render(scene, camera);
  bewaakKwaliteit(nu);
}

// ---------- Kwaliteitsbewaking ----------
let meetStart = 0, meetFrames = 0, vluchtStart = 0;

function bewaakKwaliteit(nu) {
  if (!vluchtStart) vluchtStart = nu;
  if (nu - vluchtStart < 3) return;               // eerste 3 s overslaan
  if (!meetStart) { meetStart = nu; meetFrames = 0; return; }
  meetFrames++;
  const duur = nu - meetStart;
  if (duur < 2) return;
  const fps = meetFrames / duur;
  meetStart = nu; meetFrames = 0;
  if (fps >= 45) return;
  const traagBijLaag = stappen[stapIndex] <= 1;
  if (stapIndex < stappen.length - 1) {
    stapIndex++;
    pasPixelRatioToe();
    maatAan();
  }
  if (traagBijLaag && !laagGezet) {
    laagGezet = true;
    if (wereld.setKwaliteit) wereld.setKwaliteit('laag');
  }
}

function start() {
  laatste = 0; meetStart = 0; meetFrames = 0; vluchtStart = 0;
  renderer.setAnimationLoop(frame);
}

function pauzeer() { if (renderer) renderer.setAnimationLoop(null); }

document.addEventListener('visibilitychange', () => {
  if (scherm !== 'vlucht' || !wereld) return;
  if (document.hidden) { pauzeer(); laat(); }
  else if (!bezigMetTerug) { start(); vraagWakeLock(); }
});

// ---------- Terugknop ----------
let bezigMetTerug = false;
let terugTimer = 0;

function toonTerug() {
  el.terug.classList.add('zichtbaar');
  clearTimeout(terugTimer);
  terugTimer = setTimeout(() => el.terug.classList.remove('zichtbaar'), 3500);
}
for (const naam of ['pointermove', 'pointerdown', 'touchstart']) {
  addEventListener(naam, () => { if (scherm === 'vlucht') toonTerug(); }, { passive: true });
}

async function terug() {
  if (bezig || scherm !== 'vlucht') return;
  bezig = bezigMetTerug = true;
  clearTimeout(terugTimer);
  el.terug.classList.remove('zichtbaar');
  await Promise.all([fade(1, 2.5), audio.stop({ fadeOut: 2.5 }).catch(() => {})]);
  opruimen();
  toon('keuze');
  await fade(0, 1);
  bezig = bezigMetTerug = false;
}

el.terug.addEventListener('click', terug);
addEventListener('keydown', (e) => { if (e.key === 'Escape') terug(); });

// Alles van de vlucht opruimen
function opruimen() {
  pauzeer();
  window.removeEventListener('deviceorientation', bijKanteling);
  laat();
  if (wereld) {
    try { wereld.dispose(); } catch (e) { console.error(e); }
  }
  wereld = null; info = null;
  while (scene.children.length) scene.remove(scene.children[0]);
  scene.background = null; scene.fog = null;
  resetBesturing();
}

// ---------- Scherm wakker houden ----------
async function vraagWakeLock() {
  try {
    if ('wakeLock' in navigator && !wakeLock) {
      wakeLock = await navigator.wakeLock.request('screen');
      wakeLock.addEventListener('release', () => { wakeLock = null; });
    }
  } catch (e) { wakeLock = null; }
}
function laat() {
  try { if (wakeLock) wakeLock.release(); } catch (e) { /* negeren */ }
  wakeLock = null;
}

// ---------- Service worker ----------
if ('serviceWorker' in navigator && /^https?:$/.test(location.protocol)) {
  addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
