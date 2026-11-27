// Ministad — het boodschappenspel: een lijstje, een portemonnee, vijf minuten en winkels om in te gaan.
import * as THREE from 'three';
import { poseStaan, poseLopen, poseZitten } from './figuren.js';

export const SPEELTIJD = 5 * 60;
const AANTAL = 6;
const DEUR_OPEN = 1.45;

// Wat je in elke soort winkel kan kopen: [naam, tekentje, prijs]
const WAREN = {
  bakker: [['Brood', '🍞', 2.6], ['Croissants', '🥐', 3.4], ['Stokbrood', '🥖', 1.9], ['Taart', '🎂', 12.5]],
  slager: [['Worstjes', '🌭', 4.2], ['Kip', '🍗', 6.5], ['Hamburgers', '🍔', 5.8]],
  groenten: [['Appels', '🍎', 2.4], ['Bananen', '🍌', 1.9], ['Tomaten', '🍅', 2.6], ['Wortels', '🥕', 1.3], ['Druiven', '🍇', 3.5]],
  bloemen: [['Tulpen', '🌷', 6], ['Zonnebloemen', '🌻', 4.5], ['Rozen', '🌹', 8.5]],
  apotheek: [['Pleisters', '🩹', 3.2], ['Hoestsiroop', '🧴', 7.5], ['Zonnecrème', '🧴', 9.5]],
  boeken: [['Stripboek', '📗', 8.5], ['Kleurboek', '🖍️', 4.5], ['Kookboek', '📕', 15]],
  kranten: [['Krant', '📰', 2.2], ['Tijdschrift', '📖', 4.8], ['Postkaart', '✉️', 1]],
  choco: [['Chocoladereep', '🍫', 2.4], ['Pralines', '🍬', 8], ['Chocolade-ei', '🥚', 3.5]],
  speelgoed: [['Ballon', '🎈', 1.5], ['Knikkers', '🔮', 2.5], ['Bal', '⚽', 6.5], ['Puzzel', '🧩', 9.5]],
  ijs: [['IJsje', '🍦', 2.5], ['Pot ijs', '🍨', 6.5]],
  frituur: [['Frietjes', '🍟', 3.2], ['Frikandel', '🌭', 2.8]],
  kapper: [['Haarspeldjes', '🎀', 2], ['Shampoo', '🧴', 5.5]],
  fietsen: [['Fietsbel', '🔔', 4], ['Fietslampje', '🔦', 6.5], ['Bandenplakset', '🛠️', 3]],
  kledij: [['Sokken', '🧦', 4.5], ['Muts', '🧢', 9], ['Sjaal', '🧣', 12]],
  optiek: [['Brillendoekje', '👓', 1.5], ['Zonnebril', '🕶️', 15]],
  cafe: [['Koffie', '☕', 2.8], ['Warme chocomelk', '☕', 3.2], ['Appelsap', '🧃', 2.6]],
  Pizzeria: [['Pizza', '🍕', 9.5], ['Lasagne', '🍝', 11]],
  Sushi: [['Sushi', '🍣', 12], ['Misosoep', '🍜', 4.5]],
  Brasserie: [['Spaghetti', '🍝', 12.5], ['Pannenkoeken', '🥞', 7]]
};
const PLEK = {
  bakker: 'bij de bakker', slager: 'bij de slager', groenten: 'bij de groenteman', bloemen: 'bij de bloemist',
  apotheek: 'bij de apotheek', boeken: 'in de boekhandel', kranten: 'in de krantenwinkel', choco: 'bij de chocolatier',
  speelgoed: 'in de speelgoedwinkel', ijs: 'in de ijssalon', frituur: 'in de frituur', kapper: 'bij de kapper',
  fietsen: 'in de fietsenwinkel', kledij: 'in de kledingwinkel'
};
const KERN = ['bakker', 'groenten', 'slager', 'bloemen', 'apotheek', 'kranten'];
const EXTRA = ['boeken', 'choco', 'speelgoed', 'ijs', 'frituur', 'fietsen', 'kapper', 'kledij'];

export const euro = (x) => '€ ' + x.toFixed(2).replace('.', ',');
const klok = (s) => { s = Math.max(0, Math.ceil(s)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
const schud = (a) => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const hoek = (dx, dz) => Math.atan2(-dx, -dz);

function warenVan(w) {
  return (WAREN[w.naam.split(' ')[0]] || WAREN[w.soort] || []).map(([naam, teken, prijs]) => ({ naam, teken, prijs, soort: w.soort }));
}

function zaad(n) {
  let s = n * 9301 + 49297;
  return () => { s = (s * 9301 + 49297) % 233280; return s / 233280; };
}

export class Spel {
  constructor(ctx) {
    Object.assign(this, ctx);           // scene, stad, figuren, geluid, speler, el, deuren (Map id -> Object3D)
    this.toestand = 'start';
    this.winkels = this.stad.winkels;
    this.naam = 'Speler';
    this.deurData = new Map();
    for (const w of this.winkels) {
      const obj = this.deuren.get(w.id);
      if (!obj) continue;
      const [dx, dz] = w.deur.dicht, [ox, oz] = w.deur.open;
      const teken = (dz * ox - dx * oz) > 0 ? 1 : -1;       // welke kant draait naar binnen
      this.deurData.set(w.id, { w, obj, hoek: 0, doel: 0, teken, weg: 0 });
    }
    this.licht = new THREE.PointLight('#ffe2b8', 0, 11, 1.4);
    this.scene.add(this.licht);
    this.bewoners = new Map();
    this.markers = [];
    this.tekens = new Map();
    this.actieWat = null;
    this.binnenIn = null;
    this.meldTimer = 0;
    this.maakLijstje();
    this.bouwStartlijst();
    this.el.sluitWinkel.addEventListener('click', () => this.sluitWinkel());
  }

  // ---------- lijstje en geld ----------
  maakLijstje() {
    const aanwezig = new Set(this.winkels.map((w) => w.soort));
    const kern = schud(KERN.filter((s) => aanwezig.has(s)));
    const extra = schud(EXTRA.filter((s) => aanwezig.has(s)));
    const soorten = [...kern.slice(0, 4), ...extra].slice(0, AANTAL);
    this.lijst = soorten.map((soort) => {
      const opties = WAREN[soort].filter((w) => w[2] <= 7);
      const [naam, teken, prijs] = opties[Math.floor(Math.random() * opties.length)];
      return { naam, teken, prijs, soort, gedaan: false };
    });
    const som = this.lijst.reduce((a, b) => a + b.prijs, 0);
    this.startGeld = Math.ceil(som + 3 + Math.random() * 3);
    this.geld = this.startGeld;
    this.tas = [];
    this.tijd = SPEELTIJD;
  }

  bouwStartlijst() {
    this.el.startLijst.innerHTML = '';
    for (const l of this.lijst) {
      const li = document.createElement('li');
      li.innerHTML = `<span class="teken">${l.teken}</span> <span>${l.naam}</span> <small>${PLEK[l.soort] || ''}</small>`;
      this.el.startLijst.append(li);
    }
    this.el.startGeld.textContent = euro(this.startGeld);
  }

  bouwLijst() {
    this.el.lijstNaam.textContent = 'Lijstje van ' + this.naam;
    this.el.lijst.innerHTML = '';
    this.lijst.forEach((l, i) => {
      const li = document.createElement('li');
      li.id = 'lijn-' + i;
      li.innerHTML = `<span class="teken">${l.teken}</span><span class="wat">${l.naam}<small>${PLEK[l.soort] || ''}</small></span>`;
      if (l.gedaan) li.classList.add('gedaan');
      this.el.lijst.append(li);
    });
    this.toonTeller();
  }

  toonTeller() {
    const n = this.lijst.filter((l) => l.gedaan).length;
    this.el.lijstTeller.textContent = `${n}/${this.lijst.length}`;
  }

  begin(naam) {
    this.naam = (naam || '').trim().slice(0, 16) || 'Speler';
    this.toestand = 'spel';
    this.tijd = SPEELTIJD;
    this.geld = this.startGeld;
    this.tas = [];
    this.bouwLijst();
    this.maakMarkers();
    this.laatsteTik = null;
    this.toonHud();
    this.meld(`Veel succes, ${this.naam}! Volg de tekentjes.`);
  }

  opnieuw() {
    for (const d of this.deurData.values()) { d.doel = 0; }
    this.sluitPaneel();
    this.maakLijstje();
    this.bouwStartlijst();
    this.toestand = 'start';
  }

  // ---------- markeringen boven de juiste winkels ----------
  tekenTextuur(teken) {
    if (this.tekens.has(teken)) return this.tekens.get(teken);
    const c = document.createElement('canvas');
    c.width = c.height = 128;
    const g = c.getContext('2d');
    g.fillStyle = '#ffffff';
    g.beginPath(); g.arc(64, 58, 50, 0, Math.PI * 2); g.fill();
    g.beginPath(); g.moveTo(44, 100); g.lineTo(84, 100); g.lineTo(64, 126); g.closePath(); g.fill();
    g.lineWidth = 6; g.strokeStyle = '#e85d3f';
    g.beginPath(); g.arc(64, 58, 50, 0, Math.PI * 2); g.stroke();
    g.font = '58px "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif';
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(teken, 64, 62);
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    this.tekens.set(teken, t);
    return t;
  }

  maakMarkers() {
    for (const m of this.markers) this.scene.remove(m.sprite);
    this.markers = [];
    for (const w of this.winkels) {
      const nodig = this.lijst.filter((l) => !l.gedaan && l.soort === w.soort);
      if (!nodig.length) continue;
      const mat = new THREE.SpriteMaterial({ map: this.tekenTextuur(nodig[0].teken), depthTest: false, transparent: true });
      const sprite = new THREE.Sprite(mat);
      sprite.scale.set(1.3, 1.3, 1);
      sprite.renderOrder = 10;
      sprite.position.set(w.ingang.x, w.vloer + 4.3, w.ingang.z);
      this.scene.add(sprite);
      this.markers.push({ sprite, w, fase: Math.random() * 6 });
    }
  }

  /** Voor de kaart: waar moet je nog naartoe? */
  kaartPunten() {
    if (this.toestand !== 'spel' && this.toestand !== 'winkel') return [];
    return this.markers.map((m) => ({ x: m.w.ingang.x, z: m.w.ingang.z, teken: this.lijst.find((l) => !l.gedaan && l.soort === m.w.soort)?.teken || '' }));
  }

  // ---------- deuren ----------
  dichtsteDeur(x, z, max) {
    let beste = null, bd = max;
    for (const d of this.deurData.values()) {
      const a = Math.hypot(d.w.deur.x - x, d.w.deur.z - z);
      if (a < bd) { bd = a; beste = d; }
    }
    return beste;
  }

  zetDeur(d, open) {
    const doel = open ? DEUR_OPEN * d.teken : 0;
    if (d.doel === doel) return;
    d.doel = doel;
    d.weg = 0;
    this.geluid.deur(open);
    if (open) this.geluid.deurbel();
  }

  /** Dichte deuren zijn muren. */
  extraVakken() {
    const uit = [];
    for (const d of this.deurData.values()) {
      if (Math.abs(d.hoek) < 0.5) uit.push(d.w.deur.vak.concat(2.4));
    }
    return uit;
  }

  binnenWinkel(x, z) {
    for (const w of this.winkels) {
      const [x0, z0, x1, z1] = w.binnen;
      if (x > x0 - 0.05 && x < x1 + 0.05 && z > z0 - 0.05 && z < z1 + 0.05) return w;
    }
    return null;
  }

  // ---------- winkeliers en klanten ----------
  bewoon(w) {
    const r = zaad(w.id + 7);
    const b = { winkelier: null, klanten: [], zitters: [] };
    const fig = this.figuren;
    const zet = (p, x, z, h, y = w.vloer) => { p.obj.position.set(x, y, z); p.obj.rotation.y = h; this.scene.add(p.obj); };
    b.winkelier = fig.persoon({ rugzak: false, helm: false }, r);
    zet(b.winkelier, w.winkelier.x, w.winkelier.z, w.winkelier.h);
    if (w.klanten.length && r() < 0.6) {
      const k = fig.persoon({ rugzak: r() < 0.3 }, r);
      const plek = w.klanten[0];
      zet(k, plek.x, plek.z, plek.h);
      b.klanten.push({ p: k, plekken: w.klanten, i: 0, t: 3 + r() * 5, v: 0 });
    }
    for (const z of w.zitjes) {
      if (r() < 0.5) continue;
      const p = fig.persoon({}, r);
      zet(p, z.x + Math.sin(z.h) * 0.12, z.z + Math.cos(z.h) * 0.12, z.h, z.y + 0.05 - 0.9);
      b.zitters.push(p);
    }
    this.bewoners.set(w.id, b);
  }

  ontruim(id) {
    const b = this.bewoners.get(id);
    if (!b) return;
    this.scene.remove(b.winkelier.obj);
    for (const k of b.klanten) this.scene.remove(k.p.obj);
    for (const z of b.zitters) this.scene.remove(z.obj);
    this.bewoners.delete(id);
  }

  cirkels() {
    const uit = [];
    for (const b of this.bewoners.values()) for (const k of b.klanten) uit.push({ x: k.p.obj.position.x, z: k.p.obj.position.z, r: 0.28 });
    return uit;
  }

  // ---------- kopen ----------
  openWinkel(w) {
    this.huidigeWinkel = w;
    this.toestand = 'winkel';
    const el = this.el;
    el.winkelNaam.textContent = w.naam;
    el.winkelZegt.textContent = `Dag ${this.naam}! Wat mag het zijn?`;
    this.geluid.spreek(`Dag ${this.naam}! Wat mag het zijn?`, 0.9 + (w.id % 5) * 0.08);
    el.waren.innerHTML = '';
    warenVan(w).forEach((waar, i) => {
      const knop = document.createElement('button');
      knop.type = 'button';
      knop.className = 'waar';
      const opLijst = this.lijst.some((l) => !l.gedaan && l.naam === waar.naam && l.soort === waar.soort);
      knop.innerHTML = `<span class="teken">${waar.teken}</span><span class="naam">${waar.naam}</span>` +
        `<span class="prijs">${euro(waar.prijs)}</span>${opLijst ? '<span class="op-lijst">op je lijstje</span>' : ''}` +
        `<kbd class="sneltoets">${i + 1}</kbd>`;
      knop.addEventListener('click', () => this.koop(waar, knop));
      el.waren.append(knop);
    });
    el.winkelGeld.textContent = 'In je portemonnee: ' + euro(this.geld);
    el.winkel.hidden = false;
    const eerste = el.waren.querySelector('button');
    if (eerste) eerste.focus({ preventScroll: true });
  }

  koop(waar, knop) {
    const el = this.el;
    if (this.toestand !== 'winkel') return;
    if (waar.prijs > this.geld + 1e-9) {
      this.geluid.fout();
      el.winkelZegt.textContent = 'Oei, daar heb je niet genoeg geld voor.';
      this.geluid.spreek('Oei, daar heb je niet genoeg geld voor.');
      knop.classList.add('nee');
      setTimeout(() => knop.classList.remove('nee'), 500);
      return;
    }
    this.geld = Math.round((this.geld - waar.prijs) * 100) / 100;
    this.tas.push(waar);
    this.geluid.kassa();
    this.praat = 1.5;
    const lijn = this.lijst.find((l) => !l.gedaan && l.naam === waar.naam && l.soort === waar.soort);
    if (lijn) {
      lijn.gedaan = true;
      const i = this.lijst.indexOf(lijn);
      setTimeout(() => {
        this.geluid.schrap();
        document.getElementById('lijn-' + i)?.classList.add('gedaan');
        this.toonTeller();
      }, 650);
      knop.querySelector('.op-lijst')?.remove();
      el.winkelZegt.textContent = `Alsjeblieft, ${waar.naam.toLowerCase()}. Dat is ${euro(waar.prijs)}.`;
      this.geluid.spreek('Alsjeblieft!');
      this.maakMarkers();
    } else {
      el.winkelZegt.textContent = `Alsjeblieft! (${waar.naam} stond niet op je lijstje.)`;
      this.geluid.spreek('Alsjeblieft!');
    }
    el.winkelGeld.textContent = 'In je portemonnee: ' + euro(this.geld);
    this.toonHud();
    if (this.lijst.every((l) => l.gedaan)) setTimeout(() => this.einde(true), 1200);
  }

  sluitPaneel() { this.el.winkel.hidden = true; this.huidigeWinkel = null; }

  sluitWinkel() {
    if (this.toestand !== 'winkel') return;
    this.sluitPaneel();
    this.toestand = 'spel';
    this.geluid.spreek('Dank je wel, tot ziens!');
    this.geluid.klik();
    if (this.naSluiten) this.naSluiten();
  }

  koopMetToets(n) {
    const knop = this.el.waren.querySelectorAll('button')[n - 1];
    if (knop) knop.click();
  }

  // ---------- de knop 'actie' (E of tikken) ----------
  bepaalActie() {
    const s = this.speler;
    const w = this.binnenIn;
    if (w && Math.hypot(w.toonbank.x - s.x, w.toonbank.z - s.z) < 1.6) return { soort: 'kopen', w, tekst: '🛒 Kopen' };
    const d = this.dichtsteDeur(s.x, s.z, 1.8);
    if (d) {
      const open = Math.abs(d.doel) > 0.1;
      return { soort: 'deur', d, tekst: open ? '🚪 Deur sluiten' : '🚪 Deur openen' };
    }
    return null;
  }

  actie() {
    if (this.toestand === 'winkel') { this.sluitWinkel(); return; }
    if (this.toestand !== 'spel' || !this.actieWat) return;
    const a = this.actieWat;
    if (a.soort === 'kopen') this.openWinkel(a.w);
    else this.zetDeur(a.d, Math.abs(a.d.doel) < 0.1);
  }

  // ---------- einde ----------
  einde(gewonnen) {
    if (this.toestand === 'einde') return;
    this.sluitPaneel();
    this.toestand = 'einde';
    const el = this.el;
    const gebruikt = Math.round(SPEELTIJD - this.tijd);
    let scores = [];
    try { scores = JSON.parse(localStorage.getItem('ministad-scores') || '[]'); } catch (e) { scores = []; }
    if (gewonnen) {
      this.geluid.gewonnen();
      this.geluid.spreek(`Hoera ${this.naam}, alles gekocht!`);
      el.eindeTitel.textContent = `Hoera, ${this.naam}!`;
      el.eindeTekst.textContent = `Je hebt alle boodschappen in ${klok(gebruikt)} gehaald, en je hebt nog ${euro(this.geld)} over.`;
      scores.push({ naam: this.naam, tijd: gebruikt, geld: this.geld });
      scores.sort((a, b) => a.tijd - b.tijd || b.geld - a.geld);
      scores = scores.slice(0, 5);
      try { localStorage.setItem('ministad-scores', JSON.stringify(scores)); } catch (e) { /* geen opslag */ }
    } else {
      this.geluid.verloren();
      const mist = this.lijst.filter((l) => !l.gedaan);
      el.eindeTitel.textContent = 'De tijd is op!';
      el.eindeTekst.textContent = `Jammer, ${this.naam}. Je had nog nodig: ` + mist.map((l) => `${l.teken} ${l.naam.toLowerCase()}`).join(', ') + '.';
    }
    el.scores.innerHTML = '';
    for (const s of scores) {
      const li = document.createElement('li');
      li.textContent = `${s.naam}: ${klok(s.tijd)}`;
      el.scores.append(li);
    }
    el.scoreBlok.hidden = !scores.length;
    el.einde.hidden = false;
    for (const m of this.markers) this.scene.remove(m.sprite);
    this.markers = [];
    if (this.naEinde) this.naEinde();
  }

  // ---------- elk beeldje ----------
  meld(tekst) {
    this.el.melding.textContent = tekst;
    this.el.melding.classList.add('zichtbaar');
    this.meldTimer = 3.5;
  }

  toonHud() {
    this.el.tijd.textContent = klok(this.tijd);
    this.el.tijdBlok.classList.toggle('bijna', this.tijd <= 30);
    this.el.geld.textContent = euro(this.geld);
  }

  update(dt, t) {
    const s = this.speler;
    // tijd
    if (this.toestand === 'spel' || this.toestand === 'winkel') {
      this.tijd -= dt;
      const sec = Math.ceil(this.tijd);
      if (sec !== this.laatsteTik) {
        this.laatsteTik = sec;
        if (sec <= 30 && sec > 0) this.geluid.tik(sec <= 10);
        this.toonHud();
      }
      if (this.tijd <= 0) { this.tijd = 0; this.toonHud(); this.einde(false); }
    }
    // deuren draaien
    for (const d of this.deurData.values()) {
      if (Math.abs(d.hoek - d.doel) > 1e-3) {
        d.hoek += Math.sign(d.doel - d.hoek) * Math.min(Math.abs(d.doel - d.hoek), dt * 2.6);
        d.obj.rotation.y = d.hoek;
      }
      if (Math.abs(d.doel) > 0.1) {
        const afst = Math.hypot(d.w.deur.x - s.x, d.w.deur.z - s.z);
        d.weg = afst > 3.2 ? d.weg + dt : 0;
        if (d.weg > 2.5) this.zetDeur(d, false);
      }
    }
    // binnen of buiten?
    this.binnenIn = this.binnenWinkel(s.x, s.z);
    const w = this.binnenIn;
    if (w) {
      this.licht.position.set(...w.licht);
      this.licht.intensity += (4 - this.licht.intensity) * Math.min(1, dt * 4);
    } else {
      this.licht.intensity *= Math.max(0, 1 - dt * 4);
    }
    // winkeliers en klanten in de buurt van de speler
    for (const winkel of this.winkels) {
      const a = Math.hypot(winkel.ingang.x - s.x, winkel.ingang.z - s.z);
      if (a < 26 && !this.bewoners.has(winkel.id)) this.bewoon(winkel);
      else if (a > 40 && this.bewoners.has(winkel.id)) this.ontruim(winkel.id);
    }
    this.praat = Math.max(0, (this.praat || 0) - dt);
    for (const [id, b] of this.bewoners) {
      const winkel = this.winkels[id];
      const k = b.winkelier;
      const speler = this.binnenIn === winkel;
      k.kijk = 0;
      if (speler) {
        let a = hoek(s.x - winkel.winkelier.x, s.z - winkel.winkelier.z) - winkel.winkelier.h;
        k.kijk = Math.max(-1, Math.min(1, Math.atan2(Math.sin(a), Math.cos(a))));
      }
      const bezig = this.huidigeWinkel === winkel ? (this.praat > 0 ? 1 : 0.5) : 0.1;
      poseStaan(k, t, bezig);
      for (const kl of b.klanten) {
        kl.t -= dt;
        const doel = kl.plekken[kl.i];
        const p = kl.p.obj.position;
        const dx = doel.x - p.x, dz = doel.z - p.z, l = Math.hypot(dx, dz);
        if (l > 0.05) {
          const v = Math.min(l, 0.9 * dt);
          p.x += dx / l * v; p.z += dz / l * v;
          kl.p.obj.rotation.y = hoek(dx, dz);
          kl.p.fase += v * Math.PI * 2 / 1.3;
          poseLopen(kl.p, 0.8);
        } else {
          kl.p.obj.rotation.y += (doel.h - kl.p.obj.rotation.y) * Math.min(1, dt * 4);
          kl.p.kijk = Math.sin(t * 0.6 + kl.p.fase) * 0.6;
          poseStaan(kl.p, t, 0.25);
          if (kl.t <= 0) { kl.i = (kl.i + 1) % kl.plekken.length; kl.t = 4 + Math.random() * 6; }
        }
      }
      for (const z of b.zitters) poseZitten(z, t);
    }
    // markeringen dansen een beetje
    for (const m of this.markers) {
      m.fase += dt * 3;
      m.sprite.position.y = m.w.vloer + 4.2 + Math.sin(m.fase) * 0.18;
      const a = Math.hypot(m.w.ingang.x - s.x, m.w.ingang.z - s.z);
      const sc = 1.2 + Math.min(2.2, a / 30);
      m.sprite.scale.set(sc, sc, 1);
    }
    // de actieknop
    const actie = this.toestand === 'spel' ? this.bepaalActie() : null;
    if ((actie && actie.tekst) !== (this.actieWat && this.actieWat.tekst)) {
      this.el.actie.hidden = !actie;
      if (actie) this.el.actieTekst.textContent = actie.tekst;
    }
    this.actieWat = actie;
    // melding verdwijnt vanzelf
    if (this.meldTimer > 0) {
      this.meldTimer -= dt;
      if (this.meldTimer <= 0) this.el.melding.classList.remove('zichtbaar');
    }
  }
}
