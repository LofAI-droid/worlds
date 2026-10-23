// Zweef: geluid. Laden, naadloos loopen (crossfade), faden en analyse.
// Graaf: bronnen -> lusGain (per bron) -> hoofdGain -> analyser -> destination.

const CROSSFADE = 6;      // seconden overlap tussen twee bronnen
const VOORUIT = 10;       // seconden vóór de overgang waarop de volgende bron gepland wordt
const MIN_LUS = 20;       // korter dan dit: gewoon source.loop

let ctx = null;
let hoofd = null;
let analyserNode = null;
let freqData = null;

let buffer = null;        // alleen de laatst geladen buffer
let bufferUrl = null;
let bezig = null;         // { url, belofte } tijdens het laden

let bronnen = new Set();  // { bron, gain }
let timer = null;
let speelt = false;
let token = 0;            // ophogen = lopende speel/stop-acties zijn achterhaald

// Vaste curves voor de equal-power crossfade en de zachte fades
const STAPPEN = 64;
const curveUit = new Float32Array(STAPPEN);
const curveIn = new Float32Array(STAPPEN);
for (let i = 0; i < STAPPEN; i++) {
  const x = (i / (STAPPEN - 1)) * Math.PI / 2;
  curveUit[i] = Math.cos(x);
  curveIn[i] = Math.sin(x);
}

function maakContext() {
  if (ctx) return ctx;
  const AC = window.AudioContext || window.webkitAudioContext;
  ctx = new AC();
  hoofd = ctx.createGain();
  hoofd.gain.value = 0;
  analyserNode = ctx.createAnalyser();
  analyserNode.fftSize = 512;
  analyserNode.smoothingTimeConstant = 0.8;
  freqData = new Uint8Array(analyserNode.frequencyBinCount);
  hoofd.connect(analyserNode);
  analyserNode.connect(ctx.destination);
  // iOS kan de context onderbreken (bel, Siri): probeer te hervatten
  ctx.addEventListener('statechange', () => {
    if (ctx.state === 'interrupted') hervat();
  });
  return ctx;
}

function hervat() {
  if (!ctx) return;
  try {
    const p = ctx.resume();
    if (p && p.catch) p.catch(() => {});
  } catch (e) { /* niets */ }
}

function wisTimer() {
  if (timer !== null) { clearTimeout(timer); timer = null; }
}

// Alle bronnen meteen stoppen, met een heel korte fade tegen tikken
function stopBronnen() {
  wisTimer();
  speelt = false;
  const nu = ctx ? ctx.currentTime : 0;
  for (const b of bronnen) {
    try {
      b.gain.gain.cancelScheduledValues(nu);
      b.gain.gain.setValueAtTime(b.gain.gain.value, nu);
      b.gain.gain.linearRampToValueAtTime(0, nu + 0.03);
      b.bron.onended = null;
      b.bron.stop(nu + 0.05);
    } catch (e) { /* al gestopt */ }
    const gain = b.gain, bron = b.bron;
    setTimeout(() => {
      try { bron.disconnect(); } catch (e) { /* niets */ }
      try { gain.disconnect(); } catch (e) { /* niets */ }
    }, 120);
  }
  bronnen = new Set();
}

// Eén bron plannen vanaf ctx-tijd `start`; `kruis` = er loopt al een vorige bron
function plan(start, kruis) {
  const bron = ctx.createBufferSource();
  bron.buffer = buffer;
  const gain = ctx.createGain();
  bron.connect(gain);
  gain.connect(hoofd);
  const item = { bron, gain };
  bronnen.add(item);
  bron.onended = () => {
    bronnen.delete(item);
    try { bron.disconnect(); } catch (e) { /* niets */ }
    try { gain.disconnect(); } catch (e) { /* niets */ }
  };

  if (buffer.duration < MIN_LUS) {
    bron.loop = true;
    gain.gain.value = 1;
    bron.start(start);
    return;
  }

  if (kruis) {
    gain.gain.value = 0;
    gain.gain.setValueCurveAtTime(curveIn, start, CROSSFADE);
  } else {
    gain.gain.value = 1;
  }
  bron.start(start);

  const einde = start + buffer.duration;
  const volgende = einde - CROSSFADE;
  // Oude bron zakt tijdens de laatste CROSSFADE seconden volgens cos
  gain.gain.setValueCurveAtTime(curveUit, volgende, CROSSFADE);

  // Volgende bron ruim op tijd inplannen (timing zelf blijft op de context-klok)
  const wacht = Math.max(0, (volgende - VOORUIT - ctx.currentTime) * 1000);
  const mijnToken = token;
  wisTimer();
  timer = setTimeout(() => {
    timer = null;
    if (mijnToken !== token || !speelt) return;
    plan(volgende, true);
  }, wacht);
}

function decode(data) {
  // callbackvorm met Promise-wrapper voor oudere Safari
  return new Promise((ok, fout) => {
    const p = ctx.decodeAudioData(data, ok, fout);
    if (p && p.catch) p.catch(fout);
  });
}

function zichtbaarheid() {
  if (!ctx) return;
  if (document.hidden) {
    try {
      const p = ctx.suspend();
      if (p && p.catch) p.catch(() => {});
    } catch (e) { /* niets */ }
  } else if (speelt) {
    hervat();
  }
}
document.addEventListener('visibilitychange', zichtbaarheid);

// Banden voor niveaus()
const resultaat = { niveau: 0, laag: 0, midden: 0, hoog: 0 };
function bandGemiddelde(van, tot) {
  if (tot <= van) return 0;
  let som = 0;
  for (let i = van; i < tot; i++) som += freqData[i];
  return som / (tot - van) / 255;
}
function afvlakken(oud, doel) {
  return oud + (doel - oud) * (doel > oud ? 0.25 : 0.05);
}

export const audio = {
  ontgrendel() {
    try {
      if (navigator.audioSession) navigator.audioSession.type = 'playback';
    } catch (e) { /* niet ondersteund */ }
    try {
      maakContext();
      if (ctx.state !== 'running') hervat();
    } catch (e) {
      console.warn('Audio ontgrendelen mislukt:', e);
    }
  },

  laad(url) {
    if (buffer && bufferUrl === url) return Promise.resolve(buffer);
    if (bezig && bezig.url === url) return bezig.belofte;
    maakContext();
    const belofte = (async () => {
      let res;
      try {
        res = await fetch(url);
      } catch (e) {
        throw new Error('Muziek laden mislukt (netwerk): ' + url);
      }
      if (!res.ok) throw new Error('Muziek laden mislukt (' + res.status + '): ' + url);
      const data = await res.arrayBuffer();
      let nieuw;
      try {
        nieuw = await decode(data);
      } catch (e) {
        throw new Error('Muziek decoderen mislukt: ' + url);
      }
      buffer = nieuw;
      bufferUrl = url;
      return nieuw;
    })();
    bezig = { url, belofte };
    const klaar = () => { if (bezig && bezig.belofte === belofte) bezig = null; };
    belofte.then(klaar, klaar);
    return belofte;
  },

  get analyser() {
    return analyserNode;
  },

  async speel(url, { fadeIn = 4 } = {}) {
    const mijnToken = ++token;
    maakContext();
    stopBronnen();
    await audio.laad(url);
    if (mijnToken !== token) return; // intussen iets anders gevraagd
    if (ctx.state !== 'running') hervat();

    const nu = ctx.currentTime;
    const duur = Math.max(0.05, fadeIn);
    // Zachte S-curve van stilte naar 1
    const curve = new Float32Array(STAPPEN);
    for (let i = 0; i < STAPPEN; i++) {
      const s = Math.sin((i / (STAPPEN - 1)) * Math.PI / 2);
      curve[i] = s * s;
    }
    hoofd.gain.cancelScheduledValues(nu);
    hoofd.gain.setValueAtTime(0, nu);
    hoofd.gain.setValueCurveAtTime(curve, nu + 0.02, duur);

    speelt = true;
    plan(nu + 0.05, false);
  },

  async stop({ fadeOut = 2.5 } = {}) {
    const mijnToken = ++token;
    if (!ctx || !speelt) {
      if (ctx) stopBronnen();
      return;
    }
    const nu = ctx.currentTime;
    const huidig = hoofd.gain.value;
    const duur = Math.max(0.05, fadeOut);
    const curve = new Float32Array(STAPPEN);
    for (let i = 0; i < STAPPEN; i++) {
      curve[i] = huidig * Math.cos((i / (STAPPEN - 1)) * Math.PI / 2);
    }
    hoofd.gain.cancelScheduledValues(nu);
    hoofd.gain.setValueAtTime(huidig, nu);
    hoofd.gain.setValueCurveAtTime(curve, nu + 0.01, duur);
    wisTimer();
    await new Promise((ok) => setTimeout(ok, duur * 1000 + 80));
    if (mijnToken !== token) return; // intussen een nieuwe speel() gestart
    stopBronnen();
    hoofd.gain.cancelScheduledValues(ctx.currentTime);
    hoofd.gain.setValueAtTime(0, ctx.currentTime);
  },

  niveaus() {
    if (!analyserNode || !speelt) {
      resultaat.niveau = resultaat.laag = resultaat.midden = resultaat.hoog = 0;
      return resultaat;
    }
    analyserNode.getByteFrequencyData(freqData);
    const hzPerBin = ctx.sampleRate / analyserNode.fftSize;
    const n = freqData.length;
    const grens1 = Math.min(n, Math.max(2, Math.round(250 / hzPerBin)));
    const grens2 = Math.min(n, Math.max(grens1 + 1, Math.round(2000 / hzPerBin)));
    const eind = Math.min(n, Math.max(grens2 + 1, Math.round(12000 / hzPerBin)));

    const laag = bandGemiddelde(1, grens1);
    const midden = bandGemiddelde(grens1, grens2);
    const hoog = Math.min(1, bandGemiddelde(grens2, eind) * 1.6);
    const alles = bandGemiddelde(1, eind);

    resultaat.laag = afvlakken(resultaat.laag, laag);
    resultaat.midden = afvlakken(resultaat.midden, midden);
    resultaat.hoog = afvlakken(resultaat.hoog, hoog);
    resultaat.niveau = afvlakken(resultaat.niveau, alles);
    return resultaat;
  }
};
