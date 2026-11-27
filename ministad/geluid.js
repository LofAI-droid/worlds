// Ministad — alle geluiden, in de browser opgewekt met Web Audio (geen geluidsbestanden).
// Losse geluiden (stap, deurbel, kassa...) en achtergrond (stad, verkeer, vogels).

const rnd = (a, b) => a + Math.random() * (b - a);

export class Geluid {
  constructor() {
    this.ctx = null;
    this.aan = true;
    try { this.aan = localStorage.getItem('ministad-geluid') !== 'uit'; } catch (e) { /* geen opslag */ }
    this.binnen = false;
    this.vogelTimer = 2;
    this.belTimer = 0;
  }

  /** Moet vanuit een klik of toets gestart worden (regel van de browsers). */
  start() {
    if (this.ctx) { this.ctx.resume(); return; }
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const c = this.ctx = new AC();
    this.master = c.createGain();
    this.master.gain.value = this.aan ? 0.9 : 0;
    const comp = c.createDynamicsCompressor();
    this.master.connect(comp).connect(c.destination);
    // ruisbuffers
    const n = c.sampleRate * 2;
    this.wit = c.createBuffer(1, n, c.sampleRate);
    this.bruin = c.createBuffer(1, n, c.sampleRate);
    const w = this.wit.getChannelData(0), b = this.bruin.getChannelData(0);
    let laatst = 0;
    for (let i = 0; i < n; i++) {
      w[i] = Math.random() * 2 - 1;
      laatst = (laatst + 0.02 * w[i]) / 1.02;
      b[i] = laatst * 3.5;
    }
    // achtergrond: het gezoem van de stad
    this.stad = this.lus(this.bruin);
    this.stadFilter = c.createBiquadFilter();
    this.stadFilter.type = 'lowpass';
    this.stadFilter.frequency.value = 500;
    this.stadGain = c.createGain();
    this.stadGain.gain.value = 0.05;
    this.stad.connect(this.stadFilter).connect(this.stadGain).connect(this.master);
    // verkeer: een motorgeluid dat luider wordt als er iets dichtbij rijdt
    this.motor = c.createOscillator();
    this.motor.type = 'sawtooth';
    this.motor.frequency.value = 50;
    this.motor2 = c.createOscillator();
    this.motor2.type = 'square';
    this.motor2.frequency.value = 25.3;
    const motorMix = c.createGain();
    motorMix.gain.value = 0.5;
    this.motorFilter = c.createBiquadFilter();
    this.motorFilter.type = 'lowpass';
    this.motorFilter.frequency.value = 260;
    this.motorGain = c.createGain();
    this.motorGain.gain.value = 0;
    this.motor.connect(this.motorFilter);
    this.motor2.connect(motorMix).connect(this.motorFilter);
    const rol = this.lus(this.wit);                        // banden op het asfalt
    const rolFilter = c.createBiquadFilter();
    rolFilter.type = 'bandpass';
    rolFilter.frequency.value = 700;
    rolFilter.Q.value = 0.7;
    this.rolGain = c.createGain();
    this.rolGain.gain.value = 0;
    rol.connect(rolFilter).connect(this.rolGain).connect(this.master);
    this.motorFilter.connect(this.motorGain).connect(this.master);
    this.motor.start();
    this.motor2.start();
  }

  lus(buffer) {
    const s = this.ctx.createBufferSource();
    s.buffer = buffer;
    s.loop = true;
    s.loopStart = Math.random();
    s.start(0, Math.random() * 1.5);
    return s;
  }

  zetAan(aan) {
    this.aan = aan;
    try { localStorage.setItem('ministad-geluid', aan ? 'aan' : 'uit'); } catch (e) { /* geen opslag */ }
    if (this.ctx) this.master.gain.setTargetAtTime(aan ? 0.9 : 0, this.ctx.currentTime, 0.05);
    if (!aan && window.speechSynthesis) speechSynthesis.cancel();
  }

  get klaar() { return this.ctx && this.aan && this.ctx.state === 'running'; }

  // ---------- bouwstenen ----------
  ruis(duur, filterType, freq, q, volume, wanneer = 0, attack = 0.002) {
    const c = this.ctx, t = c.currentTime + wanneer;
    const s = c.createBufferSource();
    s.buffer = this.wit;
    const f = c.createBiquadFilter();
    f.type = filterType;
    f.frequency.value = freq;
    f.Q.value = q;
    const g = c.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(volume, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + duur);
    s.connect(f).connect(g).connect(this.master);
    s.start(t, Math.random() * 1.5);
    s.stop(t + duur + 0.05);
    return { f, g, t };
  }

  toon(freq, duur, type = 'sine', volume = 0.2, wanneer = 0, attack = 0.005, glijNaar = null) {
    const c = this.ctx, t = c.currentTime + wanneer;
    const o = c.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(freq, t);
    if (glijNaar) o.frequency.exponentialRampToValueAtTime(glijNaar, t + duur);
    const g = c.createGain();
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(volume, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + duur);
    o.connect(g).connect(this.master);
    o.start(t);
    o.stop(t + duur + 0.05);
  }

  /** Een metalen klank (bel, munt): niet-harmonische boventonen die uitsterven. */
  metaal(basis, duur, volume, wanneer = 0, verhoudingen = [1, 2.76, 5.4, 8.93]) {
    verhoudingen.forEach((r, i) => this.toon(basis * r, duur / (1 + i * 0.6), 'sine', volume / (1 + i * 0.8), wanneer, 0.002));
  }

  // ---------- losse geluiden ----------
  stap(ondergrond, hard = false) {
    if (!this.klaar) return;
    const v = (hard ? 0.5 : 0.32) * rnd(0.8, 1.1);
    if (ondergrond === 'gras') {
      this.ruis(0.12, 'highpass', 2500, 0.5, v * 0.35);
    } else if (ondergrond === 'binnen') {
      this.ruis(0.05, 'bandpass', rnd(1800, 2400), 1.2, v * 0.9);
      this.ruis(0.09, 'lowpass', 300, 0.7, v * 0.6);
    } else if (ondergrond === 'straat') {
      this.ruis(0.08, 'bandpass', rnd(650, 900), 0.9, v);
    } else {
      this.ruis(0.06, 'bandpass', rnd(1200, 1600), 1.0, v);
      this.ruis(0.03, 'highpass', 4000, 0.7, v * 0.25);
    }
  }

  sprong() { if (this.klaar) this.ruis(0.18, 'bandpass', 500, 0.8, 0.12, 0, 0.04); }

  landing() { if (this.klaar) this.ruis(0.12, 'lowpass', 400, 0.7, 0.4); }

  deurbel() {
    if (!this.klaar) return;
    // een winkelbelletje dat even nadingelt
    for (let k = 0; k < 3; k++) this.metaal(rnd(1700, 1900), 0.9, 0.09 * (1 - k * 0.25), k * rnd(0.08, 0.13));
  }

  deur(open) {
    if (!this.klaar) return;
    this.ruis(0.35, 'bandpass', open ? 900 : 600, 2.5, 0.05, 0, 0.12);         // scharnier
    if (!open) this.ruis(0.14, 'lowpass', 220, 0.8, 0.5, 0.25);                // dicht
  }

  kassa() {
    if (!this.klaar) return;
    this.ruis(0.05, 'bandpass', 2500, 2, 0.15);                                // toetsen
    this.ruis(0.05, 'bandpass', 2500, 2, 0.12, 0.09);
    this.ruis(0.25, 'lowpass', 500, 0.7, 0.25, 0.2, 0.02);                     // lade
    this.metaal(2400, 0.8, 0.12, 0.22, [1, 1.5, 2.0]);                         // ting
    this.munten(0.45);
  }

  munten(wanneer = 0) {
    if (!this.klaar) return;
    for (let k = 0; k < 4; k++) this.metaal(rnd(3800, 5200), 0.18, 0.05, wanneer + k * rnd(0.04, 0.08), [1, 1.7, 2.9]);
  }

  schrap() {
    if (!this.klaar) return;
    // een potloodstreep
    const r = this.ruis(0.45, 'bandpass', 3200, 2.5, 0.12, 0, 0.03);
    r.f.frequency.linearRampToValueAtTime(4200, r.t + 0.4);
    this.toon(1320, 0.25, 'sine', 0.08, 0.35);
    this.toon(1760, 0.35, 'sine', 0.08, 0.45);
  }

  fout() {
    if (!this.klaar) return;
    this.toon(330, 0.16, 'triangle', 0.15);
    this.toon(247, 0.3, 'triangle', 0.15, 0.17);
  }

  klik() { if (this.klaar) this.ruis(0.03, 'highpass', 3000, 0.7, 0.1); }

  tik(laatste = false) {
    if (!this.klaar) return;
    this.ruis(0.02, 'highpass', 5000, 1, 0.2);
    if (laatste) this.toon(880, 0.12, 'sine', 0.12, 0.01);
  }

  gewonnen() {
    if (!this.klaar) return;
    [523, 659, 784, 1047, 1319].forEach((f, i) => this.toon(f, 0.5, 'triangle', 0.16, i * 0.11));
    this.metaal(2093, 1.5, 0.08, 0.55);
  }

  verloren() {
    if (!this.klaar) return;
    [392, 349, 311, 262].forEach((f, i) => this.toon(f, 0.45, 'triangle', 0.15, i * 0.22));
  }

  fietsbel(afstand) {
    if (!this.klaar || this.belTimer > 0) return;
    this.belTimer = 5;
    const v = Math.max(0.03, 0.18 * (1 - afstand / 14));
    this.metaal(2350, 0.45, v, 0, [1, 1.32, 2.6]);
    this.metaal(2350, 0.45, v, 0.16, [1, 1.32, 2.6]);
  }

  duiven(afstand) {
    if (!this.klaar) return;
    const v = Math.max(0.02, 0.25 * (1 - afstand / 20));
    // klapperende vleugels
    for (let k = 0; k < 7; k++) this.ruis(0.06, 'bandpass', rnd(900, 1500), 0.8, v * (1 - k / 9), k * 0.055);
  }

  vogel(volume) {
    const n = 2 + Math.floor(Math.random() * 3);
    const f = rnd(2600, 4200);
    for (let k = 0; k < n; k++) this.toon(f * rnd(0.9, 1.1), 0.09, 'sine', volume, k * rnd(0.11, 0.16), 0.01, f * rnd(1.2, 1.5));
  }

  /** De winkelier praat (spraak van de browser, als die Nederlands kent). */
  spreek(tekst, hoogte = 1) {
    if (!this.aan || !window.speechSynthesis) return;
    try {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(tekst);
      const stemmen = speechSynthesis.getVoices();
      const stem = stemmen.find((s) => /^nl-BE/i.test(s.lang)) || stemmen.find((s) => /^nl/i.test(s.lang));
      if (!stem) return;                                  // geen Nederlandse stem: liever stil
      u.voice = stem;
      u.lang = stem.lang;
      u.pitch = hoogte;
      u.rate = 1.0;
      u.volume = 0.9;
      speechSynthesis.speak(u);
    } catch (e) { /* geen spraak */ }
  }

  // ---------- achtergrond, elk beeldje ----------
  /** omgeving: { binnen, verkeer: [{ afstand, v, type }], park (afstand tot het park), fietsDichtbij } */
  update(dt, omgeving) {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    this.belTimer = Math.max(0, this.belTimer - dt);
    const binnen = omgeving.binnen;
    this.stadFilter.frequency.setTargetAtTime(binnen ? 220 : 520, t, 0.3);
    this.stadGain.gain.setTargetAtTime(binnen ? 0.025 : 0.05, t, 0.3);
    // het dichtstbijzijnde motorvoertuig bepaalt het motorgeluid
    let luid = 0, toonhoogte = 45, rol = 0;
    for (const v of omgeving.verkeer) {
      if (v.type === 'Fiets' || v.type === 'Bakfiets') continue;
      const g = Math.max(0, 1 - v.afstand / 38) ** 2 * (0.25 + Math.min(1, v.v / 8) * 0.75);
      rol += g * Math.min(1, v.v / 6);
      if (g > luid) {
        luid = g;
        toonhoogte = (v.type === 'Bus' ? 32 : v.type === 'Scooter' ? 95 : 42) + v.v * (v.type === 'Scooter' ? 9 : 4);
      }
    }
    const demp = binnen ? 0.25 : 1;
    this.motorGain.gain.setTargetAtTime(Math.min(0.22, luid * 0.22) * demp, t, 0.15);
    this.motor.frequency.setTargetAtTime(toonhoogte, t, 0.2);
    this.motor2.frequency.setTargetAtTime(toonhoogte * 0.503, t, 0.2);
    this.rolGain.gain.setTargetAtTime(Math.min(0.05, rol * 0.05) * demp, t, 0.2);
    // vogels: vaker in het park, niet binnen
    this.vogelTimer -= dt;
    if (this.vogelTimer <= 0) {
      const bijPark = Math.max(0, 1 - omgeving.park / 60);
      this.vogelTimer = rnd(2, 7) * (1 - bijPark * 0.6);
      if (!binnen && this.aan) this.vogel(0.012 + bijPark * 0.035);
    }
    if (omgeving.fietsDichtbij !== null && omgeving.fietsDichtbij !== undefined && !binnen) this.fietsbel(omgeving.fietsDichtbij);
  }
}
