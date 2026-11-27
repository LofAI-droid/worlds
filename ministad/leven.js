// Ministad — het leven in de stad: verkeer, voetgangers, dieren.
// Coördinaten zijn three.js-coördinaten (x oost, z zuid). Een richting (dx, dz) hoort bij
// draaihoek h = atan2(-dx, -dz); rechts van richting d ligt (-d.z, d.x).
import * as THREE from 'three';
import {
  ZADEL, kies, poseDuif, poseHond, poseKat, poseLopen, poseRijden, poseStaan, poseZitten
} from './figuren.js';

const R = 5;                       // halve wegbreedte
const STOPLIJN = 9;                // afstand van de voorkant tot het midden van het kruispunt
const hoek = (dx, dz) => Math.atan2(-dx, -dz);
const rechts = (d) => [-d[1], d[0]];
const RICHTINGEN = [[1, 0], [-1, 0], [0, 1], [0, -1]];

function draaiNaar(obj, doel, k) {
  let v = doel - obj.rotation.y;
  v = Math.atan2(Math.sin(v), Math.cos(v));
  obj.rotation.y += v * Math.min(1, k);
}

function bezier(p0, p1, p2, t, uit) {
  const a = (1 - t) * (1 - t), b = 2 * (1 - t) * t, c = t * t;
  uit[0] = a * p0[0] + b * p1[0] + c * p2[0];
  uit[1] = a * p0[1] + b * p1[1] + c * p2[1];
  return uit;
}

function zaad(n) {                 // eenvoudige herhaalbare toevalsgenerator
  let s = n >>> 0;
  return () => {
    s = (s + 0x6D2B79F5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// =====================================================================
//  Wegennet en voertuigen
// =====================================================================
class Wegennet {
  constructor(stad) {
    this.A = stad.straten;
    this.N = this.A.length;
    this.STEEK = this.A[1] - this.A[0];
    this.sloten = new Map();
  }
  pos(ix, iz) { return [this.A[ix], this.A[iz]]; }
  geldig(ix, iz) { return ix >= 0 && iz >= 0 && ix < this.N && iz < this.N; }
  neem(sleutel, wie) {
    const h = this.sloten.get(sleutel);
    if (h && h !== wie) return false;
    this.sloten.set(sleutel, wie);
    return true;
  }
  geefVrij(sleutel, wie) { if (this.sloten.get(sleutel) === wie) this.sloten.delete(sleutel); }
}

const TYPES = {
  Auto: { L: 4.3, B: 1.8, v: 8.5, strook: 'auto' },
  Taxi: { L: 4.3, B: 1.8, v: 9, strook: 'auto' },
  Bus: { L: 11, B: 2.5, v: 7, strook: 'bus' },
  Fiets: { L: 1.8, B: 0.6, v: 4.6, strook: 'fiets' },
  Bakfiets: { L: 2.4, B: 0.8, v: 3.8, strook: 'fiets' },
  Scooter: { L: 1.7, B: 0.7, v: 7.5, strook: 'fiets' }
};

class Voertuig {
  constructor(leven, type, obj, start) {
    const t = TYPES[type];
    this.leven = leven;
    this.net = leven.net;
    this.type = type;
    this.obj = obj;
    this.L = t.L; this.B = t.B;
    this.vmax = t.v * (0.9 + leven.rnd() * 0.2);
    this.strook = leven.stad.rijstrook[t.strook];
    this.v = this.vmax * 0.6;
    this.ix = start.ix; this.iz = start.iz; this.d = start.d; this.s = start.s;
    this.modus = 'weg';
    this.route = start.route || null;
    this.routeIdx = start.routeIdx || 0;
    this.stap = 0;                 // knooppunten sinds de laatste hoek van de busroute
    this.volgende = this.kiesVolgende();
    this.slot = null; this.vorigSlot = null;
    this.wacht = 0; this.halteWacht = 0; this.halteKlaar = false;
    this.pos = [0, 0]; this.kop = [0, -1];
    this.berijders = [];
    this.wielFase = 0;
    this.zetPositie();
  }

  get doel() { return [this.ix + this.d[0], this.iz + this.d[1]]; }

  kiesVolgende() {
    const [bx, bz] = this.doel;
    if (this.route) {
      const n = this.route.length;
      const hoekpunt = this.route[(this.routeIdx + 1) % n];
      if (hoekpunt[0] !== bx || hoekpunt[1] !== bz) return this.d;          // rechtdoor tot de hoek
      const na = this.route[(this.routeIdx + 2) % n];
      return [Math.sign(na[0] - bx), Math.sign(na[1] - bz)];
    }
    const opties = [];
    for (const r of RICHTINGEN) {
      if (r[0] === -this.d[0] && r[1] === -this.d[1]) continue;
      if (!this.net.geldig(bx + r[0], bz + r[1])) continue;
      const rechtdoor = r[0] === this.d[0] && r[1] === this.d[1];
      opties.push([r, rechtdoor ? 2 : 1]);
    }
    let som = opties.reduce((a, o) => a + o[1], 0) * this.leven.rnd();
    for (const [r, w] of opties) { som -= w; if (som <= 0) return r; }
    return opties[0][0];
  }

  halteHier() {
    if (!this.route) return null;
    for (const h of this.leven.stad.bushaltes) {
      if (h.seg !== this.routeIdx) continue;
      const lokaal = h.s - this.stap * this.net.STEEK;
      if (lokaal >= 0 && lokaal <= this.net.STEEK) return lokaal;
    }
    return null;
  }

  zetPositie() {
    const [ax, az] = this.net.pos(this.ix, this.iz);
    if (this.modus === 'weg') {
      const r = rechts(this.d);
      this.pos[0] = ax + this.d[0] * this.s + r[0] * this.strook;
      this.pos[1] = az + this.d[1] * this.s + r[1] * this.strook;
      this.kop[0] = this.d[0]; this.kop[1] = this.d[1];
    } else {
      const b = this.bocht;
      bezier(b.p0, b.p1, b.p2, b.t, this.pos);
      const t2 = Math.min(1, b.t + 0.02), t1 = Math.max(0, b.t - 0.02);
      const q2 = bezier(b.p0, b.p1, b.p2, t2, [0, 0]), q1 = bezier(b.p0, b.p1, b.p2, t1, [0, 0]);
      const l = Math.hypot(q2[0] - q1[0], q2[1] - q1[1]) || 1;
      this.kop[0] = (q2[0] - q1[0]) / l; this.kop[1] = (q2[1] - q1[1]) / l;
    }
    this.obj.position.set(this.pos[0], 0, this.pos[1]);
    this.obj.rotation.y = hoek(this.kop[0], this.kop[1]);
  }

  startBocht() {
    const [bx, bz] = this.doel;
    const B = this.net.pos(bx, bz);
    const d = this.d, d2 = this.volgende;
    const r1 = rechts(d), r2 = rechts(d2);
    const o = this.strook;
    const p0 = [B[0] - d[0] * R + r1[0] * o, B[1] - d[1] * R + r1[1] * o];
    const p2 = [B[0] + d2[0] * R + r2[0] * o, B[1] + d2[1] * R + r2[1] * o];
    const rechtdoor = d[0] === d2[0] && d[1] === d2[1];
    const p1 = rechtdoor ? [B[0] + r1[0] * o, B[1] + r1[1] * o]
      : [B[0] + r1[0] * o + r2[0] * o, B[1] + r1[1] * o + r2[1] * o];
    let len = 0, vorig = p0;
    for (let i = 1; i <= 8; i++) {
      const q = bezier(p0, p1, p2, i / 8, [0, 0]);
      len += Math.hypot(q[0] - vorig[0], q[1] - vorig[1]);
      vorig = q;
    }
    this.bocht = { p0, p1, p2, t: 0, len };
    this.modus = 'bocht';
  }

  eindBocht(rest) {
    this.ix += this.d[0]; this.iz += this.d[1];
    this.d = this.volgende;
    if (this.route) {
      const hoekpunt = this.route[(this.routeIdx + 1) % this.route.length];
      if (hoekpunt[0] === this.ix && hoekpunt[1] === this.iz) {
        this.routeIdx = (this.routeIdx + 1) % this.route.length;
        this.stap = 0;
      } else {
        this.stap++;
      }
    }
    this.modus = 'weg';
    this.s = R + rest;
    this.vorigSlot = this.slot;
    this.slot = null;
    this.wacht = 0;
    this.halteKlaar = false;
    this.volgende = this.kiesVolgende();
  }

  /** Is er na het kruispunt plaats, zodat ik niet op het kruispunt of zebrapad blijf staan? */
  uitgangVrij() {
    const [bx, bz] = this.doel, d2 = this.volgende;
    for (const o of this.leven.voertuigen) {
      if (o === this || o.strook !== this.strook && Math.abs(o.strook - this.strook) > 1) continue;
      if (o.modus === 'weg' && o.ix === bx && o.iz === bz && o.d[0] === d2[0] && o.d[1] === d2[1] &&
          o.s - o.L / 2 < R + this.L + 5) return false;
    }
    return true;
  }

  /** Hoe snel mag ik nog, gezien wat er voor me is? */
  vrijeBaan() {
    let vMag = Infinity;
    const hx = this.kop[0], hz = this.kop[1];
    const vooruit = this.modus === 'bocht' ? 7 : 16;
    const kijk = (o, oL, oB, ox, oz, okop) => {
      const rx = ox - this.pos[0], rz = oz - this.pos[1];
      const langs = rx * hx + rz * hz;
      if (langs <= 0 || langs > vooruit + oL / 2) return;
      const dwars = Math.abs(rx * -hz + rz * hx);
      if (dwars > this.B / 2 + oB / 2 + (okop ? 0.15 : 1.1)) return;     // voor mensen ruimer kijken
      if (okop && (okop[0] * hx + okop[1] * hz) < 0.3) return;   // tegenliggers en kruisend verkeer: sloten regelen dat
      if (!okop && langs < this.L / 2 + 0.05) return;              // wie naast het voertuig staat, wacht zelf
      const gat = langs - this.L / 2 - oL / 2;
      vMag = Math.min(vMag, Math.max(0, (gat - 1.3) * 1.6));
    };
    for (const o of this.leven.voertuigen) {
      if (o === this) continue;
      if (this.modus === 'bocht' && o.wachtOpSlot) continue;
      kijk(o, o.L, o.B, o.pos[0], o.pos[1], o.kop);
    }
    for (const p of this.leven.opStraat) {
      kijk(p, 0.5, 0.6, p.x, p.z, null);
      // in een bocht: niemand in de buurt van de neus
      if (this.modus === 'bocht') {
        const nx = this.pos[0] + hx * this.L / 2, nz = this.pos[1] + hz * this.L / 2;
        const voor = (p.x - this.pos[0]) * hx + (p.z - this.pos[1]) * hz;
        if (voor >= this.L / 2 + 0.05 && Math.hypot(p.x - nx, p.z - nz) < 3) vMag = 0;
      }
    }
    return vMag;
  }

  update(dt) {
    const STEEK = this.net.STEEK;
    let vDoel = this.vmax;
    const remAf = (afstand) => (afstand <= 0 ? 0 : Math.sqrt(2 * 3.5 * afstand));
    this.wachtOpSlot = false;
    if (this.modus === 'weg') {
      const sStop = STEEK - STOPLIJN - this.L / 2;
      // bushalte
      const halte = this.halteHier();
      if (halte !== null && !this.halteKlaar) {
        const rest = halte - this.s;
        if (rest > -1) vDoel = Math.min(vDoel, remAf(rest));
        if (rest < 0.6 && this.v < 0.3) {
          this.halteWacht += dt;
          if (this.halteWacht > 5) { this.halteKlaar = true; this.halteWacht = 0; }
        }
      }
      // kruispunt: eerst het slot krijgen
      if (!this.slot) {
        const sleutel = this.doel.join(',');
        if (this.s > sStop - 3 && this.uitgangVrij() && this.net.neem(sleutel, this)) {
          this.slot = sleutel;
        } else {
          vDoel = Math.min(vDoel, remAf(sStop - this.s));
          if (this.s > sStop - 3) {
            this.wacht += dt;
            this.wachtOpSlot = true;
            if (this.wacht > 8) this.slot = 'geforceerd';
          }
        }
      } else {
        vDoel = Math.min(vDoel, this.vmax * 0.65);                         // traag het kruispunt op
      }
      if (this.vorigSlot && this.s > R + this.L / 2 + 0.8) {
        this.net.geefVrij(this.vorigSlot, this);
        this.vorigSlot = null;
      }
    } else {
      vDoel = Math.min(vDoel, this.vmax * 0.6);
    }
    vDoel = Math.min(vDoel, this.vrijeBaan());
    const dv = vDoel - this.v;
    this.v += Math.max(-9 * dt, Math.min(2.6 * dt, dv));
    if (this.v < 0.02 && vDoel <= 0) this.v = 0;

    if (this.modus === 'weg') {
      this.s += this.v * dt;
      if (this.s >= STEEK - R) {
        const rest = this.s - (STEEK - R);
        this.startBocht();
        this.bocht.t = rest / this.bocht.len;
      }
    } else {
      this.bocht.t += this.v * dt / this.bocht.len;
      if (this.bocht.t >= 1) this.eindBocht((this.bocht.t - 1) * this.bocht.len);
    }
    this.zetPositie();
    this.wielFase += this.v * dt / 2.1 * Math.PI * 2;
    for (const b of this.berijders) {
      b.fase = this.wielFase;
      poseRijden(b, ZADEL[this.type].soort);
    }
  }
}

// =====================================================================
//  Voetgangers
// =====================================================================
class Voetganger {
  constructor(leven, persoon, start, opties = {}) {
    this.leven = leven;
    this.p = persoon;
    this.obj = persoon.obj;
    this.rennen = !!opties.rennen;
    this.vmax = this.rennen ? 2.5 + leven.rnd() * 0.5 : 1.05 + leven.rnd() * 0.45;
    this.lat = 0.15 + leven.rnd() * 0.2;
    this.knoop = start;
    this.vorig = null;
    this.v = this.vmax;
    this.x = 0; this.z = 0;
    this.toestand = 'lopen';
    this.timer = 0;
    this.hond = null;
    this.nieuwSegment(true);
    if (this.oversteek) this.toestand = 'lopen';             // wie al op straat staat, loopt door
  }

  knoopPos(k) {
    const B = this.leven.stad.blokken, L = this.leven.stad.looplijn;
    return [k[2] ? B[k[0]][1] - L : B[k[0]][0] + L, k[3] ? B[k[1]][1] - L : B[k[1]][0] + L];
  }

  buren(k) {
    const [jx, jz, cx, cz] = k, N = this.leven.stad.blokken.length;
    const uit = [[jx, jz, 1 - cx, cz, false], [jx, jz, cx, 1 - cz, false]];
    if (cx === 1 && jx + 1 < N) uit.push([jx + 1, jz, 0, cz, true]);
    if (cx === 0 && jx > 0) uit.push([jx - 1, jz, 1, cz, true]);
    if (cz === 1 && jz + 1 < N) uit.push([jx, jz + 1, cx, 0, true]);
    if (cz === 0 && jz > 0) uit.push([jx, jz - 1, cx, 1, true]);
    return uit;
  }

  nieuwSegment(eerste = false) {
    const opties = this.buren(this.knoop).filter((b) => !this.vorig || b.slice(0, 4).join() !== this.vorig.join());
    const keuze = kies(opties, this.leven.rnd);
    this.oversteek = keuze[4];
    this.van = this.knoopPos(this.knoop);
    this.naar = this.knoopPos(keuze);
    this.volgendeKnoop = keuze.slice(0, 4);
    const dx = this.naar[0] - this.van[0], dz = this.naar[1] - this.van[1];
    this.len = Math.hypot(dx, dz);
    this.dir = [dx / this.len, dz / this.len];
    this.af = eerste ? this.leven.rnd() * this.len : 0;
    this.etalage = !this.oversteek && !this.rennen && this.leven.rnd() < 0.3 ? 3 + this.leven.rnd() * (this.len - 6) : -1;
    if (this.oversteek) { this.toestand = 'wachten'; this.timer = 0; }
  }

  oversteekVeilig() {
    const mx = (this.van[0] + this.naar[0]) / 2, mz = (this.van[1] + this.naar[1]) / 2;
    for (const v of this.leven.voertuigen) {
      const rx = mx - v.pos[0], rz = mz - v.pos[1];
      const afst = Math.hypot(rx, rz);
      if (afst > 25) continue;
      // staat er een voertuig op of vlak voor het zebrapad?
      for (let k = 0; k <= 10; k++) {
        const px = this.van[0] + (this.naar[0] - this.van[0]) * k / 10 - v.pos[0];
        const pz = this.van[1] + (this.naar[1] - this.van[1]) * k / 10 - v.pos[1];
        const langs = px * v.kop[0] + pz * v.kop[1], dwars = px * -v.kop[1] + pz * v.kop[0];
        if (langs > -v.L / 2 - 1 && langs < v.L / 2 + 2.5 && Math.abs(dwars) < v.B / 2 + 1) return false;
      }
      if (v.modus === 'bocht' && afst < 15) return false;                    // draait misschien naar hier
      if (v.v > 0.4 && afst < 18 && rx * v.kop[0] + rz * v.kop[1] > -1) return false;
    }
    return true;
  }

  voertuigOpPad() {
    for (const v of this.leven.voertuigen) {
      if (Math.abs(v.pos[0] - this.x) > 9 || Math.abs(v.pos[1] - this.z) > 9) continue;
      for (const a of [0.45, 0.9]) {
        const px = this.x + this.dir[0] * a - v.pos[0], pz = this.z + this.dir[1] * a - v.pos[1];
        const langs = px * v.kop[0] + pz * v.kop[1], dwars = px * -v.kop[1] + pz * v.kop[0];
        if (langs > -v.L / 2 - 0.35 && langs < v.L / 2 && Math.abs(dwars) < v.B / 2 + 0.35) return true;
      }
    }
    return false;
  }

  spelerVoor(speler) {
    const rx = speler.x - this.x, rz = speler.z - this.z;
    const langs = rx * this.dir[0] + rz * this.dir[1];
    const dwars = Math.abs(rx * -this.dir[1] + rz * this.dir[0]);
    return langs > 0 && langs < 1.3 && dwars < 0.65;
  }

  update(dt, t, speler) {
    let vDoel = this.vmax;
    if (this.toestand === 'wachten') {
      vDoel = 0;
      this.timer += dt;
      if (this.timer > 0.6 && this.oversteekVeilig()) this.toestand = 'lopen';
      this.p.kijk = Math.sin(t * 1.5 + this.p.fase) * 0.7;                  // links en rechts kijken
    } else if (this.toestand === 'kijken') {
      vDoel = 0;
      this.timer -= dt;
      if (this.timer <= 0) this.toestand = 'lopen';
    } else {
      this.p.kijk = 0;
      if (this.etalage > 0 && this.af >= this.etalage) {
        this.toestand = 'kijken';
        this.timer = 2 + this.leven.rnd() * 4;
        this.etalage = -1;
      }
    }
    if (this.oversteek && this.toestand === 'lopen' && this.voertuigOpPad()) vDoel = 0;
    if (speler && this.spelerVoor(speler)) {
      vDoel = 0;
      this.p.kijk = Math.atan2(Math.sin(hoek(speler.x - this.x, speler.z - this.z) - this.obj.rotation.y),
        Math.cos(hoek(speler.x - this.x, speler.z - this.z) - this.obj.rotation.y));
      this.p.kijk = Math.max(-1, Math.min(1, this.p.kijk));
    }
    this.v += Math.max(-6 * dt, Math.min(3 * dt, vDoel - this.v));
    this.af += this.v * dt;
    if (this.af >= this.len) {
      this.vorig = this.knoop;
      this.knoop = this.volgendeKnoop;
      this.nieuwSegment();
    }
    const r = rechts(this.dir);
    this.x = this.van[0] + this.dir[0] * this.af + r[0] * this.lat;
    this.z = this.van[1] + this.dir[1] * this.af + r[1] * this.lat;
    const B = this.leven.stad.blokken;
    const opStoep = B.some(([a, b]) => this.x >= a && this.x <= b) && B.some(([a, b]) => this.z >= a && this.z <= b);
    const y = opStoep ? this.leven.stad.stoephoogte : 0;
    this.obj.position.set(this.x, y, this.z);
    let kijkHoek = hoek(this.dir[0], this.dir[1]);
    if (this.toestand === 'kijken') {
      // naar de etalage: weg van de stoeprand
      const [jx, jz] = this.knoop;
      const mx = (B[jx][0] + B[jx][1]) / 2, mz = (B[jz][0] + B[jz][1]) / 2;
      kijkHoek = Math.abs(this.dir[0]) > 0.5 ? hoek(0, Math.sign(mz - this.z)) : hoek(Math.sign(mx - this.x), 0);
    }
    draaiNaar(this.obj, kijkHoek, dt * 8);
    this.p.fase += this.v * dt * Math.PI * 2 / (this.rennen ? 2.2 : 1.35);
    const sterkte = Math.min(1, this.v / Math.max(0.6, this.vmax * 0.6));
    if (sterkte < 0.05) poseStaan(this.p, t); else poseLopen(this.p, sterkte, this.rennen);
    this.opStraat = !opStoep;
  }
}

// Een hond aan de leiband volgt zijn baasje.
class Leibandhond {
  constructor(leven, hond, baas) {
    this.leven = leven; this.h = hond; this.obj = hond.obj; this.baas = baas;
    this.x = baas.x; this.z = baas.z;
    const geo = new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(6, 3));
    this.lijn = new THREE.Line(geo, new THREE.LineBasicMaterial({ color: '#2b2b2b' }));
    this.lijn.frustumCulled = false;
    leven.scene.add(this.lijn);
    this.hand = new THREE.Vector3(); this.hals = new THREE.Vector3();
  }
  update(dt, t) {
    const b = this.baas;
    const r = rechts(b.dir);
    const tx = b.x + r[0] * 0.55 - b.dir[0] * 0.2, tz = b.z + r[1] * 0.55 - b.dir[1] * 0.2;
    const dx = tx - this.x, dz = tz - this.z;
    const afst = Math.hypot(dx, dz);
    const v = Math.min(afst * 2.5, 3.2);
    if (afst > 0.02) {
      this.x += dx / afst * v * dt;
      this.z += dz / afst * v * dt;
      if (v > 0.15) draaiNaar(this.obj, hoek(dx, dz), dt * 7);
    }
    this.obj.position.set(this.x, b.obj.position.y, this.z);
    this.h.fase += v * dt * Math.PI * 2 / 0.7;
    poseHond(this.h, Math.min(1, v / 1.2), t, b.toestand === 'kijken' ? 1 : 0);
    b.p.d.armR.updateWorldMatrix(true, false);
    this.hand.set(0, -0.55, 0).applyMatrix4(b.p.d.armR.matrixWorld);
    this.h.d.lijn.getWorldPosition(this.hals);
    const pos = this.lijn.geometry.attributes.position;
    pos.setXYZ(0, this.hand.x, this.hand.y, this.hand.z);
    pos.setXYZ(1, this.hals.x, this.hals.y, this.hals.z);
    pos.needsUpdate = true;
  }
}

// Kinderen en een hond die vrij rondlopen in het park.
class Zwerver {
  constructor(leven, figuur, gebied, opties) {
    this.leven = leven; this.f = figuur; this.obj = figuur.obj; this.gebied = gebied;
    this.hond = !!opties.hond;
    this.snel = opties.snel || 2.0;
    const p = this.kiesDoel(true);
    this.x = p[0]; this.z = p[1];
    this.doel = this.kiesDoel();
    this.rust = 0;
    this.v = 0;
  }
  vrij(x, z) {
    const g = this.gebied;
    if (g.fontein && Math.hypot(x - g.fontein.x, z - g.fontein.z) < g.fontein.r) return false;
    for (const [x0, z0, x1, z1] of g.vakken) if (x > x0 - 0.5 && x < x1 + 0.5 && z > z0 - 0.5 && z < z1 + 0.5) return false;
    return true;
  }
  kiesDoel(overal = false) {
    const g = this.gebied;
    for (let i = 0; i < 30; i++) {
      const x = g.x0 + this.leven.rnd() * (g.x1 - g.x0), z = g.z0 + this.leven.rnd() * (g.z1 - g.z0);
      if (!this.vrij(x, z)) continue;
      if (overal) return [x, z];
      const n = Math.ceil(Math.hypot(x - this.x, z - this.z) / 0.5);
      let ok = true;
      for (let k = 1; k < n && ok; k++) ok = this.vrij(this.x + (x - this.x) * k / n, this.z + (z - this.z) * k / n);
      if (ok) return [x, z];
    }
    return [this.x, this.z];
  }
  update(dt, t) {
    const dx = this.doel[0] - this.x, dz = this.doel[1] - this.z;
    const afst = Math.hypot(dx, dz);
    let vDoel = this.snel;
    if (this.rust > 0) { this.rust -= dt; vDoel = 0; }
    else if (afst < 0.3) { this.rust = 1 + this.leven.rnd() * 4; this.doel = this.kiesDoel(); vDoel = 0; }
    this.v += Math.max(-5 * dt, Math.min(4 * dt, vDoel - this.v));
    if (afst > 0.05 && this.v > 0.01) {
      this.x += dx / afst * this.v * dt;
      this.z += dz / afst * this.v * dt;
      draaiNaar(this.obj, hoek(dx, dz), dt * 6);
    }
    this.obj.position.set(this.x, this.gebied.y, this.z);
    if (this.hond) {
      this.f.fase += this.v * dt * Math.PI * 2 / 0.9;
      poseHond(this.f, Math.min(1, this.v / 1.5), t, this.rust > 0 ? 1 : 0);
    } else {
      this.f.fase += this.v * dt * Math.PI * 2 / 1.4;
      const s = Math.min(1, this.v / 1.2);
      if (s < 0.05) poseStaan(this.f, t, 0.4); else poseLopen(this.f, s, this.v > 1.5);
    }
  }
}

// =====================================================================
//  Duiven
// =====================================================================
class Duif {
  constructor(leven, duif, gebied) {
    this.leven = leven; this.f = duif; this.obj = duif.obj; this.g = gebied;
    this.toestand = 'grond';
    this.x = 0; this.z = 0; this.y = gebied.y;
    this.landOpGrond();
    this.x = this.doel[0]; this.z = this.doel[1];
    this.timer = 0;
  }
  landOpGrond() {
    const g = this.g;
    this.doel = [g.x0 + this.leven.rnd() * (g.x1 - g.x0), g.z0 + this.leven.rnd() * (g.z1 - g.z0)];
  }
  vlieg(vanX, vanZ) {
    const g = this.g;
    if (this.leven.gebeurtenis) this.leven.gebeurtenis('duif', this);
    const dx = this.x - vanX, dz = this.z - vanZ, l = Math.hypot(dx, dz) || 1;
    const nok = g.nokken[Math.floor(this.leven.rnd() * g.nokken.length)];
    this.baan = {
      p0: [this.x, this.y, this.z],
      p1: [this.x + dx / l * 6, this.y + 5 + this.leven.rnd() * 3, this.z + dz / l * 6],
      p2: [nok[0] + this.leven.rnd() - 0.5, nok[1], nok[2] + this.leven.rnd() - 0.5], t: 0
    };
    this.baan.len = Math.hypot(this.baan.p2[0] - this.x, this.baan.p2[1] - this.y, this.baan.p2[2] - this.z) * 1.3;
    this.toestand = 'vliegen';
  }
  terug() {
    this.landOpGrond();
    this.baan = {
      p0: [this.x, this.y, this.z],
      p1: [(this.x + this.doel[0]) / 2, this.y + 2, (this.z + this.doel[1]) / 2],
      p2: [this.doel[0], this.g.y, this.doel[1]], t: 0
    };
    this.baan.len = Math.hypot(this.doel[0] - this.x, this.y - this.g.y, this.doel[1] - this.z) * 1.2;
    this.toestand = 'vliegen';
    this.landt = true;
  }
  update(dt, t, speler) {
    const afst = speler ? Math.hypot(speler.x - this.x, speler.z - this.z) : 99;
    if (this.toestand === 'grond') {
      if (afst < (speler.snel ? 5.5 : 2.6) && Math.abs(speler.y - this.y) < 2) { this.vlieg(speler.x, speler.z); }
      else {
        // trippelen naar een nieuw plekje
        const dx = this.doel[0] - this.x, dz = this.doel[1] - this.z, l = Math.hypot(dx, dz);
        if (l < 0.05) {
          this.timer -= dt;
          if (this.timer <= 0) {
            this.doel = [this.x + (this.leven.rnd() - 0.5) * 2, this.z + (this.leven.rnd() - 0.5) * 2];
            const g = this.g;
            this.doel[0] = Math.max(g.x0, Math.min(g.x1, this.doel[0]));
            this.doel[1] = Math.max(g.z0, Math.min(g.z1, this.doel[1]));
            this.timer = 1 + this.leven.rnd() * 3;
          }
        } else {
          const v = Math.min(l, 0.45 * dt);
          this.x += dx / l * v; this.z += dz / l * v;
          draaiNaar(this.obj, hoek(dx, dz), dt * 10);
        }
      }
      poseDuif(this.f, false, t);
    } else if (this.toestand === 'vliegen') {
      const b = this.baan;
      b.t = Math.min(1, b.t + dt * 8 / b.len);
      const a = (1 - b.t) ** 2, m = 2 * (1 - b.t) * b.t, c = b.t * b.t;
      const nx = a * b.p0[0] + m * b.p1[0] + c * b.p2[0];
      const ny = a * b.p0[1] + m * b.p1[1] + c * b.p2[1];
      const nz = a * b.p0[2] + m * b.p1[2] + c * b.p2[2];
      if (Math.hypot(nx - this.x, nz - this.z) > 1e-4) draaiNaar(this.obj, hoek(nx - this.x, nz - this.z), dt * 12);
      this.x = nx; this.y = ny; this.z = nz;
      poseDuif(this.f, true, t);
      if (b.t >= 1) {
        if (this.landt) { this.toestand = 'grond'; this.landt = false; this.y = this.g.y; this.timer = 1; }
        else { this.toestand = 'zitten'; this.timer = 7 + this.leven.rnd() * 10; }
      }
    } else {
      this.timer -= dt;
      poseDuif(this.f, false, t);
      if (this.timer <= 0 && afst > 9) this.terug();
    }
    this.obj.position.set(this.x, this.y, this.z);
  }
}

// =====================================================================
//  Het geheel
// =====================================================================
export class Leven {
  constructor(scene, figuren, stad, opties = {}) {
    this.scene = scene;
    this.fig = figuren;
    this.stad = stad;
    this.rnd = zaad(2024);
    this.net = new Wegennet(stad);
    this.voertuigen = [];
    this.voetgangers = [];
    this.anderen = [];          // zitters, praters, katten: { update(dt, t, speler) }
    this.dieren = [];
    this.duiven = [];
    this.opStraat = [];
    const veel = opties.minder ? 0.65 : 1;
    this.maakVerkeer(veel);
    this.maakVoetgangers(Math.round(24 * veel));
    this.maakZitters(Math.round(14 * veel));
    this.maakPraters();
    this.maakPark();
    this.maakKatten(5);
    this.maakDuiven(14);
  }

  voeg(obj) { this.scene.add(obj); return obj; }

  // ---------- verkeer ----------
  vrijePlek(L) {
    const N = this.net.N;
    for (let poging = 0; poging < 200; poging++) {
      const ix = Math.floor(this.rnd() * N), iz = Math.floor(this.rnd() * N);
      const d = RICHTINGEN[Math.floor(this.rnd() * 4)];
      if (!this.net.geldig(ix + d[0], iz + d[1])) continue;
      const s = R + L / 2 + 2 + this.rnd() * (this.net.STEEK - 2 * R - STOPLIJN - L);
      const bots = this.voertuigen.some((v) => v.ix === ix && v.iz === iz && v.d === d && Math.abs(v.s - s) < 12);
      if (!bots) return { ix, iz, d, s };
    }
    return null;
  }

  maakVoertuig(type, start) {
    const obj = this.voeg(this.fig.voertuig(type, this.rnd));
    const v = new Voertuig(this, type, obj, start);
    if (ZADEL[type]) {
      const p = this.fig.persoon({ helm: type === 'Scooter' || this.rnd() < 0.3, rugzak: this.rnd() < 0.3 }, this.rnd);
      p.obj.position.set(...ZADEL[type].pos);
      obj.add(p.obj);
      v.berijders.push(p);
      if (type === 'Bakfiets' && this.rnd() < 0.8) {
        const kind = this.fig.persoon({ schaal: 0.55 }, this.rnd);
        kind.obj.position.set(0, 0.5 + 0.05 - 0.9 * 0.55, -0.47);
        obj.add(kind.obj);
        poseZitten(kind, 0);
        this.anderen.push({ update: (dt, t) => { kind.d.hoofd.rotation.y = Math.sin(t * 0.7 + kind.fase) * 0.6; } });
      }
    }
    this.voertuigen.push(v);
    return v;
  }

  maakVerkeer(veel) {
    const route = this.stad.busroute;
    for (const seg of [0, 2]) {
      const a = route[seg], e = route[(seg + 1) % route.length];
      this.maakVoertuig('Bus', {
        ix: a[0], iz: a[1], d: [Math.sign(e[0] - a[0]), Math.sign(e[1] - a[1])], s: 8, route, routeIdx: seg
      });
    }
    const lijst = [['Auto', 7], ['Taxi', 3], ['Fiets', 6], ['Bakfiets', 2], ['Scooter', 3]];
    for (const [type, n] of lijst) {
      for (let i = 0; i < Math.round(n * veel); i++) {
        const plek = this.vrijePlek(TYPES[type].L);
        if (plek) this.maakVoertuig(type, plek);
      }
    }
  }

  // ---------- mensen ----------
  maakVoetgangers(n) {
    const N = this.stad.blokken.length;
    for (let i = 0; i < n; i++) {
      const rennen = i % 9 === 4;
      const p = this.fig.persoon({ rugzak: rennen ? false : undefined }, this.rnd);
      if (rennen) { p.d.rugzak.visible = false; }
      this.voeg(p.obj);
      const start = [Math.floor(this.rnd() * N), Math.floor(this.rnd() * N), this.rnd() < 0.5 ? 0 : 1, this.rnd() < 0.5 ? 0 : 1];
      const v = new Voetganger(this, p, start, { rennen });
      this.voetgangers.push(v);
      if (!rennen && i % 5 === 1) {
        const h = this.fig.hond(this.rnd);
        this.voeg(h.obj);
        v.vmax = Math.min(v.vmax, 1.15);
        this.dieren.push(new Leibandhond(this, h, v));
      }
    }
  }

  maakZitters(n) {
    const plekken = [...this.stad.zitplaatsen];
    for (let i = plekken.length - 1; i > 0; i--) {
      const j = Math.floor(this.rnd() * (i + 1));
      [plekken[i], plekken[j]] = [plekken[j], plekken[i]];
    }
    for (const z of plekken.slice(0, n)) {
      const p = this.fig.persoon({}, this.rnd);
      this.voeg(p.obj);
      // de heup zit iets achter het midden van het zitvlak
      p.obj.position.set(z.x + Math.sin(z.h) * 0.12, z.y + 0.05 - 0.9, z.z + Math.cos(z.h) * 0.12);
      p.obj.rotation.y = z.h;
      this.anderen.push({
        update: (dt, t, speler) => {
          p.kijk = 0;
          if (speler && Math.hypot(speler.x - z.x, speler.z - z.z) < 4) {
            const a = hoek(speler.x - z.x, speler.z - z.z) - z.h;
            p.kijk = Math.max(-1.1, Math.min(1.1, Math.atan2(Math.sin(a), Math.cos(a))));
          }
          poseZitten(p, t);
        }
      });
    }
  }

  maakPraters() {
    for (const plek of this.stad.praatplekken) {
      const a = this.rnd() * Math.PI * 2;
      const n = this.rnd() < 0.5 ? 2 : 3;
      for (let k = 0; k < n; k++) {
        const p = this.fig.persoon({}, this.rnd);
        this.voeg(p.obj);
        const b = a + k * Math.PI * 2 / n;
        const x = plek.x + Math.sin(b) * 0.55, z = plek.z + Math.cos(b) * 0.55;
        p.obj.position.set(x, this.stad.stoephoogte, z);
        p.obj.rotation.y = hoek(plek.x - x, plek.z - z);
        const spreker = k;
        this.anderen.push({
          update: (dt, t) => {
            const beurt = Math.floor((t + plek.x) / 4) % n === spreker;
            poseStaan(p, t, beurt ? 1 : 0.15);
          }
        });
        this.vasteBotsers = this.vasteBotsers || [];
        this.vasteBotsers.push({ x, z, r: 0.3 });
      }
    }
  }

  maakPark() {
    const park = this.stad.park;
    const vakken = this.stad.vakken.filter((v) => v[2] > park.x0 - 1 && v[0] < park.x1 + 1 && v[3] > park.z0 - 1 && v[1] < park.z1 + 1)
      .map((v) => [v[0], v[1], v[2], v[3]]);
    const gebied = { ...park, vakken, y: this.stad.stoephoogte + 0.04 };
    for (let i = 0; i < 4; i++) {
      const p = this.fig.persoon({ schaal: 0.58 + this.rnd() * 0.12, rugzak: false }, this.rnd);
      this.voeg(p.obj);
      this.dieren.push(new Zwerver(this, p, gebied, { snel: 1.6 + this.rnd() * 1.2 }));
    }
    const h = this.fig.hond(this.rnd);
    this.voeg(h.obj);
    this.dieren.push(new Zwerver(this, h, gebied, { hond: true, snel: 3.2 }));
  }

  maakKatten(n) {
    const plekken = [...this.stad.katplekken].sort(() => this.rnd() - 0.5).slice(0, n);
    for (const pl of plekken) {
      const k = this.fig.kat(this.rnd);
      this.voeg(k.obj);
      k.obj.position.set(pl.x, pl.y, pl.z);
      k.obj.rotation.y = pl.h;
      this.anderen.push({
        update: (dt, t, speler) => {
          let kijk = Math.sin(t * 0.3 + k.fase) * 0.4, onrustig = 0;
          if (speler) {
            const afst = Math.hypot(speler.x - pl.x, speler.z - pl.z);
            if (afst < 6) {
              const a = hoek(speler.x - pl.x, speler.z - pl.z) - pl.h;
              kijk = Math.max(-1.2, Math.min(1.2, Math.atan2(Math.sin(a), Math.cos(a))));
              onrustig = Math.max(0, 1 - afst / 3);
            }
          }
          poseKat(k, t, kijk, onrustig);
        }
      });
    }
  }

  maakDuiven(n) {
    const g = this.stad.duiven;
    // nokken: daken rond het plein waar duiven op kunnen gaan zitten
    const mx = (g.x0 + g.x1) / 2, mz = (g.z0 + g.z1) / 2;
    const nokken = this.stad.vakken
      .filter((v) => v[4] > 5 && v[4] < 25 && Math.hypot((v[0] + v[2]) / 2 - mx, (v[1] + v[3]) / 2 - mz) < 45)
      .map((v) => [(v[0] + v[2]) / 2, v[4] + 0.1, (v[1] + v[3]) / 2]);
    const gebied = { ...g, y: this.stad.stoephoogte, nokken: nokken.length ? nokken : [[mx, 8, mz]] };
    for (let i = 0; i < n; i++) {
      const d = this.fig.duif();
      this.voeg(d.obj);
      this.duiven.push(new Duif(this, d, gebied));
    }
  }

  /** Bewegende dingen waar de wandelaar tegen botst: cirkels { x, z, r }. */
  botsers() {
    const uit = [];
    for (const v of this.voertuigen) {
      const n = Math.max(1, Math.round(v.L / v.B));
      for (let k = 0; k < n; k++) {
        const t = (k + 0.5) / n - 0.5;
        uit.push({ x: v.pos[0] + v.kop[0] * t * v.L * (n > 1 ? (n - 1) / n * 1.1 : 0), z: v.pos[1] + v.kop[1] * t * v.L * (n > 1 ? (n - 1) / n * 1.1 : 0), r: v.B / 2 + 0.05 });
      }
    }
    for (const p of this.voetgangers) uit.push({ x: p.x, z: p.z, r: 0.28 });
    if (this.vasteBotsers) uit.push(...this.vasteBotsers);
    return uit;
  }

  update(dt, t, speler) {
    this.opStraat.length = 0;
    for (const p of this.voetgangers) if (p.opStraat) this.opStraat.push(p);
    if (speler && speler.opStraat) this.opStraat.push(speler);
    for (const v of this.voertuigen) v.update(dt);
    for (const p of this.voetgangers) p.update(dt, t, speler);
    for (const d of this.dieren) d.update(dt, t, speler);
    for (const a of this.anderen) a.update(dt, t, speler);
    for (const d of this.duiven) d.update(dt, t, speler);
  }
}
