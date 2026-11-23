// Hill Scout site: Explore (3D hill range + filters), Hill detail, Bring your data, Console.
// All numbers come from data/site.json, which `scout site` exports from the scout's own records.
import { mountScene, headroom } from "./scene.js";
import { renderPredict } from "./predict.js";

const $ = (sel, el = document) => el.querySelector(sel);
const app = $("#app");
let DATA = null;
let scene = null;
const state = { q: "", task: "all", diff: "all", sort: "newest", run: null, consoleTab: "picks", hillTab: "gates" };

// ---------- helpers ----------
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function fmt(v, h) {
  if (v == null || Number.isNaN(v)) return "–";
  if (h && h.metric === "balanced_accuracy") return v.toFixed(3);
  const a = Math.abs(v);
  return a >= 1000 ? Math.round(v).toLocaleString("en-US") : a >= 10 ? v.toFixed(1) : v.toFixed(3);
}
const metricName = (h) => (h.metric === "balanced_accuracy" ? "Balanced accuracy" : "RMSE");
const better = (h) => (h.direction === "max" ? "higher is better" : "lower is better");
const pretty = (t) => t.replace(/[_-]+/g, " ");
function track(name, data) { try { window.umami && window.umami.track(name, data); } catch (e) { /* analytics is optional */ } }
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); setTimeout(() => t.classList.remove("show"), 1800); }
async function copy(text, what) {
  try { await navigator.clipboard.writeText(text); toast(`${what} copied`); }
  catch (e) { toast("Copy failed; select the text instead"); }
}
function bestClimb(h) {
  const vals = (h.climb_history || []).flatMap((c) => c.attempts).map((a) => a.value).filter((v) => v != null);
  if (!vals.length) return null;
  return h.direction === "max" ? Math.max(...vals) : Math.min(...vals);
}
// position on a 0..1 "progress" axis where right is better
function progress(v, h) {
  if (v == null) return null;
  return h.direction === "max" ? Math.max(0, Math.min(1, v)) : Math.max(0, Math.min(1, 1 - v / h.baseline));
}

// ---------- theme ----------
function applyTheme(t) {
  if (t === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  $("#theme").textContent = { auto: "Theme: auto", light: "Theme: light", dark: "Theme: dark" }[t];
}
let theme = "auto";
try { theme = localStorage.getItem("hs-theme") || "auto"; } catch (e) { /* private mode */ }
applyTheme(theme);
$("#theme").addEventListener("click", () => {
  theme = { auto: "light", light: "dark", dark: "auto" }[theme];
  try { localStorage.setItem("hs-theme", theme); } catch (e) { /* ignore */ }
  applyTheme(theme);
  route();
});

// ---------- router ----------
function route() {
  if (scene) { scene.dispose(); scene = null; }
  const parts = (location.hash.replace(/^#\/?/, "") || "explore").split("/");
  const page = parts[0];
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.route === page || (page === "hill" && a.dataset.route === "explore")));
  if (page === "hill") renderHill(decodeURIComponent(parts[1] || ""));
  else if (page === "predict") renderPredict(app, { $, esc, parseCSV, track, toast });
  else if (page === "bring") renderBring();
  else if (page === "console") renderConsole();
  else renderExplore();
  window.scrollTo({ top: 0 });
}
addEventListener("hashchange", route);

// ---------- Explore ----------
function visibleHills() {
  const q = state.q.trim().toLowerCase();
  let hs = DATA.hills.filter((h) =>
    (state.task === "all" || h.task_type === state.task) &&
    (state.diff === "all" || h.difficulty === state.diff) &&
    (!q || [h.title, h.hill, h.subtitle, h.task, ...h.columns.map((c) => c.name)].join(" ").toLowerCase().includes(q)));
  const by = {
    newest: (a, b) => String(b.shipped_at).localeCompare(String(a.shipped_at)),
    headroom: (a, b) => headroom(b) - headroom(a),
    climbed: (a, b) => b.climbs - a.climbs,
    title: (a, b) => a.title.localeCompare(b.title),
  }[state.sort];
  return hs.sort(by);
}

function ladderBar(h) {
  const b = progress(h.baseline, h), r = progress(h.reference, h), best = progress(bestClimb(h), h);
  const lo = Math.min(b, r), hi = Math.max(b, r);
  return `<div class="ladder-bar" aria-hidden="true"><div class="track"></div>
    <div class="fill" style="left:${lo * 100}%;width:${(hi - lo) * 100}%"></div>
    <div class="pt base" style="left:${b * 100}%" title="baseline"></div>
    <div class="pt ref" style="left:${r * 100}%" title="reference"></div>
    ${best != null && best !== b ? `<div class="pt best" style="left:${best * 100}%" title="best climb"></div>` : ""}</div>
    <div class="ladder-key"><span>baseline ${fmt(h.baseline, h)}</span><span>reference ${fmt(h.reference, h)}</span></div>`;
}

function card(h) {
  return `<a class="card" href="#/hill/${encodeURIComponent(h.hill)}" data-umami-event="hill_open" data-umami-event-hill="${esc(h.hill)}">
    <div class="meta"><span class="tag ${h.difficulty}">${h.difficulty}</span><span>${h.task_type}</span><span>·</span><span>${h.rows.train.toLocaleString()} train rows</span><span>·</span><span>${h.n_features} features</span></div>
    <h3>${esc(pretty(h.title))}</h3>
    <p>${esc(h.subtitle)}</p>
    <div class="small muted">${metricName(h)}, ${better(h)}</div>
    ${ladderBar(h)}
    <div class="meta"><span>${h.climbs} climb${h.climbs === 1 ? "" : "s"}</span><span>·</span><span>${esc(h.source.license || "")}</span></div>
  </a>`;
}

function renderExplore() {
  const t = DATA.totals;
  app.innerHTML = `
  <section class="hero">
    <div>
      <h1>Fresh prediction tasks for AI agents, built every day.</h1>
      <p class="lede">An autonomous scout finds new public datasets, turns each into a scored task with hidden test labels, and ships only the ones that pass eight quality checks. Pick one and climb it.</p>
      <div class="doors">
        <a class="door" href="#/predict" data-umami-event="door_predict"><b>I have a spreadsheet</b><span>Predict what happens next, no code. See what drives it and download predictions.</span></a>
        <a class="door" href="#hills" id="browse" data-umami-event="door_hills"><b>I build AI agents</b><span>Pick a verified task below and climb it on AutoLab.</span></a>
      </div>
      <div class="stats">
        <div class="stat"><b>${t.shipped}</b><span>hills passed every check</span></div>
        <div class="stat"><b>${t.attempted}</b><span>datasets attempted</span></div>
        <div class="stat"><b>${t.rejected}</b><span>rejected by the checks</span></div>
        <div class="stat"><b>${t.climbs}</b><span>climbs so far</span></div>
      </div>
    </div>
    <div class="scene-wrap" id="scene-wrap">
      <div id="scene"></div><div class="scene-tip" id="scene-tip"></div>
      <div class="scene-legend"><span><i style="background:var(--easy)"></i>approachable</span><span><i style="background:var(--mid)"></i>moderate</span><span><i style="background:var(--hard)"></i>hard</span><span>peak height = room to improve</span></div>
      <div class="scene-hint">drag to orbit · click a peak</div>
    </div>
  </section>
  <div class="filters" id="hills">
    <input type="search" id="q" placeholder="Search hills, columns, topics" value="${esc(state.q)}" aria-label="Search hills">
    <div class="seg" id="task">${["all", "classification", "regression"].map((v) => `<button data-v="${v}" class="${state.task === v ? "on" : ""}">${v === "all" ? "All tasks" : v}</button>`).join("")}</div>
    <div class="seg" id="diff">${["all", "approachable", "moderate", "hard"].map((v) => `<button data-v="${v}" class="${state.diff === v ? "on" : ""}">${v === "all" ? "Any difficulty" : v}</button>`).join("")}</div>
    <select id="sort" aria-label="Sort hills">
      ${[["newest", "Newest"], ["headroom", "Most room to improve"], ["climbed", "Most climbed"], ["title", "A to Z"]].map(([v, l]) => `<option value="${v}" ${state.sort === v ? "selected" : ""}>${l}</option>`).join("")}
    </select>
  </div>
  <div class="cards" id="cards"></div>`;

  $("#browse").addEventListener("click", (e) => { e.preventDefault(); $("#hills").scrollIntoView({ behavior: "smooth" }); });
  const draw = () => {
    const hs = visibleHills();
    $("#cards").innerHTML = hs.length ? hs.map(card).join("") : `<div class="empty">No hill matches. Clear a filter, or <a href="#/bring">bring your own data</a>.</div>`;
    scene && scene.highlight(new Set(hs.map((h) => h.hill)));
  };
  $("#q").addEventListener("input", (e) => { state.q = e.target.value; draw(); });
  $("#q").addEventListener("change", () => track("search", { q: state.q.slice(0, 40) }));
  for (const [id, key] of [["task", "task"], ["diff", "diff"]]) {
    $(`#${id}`).addEventListener("click", (e) => {
      const b = e.target.closest("button"); if (!b) return;
      state[key] = b.dataset.v;
      $(`#${id}`).querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      track("filter", { [key]: b.dataset.v });
      draw();
    });
  }
  $("#sort").addEventListener("change", (e) => { state.sort = e.target.value; track("sort", { by: state.sort }); draw(); });
  scene = mountScene($("#scene"), $("#scene-tip"), DATA.hills, {
    fmt,
    onPick: (h) => { track("hill_open_3d", { hill: h.hill }); location.hash = `#/hill/${encodeURIComponent(h.hill)}`; },
  });
  draw();
}

// ---------- Hill detail ----------
function ladderChart(h) {
  const pts = [{ label: "Baseline", value: h.baseline, kind: "base" }, { label: "Reference", value: h.reference, kind: "ref" }];
  for (const c of h.climb_history || []) for (const a of c.attempts) pts.push({ label: a.title, value: a.value, kind: a.value == null ? "queued" : "climb", status: a.status, id: a.id });
  const W = 560, H = 230, L = 52, R = 10, T = 18, B = 46;
  const vals = pts.map((p) => p.value).filter((v) => v != null);
  // "better is up": for RMSE the axis is flipped so improvement always rises
  let lo, hi;
  if (h.direction === "max") { lo = Math.max(0, Math.min(...vals) - 0.08); hi = Math.min(1, Math.max(...vals) + 0.06); }
  else { lo = Math.max(0, Math.min(...vals) * 0.85); hi = Math.max(...vals) * 1.06; }
  const y = (v) => h.direction === "max" ? T + (1 - (v - lo) / (hi - lo)) * (H - T - B) : T + ((v - lo) / (hi - lo)) * (H - T - B);
  const PAD = 40, x = (i) => L + PAD + (pts.length === 1 ? 0.5 : i / (pts.length - 1)) * (W - L - R - 2 * PAD);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => lo + f * (hi - lo));
  const dots = pts.map((p, i) => {
    const cx = x(i);
    if (p.value == null) return `<g><circle cx="${cx}" cy="${H - B - 4}" r="6" fill="none" stroke="var(--faint)" stroke-dasharray="2 2"/><text x="${cx}" y="${H - B - 14}" text-anchor="middle">queued</text></g>`;
    const col = { base: "var(--faint)", ref: "var(--accent)", climb: "var(--mid)" }[p.kind];
    return `<g><circle cx="${cx}" cy="${y(p.value)}" r="7" fill="${col}" stroke="var(--panel)" stroke-width="2"><title>${esc(p.label)}: ${fmt(p.value, h)}</title></circle>
      <text x="${cx}" y="${y(p.value) - 13}" text-anchor="middle" style="fill:var(--fg);font-weight:600">${fmt(p.value, h)}</text></g>`;
  }).join("");
  const labels = pts.map((p, i) => `<text x="${x(i)}" y="${H - B + 18}" text-anchor="middle">${esc(p.kind === "base" ? "baseline" : p.kind === "ref" ? "reference" : `climb ${p.id || ""}`)}</text>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Score ladder for ${esc(h.title)}">
    ${ticks.map((v) => `<line class="axis" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${fmt(v, h)}</text>`).join("")}
    <line x1="${L}" x2="${W - R}" y1="${y(h.reference)}" y2="${y(h.reference)}" stroke="var(--accent)" stroke-dasharray="5 4" opacity=".6"/>
    <line x1="${L}" x2="${W - R}" y1="${y(h.baseline)}" y2="${y(h.baseline)}" stroke="var(--faint)" stroke-dasharray="5 4" opacity=".6"/>
    ${dots}${labels}
    <text x="${L}" y="${H - 6}">${metricName(h)}, ${better(h)}; better is always up</text>
  </svg>`;
}

function targetChart(h) {
  const ts = h.target_summary || {};
  if (ts.classes) {
    return `<div class="funnel">${ts.classes.map((c) => `<div class="step"><span>class ${esc(c.label)}</span><div class="bar" style="width:${(c.share * 100).toFixed(1)}%"></div><span class="n">${(c.share * 100).toFixed(1)}%</span></div>`).join("")}</div>`;
  }
  if (ts.hist) {
    const W = 520, H = 120, m = Math.max(...ts.hist, 1), bw = W / ts.hist.length;
    return `<svg viewBox="0 0 ${W} ${H + 20}" width="100%" role="img" aria-label="Distribution of the target">
      ${ts.hist.map((c, i) => `<rect x="${i * bw + 1}" y="${H - (c / m) * H}" width="${bw - 2}" height="${(c / m) * H}" rx="2" fill="var(--accent)" opacity=".8"><title>${c} rows</title></rect>`).join("")}
      <text x="0" y="${H + 16}">${fmt(ts.min, h)}</text><text x="${W}" y="${H + 16}" text-anchor="end">${fmt(ts.max, h)}</text></svg>`;
  }
  return "";
}

function renderHill(name) {
  const h = DATA.hills.find((x) => x.hill === name);
  if (!h) { app.innerHTML = `<div class="empty">No hill called ${esc(name)}. <a href="#/explore">Back to Explore</a></div>`; return; }
  track("hill_view", { hill: h.hill });
  const passed = h.gates.filter((g) => g.passed === true).length;
  const evalCmd = `hills eval ./my-submission -H ${h.hill}`;
  app.innerHTML = `
  <div class="crumbs"><a href="#/explore">Explore</a> / ${esc(h.hill)}</div>
  <div class="meta" style="margin-bottom:8px"><span class="tag ${h.difficulty}" title="${esc(h.difficulty_why)}">${h.difficulty}</span><span class="tag plain">${h.task_type}</span><span class="tag plain">${passed}/8 checks passed</span><span class="tag plain">${esc(h.source.license)}</span></div>
  <h1>${esc(pretty(h.title))}</h1>
  <p class="lede">${esc(h.subtitle)}</p>
  <div class="row-btns">
    ${h.url ? `<a class="btn primary" href="${esc(h.url)}" target="_blank" rel="noopener" data-umami-event="hill_click" data-umami-event-hill="${esc(h.hill)}">Climb this hill on AutoLab</a>` : ""}
    <button class="btn" id="copy-starter">Copy starter predict.py</button>
    <button class="btn" id="copy-cmd">Copy eval command</button>
  </div>
  ${h.url && !h.public ? `<p class="small muted" style="margin-top:8px">This hill is private on AutoLab for now; the button works for the owner and anyone it is shared with.</p>` : ""}
  ${h.public ? `<p class="small muted" style="margin-top:8px">Public on AutoLab: anyone can open it, read the task and start a climb.</p>` : ""}

  <div class="grid2 section">
    <div class="panel"><h2>Score ladder</h2>${ladderChart(h)}
      <p class="small muted">Grey is the majority-class or mean baseline, green is a default gradient-boosting model, amber dots are climb attempts on AutoLab.</p></div>
    <div class="panel"><h2>At a glance</h2>
      <dl class="kv">
        <dt>Task</dt><dd>${h.task_type}, predict <code>target</code></dd>
        <dt>Metric</dt><dd>${metricName(h)} (${better(h)})</dd>
        <dt>Baseline</dt><dd>${fmt(h.baseline, h)}</dd>
        <dt>Reference</dt><dd>${fmt(h.reference, h)}</dd>
        <dt>Best climb</dt><dd>${bestClimb(h) != null && bestClimb(h) !== h.baseline ? fmt(bestClimb(h), h) : "none above baseline yet"}</dd>
        <dt>Rows</dt><dd>${h.rows.train.toLocaleString()} train · ${h.rows.valid.toLocaleString()} valid · ${h.rows.test.toLocaleString()} test (labels hidden)</dd>
        <dt>Features</dt><dd>${h.n_features}</dd>
        <dt>Time limit</dt><dd>${h.time_limit_s} s per run</dd>
        <dt>Difficulty</dt><dd>${h.difficulty}: ${esc(h.difficulty_why)}</dd>
      </dl>
      ${(h.climb_history || []).map((c) => `<p class="small muted" style="margin-top:12px">Climb <a href="${esc(c.url)}" target="_blank" rel="noopener">${esc(c.climb)}</a>: ${esc(c.status)}.</p>`).join("")}
    </div>
  </div>

  <div class="section panel">
    <div class="tabs" id="htabs">${[["gates", "Quality checks"], ["data", "Data"], ["submit", "How to submit"], ["source", "Source"]].map(([v, l]) => `<button data-v="${v}" class="${state.hillTab === v ? "on" : ""}">${l}</button>`).join("")}</div>
    <div id="hbody"></div>
  </div>`;

  const bodies = {
    gates: () => `<ul class="gates">${h.gates.map((g) => `<li><span class="mark ${g.passed === true ? "pass" : g.passed === false ? "fail" : "skip"}">${g.passed === true ? "✓" : g.passed === false ? "✕" : "·"}</span>
        <div><b>${esc(g.name)}</b><span>${esc(g.rule)}</span><span>Measured: ${esc(g.detail)}</span></div></li>`).join("")}</ul>`,
    data: () => `
      <div class="grid2"><div><h3>Target</h3>${targetChart(h)}</div>
      <div><h3>Columns</h3><div class="table-wrap" style="max-height:240px"><table><thead><tr><th>column</th><th>type</th><th>distinct</th><th>missing</th></tr></thead>
        <tbody>${h.columns.map((c) => `<tr><td class="${c.is_target ? "target" : ""}">${esc(c.name)}</td><td>${c.type}</td><td>${c.unique}</td><td>${c.missing}</td></tr>`).join("")}</tbody></table></div></div></div>
      <h3 style="margin-top:18px">First rows of train.csv</h3>
      <div class="table-wrap"><table><thead><tr>${Object.keys(h.preview[0] || {}).map((k) => `<th class="${k === "target" ? "target" : ""}">${esc(k)}</th>`).join("")}</tr></thead>
        <tbody>${h.preview.map((r) => `<tr>${Object.entries(r).map(([k, v]) => `<td class="${k === "target" ? "target" : ""}">${esc(v ?? "")}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <p class="small muted">The highlighted column is what you predict. The test rows' labels are never shown.</p>`,
    submit: () => `
      <p>A submission is a folder with <code>predict.py</code>. The evaluator runs it in a fresh folder:</p>
      <div class="copy-wrap"><pre class="code">python predict.py --train data/train.csv --valid data/valid.csv \\
                  --test data/test_features.csv --out predictions.csv</pre></div>
      <p>Write <code>predictions.csv</code> with the columns <code>id,prediction</code>, one row per test id. Missing rows, unknown ids or a run over ${h.time_limit_s} seconds fail with a reason. Score it locally with <code>${esc(evalCmd)}</code>.</p>
      <div class="grid2"><div><h3>Reference model (the score to beat)</h3><div class="copy-wrap"><button class="btn" data-copy="starter">Copy</button><pre class="code">${esc(h.starter)}</pre></div></div>
      <div><h3>Baseline</h3><div class="copy-wrap"><button class="btn" data-copy="baseline">Copy</button><pre class="code">${esc(h.baseline_code)}</pre></div></div></div>`,
    source: () => `<dl class="kv">
        <dt>Dataset</dt><dd><a href="${esc(h.source.url)}" target="_blank" rel="noopener">${esc(h.source.title)}</a></dd>
        <dt>License</dt><dd>${esc(h.source.license)}</dd>
        <dt>Built by</dt><dd>scout run ${esc(h.run_id)}</dd>
        <dt>Bucket</dt><dd><code>${esc(h.bucket)}</code></dd>
        <dt>Preparation</dt><dd>${h.notes.length ? h.notes.map(esc).join("; ") : "no changes"}</dd>
      </dl><p class="small muted" style="margin-top:12px">${esc(h.task)}</p>`,
  };
  const drawTab = () => {
    $("#hbody").innerHTML = bodies[state.hillTab]();
    $("#hbody").querySelectorAll("[data-copy]").forEach((b) => b.addEventListener("click", () => {
      copy(b.dataset.copy === "starter" ? h.starter : h.baseline_code, "Code"); track("copy_code", { hill: h.hill, which: b.dataset.copy });
    }));
  };
  $("#htabs").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    state.hillTab = b.dataset.v;
    $("#htabs").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    drawTab();
  });
  $("#copy-starter").addEventListener("click", () => { copy(h.starter, "Starter predict.py"); track("copy_starter", { hill: h.hill }); });
  $("#copy-cmd").addEventListener("click", () => { copy(evalCmd, "Command"); track("copy_eval_cmd", { hill: h.hill }); });
  drawTab();
}

// ---------- Bring your data ----------
function parseCSV(text, maxRows = 20000) {
  const rows = []; let row = [], field = "", q = false, i = 0;
  while (i < text.length && rows.length <= maxRows) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; }
      else field += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(field); field = ""; if (row.length > 1 || row[0] !== "") rows.push(row); row = [];
    } else field += c;
    i++;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  const header = rows.shift() || [];
  const total = (text.match(/\n/g) || []).length - (text.endsWith("\n") ? 1 : 0);
  return { header, rows, total: Math.max(total, rows.length) };
}

function analyse(csv, targetIdx, taskOverride) {
  const { header, rows } = csv;
  const n = rows.length;
  const col = (j) => rows.map((r) => r[j]);
  const isNum = (vals) => { const f = vals.filter((v) => v !== "" && v != null); return f.length > 0 && f.every((v) => !Number.isNaN(Number(v))); };
  const y = col(targetIdx);
  const yFilled = y.filter((v) => v !== "" && v != null);
  const yNum = isNum(yFilled);
  const yUnique = new Set(yFilled).size;
  const integerish = yNum && yFilled.every((v) => Number.isInteger(Number(v)));
  const task = taskOverride || (yNum && !(integerish && yUnique <= 10) && yUnique > 20 ? "regression" : "classification");
  const checks = [];
  checks.push(n >= 500 ? ["ok", `${csv.total.toLocaleString()} rows; the scout needs at least 500 with a target`] : ["bad", `Only ${n} rows. The scout needs at least 500 with a target.`]);
  const missingY = n - yFilled.length;
  checks.push(missingY === 0 ? ["ok", "Every row has a target value"] : ["warn", `${missingY} rows have no target; they will be dropped`]);
  let baseline = null, baseNote = "";
  if (task === "classification") {
    const counts = {}; yFilled.forEach((v) => { counts[v] = (counts[v] || 0) + 1; });
    const k = Object.keys(counts).length;
    const rare = Object.values(counts).filter((c) => c < 10).length;
    checks.push(k >= 2 && k <= 50 ? ["ok", `${k} classes`] : ["bad", k < 2 ? "The target has a single class" : `${k} classes is more than the 50 the scout supports`]);
    if (rare) checks.push(["warn", `${rare} class(es) have fewer than 10 rows and will be dropped`]);
    baseline = k ? 1 / k : null; baseNote = "balanced accuracy of always predicting the most common class";
  } else {
    const v = yFilled.map(Number), mean = v.reduce((a, b) => a + b, 0) / v.length;
    baseline = Math.sqrt(v.reduce((a, b) => a + (b - mean) ** 2, 0) / v.length);
    baseNote = "RMSE of always predicting the mean";
    checks.push(yUnique > 10 ? ["ok", "The target is a continuous number"] : ["bad", "The target has too few distinct values for regression"]);
  }
  // leak and id checks, one column at a time
  const flagged = [];
  header.forEach((name, j) => {
    if (j === targetIdx) return;
    const vals = col(j); const uniq = new Set(vals).size;
    if (uniq === n && n > 50) { flagged.push(["warn", `<b>${esc(name)}</b> is different on every row, so it looks like an id. Ids carry no signal; check it isn't derived from the target.`]); return; }
    if (vals.every((v, i) => v === y[i])) { flagged.push(["bad", `<b>${esc(name)}</b> is identical to the target, a direct leak`]); return; }
    if (task === "classification" && uniq <= 200) {
      const by = {}; vals.forEach((v, i) => { (by[v] ||= {})[y[i]] = ((by[v] || {})[y[i]] || 0) + 1; });
      const correct = Object.values(by).reduce((a, m) => a + Math.max(...Object.values(m)), 0);
      if (correct / n >= 0.98 && uniq < n * 0.5) flagged.push(["bad", `<b>${esc(name)}</b> alone predicts the target ${(100 * correct / n).toFixed(1)}% of the time, a likely leak`]);
    }
    if (task === "regression" && isNum(vals)) {
      const a = vals.map(Number), b = y.map(Number), ma = a.reduce((s, v) => s + v, 0) / n, mb = b.reduce((s, v) => s + v, 0) / n;
      let num = 0, da = 0, db = 0; for (let i = 0; i < n; i++) { num += (a[i] - ma) * (b[i] - mb); da += (a[i] - ma) ** 2; db += (b[i] - mb) ** 2; }
      const r = num / Math.sqrt(da * db || 1);
      if (Math.abs(r) > 0.995) flagged.push(["bad", `<b>${esc(name)}</b> has correlation ${r.toFixed(3)} with the target, a likely leak`]);
    }
  });
  if (!flagged.length) checks.push(["ok", "No single column gives the answer away"]);
  const total = csv.total, test = Math.round(total * 0.2), valid = Math.round(total * 0.2);
  return { task, checks: checks.concat(flagged), baseline, baseNote, split: { train: total - test - valid, valid, test },
    types: header.map((name, j) => ({ name, type: isNum(col(j)) ? "number" : "category", unique: new Set(col(j)).size })) };
}

function renderBring() {
  app.innerHTML = `
  <h1>Turn your data into a private hill.</h1>
  <p class="lede">Import a dataset from Kaggle, OpenML or any CSV link, or drop your own file. Pick the column to predict, see the checks the scout runs and the task that would be built, then ask us to build it as a private hill or a private competition.</p>
  <div class="grid3 section">
    <div class="panel"><h3>1. Bring a dataset</h3><p class="small muted">Paste a Kaggle, OpenML or CSV link, or drop a file. Dropped files stay in your browser.</p></div>
    <div class="panel"><h3>2. See the hill</h3><p class="small muted">Split sizes, metric, baseline and the same leak and size checks the scout runs.</p></div>
    <div class="panel"><h3>3. Request it</h3><p class="small muted">We build it as a private hill on AutoLab. Agents climb it; your test labels never leave the evaluator.</p></div>
  </div>
  <div class="section panel" id="importer">
    <h2>Import from the web</h2>
    <form id="imp" class="imp-row">
      <input id="imp-ref" type="text" inputmode="url" autocomplete="off" spellcheck="false" aria-label="Dataset to import"
        placeholder="kaggle.com/datasets/owner/name, owner/name, an OpenML id, or https://…/data.csv">
      <button class="btn primary" id="imp-go" type="submit">Import</button>
    </form>
    <p class="small muted" style="margin:10px 0 0">Try:
      <button class="chip" data-ref="blastchar/telco-customer-churn">Kaggle: telco churn</button>
      <button class="chip" data-ref="https://www.kaggle.com/datasets/uciml/iris">Kaggle: iris</button>
      <button class="chip" data-ref="openml:537">OpenML 537: houses</button>
      <button class="chip" data-ref="https://github.com/mwaskom/seaborn-data/blob/master/penguins.csv">GitHub CSV: penguins</button>
    </p>
    <div id="imp-status" style="margin-top:10px"></div>
    <p class="small muted" style="margin:8px 0 0">Public datasets only, up to 60 MB. Our server downloads the file to preview it and keeps nothing. Zip files with several tables let you pick one.</p>
  </div>
  <p class="muted small" style="text-align:center;margin:14px 0">or use a file on your computer</p>
  <div class="drop" id="drop">
    <p><b>Drop a CSV here</b> or <label class="btn" style="display:inline-flex">choose a file<input type="file" id="file" accept=".csv,text/csv"></label></p>
    <p class="small muted">No file handy? <button class="btn" id="sample">Try a sample: credit applications</button></p>
  </div>
  <div id="result"></div>`;
  const drop = $("#drop");
  const load = (text, name) => { track("byod_load", { sample: name === "sample" }); showAnalysis(parseCSV(text), name); };
  $("#file").addEventListener("change", (e) => { const f = e.target.files[0]; if (f) f.text().then((t) => load(t, f.name)); });
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) f.text().then((t) => load(t, f.name)); });
  $("#sample").addEventListener("click", () => fetch("data/sample_credit.csv").then((r) => r.text()).then((t) => load(t, "sample")));
  const go = (ref, file = "") => importRef(ref, file);
  $("#imp").addEventListener("submit", (e) => { e.preventDefault(); go($("#imp-ref").value); });
  $("#importer").querySelectorAll(".chip").forEach((b) => b.addEventListener("click", () => { $("#imp-ref").value = b.dataset.ref; go(b.dataset.ref); }));
}

async function importRef(ref, file = "") {
  ref = (ref || "").trim();
  const status = $("#imp-status"), btn = $("#imp-go");
  if (!ref) { status.innerHTML = `<div class="notice err">Paste a Kaggle dataset, an OpenML id, or a link to a CSV.</div>`; return; }
  btn.disabled = true;
  status.innerHTML = `<div class="notice"><span class="spin"></span> Downloading and reading ${esc(ref.slice(0, 90))}… large datasets take up to a minute.</div>`;
  try {
    const r = await fetch(`api/import?ref=${encodeURIComponent(ref)}${file ? `&file=${encodeURIComponent(file)}` : ""}`);
    const j = await r.json().catch(() => ({ error: `server said ${r.status}` }));
    if (!r.ok) throw new Error(j.error || `server said ${r.status}`);
    const csv = parseCSV(j.csv, 20000);
    csv.total = j.total_rows;
    status.innerHTML = "";
    track("byod_import", { kind: j.source.kind });
    showAnalysis(csv, j.file, j);
  } catch (err) {
    status.innerHTML = `<div class="notice err">${esc(err.message)}</div>`;
  } finally { btn.disabled = false; }
}

function sourcePanel(meta) {
  if (!meta) return "";
  const s = meta.source;
  const kind = { kaggle: "Kaggle", openml: "OpenML", url: "Web link" }[s.kind] || s.kind;
  const files = meta.files.length > 1
    ? `<label class="small muted">Table <select id="filesel">${meta.files.map((f) => `<option value="${esc(f.name)}" ${f.name === meta.file ? "selected" : ""}>${esc(f.name)}${f.bytes ? ` (${(f.bytes / 1e6).toFixed(1)} MB)` : ""}</option>`).join("")}</select></label>` : "";
  const lic = `${s.license ? esc(s.license) : "not stated"} <span style="color:${s.open_license ? "var(--pass)" : "var(--mid)"}">(${esc(s.license_note)})</span>`;
  return `<div class="notice" style="margin-bottom:12px"><b>${kind}:</b> <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>
    ${s.subtitle ? `<span class="muted"> · ${esc(s.subtitle)}</span>` : ""}<br>
    Licence: ${lic} · ${meta.total_rows.toLocaleString()}${meta.total_is_lower_bound ? "+" : ""} rows${meta.rows_sent < meta.total_rows ? `, checks use the first ${meta.rows_sent.toLocaleString()}` : ""}
    ${meta.suggested_target ? `<br>Suggested target <b>${esc(meta.suggested_target)}</b>: ${esc(meta.target_reason)}` : ""}
    ${files ? `<div style="margin-top:8px">${files}</div>` : ""}</div>`;
}

function showAnalysis(csv, name, meta = null) {
  if (!csv.header.length) { $("#result").innerHTML = `<div class="notice err section">That file has no header row.</div>`; return; }
  const suggested = meta && meta.suggested_target ? csv.header.indexOf(meta.suggested_target) : -1;
  let targetIdx = suggested >= 0 ? suggested : csv.header.length - 1, task = "";
  const draw = () => {
    const a = analyse(csv, targetIdx, task);
    const fake = { metric: a.task === "classification" ? "balanced_accuracy" : "rmse" };
    const ok = !a.checks.some((c) => c[0] === "bad");
    $("#result").innerHTML = `
    <div class="grid2 section">
      <div class="panel">
        <h2>${esc(name === "sample" ? "credit_applications.csv (sample)" : name)}</h2>
        ${sourcePanel(meta)}
        <div class="row-btns" style="align-items:center;margin-bottom:12px">
          <label class="small muted">Predict
            <select id="target">${csv.header.map((h, j) => `<option value="${j}" ${j === targetIdx ? "selected" : ""}>${esc(h)}</option>`).join("")}</select></label>
          <label class="small muted">as
            <select id="tasksel"><option value="">auto (${a.task})</option><option value="classification" ${task === "classification" ? "selected" : ""}>classification</option><option value="regression" ${task === "regression" ? "selected" : ""}>regression</option></select></label>
        </div>
        <dl class="kv">
          <dt>Task</dt><dd>${a.task}</dd>
          <dt>Metric</dt><dd>${a.task === "classification" ? "balanced accuracy, higher is better" : "RMSE, lower is better"}</dd>
          <dt>Split</dt><dd>${a.split.train.toLocaleString()} train · ${a.split.valid.toLocaleString()} valid · ${a.split.test.toLocaleString()} test, labels hidden</dd>
          <dt>Baseline</dt><dd>${fmt(a.baseline, fake)} <span class="muted small">(${a.baseNote})</span></dd>
          <dt>Reference</dt><dd class="muted">measured when we build it (a default gradient-boosting model)</dd>
        </dl>
        <h3 style="margin-top:16px">Checks</h3>
        <ul class="checks">${a.checks.map(([lvl, msg]) => `<li><span class="dot ${lvl}"></span><span>${msg}</span></li>`).join("")}</ul>
        <p class="notice ${ok ? "ok" : ""}" style="margin-top:14px">${ok ? "This looks buildable. The full eight checks run when we build it, including the reference model and the speed check." : "Fix the red items, or pick another target column."}</p>
      </div>
      <div class="panel">${requestForm(a, name)}</div>
    </div>
    <div class="section panel"><h3>Preview</h3><div class="table-wrap"><table><thead><tr>${csv.header.map((h, j) => `<th class="${j === targetIdx ? "target" : ""}">${esc(h)}</th>`).join("")}</tr></thead>
      <tbody>${csv.rows.slice(0, 15).map((r) => `<tr>${r.map((v, j) => `<td class="${j === targetIdx ? "target" : ""}">${esc(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>`;
    $("#target").addEventListener("change", (e) => { targetIdx = Number(e.target.value); draw(); });
    $("#tasksel").addEventListener("change", (e) => { task = e.target.value; draw(); });
    wireForm(a, csv, targetIdx, name, meta);
    const fs = $("#filesel");
    if (fs) fs.addEventListener("change", (e) => importRef(meta.source.ref, e.target.value));
  };
  draw();
  $("#result").scrollIntoView({ behavior: "smooth", block: "start" });
}

function requestForm() {
  return `<h2>Request this hill</h2>
  <form id="req" novalidate>
    <div class="field"><label for="f-name">Your name</label><input id="f-name" name="name" required autocomplete="name"></div>
    <div class="field"><label for="f-email">Work email</label><input id="f-email" name="email" type="email" required autocomplete="email"></div>
    <div class="field"><label for="f-company">Company</label><input id="f-company" name="company" autocomplete="organization"></div>
    <div class="field"><label for="f-kind">What you want</label><select id="f-kind" name="kind">
      <option value="private_hill">A private hill for my team's agents</option>
      <option value="private_competition">A private competition with a deadline</option>
      <option value="eval_pack">A weekly pack of fresh evaluation tasks</option></select></div>
    <div class="field"><label for="f-deadline">Deadline (optional)</label><input id="f-deadline" name="deadline" type="date"></div>
    <div class="field"><label for="f-notes">Anything else</label><textarea id="f-notes" name="notes" placeholder="What the number stands for, who would climb it, data size"></textarea></div>
    <label class="check-row"><input type="checkbox" id="f-share"> Include the column names and the checks above with my request. Off by default; your rows are never sent.</label>
    <p class="small muted">We store your request (name, email, company, notes, and the column names only if you tick the box above) in our database, and use it only to reply. A person reads every request before anything is built. Ask us to delete it at any time.</p>
    <button class="btn primary" type="submit" id="f-send">Send request</button>
    <div id="f-status" style="margin-top:10px"></div>
  </form>`;
}

function wireForm(a, csv, targetIdx, name, meta) {
  $("#req").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target, status = $("#f-status");
    const body = { name: f.name.value.trim(), email: f.email.value.trim(), company: f.company.value.trim(), kind: f.kind.value,
      deadline: f.deadline.value, notes: f.notes.value.trim().slice(0, 2000), task: a.task, rows: csv.total };
    if (meta) { body.source_ref = meta.source.ref; body.source_url = meta.source.url; body.source_license = meta.source.license; body.file = meta.file; body.target = csv.header[targetIdx]; }
    if (!body.name || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(body.email)) { status.innerHTML = `<div class="notice err">Add your name and a valid email.</div>`; return; }
    if ($("#f-share").checked) { body.columns = csv.header.slice(0, 200); body.target = csv.header[targetIdx]; body.checks = a.checks.map((c) => c[1].replace(/<[^>]+>/g, "")); if (!meta) body.file = name === "sample" ? "sample" : "user file"; }
    $("#f-send").disabled = true;
    try {
      const r = await fetch("api/request", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const j = await r.json().catch(() => ({}));
      if (j.paused) { status.innerHTML = `<div class="notice">Requests are paused while we set up storage, so nothing was saved. Please check back soon.</div>`; return; }
      if (!r.ok) throw new Error(j.error || `server said ${r.status}`);
      status.innerHTML = `<div class="notice ok">Request received (reference ${esc(j.id)}). We'll reply to ${esc(body.email)}.</div>`;
      track("request_sent", { kind: body.kind, task: body.task });
      f.reset();
    } catch (err) {
      status.innerHTML = `<div class="notice err">We couldn't send that: ${esc(err.message)}. Please try again in a minute.</div>`;
    } finally { $("#f-send").disabled = false; }
  });
}

// ---------- Console ----------
function renderConsole() {
  const t = DATA.totals, runs = DATA.runs;
  if (!state.run && runs.length) state.run = runs[runs.length - 1].run_id;
  const shortlisted = runs.reduce((a, r) => a + r.picks.length, 0);
  const built = runs.reduce((a, r) => a + r.built, 0), gated = runs.reduce((a, r) => a + r.gated, 0);
  const steps = [["In scope (per run)", t.discovered], ["Shortlisted", shortlisted], ["Attempted", t.attempted], ["Got to a build", built], ["Built and gated", gated], ["Shipped", t.shipped]];
  const max = Math.max(...steps.map((s) => s[1]), 1);
  const egbe = DATA.spend.egbe_usd, cap = DATA.spend.egbe_cap_usd;
  app.innerHTML = `
  <h1>Scout console</h1>
  <p class="lede">What the autonomous scout did, run by run: what it picked and why, what each check measured, what it learned, and what it spent.</p>
  <div class="stats" style="grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">
    <div class="stat"><b>${runs.length}</b><span>runs</span></div>
    <div class="stat"><b>${t.attempted}</b><span>candidates attempted</span></div>
    <div class="stat"><b>${t.shipped}</b><span>shipped</span></div>
    <div class="stat"><b>${t.rejected}</b><span>rejected</span></div>
    <div class="stat"><b>${t.public}</b><span>public on AutoLab</span></div>
    <div class="stat"><b>${t.climbs}</b><span>climbs</span></div>
  </div>
  <div class="grid2 section">
    <div class="panel"><h2>Funnel, all runs</h2><div class="funnel">${steps.map(([l, n]) => `<div class="step"><span>${l}</span><div class="bar" style="width:${(n / max) * 100}%"></div><span class="n">${n}</span></div>`).join("")}</div>
      <p class="small muted" style="margin-top:10px">"In scope" is the per-run pool after the row, feature and task-type filters.</p></div>
    <div class="panel"><h2>Spend and limits</h2>
      <p class="small">Egbe today: $${egbe.toFixed(2)} of the $${cap} cap</p><div class="meter"><i style="width:${Math.min(100, (egbe / cap) * 100)}%"></i></div>
      <p class="small" style="margin-top:14px">AutoLab climb churn-climb-1: reached its $${DATA.spend.autolab_climb_cap_usd} cap</p><div class="meter full"><i style="width:100%"></i></div>
      <h3 style="margin-top:18px">What it learned</h3><ul class="lessons small">${DATA.lessons.map((l) => `<li>${esc(l)}</li>`).join("")}</ul></div>
  </div>
  <div class="section panel">
    <div class="row-btns" style="justify-content:space-between;align-items:center;margin-bottom:10px">
      <h2 style="margin:0">Runs</h2>
      <div class="seg" id="runsel">${runs.map((r) => `<button data-v="${r.run_id}" class="${state.run === r.run_id ? "on" : ""}">${r.run_id}</button>`).join("")}</div>
    </div>
    <div class="tabs" id="ctabs">${[["picks", "Picks and outcomes"], ["buckets", "What the bandit learned"], ["sources", "Sources"]].map(([v, l]) => `<button data-v="${v}" class="${state.consoleTab === v ? "on" : ""}">${l}</button>`).join("")}</div>
    <div id="cbody"></div>
  </div>`;
  const draw = () => {
    const r = runs.find((x) => x.run_id === state.run);
    if (!r) { $("#cbody").innerHTML = `<div class="empty">No runs yet.</div>`; return; }
    const head = `<p class="small muted">${r.pool_in_scope} in scope, ${r.pool_unseen} not seen before · ${r.attempted} attempted · ${r.gated} gated · <b>${r.shipped} shipped</b> · started ${esc(r.started)}</p>`;
    if (state.consoleTab === "picks") {
      $("#cbody").innerHTML = head + `<div class="table-wrap" style="max-height:none"><table class="picks"><thead><tr><th>#</th><th>candidate</th><th>bucket</th><th>rate before</th><th>draw</th><th>outcome</th><th>why</th></tr></thead><tbody>
        ${r.picks.map((p) => `<tr><td>${p.rank}</td><td>${p.hill && p.outcome === "shipped" ? `<a href="#/hill/${encodeURIComponent(p.hill)}">${esc(pretty(p.title))}</a>` : esc(pretty(p.title))}<div class="small muted">${esc(p.key)}</div></td>
          <td><code class="small">${esc(p.bucket)}</code></td><td>${p.rate.toFixed(2)}</td><td>${p.sample.toFixed(3)}</td>
          <td><span class="pill ${p.outcome || "none"}">${p.outcome || "not reached"}</span></td><td class="why">${esc(p.outcome === "shipped" ? "passed all 8 checks" : p.why)}</td></tr>`).join("")}
        </tbody></table></div>`;
    } else if (state.consoleTab === "buckets") {
      const names = [...new Set([...Object.keys(r.buckets_before), ...Object.keys(r.buckets_after)])].sort();
      const W = 640, rowH = 30, H = names.length * rowH + 30, L = 270, R = 40, x = (v) => L + v * (W - L - R);
      $("#cbody").innerHTML = head + `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Bucket success rates before and after this run">
        ${[0, 0.25, 0.5, 0.75, 1].map((v) => `<line class="axis" x1="${x(v)}" x2="${x(v)}" y1="0" y2="${H - 22}"/><text x="${x(v)}" y="${H - 6}" text-anchor="middle">${v.toFixed(2)}</text>`).join("")}
        ${names.map((b, i) => {
          const before = (r.buckets_before[b] || {}).rate ?? 0.5, after = (r.buckets_after[b] || {}).rate ?? before, yy = i * rowH + 16;
          const col = after > before ? "var(--pass)" : after < before ? "var(--fail)" : "var(--faint)";
          return `<text x="${L - 10}" y="${yy + 4}" text-anchor="end" style="font-family:var(--mono);font-size:10.5px">${esc(b)}</text>
            <line x1="${x(before)}" x2="${x(after)}" y1="${yy}" y2="${yy}" stroke="${col}" stroke-width="3"/>
            <circle cx="${x(before)}" cy="${yy}" r="5" fill="var(--faint)"><title>before ${before.toFixed(2)}</title></circle>
            <circle cx="${x(after)}" cy="${yy}" r="6" fill="${col}"><title>after ${after.toFixed(2)}</title></circle>`;
        }).join("")}</svg>
        <p class="small muted">Each row is a kind of dataset (source, task, size, feature count). Grey is its success rate going into the run, the coloured dot is after. The next run draws its picks from these rates.</p>`;
    } else {
      $("#cbody").innerHTML = head + `<table><thead><tr><th>source</th><th>status</th><th>discovered</th><th>in scope</th></tr></thead><tbody>
        ${Object.entries(r.sources).map(([n, s]) => `<tr><td>${esc(n)}</td><td class="why">${s.available ? "used" : "skipped: " + esc(s.why)}</td><td>${s.discovered ?? "–"}</td><td>${s.in_scope ?? "–"}</td></tr>`).join("")}</tbody></table>`;
    }
  };
  $("#runsel").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; state.run = b.dataset.v; $("#runsel").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); draw(); });
  $("#ctabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (!b) return; state.consoleTab = b.dataset.v; $("#ctabs").querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); draw(); });
  draw();
}

// ---------- boot ----------
fetch("data/site.json").then((r) => r.json()).then((d) => {
  DATA = d;
  $("#foot").innerHTML = `Built from the scout's own records on ${esc(d.generated.replace("T", " ").replace("+00:00", " UTC"))}. ${d.totals.public} of ${d.totals.shipped} hills are public on AutoLab. Analytics: page views and clicks, no session recording.`;
  route();
}).catch(() => { app.innerHTML = `<div class="empty">Couldn't load the catalogue data. Refresh to try again.</div>`; });
