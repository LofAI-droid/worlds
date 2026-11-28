// Rave against the machine — besturing met een controller (Gamepad API).
// Nacon PC-controllers gedragen zich als een Xbox-controller (XInput); browsers geven ze de
// "standard"-indeling. Knopnummers hieronder volgen die indeling.

export const KNOP = {
  A: 0, B: 1, X: 2, Y: 3, LB: 4, RB: 5, LT: 6, RT: 7,
  SELECT: 8, START: 9, L3: 10, R3: 11, OP: 12, NEER: 13, LINKS: 14, RECHTS: 15
};
const DODE_ZONE = 0.15;

function stick(x, y) {
  const d = Math.hypot(x, y);
  if (d < DODE_ZONE) return { x: 0, y: 0, d: 0 };
  // buiten de dode zone herschalen naar 0..1 en kwadratisch, voor fijne controle bij kleine uitslag
  const n = Math.min(1, (d - DODE_ZONE) / (1 - DODE_ZONE));
  const f = (n * n) / d;
  return { x: x * f, y: y * f, d: n * n };
}

export class Pad {
  constructor() {
    this.index = null;
    this.naam = '';
    this.vorig = [];
    this.links = { x: 0, y: 0, d: 0 };
    this.rechts = { x: 0, y: 0, d: 0 };
    this.rt = 0;
    this.lt = 0;
    this.gedrukt = new Set();      // knoppen die deze frame neergingen
    this.vast = new Set();         // knoppen die nu ingedrukt zijn
    this.onVerbonden = null;
    this.onVerbroken = null;
    addEventListener('gamepadconnected', (e) => this.verbind(e.gamepad));
    addEventListener('gamepaddisconnected', (e) => {
      if (e.gamepad.index !== this.index) return;
      this.index = null;
      this.leeg();
      this.zoek();
      if (this.index === null && this.onVerbroken) this.onVerbroken();
    });
  }

  get actief() { return this.index !== null; }

  verbind(gp) {
    if (!gp || this.index !== null) return;
    this.index = gp.index;
    this.naam = gp.id || 'controller';
    this.vorig = gp.buttons.map((b) => b.pressed);   // knoppen die al vastzitten tellen niet als druk
    if (this.onVerbonden) this.onVerbonden(this.naam);
  }

  zoek() {
    const lijst = navigator.getGamepads ? navigator.getGamepads() : [];
    for (const gp of lijst) if (gp && gp.connected) { this.verbind(gp); break; }
  }

  leeg() {
    this.links = { x: 0, y: 0, d: 0 };
    this.rechts = { x: 0, y: 0, d: 0 };
    this.rt = this.lt = 0;
    this.gedrukt.clear();
    this.vast.clear();
  }

  /** Eén keer per frame aanroepen. */
  lees() {
    this.gedrukt.clear();
    this.vast.clear();
    if (!navigator.getGamepads) return;
    if (this.index === null) this.zoek();
    if (this.index === null) return;
    const gp = navigator.getGamepads()[this.index];
    if (!gp || !gp.connected) { this.leeg(); return; }
    const as = gp.axes;
    this.links = stick(as[0] || 0, as[1] || 0);
    this.rechts = stick(as[2] || 0, as[3] || 0);
    const knop = (i) => gp.buttons[i] || { pressed: false, value: 0 };
    this.lt = knop(KNOP.LT).value || (knop(KNOP.LT).pressed ? 1 : 0);
    this.rt = knop(KNOP.RT).value || (knop(KNOP.RT).pressed ? 1 : 0);
    gp.buttons.forEach((b, i) => {
      if (b.pressed) this.vast.add(i);
      if (b.pressed && !this.vorig[i]) this.gedrukt.add(i);
      this.vorig[i] = b.pressed;
    });
  }

  druk(k) { return this.gedrukt.has(k); }
  houd(k) { return this.vast.has(k); }

  /** Korte trilling, waar de browser en de controller dat kunnen. */
  tril(duur = 180, zwak = 0.5, sterk = 0.8) {
    if (this.index === null || !navigator.getGamepads) return;
    const gp = navigator.getGamepads()[this.index];
    const v = gp && gp.vibrationActuator;
    if (!v || !v.playEffect) return;
    v.playEffect('dual-rumble', { duration: duur, weakMagnitude: zwak, strongMagnitude: sterk }).catch(() => {});
  }
}
