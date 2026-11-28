// Rave against the machine — nachtlucht (sterren, maan) en lage hoogtemist.
import * as THREE from 'three';

export const NACHT = new THREE.Color('#060914');          // mistkleur, nachtblauw
export const MAAN_RICHTING = new THREE.Vector3(-0.32, 0.5, -0.8).normalize();   // achter het podium

/**
 * Maakt van three.js' FogExp2 een lage mist: dicht bij de grond, ijler naar boven.
 * Moet gebeuren voor er iets gecompileerd wordt. Werkt voor alle ingebouwde materialen
 * die `transformed` kennen (mesh, points, lijnen). Sprites gebruiken we niet.
 */
export function maakHoogteMist() {
  const C = THREE.ShaderChunk;
  C.fog_pars_vertex = `#ifdef USE_FOG
  varying float vFogDepth;
  varying float vFogHoogte;
#endif`;
  C.fog_vertex = `#ifdef USE_FOG
  vFogDepth = - mvPosition.z;
  {
    vec4 mistW = vec4(transformed, 1.0);
    #ifdef USE_INSTANCING
      mistW = instanceMatrix * mistW;
    #endif
    mistW = modelMatrix * mistW;
    vFogHoogte = mistW.y;
  }
#endif`;
  C.fog_pars_fragment = `#ifdef USE_FOG
  uniform vec3 fogColor;
  varying float vFogDepth;
  varying float vFogHoogte;
  #ifdef FOG_EXP2
    uniform float fogDensity;
  #else
    uniform float fogNear;
    uniform float fogFar;
  #endif
#endif`;
  C.fog_fragment = `#ifdef USE_FOG
  #ifdef FOG_EXP2
    // dichter laag bij de grond; hoog in de bomen en lucht ijler
    float mistLaag = mix(1.0, 0.42, smoothstep(1.0, 16.0, vFogHoogte));
    float mistD = fogDensity * mistLaag;
    float fogFactor = 1.0 - exp( - mistD * mistD * vFogDepth * vFogDepth );
  #else
    float fogFactor = smoothstep( fogNear, fogFar, vFogDepth );
  #endif
  gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );
#endif`;
}

/** Hemelkoepel met sterren, melkweg-waas, maan en een gloed van het feest aan de horizon. */
export function maakLucht(camera) {
  const uniforms = {
    tijd: { value: 0 },
    maan: { value: MAAN_RICHTING },
    horizon: { value: NACHT.clone() },
    feest: { value: new THREE.Color('#3a0f4a') },      // licht.js zet dit op de kleur van het podium
    feestRichting: { value: new THREE.Vector3(0, 0, -1) }
  };
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, fog: false, uniforms,
    vertexShader: `varying vec3 vR;
      void main() { vR = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); gl_Position.z = gl_Position.w; }`,
    fragmentShader: `uniform float tijd; uniform vec3 maan; uniform vec3 horizon; uniform vec3 feest; uniform vec3 feestRichting;
      varying vec3 vR;
      float hash(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
      float ruis(vec3 x) {
        vec3 i = floor(x), f = fract(x); f = f * f * (3.0 - 2.0 * f);
        return mix(mix(mix(hash(i), hash(i + vec3(1,0,0)), f.x), mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
                   mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x), mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z);
      }
      float sterren(vec3 r, float schaal, float kans) {
        vec3 p = r * schaal; vec3 c = floor(p);
        float h = hash(c);
        if (h < kans) return 0.0;
        vec3 mid = c + 0.5 + (vec3(hash(c + 7.1), hash(c + 3.3), hash(c + 1.7)) - 0.5) * 0.6;
        float d = length(p - mid);
        float flik = 0.75 + 0.25 * sin(tijd * (1.5 + h * 4.0) + h * 60.0);
        return smoothstep(0.09, 0.0, d) * (h - kans) / (1.0 - kans) * flik;
      }
      void main() {
        vec3 r = normalize(vR);
        float h = max(r.y, 0.0);
        vec3 zenit = vec3(0.004, 0.006, 0.016);
        vec3 k = mix(horizon * 1.3, zenit, pow(h, 0.45));
        // melkweg: schuine band met ruis
        float band = exp(-pow(dot(r, normalize(vec3(0.55, 0.35, 0.75))) * 3.2, 2.0));
        float wolk = ruis(r * 6.0) * 0.6 + ruis(r * 14.0) * 0.4;
        k += vec3(0.020, 0.022, 0.035) * band * wolk * smoothstep(0.0, 0.3, h);
        float s = sterren(r, 220.0, 0.965) * 1.6 + sterren(r, 90.0, 0.985) * 3.0;
        k += vec3(0.85, 0.9, 1.0) * s * smoothstep(0.02, 0.25, h) * (1.0 - band * 0.3);
        // feestgloed aan de horizon richting podium
        float fr = max(dot(normalize(vec3(r.x, 0.0, r.z)), feestRichting), 0.0);
        k += feest * pow(fr, 3.0) * exp(-h * 9.0) * 0.6;
        // maan
        float m = dot(r, maan);
        float schijf = smoothstep(0.99955, 0.99968, m);
        vec3 mp = r - maan * m;
        float vlek = ruis(mp * 900.0) * 0.5 + ruis(mp * 2400.0) * 0.5;
        k += vec3(1.0, 0.97, 0.9) * schijf * (2.2 - vlek * 0.9);
        k += vec3(0.35, 0.42, 0.6) * pow(max(m, 0.0), 900.0) * 0.6 + vec3(0.06, 0.08, 0.14) * pow(max(m, 0.0), 40.0) * 0.5;
        if (r.y < 0.0) k = mix(k, horizon, smoothstep(0.0, -0.08, r.y));
        gl_FragColor = vec4(k, 1.0);
      }`
  });
  const lucht = new THREE.Mesh(new THREE.SphereGeometry(500, 48, 24), mat);
  lucht.frustumCulled = false;
  lucht.renderOrder = -10;
  lucht.onBeforeRender = () => lucht.position.copy(camera.position);
  lucht.name = 'nachtlucht';
  return { mesh: lucht, uniforms };
}
