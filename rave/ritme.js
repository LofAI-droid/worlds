// Rave against the machine — de beat.
// Eén gedeeld object `ritme` dat licht.js en dansers.js elke frame lezen:
//   beat     0..1 puls die op elke kick naar 1 springt en snel uitdooft
//   bpm      geschat of vast tempo
//   fase     'basis' | 'opbouw' | 'drop'
//   energie  0..1 hoe vol het nu klinkt
//   bron     'microfoon' | 'tempo'
// Extra (handig, niet verplicht): tel (aantal beats), beatFase (0..1 binnen de beat),
// spanning (0..1 hoe ver de opbouw is), drop (0..1 vloeiend), sindsWissel (s in deze fase).
//
// Spotify geeft geen toegang tot de audio. Daarom luisteren we (met toestemming) via de
// microfoon naar wat uit de luidsprekers komt, of tikken we op een vast tempo.

export const ritme = {
  beat: 0, bpm: 142, fase: 'basis', energie: 0.35, bron: 'tempo',
  tel: 0, beatFase: 0, spanning: 0, drop: 0, sindsWissel: 0
};

const FASEN = ['basis', 'opbouw', 'drop'];
const params = new URLSearchParams(location.search);
const gedwongen = FASEN.includes(params.get('fase')) ? params.get('fase') : null;
const startBpm = Math.min(180, Math.max(90, Number(params.get('bpm')) || 142));
ritme.bpm = startBpm;
const DOOF = 7.5;                      // hoe snel de beat-puls uitdooft (1/s)

const klem = (v, a, b) => Math.max(a, Math.min(b, v));

// =====================================================================
//  Terugval: vast tempo met een eigen cyclus basis -> opbouw -> drop
// =====================================================================
const tempo = {
  bpm: startBpm,
  fase: 0,              // positie binnen de huidige beat (0..1)
  beats: 0,             // beats in de huidige cyclus
  cyclus: null,         // { basis, opbouw, drop } in beats
  taps: []
};

function nieuweCyclus() {
  // ≈ 70% basis, 15% opbouw, 15% drop; 2 à 3 minuten bij ~142 BPM; op hele maten (4 beats)
  const maten = 72 + Math.floor(Math.random() * 6) * 8;           // 72..112 maten
  const opbouw = Math.max(8, Math.round(maten * 0.15 / 4) * 4);
  const drop = Math.max(8, Math.round(maten * 0.15 / 4) * 4);
  tempo.cyclus = { basis: (maten - opbouw - drop) * 4, opbouw: opbouw * 4, drop: drop * 4 };
  tempo.beats = 0;
}
nieuweCyclus();
// begin niet altijd vooraan in de basis: dan zie je sneller iets gebeuren
tempo.beats = Math.floor(tempo.cyclus.basis * 0.55 / 4) * 4;

function tempoFase() {
  const c = tempo.cyclus, b = tempo.beats + tempo.fase;
  if (b < c.basis) return ['basis', b / c.basis];
  if (b < c.basis + c.opbouw) return ['opbouw', (b - c.basis) / c.opbouw];
  return ['drop', (b - c.basis - c.opbouw) / c.drop];
}

function stapTempo(dt) {
  tempo.fase += dt * tempo.bpm / 60;
  let kick = false;
  while (tempo.fase >= 1) {
    tempo.fase -= 1;
    tempo.beats++;
    kick = true;
    const c = tempo.cyclus;
    if (tempo.beats >= c.basis + c.opbouw + c.drop) nieuweCyclus();
  }
  const [eigen, voortgang] = tempoFase();
  const fase = gedwongen || eigen;
  ritme.bpm = tempo.bpm;
  ritme.beatFase = tempo.fase;
  if (kick) {
    // in de laatste maten van de opbouw valt de kick weg (zoals in echte psytrance), dan de drop
    const stil = fase === 'opbouw' && voortgang > 0.75;
    if (!stil) geefBeat(fase === 'basis' ? 0.85 : 1);
  }
  zetFase(fase);
  ritme.spanning = fase === 'opbouw' ? voortgang : 0;
  const doelE = fase === 'drop' ? 0.95 : fase === 'opbouw' ? 0.45 + voortgang * 0.45 : 0.4;
  ritme.energie += (doelE - ritme.energie) * Math.min(1, dt * 1.5);
}

/** Meetikken: tempo (vanaf 3 tikken) en beatfase gelijkzetten. */
export function tik() {
  const nu = performance.now() / 1000;
  const t = tempo.taps;
  if (t.length && nu - t[t.length - 1] > 2) t.length = 0;
  t.push(nu);
  if (t.length > 9) t.shift();
  if (t.length >= 3) {
    const tussen = [];
    for (let i = 1; i < t.length; i++) tussen.push(t[i] - t[i - 1]);
    tussen.sort((a, b) => a - b);
    const mediaan = tussen[Math.floor(tussen.length / 2)];
    tempo.bpm = klem(Math.round(60 / mediaan * 2) / 2, 80, 190);
  }
  tempo.fase = 0;                      // de tik valt op de beat
  geefBeat(1);
  if (mic.aan) mic.tikBpm = tempo.bpm;
  return tempo.bpm;
}

/** Spring in de eigen cyclus naar het begin van de drop (toets X). */
export function dropNu() {
  const c = tempo.cyclus;
  tempo.beats = c.basis + c.opbouw;
  tempo.fase = 0;
  geefBeat(1);
}

// =====================================================================
//  Microfoon: kicks, tempo en fase uit het geluid in de kamer
// =====================================================================
const mic = {
  aan: false, ctx: null, analyser: null, stroom: null, timer: 0,
  spec: null, vorig: null,
  flux: [], onsets: [], laatsteOnset: -1, laatsteBeat: -1,
  kort: 0, lang: 0, hoog: 0, hoogLang: 0, piek: 1e-6,
  hoogGeschiedenis: [], gatSinds: 0, kickTerugSinds: -100,
  bpm: startBpm, tikBpm: 0, interneFase: 0, faseKandidaat: 'basis', kandidaatSinds: 0
};

/** Vraag de microfoon. Geeft een belofte die true geeft als het lukte. */
export async function startMicrofoon() {
  if (mic.aan) return true;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error('geen microfoon-API');
  const stroom = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 }
  });
  const AC = window.AudioContext || window.webkitAudioContext;
  const ctx = new AC({ latencyHint: 'interactive' });
  if (ctx.state === 'suspended') await ctx.resume();
  const bron = ctx.createMediaStreamSource(stroom);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;                 // ~21 ms venster bij 48 kHz
  analyser.smoothingTimeConstant = 0;
  analyser.minDecibels = -100;
  analyser.maxDecibels = -10;
  bron.connect(analyser);                  // niet naar ctx.destination: we spelen niets af
  Object.assign(mic, {
    aan: true, ctx, analyser, stroom,
    spec: new Float32Array(analyser.frequencyBinCount),
    vorig: new Float32Array(analyser.frequencyBinCount),
    flux: [], onsets: [], laatsteOnset: -1, laatsteBeat: -1, gatSinds: 0
  });
  ritme.bron = 'microfoon';
  mic.timer = setInterval(analyseer, 10);   // los van de framesnelheid
  stroom.getAudioTracks().forEach((t) => t.addEventListener('ended', stopMicrofoon));
  return true;
}

export function stopMicrofoon() {
  if (!mic.aan) return;
  clearInterval(mic.timer);
  mic.stroom.getTracks().forEach((t) => t.stop());
  mic.ctx.close().catch(() => {});
  mic.aan = false;
  ritme.bron = 'tempo';
  tempo.bpm = Math.round(mic.bpm);
}

export const microfoonAan = () => mic.aan;

function band(spec, hz0, hz1) {
  const n = spec.length, ny = mic.ctx.sampleRate / 2;
  const a = Math.max(1, Math.floor(hz0 / ny * n)), b = Math.min(n - 1, Math.ceil(hz1 / ny * n));
  return [a, b];
}

function analyseer() {
  const nu = mic.ctx.currentTime;
  const { analyser, spec, vorig } = mic;
  analyser.getFloatFrequencyData(spec);           // dB
  const [k0, k1] = band(spec, 35, 130);           // kick
  const [h0, h1] = band(spec, 4000, 12000);       // hi-hats, ruis-opbouw
  let flux = 0, laag = 0, hoog = 0, alles = 0;
  for (let i = 1; i < spec.length; i++) {
    const db = Math.max(-100, spec[i]);
    const mag = Math.pow(10, db / 20);
    alles += mag * mag;
    if (i >= k0 && i <= k1) {
      const d = db - vorig[i];                        // log-spectrale flux, halfgolf gelijkgericht
      if (d > 0) flux += d;
      laag += mag * mag;
    } else if (i >= h0 && i <= h1) hoog += mag * mag;
    vorig[i] = db;
  }
  flux /= (k1 - k0 + 1);

  // energie: kort (~0.7 s) en lang (~10 s), automatisch genormaliseerd op de recente piek
  const rms = Math.sqrt(alles / spec.length);
  mic.kort += (rms - mic.kort) * 0.014;
  mic.lang += (rms - mic.lang) * 0.001;
  mic.piek = Math.max(mic.piek * 0.99995, mic.kort);
  mic.hoog += (hoog - mic.hoog) * 0.02;
  mic.hoogLang += (hoog - mic.hoogLang) * 0.002;

  // adaptieve drempel: mediaan + k * gemiddelde afwijking over ~1.5 s
  const f = mic.flux;
  f.push(flux);
  if (f.length > 150) f.shift();
  const gesorteerd = [...f].sort((a, b) => a - b);
  const med = gesorteerd[gesorteerd.length >> 1];
  let afw = 0;
  for (const v of f) afw += Math.abs(v - med);
  afw /= f.length;
  const drempel = med + Math.max(1.2, afw * 2.2);
  const periode = 60 / mic.bpm;
  const genoegStil = nu - mic.laatsteOnset > Math.max(0.26, periode * 0.62);
  const luid = laag > 1e-7;
  if (f.length > 30 && flux > drempel && genoegStil && luid) {
    mic.laatsteOnset = nu;
    mic.onsets.push(nu);
    while (mic.onsets.length && nu - mic.onsets[0] > 10) mic.onsets.shift();
    schatBpm();
    const sterkte = klem((flux - med) / (afw * 6 + 3), 0.55, 1);
    geefBeat(sterkte);
    mic.laatsteBeat = nu;
    mic.interneFase = 0;
    if (mic.gatSinds > 3.5) mic.kickTerugSinds = nu;   // kick komt terug na een break
    mic.gatSinds = 0;
  } else {
    // ontbrekende kick opvullen zolang het patroon stabiel is (gemiste detectie)
    const sinds = nu - mic.laatsteBeat;
    if (mic.onsets.length > 6 && nu - mic.laatsteOnset < periode * 2.2 && sinds > periode * 1.08) {
      geefBeat(0.55);
      mic.laatsteBeat = nu - (sinds - periode);
    }
    mic.gatSinds = nu - mic.laatsteOnset;
  }
  mic.interneFase = klem((nu - mic.laatsteBeat) / periode, 0, 1);
  bepaalFase(nu);
}

function schatBpm() {
  const o = mic.onsets;
  if (o.length < 5) return;
  // histogram van alle tussentijden (ook over 2-4 beats), gevouwen naar 110..180 BPM
  const bakken = new Float32Array(141);           // 110..180 in halve BPM
  for (let i = 0; i < o.length; i++) {
    for (let j = i + 1; j < o.length && j < i + 5; j++) {
      const d = o[j] - o[i];
      for (let n = 1; n <= 4; n++) {
        let bpm = 60 / (d / n);
        if (bpm < 105 || bpm > 185) continue;
        while (bpm < 110) bpm *= 2;
        while (bpm > 180) bpm /= 2;
        const gewicht = 1 / n;
        const c = (bpm - 110) * 2;
        for (let k = Math.max(0, Math.floor(c) - 3); k <= Math.min(140, Math.ceil(c) + 3); k++) {
          bakken[k] += gewicht * Math.exp(-((k - c) ** 2) / 4);
        }
      }
    }
  }
  // voorkeur voor psytrance (135..150)
  let beste = 0, besteW = -1;
  for (let k = 0; k <= 140; k++) {
    const bpm = 110 + k / 2;
    const w = bakken[k] * (bpm >= 134 && bpm <= 151 ? 1.35 : 1);
    if (w > besteW) { besteW = w; beste = bpm; }
  }
  if (besteW > 0) mic.bpm += (beste - mic.bpm) * 0.25;
  if (mic.tikBpm) mic.bpm += (mic.tikBpm - mic.bpm) * 0.5, mic.tikBpm = 0;
}

function bepaalFase(nu) {
  // basis: kick loopt gewoon. opbouw: kick weg (break) maar hoog/energie stijgt, of hoog
  // klimt duidelijk boven het lange gemiddelde. drop: kick terug na een break, of de korte
  // energie ligt duidelijk boven de lange.
  const verhouding = mic.kort / Math.max(1e-6, mic.lang);
  const hoogStijgt = mic.hoog / Math.max(1e-9, mic.hoogLang);
  let kandidaat = 'basis';
  if (mic.gatSinds > 1.6) kandidaat = hoogStijgt > 1.15 || verhouding > 1.02 ? 'opbouw' : 'basis';
  else if (nu - mic.kickTerugSinds < 24 || verhouding > 1.18) kandidaat = 'drop';
  else if (hoogStijgt > 1.45) kandidaat = 'opbouw';
  if (kandidaat !== mic.faseKandidaat) { mic.faseKandidaat = kandidaat; mic.kandidaatSinds = nu; }
  // naar drop meteen, andere wissels pas na 2.5 s (geen geflikker)
  if (kandidaat === 'drop' || nu - mic.kandidaatSinds > 2.5) zetFase(kandidaat);
  ritme.energie = klem(mic.kort / mic.piek, 0, 1) * 0.85 + (ritme.fase === 'drop' ? 0.15 : 0);
  ritme.spanning = ritme.fase === 'opbouw' ? klem((hoogStijgt - 1) * 1.5, 0, 1) : 0;
}

// =====================================================================
//  Gemeenschappelijk
// =====================================================================
function geefBeat(sterkte) {
  ritme.beat = Math.max(ritme.beat, sterkte);
  ritme.tel++;
}

function zetFase(f) {
  if (gedwongen) f = gedwongen;
  if (f !== ritme.fase) { ritme.fase = f; ritme.sindsWissel = 0; }
}

/** Elke frame oproepen. */
export function stapRitme(dt) {
  ritme.beat *= Math.exp(-DOOF * dt);
  ritme.sindsWissel += dt;
  if (mic.aan) {
    ritme.bpm = Math.round(mic.bpm * 2) / 2;
    ritme.beatFase = mic.interneFase;
    // de eigen klok loopt mee, zodat een terugval naar tempo naadloos is
    tempo.bpm = ritme.bpm;
  } else {
    stapTempo(dt);
  }
  if (gedwongen) zetFase(gedwongen);
  const doelDrop = ritme.fase === 'drop' ? 1 : 0;
  ritme.drop += (doelDrop - ritme.drop) * Math.min(1, dt * (doelDrop ? 4 : 0.8));
}
