// "The scout's journey": a 3D replay of the real runs. Each dataset the scout tried rides along a
// path through nine checkpoints (licence & data, then the 8 gates). Rejected ones turn red and drop
// off at the checkpoint that stopped them; shipped ones climb onto the mountain at the end.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
export const STATIONS = [
  { id: "prepare", short: "Licence & data" },
  { id: "valid", short: "Valid" },
  { id: "baseline_scores", short: "Baseline" },
  { id: "deterministic", short: "Repeatable" },
  { id: "fast", short: "Fast" },
  { id: "headroom", short: "Room to improve" },
  { id: "not_trivial", short: "Not too easy" },
  { id: "no_leak", short: "No leak" },
  { id: "rejects_junk", short: "Rejects junk" },
];
const X0 = -11, X1 = 8.5, END = 12;
const stationX = (i) => X0 + 3 + (i * (X1 - X0 - 3)) / (STATIONS.length - 1);

function label(text, color, size = 0.5) {
  const c = document.createElement("canvas"), g = c.getContext("2d"), font = "600 44px ui-sans-serif, system-ui, sans-serif";
  g.font = font; const w = Math.ceil(g.measureText(text).width) + 30; c.width = w; c.height = 64;
  g.font = font; g.fillStyle = color; g.textBaseline = "middle"; g.fillText(text, 15, 34);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthWrite: false }));
  s.scale.set((w / 64) * size, size, 1); return s;
}

export function mountJourney(container, items, { onItem, onCount }) {
  let renderer;
  try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }); }
  catch (e) { container.innerHTML = '<div class="scene-fallback">The 3D replay needs WebGL. The diagrams below explain the same steps.</div>'; return { dispose() {}, setPlaying() {}, restart() {} }; }
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 200);
  camera.position.set(0.5, 8, 18.5);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0.5, 0.5, 0); controls.enableDamping = true; controls.minDistance = 10; controls.maxDistance = 38;
  controls.maxPolarAngle = Math.PI * 0.48;
  scene.add(new THREE.HemisphereLight(0xffffff, 0x445544, 1.25));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4); sun.position.set(4, 12, 9); scene.add(sun);

  const fg = css("--fg") || "#222", muted = css("--muted") || "#666", pass = css("--pass") || "#2f7d4f", fail = css("--fail") || "#b0402f";
  const accent = css("--accent") || "#2f6b55", mid = css("--mid") || "#b06d0f";
  // ground + path
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(60, 30), new THREE.MeshStandardMaterial({ color: css("--bg-2") || "#efece3", roughness: 1 }));
  ground.rotation.x = -Math.PI / 2; ground.position.y = -0.02; scene.add(ground);
  const path = new THREE.Mesh(new THREE.BoxGeometry(END - X0 + 2, 0.06, 1.6), new THREE.MeshStandardMaterial({ color: css("--line") || "#ddd", roughness: 0.9 }));
  path.position.set((END + X0) / 2, 0.02, 0); scene.add(path);

  // sources
  const srcColors = { OpenML: accent, Kaggle: "#20beff", Web: mid };
  Object.entries(srcColors).forEach(([name, col], i) => {
    const pad = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 0.9, 0.15, 24), new THREE.MeshStandardMaterial({ color: col, roughness: 0.6 }));
    pad.position.set(X0 - 1.5, 0.08, (i - 1) * 2.6); scene.add(pad);
    const l = label(name, fg, 0.6); l.position.set(X0 - 1.5, 0.75, (i - 1) * 2.6); scene.add(l);
  });

  // checkpoints (arches)
  const rings = STATIONS.map((st, i) => {
    const mat = new THREE.MeshStandardMaterial({ color: i === 0 ? muted : accent, roughness: 0.5, transparent: true, opacity: 0.85 });
    const ring = new THREE.Mesh(new THREE.TorusGeometry(1.15, 0.13, 12, 40, Math.PI), mat);
    ring.position.set(stationX(i), 0.05, 0); ring.rotation.y = Math.PI / 2; scene.add(ring);
    const l = label(st.short, fg, 0.5); l.position.set(stationX(i), 1.7 + (i % 2) * 0.6, 0); scene.add(l);
    return { ring, mat, base: mat.color.clone(), flash: 0 };
  });

  // the mountain that collects shipped hills
  const mountain = new THREE.Mesh(new THREE.ConeGeometry(2.1, 3.2, 7), new THREE.MeshStandardMaterial({ color: pass, roughness: 0.8, flatShading: true }));
  mountain.position.set(END, 1.6, 0); scene.add(mountain);
  const cap = new THREE.Mesh(new THREE.ConeGeometry(0.62, 0.95, 7), new THREE.MeshStandardMaterial({ color: 0xffffff, flatShading: true }));
  cap.position.set(END, 2.75, 0); scene.add(cap);
  const ml = label("Shipped hills", fg, 0.62); ml.position.set(END, 3.9, 0); scene.add(ml);
  const flags = [];

  // movers
  const boxGeo = new THREE.BoxGeometry(0.62, 0.62, 0.62);
  let queue = [], movers = [], shipped = 0, rejected = 0, spawnT = 0, playing = !reduced, speed = 1;
  const restart = () => {
    movers.forEach((m) => scene.remove(m.mesh)); flags.forEach((f) => scene.remove(f)); movers = []; flags.length = 0;
    queue = items.map((it, k) => ({ ...it, k })); shipped = 0; rejected = 0; spawnT = 0; onCount(shipped, rejected, items.length);
  };
  const spawn = (it) => {
    const col = srcColors[it.source] || accent;
    const mesh = new THREE.Mesh(boxGeo, new THREE.MeshStandardMaterial({ color: col, roughness: 0.55 }));
    const lane = ({ OpenML: 0, Kaggle: 1, Web: 2 }[it.source] ?? 0) - 1;
    mesh.position.set(X0 - 1.5, 0.45, lane * 2.6); scene.add(mesh);
    movers.push({ it, mesh, phase: "merge", lane, vy: 0, t: 0 });
    onItem(it, "start");
  };

  restart();
  const clock = new THREE.Clock();
  const tmp = new THREE.Color();
  let raf = 0, alive = true;
  (function loop() {
    if (!alive) return;
    const dt = Math.min(clock.getDelta(), 0.05) * speed;
    if (playing) {
      spawnT -= dt;
      if (queue.length && spawnT <= 0) { spawn(queue.shift()); spawnT = 1.7; }
      if (!queue.length && !movers.length) { spawnT -= dt; if (spawnT < -3) restart(); }
      for (const m of [...movers]) {
        const p = m.mesh.position;
        m.mesh.rotation.y += dt * 1.5;
        if (m.phase === "merge") {
          p.x += dt * 3; p.z += (0 - p.z) * Math.min(1, dt * 3);
          if (p.x >= X0) m.phase = "ride";
        } else if (m.phase === "ride") {
          p.x += dt * 3.2;
          const stop = m.it.gate;
          if (stop >= 0 && p.x >= stationX(stop)) {
            m.phase = "fall"; rings[stop].flash = 1;
            m.mesh.material.color.set(fail); m.vy = 2.5; m.vz = (Math.random() < 0.5 ? -1 : 1) * 2.2;
            rejected++; onCount(shipped, rejected, items.length); onItem(m.it, "rejected");
          } else if (p.x >= X1 + 0.8) {
            if (stop < 0 && p.x >= stationX(STATIONS.length - 1)) rings.forEach((r) => { if (r.flash <= 0) r.flash = -0.6; });
            m.phase = "climb"; m.t = 0; m.from = p.clone();
          }
        } else if (m.phase === "fall") {
          m.vy -= dt * 9; p.y += m.vy * dt; p.z += m.vz * dt; m.mesh.rotation.x += dt * 5;
          m.mesh.material.transparent = true; m.mesh.material.opacity = Math.max(0, m.mesh.material.opacity - dt * 0.6);
          if (p.y < -3 || m.mesh.material.opacity <= 0) { scene.remove(m.mesh); movers.splice(movers.indexOf(m), 1); }
        } else if (m.phase === "climb") {
          m.t += dt * 0.8; const t = Math.min(1, m.t);
          const ang = shipped * 1.1;
          const target = new THREE.Vector3(END + Math.cos(ang) * 1.0, 1.2 + (shipped % 3) * 0.55, Math.sin(ang) * 1.0);
          p.lerpVectors(m.from, target, t); p.y += Math.sin(t * Math.PI) * 1.6;
          m.mesh.material.color.lerp(tmp.set(pass), dt * 2);
          if (t >= 1) {
            scene.remove(m.mesh); movers.splice(movers.indexOf(m), 1);
            const flag = new THREE.Group();
            const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.7), new THREE.MeshStandardMaterial({ color: fg }));
            const cloth = new THREE.Mesh(new THREE.PlaneGeometry(0.42, 0.26), new THREE.MeshStandardMaterial({ color: srcColors[m.it.source] || accent, side: THREE.DoubleSide }));
            cloth.position.set(0.21, 0.22, 0); pole.position.y = 0; flag.add(pole, cloth); flag.position.copy(target); scene.add(flag); flags.push(flag);
            shipped++; onCount(shipped, rejected, items.length); onItem(m.it, "shipped");
          }
        }
      }
    }
    for (const r of rings) {
      if (r.flash > 0) { r.mat.color.copy(r.base).lerp(tmp.set(fail), r.flash); r.flash = Math.max(0, r.flash - dt * 0.9); }
      else if (r.flash < 0) { r.mat.color.copy(r.base).lerp(tmp.set(pass), -r.flash); r.flash = Math.min(0, r.flash + dt * 0.9); }
      else r.mat.color.copy(r.base);
    }
    flags.forEach((f, i) => { f.children[1].rotation.y = Math.sin(performance.now() / 300 + i) * 0.3; });
    controls.update(); renderer.render(scene, camera);
    raf = requestAnimationFrame(loop);
  })();

  const resize = () => {
    const w = container.clientWidth, h = container.clientHeight;
    renderer.setSize(w, h, false); renderer.domElement.style.width = "100%"; renderer.domElement.style.height = "100%";
    camera.aspect = w / Math.max(1, h);
    camera.position.z = w < 600 ? 34 : 18.5;
    camera.updateProjectionMatrix();
  };
  const ro = new ResizeObserver(resize); ro.observe(container); resize();
  return {
    setPlaying(v) { playing = v; }, setSpeed(v) { speed = v; }, restart,
    dispose() { alive = false; cancelAnimationFrame(raf); ro.disconnect(); controls.dispose(); renderer.dispose(); },
  };
}
