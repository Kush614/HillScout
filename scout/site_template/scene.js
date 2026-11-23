// 3D "hill range": one peak per hill. Height = headroom (how far the reference model
// climbs above the baseline), colour = difficulty. Orbit, hover for scores, click to open.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export function headroom(h) {
  if (h.baseline == null || h.reference == null) return 0;
  if (h.direction === "max") return Math.max(0, h.reference - h.baseline) / 0.5; // 0.5 bacc gain = full height
  return Math.max(0, 1 - h.reference / h.baseline); // fraction of error removed
}

// Deterministic pseudo-random from a string, so each hill always gets the same ridge shape.
function rng(seed) {
  let s = 0;
  for (const ch of seed) s = (s * 31 + ch.charCodeAt(0)) >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296);
}

function peakGeometry(height, seed) {
  const r = rng(seed);
  const geo = new THREE.ConeGeometry(1, 1, 7, 6, false);
  const pos = geo.attributes.position;
  const v = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i);
    const t = v.y + 0.5; // 0 at base, 1 at tip
    const jitter = (r() - 0.5) * 0.22 * (1 - t);
    v.x *= 1 + jitter; v.z *= 1 + (r() - 0.5) * 0.22 * (1 - t);
    v.y = t * height;
    pos.setXYZ(i, v.x, v.y, v.z);
  }
  geo.computeVertexNormals();
  return geo;
}

function labelSprite(text, color) {
  const c = document.createElement("canvas");
  const ctx = c.getContext("2d");
  const font = "600 44px ui-sans-serif, system-ui, sans-serif";
  ctx.font = font;
  const w = Math.ceil(ctx.measureText(text).width) + 36;
  c.width = w; c.height = 72;
  ctx.font = font;
  ctx.fillStyle = "rgba(0,0,0,0)"; ctx.fillRect(0, 0, w, 72);
  ctx.fillStyle = color; ctx.textBaseline = "middle"; ctx.fillText(text, 18, 38);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, sizeAttenuation: false }));
  sp.scale.set((w / 72) * 0.042, 0.042, 1);
  return sp;
}

export function mountScene(container, tip, hills, { onPick, fmt }) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  } catch (e) {
    container.innerHTML = '<div class="scene-fallback">3D view needs WebGL, which this browser has turned off. The list below has every hill.</div>';
    return { highlight() {}, dispose() {} };
  }
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  container.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(css("--scene-bg") || "#e9e6dc", 24, 48);
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 200);
  camera.position.set(0, 8.5, 21);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true; controls.dampingFactor = 0.08;
  controls.minDistance = 7; controls.maxDistance = 30; controls.maxPolarAngle = Math.PI * 0.47;
  controls.target.set(0, 1.6, 0);
  controls.autoRotate = !reduced; controls.autoRotateSpeed = 0.55;

  scene.add(new THREE.HemisphereLight(0xffffff, 0x445544, 1.2));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6);
  sun.position.set(6, 12, 8);
  scene.add(sun);

  // ground: a gently rolling plane
  const ground = new THREE.PlaneGeometry(40, 40, 60, 60);
  const gp = ground.attributes.position;
  for (let i = 0; i < gp.count; i++) {
    const x = gp.getX(i), y = gp.getY(i);
    gp.setZ(i, Math.sin(x * 0.35) * Math.cos(y * 0.3) * 0.18);
  }
  ground.computeVertexNormals();
  const groundMat = new THREE.MeshStandardMaterial({ color: css("--bg-2") || "#efece3", roughness: 1 });
  const groundMesh = new THREE.Mesh(ground, groundMat);
  groundMesh.rotation.x = -Math.PI / 2;
  scene.add(groundMesh);
  const grid = new THREE.GridHelper(40, 40, css("--line") || "#ddd", css("--line") || "#ddd");
  grid.position.y = 0.02; grid.material.transparent = true; grid.material.opacity = 0.8;
  scene.add(grid);

  const colors = { approachable: css("--easy"), moderate: css("--mid"), hard: css("--hard"), unknown: css("--faint") };
  const peaks = [];
  const n = hills.length;
  hills.forEach((h, i) => {
    const angle = (i / Math.max(n, 1)) * Math.PI * 2 + 0.4;
    const radius = n <= 1 ? 0 : 4.2 + (i % 2) * 1.4;
    const height = 0.8 + headroom(h) * 4.2;
    const mat = new THREE.MeshStandardMaterial({ color: colors[h.difficulty] || colors.unknown, roughness: 0.75, flatShading: true });
    const mesh = new THREE.Mesh(peakGeometry(height, h.hill), mat);
    const width = 1.1 + Math.min(1.2, Math.log10(Math.max(h.rows.train, 10)) / 4);
    mesh.scale.set(width, 1, width);
    mesh.position.set(Math.cos(angle) * radius, 0, Math.sin(angle) * radius);
    mesh.userData = { hill: h, baseColor: mat.color.clone() };
    scene.add(mesh);
    // snow cap marks the reference score; a ring at the base marks the baseline
    const cap = new THREE.Mesh(new THREE.ConeGeometry(0.28 * width, 0.5, 7), new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.6, flatShading: true }));
    cap.position.set(mesh.position.x, height - 0.22, mesh.position.z);
    scene.add(cap);
    const label = labelSprite(h.title.replace(/[_-]+/g, " ").slice(0, 22), css("--fg") || "#222");
    label.position.set(mesh.position.x, height + 0.45, mesh.position.z);
    scene.add(label);
    peaks.push({ mesh, cap, label });
  });

  const ray = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  let hovered = null;
  function pick(ev) {
    const r = renderer.domElement.getBoundingClientRect();
    mouse.x = ((ev.clientX - r.left) / r.width) * 2 - 1;
    mouse.y = -((ev.clientY - r.top) / r.height) * 2 + 1;
    ray.setFromCamera(mouse, camera);
    const hit = ray.intersectObjects(peaks.map((p) => p.mesh))[0];
    return hit ? hit.object : null;
  }
  renderer.domElement.addEventListener("pointermove", (ev) => {
    const obj = pick(ev);
    if (hovered && hovered !== obj) hovered.material.emissive.setHex(0x000000);
    hovered = obj;
    if (obj) {
      obj.material.emissive.setHex(0x222222);
      const h = obj.userData.hill;
      const r = container.getBoundingClientRect();
      tip.style.display = "block";
      tip.style.left = `${ev.clientX - r.left}px`;
      tip.style.top = `${ev.clientY - r.top}px`;
      tip.innerHTML = `<b>${h.title}</b><br>${h.metric === "rmse" ? "RMSE" : "Balanced accuracy"}: ${fmt(h.baseline, h)} → ${fmt(h.reference, h)}<br><span class="muted">${h.difficulty} · click to open</span>`;
      renderer.domElement.style.cursor = "pointer";
    } else {
      tip.style.display = "none";
      renderer.domElement.style.cursor = "grab";
    }
  });
  renderer.domElement.addEventListener("pointerleave", () => { tip.style.display = "none"; });
  let downAt = null;
  renderer.domElement.addEventListener("pointerdown", (ev) => { downAt = [ev.clientX, ev.clientY]; controls.autoRotate = false; });
  renderer.domElement.addEventListener("pointerup", (ev) => {
    if (!downAt) return;
    const moved = Math.hypot(ev.clientX - downAt[0], ev.clientY - downAt[1]);
    downAt = null;
    if (moved > 5) return;
    const obj = pick(ev);
    if (obj) onPick(obj.userData.hill);
  });

  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = "100%"; renderer.domElement.style.height = "100%";
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
  }
  const ro = new ResizeObserver(resize);
  ro.observe(container);
  resize();

  let raf = 0, alive = true;
  (function loop() {
    if (!alive) return;
    controls.update();
    renderer.render(scene, camera);
    raf = requestAnimationFrame(loop);
  })();

  return {
    highlight(visibleNames) {
      for (const p of peaks) {
        const on = visibleNames.has(p.mesh.userData.hill.hill);
        p.mesh.material.transparent = !on; p.mesh.material.opacity = on ? 1 : 0.18;
        p.cap.visible = on; p.label.visible = on;
      }
    },
    dispose() {
      alive = false; cancelAnimationFrame(raf); ro.disconnect(); controls.dispose(); renderer.dispose();
    },
  };
}
