// Rave against the machine — lampen, stralen, lasers, vuur, blinders, rook en gloed.
// Leest de `licht_*`-ankers (Empties) en `gloed_*`-materialen uit rave.glb (zie AFSPRAKEN.md)
// en laat alles meebewegen met het gedeelde `ritme`-object.
//
// Schijnrichting: de lokale −Z van een Blender-empty wordt na de glTF-export (+Y omhoog)
// de lokale −Y van de three.js-node. Die richting gebruiken we.
import * as THREE from 'three';

const TYPES = ['spot', 'laser', 'boom', 'vuur', 'blinder', 'rook'];
const STANDAARD_KLEUR = {
  spot: '#22e6ff', laser: '#33ff66', boom: '#ff2fd0', vuur: '#ff7a1a', blinder: '#fff2dd', rook: '#ffffff'
};
export const PALET = ['#22e6ff', '#ff2fd0', '#ff8a1a', '#7a2cff', '#9dff2a', '#ff2040'].map((k) => new THREE.Color(k));

const klem = (v, a, b) => Math.max(a, Math.min(b, v));
const glad = (a, b, x) => { const t = klem((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const OMHOOG = new THREE.Vector3(0, 1, 0);

// ---------- gedeelde GLSL ----------
const RUIS_GLSL = `
float rHash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float rRuis(vec3 x) {
  vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(rHash(i), rHash(i + vec3(1,0,0)), f.x), mix(rHash(i + vec3(0,1,0)), rHash(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(rHash(i + vec3(0,0,1)), rHash(i + vec3(1,0,1)), f.x), mix(rHash(i + vec3(0,1,1)), rHash(i + vec3(1,1,1)), f.x), f.y), f.z);
}
float rMist(vec3 w, float t) {
  return rRuis(w * 0.35 + vec3(t * 0.15, -t * 0.05, t * 0.1)) * 0.6 + rRuis(w * 1.1 - vec3(0.0, t * 0.2, t * 0.12)) * 0.4;
}`;

// ---------- randlicht voor de figuren ----------
export const randUniforms = {
  uRandKleur: { value: new THREE.Color('#2a6fff') },
  uPodium: { value: new THREE.Vector3(0, 5, -24) }
};

/** Voegt een randlicht (vanuit het podium, achter de figuren) toe aan een standaardmateriaal. */
export function randLicht(mat) {
  mat.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, randUniforms);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vRandW;')
      .replace('#include <project_vertex>', '#include <project_vertex>\nvRandW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vRandW;\nuniform vec3 uRandKleur;\nuniform vec3 uPodium;')
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
        {
          vec3 naarP = normalize((viewMatrix * vec4(normalize(uPodium - vRandW), 0.0)).xyz);
          vec3 V = normalize(vViewPosition);
          float fres = pow(1.0 - clamp(dot(normal, V), 0.0, 1.0), 2.5);
          float kant = smoothstep(-0.15, 0.6, dot(normal, naarP));
          float achter = smoothstep(-0.4, 0.8, dot(-V, naarP));
          totalEmissiveRadiance += uRandKleur * fres * kant * (0.2 + 0.8 * achter);
        }`);
  };
  mat.customProgramCacheKey = () => 'randlicht';
  mat.needsUpdate = true;
}

// ---------- texturen op canvas ----------
function radiaalTextuur(n = 128, hard = 0) {
  const c = document.createElement('canvas');
  c.width = c.height = n;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(n / 2, n / 2, 0, n / 2, n / 2, n / 2);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(hard ? 0.18 : 0.05, 'rgba(255,255,255,0.85)');
  grad.addColorStop(0.35, 'rgba(255,255,255,0.22)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, n, n);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.NoColorSpace;
  return t;
}

function rookTextuur(n = 128) {
  // fbm-ruis met een zachte ronde rand, in het alfakanaal
  const c = document.createElement('canvas');
  c.width = c.height = n;
  const g = c.getContext('2d');
  const beeld = g.createImageData(n, n);
  const roosters = [4, 8, 16, 32].map((s) => {
    const r = new Float32Array((s + 1) * (s + 1));
    for (let i = 0; i < r.length; i++) r[i] = Math.random();
    // naadloos maken is niet nodig: de rand verdwijnt toch
    return { s, r };
  });
  const waarde = ({ s, r }, x, y) => {
    const fx = x * s, fy = y * s, ix = Math.floor(fx), iy = Math.floor(fy);
    const tx = fx - ix, ty = fy - iy, sx = tx * tx * (3 - 2 * tx), sy = ty * ty * (3 - 2 * ty);
    const a = r[iy * (s + 1) + ix], b = r[iy * (s + 1) + ix + 1], c2 = r[(iy + 1) * (s + 1) + ix], d = r[(iy + 1) * (s + 1) + ix + 1];
    return (a + (b - a) * sx) + ((c2 + (d - c2) * sx) - (a + (b - a) * sx)) * sy;
  };
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const u = x / n, v = y / n;
      let f = 0, amp = 0.5;
      for (const r of roosters) { f += waarde(r, u * 0.999, v * 0.999) * amp; amp *= 0.5; }
      const d = Math.hypot(u - 0.5, v - 0.5) * 2;
      const rand = Math.max(0, 1 - d);
      const a = Math.max(0, Math.min(1, (f - 0.25) * 1.6)) * rand * rand;
      const i = (y * n + x) * 4;
      beeld.data[i] = beeld.data[i + 1] = beeld.data[i + 2] = 255;
      beeld.data[i + 3] = Math.round(a * 255);
    }
  }
  g.putImageData(beeld, 0, 0);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.NoColorSpace;
  return t;
}

// ---------- volumetrische kegel ----------
function kegelMateriaal(kleur) {
  return new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, fog: false,
    uniforms: { kleur: { value: kleur.clone() }, sterkte: { value: 1 }, tijd: { value: 0 } },
    vertexShader: `varying float vLangs; varying vec3 vN; varying vec3 vV; varying vec3 vW;
      void main() {
        vLangs = 1.0 - uv.y;
        vec4 w = modelMatrix * vec4(position, 1.0);
        vW = w.xyz;
        vec4 mv = viewMatrix * w;
        vV = -mv.xyz;
        vN = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `uniform vec3 kleur; uniform float sterkte; uniform float tijd;
      varying float vLangs; varying vec3 vN; varying vec3 vV; varying vec3 vW;
      ${RUIS_GLSL}
      void main() {
        float afst = length(vV);
        float rand = pow(abs(dot(normalize(vN), vV / afst)), 1.4);
        float lengte = smoothstep(0.0, 0.025, vLangs) * pow(1.0 - vLangs, 1.3);
        float grond = smoothstep(0.0, 1.4, vW.y);
        float laag = mix(1.2, 0.55, smoothstep(1.5, 12.0, vW.y));
        float mist = 0.45 + 0.75 * rMist(vW, tijd);
        float dichtbij = smoothstep(0.4, 3.0, afst);
        float ver = exp(-afst * 0.01);
        float a = rand * lengte * grond * laag * mist * dichtbij * ver * sterkte;
        gl_FragColor = vec4(kleur * a, 1.0);
      }`
  });
}

let kegelGeo = null;
function kegelGeometrie() {
  if (!kegelGeo) {
    // eenheidskegel: punt (iets afgeknot) in de oorsprong, opening op z = 1 met straal 1
    kegelGeo = new THREE.CylinderGeometry(0.03, 1, 1, 28, 1, true);
    kegelGeo.translate(0, -0.5, 0);
    kegelGeo.rotateX(-Math.PI / 2);
  }
  return kegelGeo;
}

function maakKegel(kleur, lengte, hoek) {
  const m = new THREE.Mesh(kegelGeometrie(), kegelMateriaal(kleur));
  const r = Math.tan(hoek) * lengte;
  m.scale.set(r, r, lengte);
  m.frustumCulled = false;
  m.renderOrder = 5;
  return m;
}

// =====================================================================
export class Lichtshow {
  /**
   * @param {object} o  { scene, wereld (glTF-scene met de licht_-ankers), gloedWortel (waar de gloed_-materialen
   *                      hangen, standaard wereld), data (botsing.json), kwaliteit: 'hoog'|'licht' }
   */
  constructor({ scene, wereld, gloedWortel = null, data, kwaliteit = 'hoog' }) {
    this.scene = scene;
    this.data = data;
    this.groep = new THREE.Group();
    this.groep.name = 'lichtshow';
    scene.add(this.groep);
    this.tijd = 0;
    this.kwaliteit = kwaliteit;
    this.dominant = new THREE.Color('#3a0f4a');
    this.texGloed = radiaalTextuur(128, 1);
    this.texRook = rookTextuur(128);

    wereld.updateMatrixWorld(true);
    this.ankers = Object.fromEntries(TYPES.map((t) => [t, []]));
    const q = new THREE.Quaternion();
    wereld.traverse((o) => {
      const m = /^licht_([a-z]+)/.exec(o.name || '');
      if (!m || !this.ankers[m[1]]) return;
      const pos = o.getWorldPosition(new THREE.Vector3());
      o.getWorldQuaternion(q);
      const richting = new THREE.Vector3(0, -1, 0).applyQuaternion(q).normalize();
      const kleur = new THREE.Color(typeof o.userData.kleur === 'string' ? o.userData.kleur : STANDAARD_KLEUR[m[1]]);
      this.ankers[m[1]].push({ naam: o.name, pos, richting, kleur });
    });
    for (const lijst of Object.values(this.ankers)) lijst.sort((a, b) => a.naam.localeCompare(b.naam, 'nl', { numeric: true }));
    this.vulOntbrekendeAankers();

    const pod = data.podium;
    this.podiumMidden = new THREE.Vector3((pod.x0 + pod.x1) / 2, pod.y + 4, (pod.z0 + pod.z1) / 2);
    randUniforms.uPodium.value.copy(this.podiumMidden);

    this.maakSpots();
    this.maakLasers();
    this.maakBoom();
    this.maakVuur();
    this.maakBlinders();
    this.maakRook();
    this.zoekGloed(gloedWortel || wereld);
    this.zetKwaliteit(kwaliteit);
  }

  /** Als het terrein (nog) geen ankers heeft, zet er een paar op logische plaatsen. */
  vulOntbrekendeAankers() {
    const a = this.ankers;
    const V = (x, y, z) => new THREE.Vector3(x, y, z);
    const naar = (p, d) => d.clone().sub(p).normalize();
    if (!a.spot.length) {
      for (let i = 0; i < 6; i++) {
        const p = V(-6 + i * 2.4, 8.5, -20);
        a.spot.push({ naam: 'licht_spot_' + i, pos: p, richting: naar(p, V(p.x * 0.6, 0, 8)), kleur: PALET[i % 4].clone() });
      }
    }
    if (!a.laser.length) {
      for (let i = 0; i < 6; i++) {
        const p = V(-7 + i * 2.8, 8.9, -27.5);
        a.laser.push({ naam: 'licht_laser_' + i, pos: p, richting: naar(p, V(p.x * 0.4, 4, 20)), kleur: PALET[[4, 5, 0][i % 3]].clone() });
      }
    }
    if (!a.rook.length) {
      for (const [x, z] of [[-6, -13], [6, -13], [0, -3]]) a.rook.push({ naam: 'licht_rook', pos: V(x, 0, z), richting: V(0, 1, 0), kleur: new THREE.Color(1, 1, 1) });
    }
  }

  // ---------------------------------------------------------- spots
  maakSpots() {
    this.spots = this.ankers.spot.map((a, i) => {
      const grondT = a.richting.y < -0.05 ? a.pos.y / -a.richting.y : 40;
      const lengte = Math.min(grondT * 1.08 + 1, 48);
      const kegel = maakKegel(a.kleur, lengte, 0.085);
      kegel.position.copy(a.pos);
      this.groep.add(kegel);
      // horizontale as loodrecht op de straal, voor het kantelen
      const zij = new THREE.Vector3().crossVectors(a.richting, OMHOOG);
      if (zij.lengthSq() < 1e-4) zij.set(1, 0, 0);
      zij.normalize();
      return {
        ...a, kegel, lengte, zij, licht: null, dir: a.richting.clone(),
        fase: i * 1.7, links: i % 2 ? 1 : -1, kleurNu: a.kleur.clone()
      };
    });
    // echte lampen: een beperkt aantal, gelijk verdeeld over de spots
    this.spotLampen = [];
    for (let k = 0; k < 4; k++) {
      const l = new THREE.SpotLight(0xffffff, 0, 0, 0.3, 0.65, 2);
      l.visible = false;
      this.groep.add(l, l.target);
      this.spotLampen.push(l);
    }
    const schaduw = this.spotLampen[0];
    schaduw.shadow.mapSize.set(1024, 1024);
    schaduw.shadow.camera.near = 2;
    schaduw.shadow.camera.far = 70;
    schaduw.shadow.bias = -0.0006;
    schaduw.shadow.normalBias = 0.04;
  }

  verdeelSpotLampen() {
    const n = this.kwaliteit === 'licht' ? 2 : 4;
    const s = this.spots;
    this.spots.forEach((sp) => { sp.licht = null; });
    this.spotLampen.forEach((l, k) => {
      l.visible = k < n && s.length > 0;
      l.castShadow = k === 0 && this.kwaliteit !== 'licht';
      if (!l.visible) return;
      // de schaduwlamp krijgt de middelste spot; de rest verdeeld
      const volg = [...s].sort((a, b) => Math.abs(a.pos.x) - Math.abs(b.pos.x));
      let sp;
      if (k === 0) sp = volg[0];
      else {
        const rest = s.filter((x) => x !== volg[0]);
        sp = rest[Math.floor((k - 1 + 0.5) * rest.length / Math.max(1, n - 1))] || rest[0];
      }
      if (sp) { sp.licht = l; l.color.copy(sp.kleur); }
      else l.visible = false;
    });
  }

  // ---------------------------------------------------------- lasers
  maakLasers() {
    const per = 7;
    this.laserPer = per;
    const n = this.ankers.laser.length * per;
    this.lasers = this.ankers.laser.map((a, i) => {
      const zij = new THREE.Vector3().crossVectors(a.richting, OMHOOG);
      if (zij.lengthSq() < 1e-4) zij.set(1, 0, 0);
      zij.normalize();
      return { ...a, zij, fase: i * 0.9, aan: 0 };
    });
    const geo = new THREE.BufferGeometry();
    const pos = new Float32Array(n * 4 * 3);
    const kleur = new Float32Array(n * 4 * 3);
    const dw = new Float32Array(n * 4 * 2);
    const idx = [];
    for (let b = 0; b < n; b++) {
      const o = b * 4;
      dw.set([-1, 0, 1, 0, -1, 1, 1, 1], b * 8);
      idx.push(o, o + 1, o + 2, o + 1, o + 3, o + 2);
    }
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3).setUsage(THREE.DynamicDrawUsage));
    geo.setAttribute('color', new THREE.BufferAttribute(kleur, 3).setUsage(THREE.DynamicDrawUsage));
    geo.setAttribute('dwars', new THREE.BufferAttribute(dw, 2));
    geo.setIndex(idx);
    const mat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide, fog: false,
      vertexColors: true,
      uniforms: { tijd: { value: 0 } },
      vertexShader: `attribute vec2 dwars; varying vec2 vD; varying vec3 vK; varying vec3 vW; varying float vAfst;
        void main() {
          vD = dwars; vK = color; vW = position;
          vec4 mv = viewMatrix * vec4(position, 1.0);
          vAfst = -mv.z;
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `uniform float tijd; varying vec2 vD; varying vec3 vK; varying vec3 vW; varying float vAfst;
        ${RUIS_GLSL}
        void main() {
          float a = vD.x;
          float kern = exp(-a * a * 14.0) + 0.25 * exp(-a * a * 2.5);
          float langs = 1.0 - pow(vD.y, 6.0);
          float mist = 0.35 + 0.9 * rMist(vW * 1.3, tijd * 1.5);
          float laag = mix(1.1, 0.6, smoothstep(2.0, 14.0, vW.y));
          float dichtbij = smoothstep(0.3, 2.0, vAfst);
          gl_FragColor = vec4(vK * kern * langs * mist * laag * dichtbij, 1.0);
        }`
    });
    this.laserMesh = new THREE.Mesh(geo, mat);
    this.laserMesh.frustumCulled = false;
    this.laserMesh.renderOrder = 6;
    this.groep.add(this.laserMesh);

    // lichtpuntjes op de grond
    const pgeo = new THREE.BufferGeometry();
    pgeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3).setUsage(THREE.DynamicDrawUsage));
    pgeo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(n * 3), 3).setUsage(THREE.DynamicDrawUsage));
    this.puntMat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false, vertexColors: true,
      uniforms: { map: { value: this.texGloed }, schaal: { value: 300 } },
      vertexShader: `varying vec3 vK; uniform float schaal;
        void main() { vK = color; vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = clamp(0.35 * schaal / -mv.z, 1.5, 48.0); gl_Position = projectionMatrix * mv; }`,
      fragmentShader: `uniform sampler2D map; varying vec3 vK;
        void main() { float a = texture2D(map, gl_PointCoord).r; gl_FragColor = vec4(vK * a, 1.0); }`
    });
    this.puntjes = new THREE.Points(pgeo, this.puntMat);
    this.puntjes.frustumCulled = false;
    this.puntjes.renderOrder = 6;
    this.groep.add(this.puntjes);
  }

  // ---------------------------------------------------------- boom-uplights
  maakBoom() {
    this.boom = this.ankers.boom.map((a, i) => {
      const kegel = maakKegel(a.kleur, 11, 0.32);
      kegel.position.copy(a.pos);
      kegel.lookAt(a.pos.clone().add(a.richting));
      this.groep.add(kegel);
      const l = new THREE.SpotLight(a.kleur, 0, 30, 0.55, 0.8, 2);
      l.position.copy(a.pos);
      l.target.position.copy(a.pos).addScaledVector(a.richting, 10);
      this.groep.add(l, l.target);
      return { ...a, kegel, licht: l, fase: i * 2.1 };
    });
  }

  // ---------------------------------------------------------- vuur
  maakVuur() {
    this.vuren = this.ankers.vuur.map((a) => {
      const l = new THREE.PointLight('#ff8a2a', 0, 26, 2);
      l.position.copy(a.pos).add(new THREE.Vector3(0, 0.9, 0));
      this.groep.add(l);
      const n = 90;
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3).setUsage(THREE.DynamicDrawUsage));
      geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(n * 3), 3).setUsage(THREE.DynamicDrawUsage));
      const vonken = new THREE.Points(geo, this.puntMat.clone());
      vonken.material.uniforms.map.value = this.texGloed;
      vonken.material.uniforms.schaal.value = 60;
      vonken.frustumCulled = false;
      this.groep.add(vonken);
      const deeltjes = Array.from({ length: n }, () => ({ p: new THREE.Vector3(), v: new THREE.Vector3(), leef: -Math.random() * 2, duur: 1 }));
      // gloed van de vlammen: een vlak dat naar de camera draait
      const gloed = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({
        map: this.texGloed, color: new THREE.Color('#ff6a10').multiplyScalar(2.2), transparent: true,
        blending: THREE.AdditiveBlending, depthWrite: false, fog: false
      }));
      gloed.position.copy(a.pos).add(new THREE.Vector3(0, 0.8, 0));
      gloed.renderOrder = 7;
      this.groep.add(gloed);
      return { ...a, licht: l, vonken, deeltjes, gloed };
    });
  }

  // ---------------------------------------------------------- blinders
  maakBlinders() {
    this.blinders = this.ankers.blinder.map((a) => {
      const schijf = new THREE.Mesh(new THREE.CircleGeometry(0.24, 24), new THREE.MeshBasicMaterial({ color: 0x000000, fog: false }));
      schijf.position.copy(a.pos).addScaledVector(a.richting, 0.05);
      schijf.lookAt(a.pos.clone().add(a.richting));
      this.groep.add(schijf);
      const halo = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({
        map: this.texGloed, color: 0x000000, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, fog: false
      }));
      halo.position.copy(schijf.position).addScaledVector(a.richting, 0.1);
      halo.renderOrder = 8;
      this.groep.add(halo);
      return { ...a, schijf, halo };
    });
    this.blinderLamp = null;
    if (this.blinders.length) {
      const mid = new THREE.Vector3();
      this.blinders.forEach((b) => mid.add(b.pos));
      mid.divideScalar(this.blinders.length);
      const l = new THREE.SpotLight('#fff2dd', 0, 70, 0.9, 0.9, 2);
      l.position.copy(mid);
      l.target.position.copy(mid).addScaledVector(this.blinders[0].richting, 20);
      this.groep.add(l, l.target);
      this.blinderLamp = l;
    }
  }

  // ---------------------------------------------------------- rook
  maakRook() {
    const per = 30;
    const n = Math.max(1, this.ankers.rook.length) * per;
    this.rookMax = n;
    const basis = new THREE.PlaneGeometry(1, 1);
    const geo = new THREE.InstancedBufferGeometry();
    geo.index = basis.index;
    geo.setAttribute('position', basis.getAttribute('position'));
    geo.setAttribute('uv', basis.getAttribute('uv'));
    const iPos = new THREE.InstancedBufferAttribute(new Float32Array(n * 3), 3).setUsage(THREE.DynamicDrawUsage);
    const iInfo = new THREE.InstancedBufferAttribute(new Float32Array(n * 3), 3).setUsage(THREE.DynamicDrawUsage); // grootte, alfa, draai
    const iKleur = new THREE.InstancedBufferAttribute(new Float32Array(n * 3), 3).setUsage(THREE.DynamicDrawUsage);
    geo.setAttribute('iPos', iPos);
    geo.setAttribute('iInfo', iInfo);
    geo.setAttribute('iKleur', iKleur);
    geo.instanceCount = n;
    const mat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, fog: false,
      uniforms: { map: { value: this.texRook } },
      vertexShader: `attribute vec3 iPos; attribute vec3 iInfo; attribute vec3 iKleur;
        varying vec2 vUv; varying float vA; varying vec3 vK;
        void main() {
          float c = cos(iInfo.z), s = sin(iInfo.z);
          vec2 p = mat2(c, s, -s, c) * position.xy * iInfo.x;
          vec4 mv = viewMatrix * vec4(iPos, 1.0);
          mv.xy += p;
          vUv = uv; vK = iKleur;
          vA = iInfo.y * smoothstep(0.8, 4.0, -mv.z);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `uniform sampler2D map; varying vec2 vUv; varying float vA; varying vec3 vK;
        void main() { float a = texture2D(map, vUv).a * vA; if (a < 0.003) discard; gl_FragColor = vec4(vK, a); }`
    });
    this.rookMesh = new THREE.Mesh(geo, mat);
    this.rookMesh.frustumCulled = false;
    this.rookMesh.renderOrder = 4;
    this.groep.add(this.rookMesh);
    this.rook = [];
    const bronnen = this.ankers.rook;
    for (let i = 0; i < n; i++) {
      const b = bronnen[i % bronnen.length];
      const d = { bron: b, p: new THREE.Vector3(), v: new THREE.Vector3(), leef: 0, duur: 1, draai: 0, dv: 0, groot: 1 };
      this.nieuwePluim(d);
      d.leef = Math.random() * d.duur;          // meteen een gevulde wolk
      d.p.addScaledVector(d.v, d.leef);
      this.rook.push(d);
    }
  }

  nieuwePluim(d) {
    const a = Math.random() * Math.PI * 2, r = Math.random() * 2.5;
    d.p.set(d.bron.pos.x + Math.cos(a) * r, d.bron.pos.y + 0.4 + Math.random() * 0.8, d.bron.pos.z + Math.sin(a) * r);
    const s = 0.25 + Math.random() * 0.45;
    d.v.set(Math.cos(a) * s, 0.04 + Math.random() * 0.1, Math.sin(a) * s + 0.15);
    d.leef = 0;
    d.duur = 12 + Math.random() * 10;
    d.draai = Math.random() * 6.28;
    d.dv = (Math.random() - 0.5) * 0.15;
    d.groot = 3 + Math.random() * 3;
  }

  // ---------------------------------------------------------- gloed-materialen
  zoekGloed(wereld) {
    this.gloed = [];
    const gezien = new Map();
    wereld.updateMatrixWorld(true);
    wereld.traverse((o) => {
      if (!o.isMesh) return;
      for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
        const r = /^gloed_([a-z]+)/.exec(m.name || '');
        if (!r) continue;
        let g = gezien.get(m);
        if (!g) {
          g = { mat: m, groep: r[1], basis: m.emissiveIntensity ?? 1, box: new THREE.Box3(), i: gezien.size };
          gezien.set(m, g);
          this.gloed.push(g);
        }
        if (!o.geometry.boundingBox) o.geometry.computeBoundingBox();
        g.box.union(o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld));
      }
    });
    this.gloedU = { uTijd: { value: 0 }, uBeat: { value: 0 }, uDrop: { value: 0 } };
    for (const g of this.gloed) {
      if (g.groep === 'led' || g.groep === 'scherm') this.patroon(g);
    }
  }

  /** LED-balken: een looplicht rond de vloer. Scherm: psychedelische visuals. */
  patroon(g) {
    const midden = g.box.getCenter(new THREE.Vector3());
    const maat = g.box.getSize(new THREE.Vector3());
    const u = { ...this.gloedU, uMidden: { value: midden }, uMaat: { value: Math.max(maat.x, maat.y, maat.z, 1) } };
    const scherm = g.groep === 'scherm';
    g.mat.onBeforeCompile = (shader) => {
      Object.assign(shader.uniforms, u);
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nvarying vec3 vGloedW;')
        .replace('#include <project_vertex>', '#include <project_vertex>\nvGloedW = (modelMatrix * vec4(transformed, 1.0)).xyz;');
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', `#include <common>
          varying vec3 vGloedW; uniform float uTijd; uniform float uBeat; uniform float uDrop; uniform vec3 uMidden; uniform float uMaat;`)
        .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
          {
          ${scherm ? `
            vec2 q = (vGloedW.xy - uMidden.xy) / uMaat * 6.0;
            float r = length(q), a = atan(q.y, q.x);
            float k = abs(mod(a * 3.0 / 3.14159 + uTijd * 0.05, 2.0) - 1.0);
            float v = sin(r * 3.0 - uTijd * (1.5 + uDrop * 3.0)) * sin(k * 6.0 + uTijd * 0.4 + r);
            vec3 kl = 0.5 + 0.5 * cos(6.2831 * (vec3(0.0, 0.33, 0.67) + r * 0.12 - uTijd * 0.07 + uDrop * 0.3));
            float hel = length(totalEmissiveRadiance);
            totalEmissiveRadiance = mix(totalEmissiveRadiance, kl * hel, 0.65) * (0.35 + 0.9 * smoothstep(-0.3, 0.9, v)) * (1.0 + uBeat * 0.6);
          ` : `
            float hoek = atan(vGloedW.z, vGloedW.x);
            float p = 0.5 + 0.5 * sin(hoek * 10.0 - uTijd * (1.5 + uDrop * 7.0));
            totalEmissiveRadiance *= mix(1.0, 0.2 + 1.6 * p * p, 0.35 + 0.55 * uDrop);
          `}
          }`);
    };
    g.mat.customProgramCacheKey = () => 'gloed_' + g.groep;
    g.mat.needsUpdate = true;
  }

  // ---------------------------------------------------------- kwaliteit
  zetKwaliteit(k) {
    this.kwaliteit = k;
    const licht = k === 'licht';
    this.verdeelSpotLampen();
    this.boom.forEach((b, i) => { b.licht.visible = !licht || i === 0; });
    if (this.blinderLamp) this.blinderLamp.visible = !licht;
    this.rookMesh.geometry.instanceCount = licht ? Math.ceil(this.rookMax * 0.45) : this.rookMax;
    this.laserActief = licht ? 4 : this.laserPer;
  }

  // ---------------------------------------------------------- per frame
  update(dt, ritme, camera) {
    this.tijd += dt;
    const t = this.tijd;
    const { beat, fase, drop, spanning } = ritme;
    const tel = ritme.tel + ritme.beatFase;
    const opbouw = fase === 'opbouw' ? spanning : 0;

    // dominante kleur (lucht, rook, randlicht): gemiddelde van de spots, in de drop feller
    this.dominant.setRGB(0, 0, 0);
    for (const s of this.spots) this.dominant.add(s.kleurNu);
    if (this.spots.length) this.dominant.multiplyScalar(1 / this.spots.length);
    randUniforms.uRandKleur.value.copy(this.dominant).multiplyScalar(0.35 + drop * 0.5 + beat * (0.25 + drop * 0.6));

    this.updateSpots(dt, t, ritme, tel, opbouw);
    this.updateLasers(t, ritme, tel, opbouw, camera);
    this.updateBoom(t, ritme);
    this.camQuat = camera.quaternion;
    this.updateVuur(dt, t);
    this.updateBlinders(t, ritme, camera, opbouw);
    this.updateRook(dt, ritme);
    this.updateGloed(t, ritme, opbouw);
  }

  updateSpots(dt, t, ritme, tel, opbouw) {
    const { beat, drop } = ritme;
    const snel = 0.25 + opbouw * 0.9 + drop * 0.4;
    for (const s of this.spots) {
      s.fase += dt * snel;
      let pan, tilt;
      if (drop > 0.5) {
        // in de drop: zwaaien op de maat, links en rechts in tegenfase
        const slag = Math.sin(tel * Math.PI / 2) * s.links;
        pan = slag * 0.32 + Math.sin(s.fase * 0.7) * 0.08;
        tilt = Math.cos(tel * Math.PI / 4) * 0.12 - 0.05;
      } else {
        pan = Math.sin(s.fase + Math.sin(s.fase * 0.37) * 1.3) * 0.28 * s.links;
        tilt = Math.sin(s.fase * 0.61 + 1.3) * 0.1;
      }
      s.dir.copy(s.richting).applyAxisAngle(OMHOOG, pan).applyAxisAngle(s.zij, tilt).normalize();
      s.kegel.position.copy(s.pos);
      s.kegel.lookAt(s.pos.x + s.dir.x, s.pos.y + s.dir.y, s.pos.z + s.dir.z);
      // kleur: in de drop wisselen spots om de 8 beats van kleur over het palet
      if (drop > 0.5) {
        const k = PALET[(Math.floor(tel / 8) + this.spots.indexOf(s)) % 4];
        s.kleurNu.lerp(k, Math.min(1, dt * 6));
      } else s.kleurNu.lerp(s.kleur, Math.min(1, dt * 2));
      const sterkte = 0.22 + 0.2 * opbouw + beat * (0.18 + drop * 0.5) + drop * 0.25;
      const u = s.kegel.material.uniforms;
      u.kleur.value.copy(s.kleurNu);
      u.sterkte.value = sterkte;
      u.tijd.value = t;
      if (s.licht) {
        s.licht.position.copy(s.pos);
        s.licht.target.position.copy(s.pos).addScaledVector(s.dir, 20);
        s.licht.color.copy(s.kleurNu);
        s.licht.intensity = 2600 * (0.55 + opbouw * 0.3 + drop * 0.4 + beat * (0.3 + drop * 0.6));
      }
    }
  }

  updateLasers(t, ritme, tel, opbouw, camera) {
    const { beat, drop, fase } = ritme;
    const geo = this.laserMesh.geometry;
    const pos = geo.attributes.position.array, kl = geo.attributes.color.array;
    const ppos = this.puntjes.geometry.attributes.position.array, pkl = this.puntjes.geometry.attributes.color.array;
    const per = this.laserPer;
    const cam = camera.position;
    const S = new THREE.Vector3(), E = new THREE.Vector3(), d = new THREE.Vector3(), w = new THREE.Vector3(), naar = new THREE.Vector3();
    let b = 0;
    const blok = Math.floor(tel / 16);
    this.lasers.forEach((L, li) => {
      // welke lasers branden: in de basis maar een paar, in de opbouw meer, in de drop allemaal
      let doel;
      if (fase === 'drop') doel = 1;
      else if (fase === 'opbouw') doel = (li % 2 === blok % 2 || opbouw > 0.5) ? 0.5 + opbouw * 0.5 : 0;
      else doel = (li === blok % this.lasers.length || li === (blok + 3) % this.lasers.length) ? 0.55 : 0;
      L.aan += (doel - L.aan) * 0.08;
      const breed = 0.25 + opbouw * 0.6 + drop * 0.85;
      const tempo = 0.35 + opbouw * 1.6 + drop * 1.2;
      const zwaai = drop > 0.5 ? Math.sin(tel * Math.PI / 4 + li) * 0.35 : Math.sin(t * tempo * 0.6 + L.fase) * 0.22;
      const kantel = drop > 0.5 ? (Math.floor(tel / 2) % 2 ? 0.12 : -0.08) + Math.sin(t * 2 + li) * 0.04 : Math.sin(t * tempo * 0.4 + L.fase * 2) * 0.1;
      const flikker = opbouw > 0.6 ? (Math.sin(t * (30 + opbouw * 40)) > 0 ? 1 : 0.15) : 1;
      const sterkte = L.aan * flikker * (1.4 + beat * (0.8 + drop * 2.2)) * 2.4;
      for (let k = 0; k < per; k++, b++) {
        const o = b * 12;
        const actief = k < this.laserActief && sterkte > 0.02;
        const hoek = per > 1 ? (k / (per - 1) - 0.5) * breed : 0;
        d.copy(L.richting).applyAxisAngle(OMHOOG, hoek + zwaai).applyAxisAngle(L.zij, kantel + Math.sin(k * 1.7 + t * tempo) * 0.04 * (1 + drop)).normalize();
        let lengte = 90;
        let raak = false;
        if (d.y < -0.01) { const tg = L.pos.y / -d.y; if (tg < 90) { lengte = tg; raak = true; } }
        S.copy(L.pos);
        E.copy(L.pos).addScaledVector(d, lengte);
        // breedte groeit met de afstand tot de camera: blijft altijd een paar pixels breed
        const ds = S.distanceTo(cam), de = E.distanceTo(cam);
        naar.copy(cam).sub(S);
        w.crossVectors(d, naar).normalize();
        const ws = Math.max(0.02, ds * 0.0022), we = Math.max(0.02, de * 0.0022);
        const zet = (i, p, s) => { pos[o + i * 3] = p.x + w.x * s; pos[o + i * 3 + 1] = p.y + w.y * s; pos[o + i * 3 + 2] = p.z + w.z * s; };
        if (actief) {
          zet(0, S, -ws); zet(1, S, ws); zet(2, E, -we); zet(3, E, we);
        } else {
          for (let i = 0; i < 12; i++) pos[o + i] = 0;
        }
        const r = L.kleur.r * sterkte, g = L.kleur.g * sterkte, bl = L.kleur.b * sterkte;
        for (let i = 0; i < 4; i++) { kl[o + i * 3] = actief ? r : 0; kl[o + i * 3 + 1] = actief ? g : 0; kl[o + i * 3 + 2] = actief ? bl : 0; }
        // puntje op de grond
        const p3 = b * 3;
        if (actief && raak) {
          ppos[p3] = E.x; ppos[p3 + 1] = 0.03; ppos[p3 + 2] = E.z;
          pkl[p3] = r * 0.9; pkl[p3 + 1] = g * 0.9; pkl[p3 + 2] = bl * 0.9;
        } else {
          ppos[p3] = ppos[p3 + 1] = ppos[p3 + 2] = 0; pkl[p3] = pkl[p3 + 1] = pkl[p3 + 2] = 0;
        }
      }
    });
    geo.attributes.position.needsUpdate = true;
    geo.attributes.color.needsUpdate = true;
    this.puntjes.geometry.attributes.position.needsUpdate = true;
    this.puntjes.geometry.attributes.color.needsUpdate = true;
    this.laserMesh.material.uniforms.tijd.value = t;
    this.puntMat.uniforms.schaal.value = innerHeight * 0.9;
  }

  updateBoom(t, ritme) {
    for (const b of this.boom) {
      const adem = 0.75 + 0.25 * Math.sin(t * 0.5 + b.fase);
      const s = adem * (0.8 + ritme.drop * 0.35 + ritme.beat * ritme.drop * 0.3);
      b.licht.intensity = 900 * s;
      b.kegel.material.uniforms.sterkte.value = 0.22 * s;
      b.kegel.material.uniforms.tijd.value = t;
    }
  }

  updateVuur(dt, t) {
    for (const v of this.vuren) {
      const fl = 0.75 + 0.18 * Math.sin(t * 9.1) + 0.12 * Math.sin(t * 23.7 + 1.3) + 0.1 * (Math.random() - 0.5);
      v.licht.intensity = 140 * fl;
      v.gloed.scale.setScalar(2.4 + fl * 0.6);
      v.gloed.quaternion.copy(this.camQuat || v.gloed.quaternion);
      v.gloed.material.opacity = 0.55 + fl * 0.35;
      const pa = v.vonken.geometry.attributes.position.array, ca = v.vonken.geometry.attributes.color.array;
      v.deeltjes.forEach((d, i) => {
        d.leef += dt;
        if (d.leef > d.duur || d.leef < 0 && d.leef + dt >= 0) {
          d.leef = 0; d.duur = 0.8 + Math.random() * 1.8;
          d.p.set(v.pos.x + (Math.random() - 0.5) * 0.8, v.pos.y + 0.3, v.pos.z + (Math.random() - 0.5) * 0.8);
          d.v.set((Math.random() - 0.5) * 0.6, 1.2 + Math.random() * 2.2, (Math.random() - 0.5) * 0.6);
        }
        if (d.leef < 0) { ca[i * 3] = ca[i * 3 + 1] = ca[i * 3 + 2] = 0; return; }
        d.v.x += Math.sin(t * 3 + i) * dt * 0.8;
        d.v.y -= dt * 0.25;
        d.p.addScaledVector(d.v, dt);
        pa[i * 3] = d.p.x; pa[i * 3 + 1] = d.p.y; pa[i * 3 + 2] = d.p.z;
        const k = 1 - d.leef / d.duur;
        const f = k * (0.6 + 0.4 * Math.sin(t * 20 + i * 3));
        ca[i * 3] = 3.5 * f; ca[i * 3 + 1] = 1.2 * f * k; ca[i * 3 + 2] = 0.15 * f * k;
      });
      v.vonken.geometry.attributes.position.needsUpdate = true;
      v.vonken.geometry.attributes.color.needsUpdate = true;
    }
  }

  updateBlinders(t, ritme, camera, opbouw) {
    const { beat, fase, tel } = ritme;
    let s;
    if (fase === 'drop') {
      const begin = ritme.sindsWissel < 1.6 ? 1 - ritme.sindsWissel / 1.6 : 0;
      s = Math.max(begin * 1.2, tel % 4 === 0 ? beat : beat * 0.12);
    } else if (opbouw > 0.7) {
      s = (Math.sin(t * (20 + opbouw * 30)) > 0.3 ? 1 : 0) * (opbouw - 0.7) * 2.2;
    } else s = 0.015;
    const naar = new THREE.Vector3();
    for (const b of this.blinders) {
      b.schijf.material.color.copy(b.kleur).multiplyScalar(0.3 + s * 40);
      naar.copy(camera.position).sub(b.pos).normalize();
      const zicht = glad(-0.1, 0.9, naar.dot(b.richting));
      b.halo.quaternion.copy(camera.quaternion);
      b.halo.scale.setScalar(1.2 + s * 7 * (0.4 + zicht));
      b.halo.material.color.copy(b.kleur).multiplyScalar(s * 3.5 * zicht + 0.02);
    }
    if (this.blinderLamp) this.blinderLamp.intensity = s * 30000;
  }

  updateRook(dt, ritme) {
    const geo = this.rookMesh.geometry;
    const P = geo.attributes.iPos.array, I = geo.attributes.iInfo.array, K = geo.attributes.iKleur.array;
    const n = geo.instanceCount;
    const pl = new THREE.Vector3(), basis = new THREE.Color('#0b1022');
    const kleur = new THREE.Color();
    for (let i = 0; i < n; i++) {
      const d = this.rook[i];
      d.leef += dt;
      if (d.leef > d.duur) this.nieuwePluim(d);
      d.p.addScaledVector(d.v, dt);
      d.v.multiplyScalar(1 - dt * 0.03);
      d.draai += d.dv * dt;
      const k = d.leef / d.duur;
      const alfa = glad(0, 0.15, k) * (1 - glad(0.6, 1, k)) * 0.16;
      P[i * 3] = d.p.x; P[i * 3 + 1] = d.p.y; P[i * 3 + 2] = d.p.z;
      I[i * 3] = d.groot * (0.6 + k * 0.9); I[i * 3 + 1] = alfa; I[i * 3 + 2] = d.draai;
      // de rook wordt verlicht door de spots die er dichtbij langs gaan
      kleur.copy(basis);
      for (const s of this.spots) {
        pl.copy(d.p).sub(s.pos);
        const langs = pl.dot(s.dir);
        if (langs < 0) continue;
        const loodrecht = pl.addScaledVector(s.dir, -langs).length();
        const breedte = 0.6 + langs * 0.09;
        const f = Math.exp(-(loodrecht * loodrecht) / (breedte * breedte)) * s.kegel.material.uniforms.sterkte.value * 2.2;
        kleur.r += s.kleurNu.r * f; kleur.g += s.kleurNu.g * f; kleur.b += s.kleurNu.b * f;
      }
      kleur.r += this.dominant.r * ritme.beat * 0.15 * ritme.drop;
      kleur.g += this.dominant.g * ritme.beat * 0.15 * ritme.drop;
      kleur.b += this.dominant.b * ritme.beat * 0.15 * ritme.drop;
      K[i * 3] = kleur.r; K[i * 3 + 1] = kleur.g; K[i * 3 + 2] = kleur.b;
    }
    geo.attributes.iPos.needsUpdate = true;
    geo.attributes.iInfo.needsUpdate = true;
    geo.attributes.iKleur.needsUpdate = true;
  }

  updateGloed(t, ritme, opbouw) {
    const { beat, drop } = ritme;
    this.gloedU.uTijd.value = t;
    this.gloedU.uBeat.value = beat;
    this.gloedU.uDrop.value = drop;
    for (const g of this.gloed) {
      let f = 1;
      switch (g.groep) {
        case 'led': f = 0.55 + beat * (1.6 + drop * 1.6) + drop * 0.8 + opbouw * 0.8; break;
        case 'scherm': f = 0.8 + beat * 0.9 + drop * 1.0 + opbouw * 0.5; break;
        case 'podium': f = 0.2 + drop * (0.6 + beat * 3.5) + (opbouw > 0.5 ? (Math.sin(t * 25) > 0 ? opbouw : 0) : 0); break;
        case 'doek': f = 1.0 + beat * 0.45 + drop * 0.3; break;
        case 'stringart': f = 1.1 + 0.45 * Math.sin(t * 0.8 + g.i); break;
        case 'paddenstoel': f = 1.0 + 0.4 * Math.sin(t * 0.5 + g.i * 1.3); break;
        case 'lampion': f = 1.15 + 0.06 * Math.sin(t * 2.3 + g.i) + 0.04 * Math.sin(t * 7.1 + g.i); break;
        case 'vuur': f = 1.5 + 0.5 * Math.sin(t * 11 + g.i) + 0.3 * Math.sin(t * 27) + 0.2 * Math.random(); break;
        case 'glowstick': f = 2.2 + beat * 0.8; break;
        default: f = 1;
      }
      g.mat.emissiveIntensity = g.basis * f;
    }
  }
}
