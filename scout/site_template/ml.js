// No-code modelling for the Predict page. Runs as a module Web Worker; the same functions are
// exported so they can be tested outside a browser. A random forest of histogram-split
// decision trees, written for clarity over speed; fine up to ~20,000 rows x ~60 columns.

const MAX_CATS = 50;
const BINS = 32;

// ---------- small utilities ----------
function rng(seed) {
  let s = seed >>> 0 || 1;
  return () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
}
const isBlank = (v) => v === undefined || v === null || String(v).trim() === "";
const toNum = (v) => (isBlank(v) ? NaN : Number(String(v).replace(/[$,%\s]/g, "")));
const median = (a) => { const s = a.filter((x) => !Number.isNaN(x)).sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : 0; };

// ---------- preparing the table ----------
export function describeColumns(header, rows, targetIdx) {
  const n = rows.length;
  return header.map((name, j) => {
    const vals = rows.map((r) => r[j]);
    const filled = vals.filter((v) => !isBlank(v));
    const nums = filled.map(toNum);
    const numeric = filled.length > 0 && nums.filter((x) => !Number.isNaN(x)).length >= 0.95 * filled.length;
    const uniq = new Set(filled.map((v) => String(v).trim())).size;
    let drop = "";
    if (j !== targetIdx) {
      if (uniq <= 1) drop = "the same on every row";
      else if (/(^|_|\b)(id|uuid|guid|key)$|^id[_ ]|(^|_)(phone|email|name)$/i.test(name) && uniq > 0.9 * filled.length) drop = "looks like an id or name";
      else if (!numeric && uniq > 0.5 * filled.length && uniq > 30) drop = "different on almost every row (free text or an id)";
      else if (filled.length < 0.3 * n) drop = "mostly empty";
    }
    return { name, index: j, numeric, unique: uniq, filled: filled.length, drop };
  });
}

export function detectTask(rows, targetIdx) {
  const vals = rows.map((r) => r[targetIdx]).filter((v) => !isBlank(v));
  const nums = vals.map(toNum);
  const allNum = vals.length && nums.every((x) => !Number.isNaN(x));
  const uniq = new Set(vals.map((v) => String(v).trim())).size;
  if (allNum && uniq > 20) return "number";
  return uniq === 2 ? "yesno" : "category";
}

function encode(header, rows, targetIdx, task, skip) {
  const cols = describeColumns(header, rows, targetIdx);
  const labelled = rows.filter((r) => !isBlank(r[targetIdx]));
  const unlabelled = rows.filter((r) => isBlank(r[targetIdx]));
  let classes = null, y;
  if (task === "number") {
    y = Float64Array.from(labelled, (r) => toNum(r[targetIdx]));
  } else {
    const counts = new Map();
    labelled.forEach((r) => { const v = String(r[targetIdx]).trim(); counts.set(v, (counts.get(v) || 0) + 1); });
    classes = [...counts.entries()].sort((a, b) => b[1] - a[1]).map((e) => e[0]);
    if (classes.length > 30) throw new Error(`"${header[targetIdx]}" has ${classes.length} different values. Pick a column with fewer choices, or one that is a number.`);
    const ix = new Map(classes.map((c, i) => [c, i]));
    y = Int32Array.from(labelled, (r) => ix.get(String(r[targetIdx]).trim()));
  }
  const feats = cols.filter((c) => c.index !== targetIdx && !c.drop && !skip.has(c.name));
  if (!feats.length) throw new Error("No usable columns are left to predict from.");
  const specs = feats.map((c) => {
    if (c.numeric) {
      const v = labelled.map((r) => toNum(r[c.index])).filter((x) => !Number.isNaN(x)).sort((a, b) => a - b);
      const edges = [];
      for (let b = 1; b < BINS; b++) { const e = v[Math.floor((b / BINS) * (v.length - 1))]; if (!edges.length || e > edges[edges.length - 1]) edges.push(e); }
      return { name: c.name, index: c.index, kind: "num", edges, median: median(v), min: v[0], max: v[v.length - 1] };
    }
    const counts = new Map();
    labelled.forEach((r) => { const v = isBlank(r[c.index]) ? "" : String(r[c.index]).trim(); if (v) counts.set(v, (counts.get(v) || 0) + 1); });
    const cats = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, MAX_CATS).map((e) => e[0]);
    // order categories by their average outcome so threshold splits group similar ones
    const target = task === "number" ? (i) => y[i] : (i) => (y[i] === (classes.length === 2 ? 1 : 0) ? 1 : 0);
    const sum = new Map(), cnt = new Map();
    labelled.forEach((r, i) => { const v = String(r[c.index] ?? "").trim(); sum.set(v, (sum.get(v) || 0) + target(i)); cnt.set(v, (cnt.get(v) || 0) + 1); });
    const order = [...cats].sort((a, b) => sum.get(a) / cnt.get(a) - sum.get(b) / cnt.get(b));
    return { name: c.name, index: c.index, kind: "cat", cats: order, code: new Map(order.map((v, i) => [v, i + 1])), mode: cats[0] };
  });
  const binOf = (spec, raw) => {
    if (spec.kind === "num") {
      const x = toNum(raw);
      if (Number.isNaN(x)) return 0;
      let lo = 0, hi = spec.edges.length;
      while (lo < hi) { const mid = (lo + hi) >> 1; if (x <= spec.edges[mid]) hi = mid; else lo = mid + 1; }
      return lo + 1;
    }
    if (isBlank(raw)) return 0;
    return spec.code.get(String(raw).trim()) || spec.cats.length + 1; // unseen -> "other"
  };
  const X = specs.map((s) => Uint8Array.from(labelled, (r) => binOf(s, r[s.index])));
  return { cols, specs, X, y, classes, labelled, unlabelled, binOf };
}

// ---------- trees ----------
function buildTree(X, y, rows, K, opts, rand) {
  const nF = X.length, mtry = Math.max(1, Math.round(opts.regression ? nF / 3 : Math.sqrt(nF)));
  const nodes = [];
  const leaf = (R) => {
    if (opts.regression) { let s = 0; for (const i of R) s += y[i]; return { v: s / R.length }; }
    const p = new Float64Array(K); for (const i of R) p[y[i]]++; for (let k = 0; k < K; k++) p[k] /= R.length; return { p };
  };
  const grow = (R, depth) => {
    const id = nodes.length; nodes.push(null);
    if (depth >= opts.maxDepth || R.length < 2 * opts.minLeaf) { nodes[id] = leaf(R); return id; }
    let best = { gain: 1e-9, f: -1, t: -1 };
    const feats = new Set(); while (feats.size < mtry) feats.add(Math.floor(rand() * nF));
    for (const f of feats) {
      const col = X[f], nb = BINS + MAX_CATS + 3;
      if (opts.regression) {
        const c = new Float64Array(nb), s = new Float64Array(nb), q = new Float64Array(nb);
        let S = 0, Q = 0;
        for (const i of R) { const b = col[i], v = y[i]; c[b]++; s[b] += v; q[b] += v * v; S += v; Q += v * v; }
        const N = R.length, parent = Q - (S * S) / N;
        let cl = 0, sl = 0, ql = 0;
        for (let b = 0; b < nb - 1; b++) {
          if (!c[b]) continue; cl += c[b]; sl += s[b]; ql += q[b];
          const cr = N - cl; if (cl < opts.minLeaf || cr < opts.minLeaf) continue;
          const sr = S - sl, qr = Q - ql;
          const gain = parent - (ql - (sl * sl) / cl) - (qr - (sr * sr) / cr);
          if (gain > best.gain) best = { gain, f, t: b };
        }
      } else {
        const h = new Float64Array(nb * K), tot = new Float64Array(K);
        for (const i of R) { h[col[i] * K + y[i]]++; tot[y[i]]++; }
        const N = R.length; let g0 = 1; for (let k = 0; k < K; k++) g0 -= (tot[k] / N) ** 2;
        const left = new Float64Array(K); let cl = 0;
        for (let b = 0; b < nb - 1; b++) {
          let any = 0; for (let k = 0; k < K; k++) { const v = h[b * K + k]; left[k] += v; any += v; }
          if (!any) continue; cl += any; const cr = N - cl;
          if (cl < opts.minLeaf || cr < opts.minLeaf) continue;
          let gl = 1, gr = 1; for (let k = 0; k < K; k++) { gl -= (left[k] / cl) ** 2; gr -= ((tot[k] - left[k]) / cr) ** 2; }
          const gain = g0 - (cl / N) * gl - (cr / N) * gr;
          if (gain > best.gain) best = { gain, f, t: b };
        }
      }
    }
    if (best.f < 0) { nodes[id] = leaf(R); return id; }
    const L = [], Rr = []; const col = X[best.f];
    for (const i of R) (col[i] <= best.t ? L : Rr).push(i);
    nodes[id] = { f: best.f, t: best.t, l: -1, r: -1 };
    nodes[id].l = grow(L, depth + 1); nodes[id].r = grow(Rr, depth + 1);
    return id;
  };
  grow(rows, 0);
  return nodes;
}

function treePredict(nodes, getBin) {
  let n = nodes[0];
  while (n.f !== undefined) n = nodes[getBin(n.f) <= n.t ? n.l : n.r];
  return n;
}

function forestPredict(model, getBin) {
  if (model.regression) { let s = 0; for (const t of model.trees) s += treePredict(t, getBin).v; return s / model.trees.length; }
  const p = new Float64Array(model.K);
  for (const t of model.trees) { const lp = treePredict(t, getBin).p; for (let k = 0; k < model.K; k++) p[k] += lp[k]; }
  for (let k = 0; k < model.K; k++) p[k] /= model.trees.length;
  return p;
}

// ---------- training and explaining ----------
export function train({ header, rows, targetIdx, task, skip = [], nTrees = 40, seed = 7 }) {
  const t0 = Date.now();
  const enc = encode(header, rows, targetIdx, task, new Set(skip));
  const { X, y, classes, specs } = enc;
  const n = y.length;
  if (n < 50) throw new Error(`Only ${n} rows have a value in "${header[targetIdx]}". At least 50 are needed.`);
  const regression = task === "number", K = regression ? 1 : classes.length;
  const rand = rng(seed);
  const order = Array.from({ length: n }, (_, i) => i);
  for (let i = n - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [order[i], order[j]] = [order[j], order[i]]; }
  const nTest = Math.max(20, Math.round(n * 0.2));
  const test = order.slice(0, nTest), trainRows = order.slice(nTest);
  const opts = { regression, maxDepth: 12, minLeaf: Math.max(2, Math.round(trainRows.length / 2000)) };
  const fit = (rowsIdx) => {
    const trees = [];
    for (let t = 0; t < nTrees; t++) {
      const boot = Array.from({ length: rowsIdx.length }, () => rowsIdx[Math.floor(rand() * rowsIdx.length)]);
      trees.push(buildTree(X, y, boot, K, opts, rand));
    }
    return { trees, regression, K };
  };
  const model = fit(trainRows);
  const predIdx = (i, perm) => forestPredict(model, (f) => X[f][perm && perm.f === f ? perm.map.get(i) : i]);

  // ---- how good, in plain numbers
  const evalSet = (perm) => {
    if (regression) {
      let ae = 0; for (const i of test) ae += Math.abs(predIdx(i, perm) - y[i]); return { mae: ae / test.length };
    }
    let pTrue = 0, correct = 0; const hit = new Float64Array(K), tot = new Float64Array(K);
    for (const i of test) { const p = predIdx(i, perm); let a = 0; for (let k = 1; k < K; k++) if (p[k] > p[a]) a = k; pTrue += p[y[i]]; tot[y[i]]++; if (a === y[i]) { correct++; hit[y[i]]++; } }
    let bacc = 0, seen = 0; for (let k = 0; k < K; k++) if (tot[k]) { bacc += hit[k] / tot[k]; seen++; }
    return { acc: correct / test.length, bacc: bacc / seen, pTrue: pTrue / test.length };
  };
  const base = evalSet(null);
  const result = { task, target: header[targetIdx], classes, n, nTest, seconds: 0 };
  if (regression) {
    let m = 0; for (const i of trainRows) m += y[i]; m /= trainRows.length;
    let bae = 0; for (const i of test) bae += Math.abs(m - y[i]);
    result.mae = base.mae; result.baselineMae = bae / test.length; result.mean = m;
    result.skill = Math.max(0, 1 - result.mae / result.baselineMae);
  } else {
    const counts = new Float64Array(K); for (const i of trainRows) counts[y[i]]++;
    let maj = 0; for (let k = 1; k < K; k++) if (counts[k] > counts[maj]) maj = k;
    let bc = 0; for (const i of test) if (y[i] === maj) bc++;
    Object.assign(result, { acc: base.acc, bacc: base.bacc, baselineAcc: bc / test.length, majority: classes[maj] });
    result.skill = Math.max(0, (base.bacc - 1 / K) / (1 - 1 / K));
    if (K === 2) {
      // "who to act on first": share of the rarer outcome found in the top 20% by predicted chance
      const pos = counts[1] <= counts[0] ? 1 : 0;
      const scored = test.map((i) => [predIdx(i)[pos], y[i] === pos ? 1 : 0]).sort((a, b) => b[0] - a[0]);
      const top = scored.slice(0, Math.max(1, Math.round(scored.length * 0.2)));
      const allPos = scored.reduce((s, r) => s + r[1], 0);
      result.positive = classes[pos];
      result.positiveShare = allPos / scored.length;
      result.top20Capture = allPos ? top.reduce((s, r) => s + r[1], 0) / allPos : 0;
      // AUC: how often a real "positive" is ranked above a real "negative" (0.5 = coin flip)
      const asc = [...scored].sort((a, b) => a[0] - b[0]);
      let rankSum = 0, nPos = 0;
      for (let i = 0; i < asc.length;) {
        let j = i; while (j < asc.length && asc[j][0] === asc[i][0]) j++;
        const avgRank = (i + j + 1) / 2;
        for (let k = i; k < j; k++) if (asc[k][1]) { rankSum += avgRank; nPos++; }
        i = j;
      }
      const nNeg = asc.length - nPos;
      result.auc = nPos && nNeg ? (rankSum - (nPos * (nPos + 1)) / 2) / (nPos * nNeg) : 0.5;
      result.skill = Math.max(0, 2 * result.auc - 1);
    }
  }
  result.grade = result.skill >= 0.6 ? "strong" : result.skill >= 0.35 ? "useful" : result.skill >= 0.12 ? "weak" : "none";

  // ---- what matters: permutation importance on the held-out rows
  const imp = specs.map((s, f) => {
    const shuffled = test.map((i) => i); for (let i = shuffled.length - 1; i > 0; i--) { const j = Math.floor(rand() * (i + 1)); [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]; }
    const r = evalSet({ f, map: new Map(test.map((i, k) => [i, shuffled[k]])) });
    const drop = regression ? r.mae - base.mae : base.pTrue - r.pTrue;
    return { name: s.name, drop };
  });
  const totalDrop = imp.reduce((a, b) => a + Math.max(0, b.drop), 0) || 1;
  const posK = regression ? 0 : (result.positive !== undefined ? classes.indexOf(result.positive) : 0);
  const score = (i) => { const p = predIdx(i); return regression ? p : p[posK]; };
  const scores = new Map(test.map((i) => [i, score(i)]));
  result.factors = imp.filter((d) => d.drop > 0).sort((a, b) => b.drop - a.drop).slice(0, 8).map((d) => {
    const f = specs.findIndex((s) => s.name === d.name), s = specs[f];
    const out = { name: d.name, share: Math.max(0, d.drop) / totalDrop, kind: s.kind };
    if (s.kind === "num") {
      const vals = test.map((i) => [toNum(enc.labelled[i][s.index]), scores.get(i)]).filter((v) => !Number.isNaN(v[0]));
      const med = median(vals.map((v) => v[0]));
      const hi = vals.filter((v) => v[0] > med), lo = vals.filter((v) => v[0] <= med);
      const avg = (a) => a.reduce((t, v) => t + v[1], 0) / Math.max(1, a.length);
      Object.assign(out, { median: med, high: avg(hi), low: avg(lo) });
    } else {
      const g = new Map();
      for (const i of test) { const v = String(enc.labelled[i][s.index] ?? "").trim() || "(blank)"; const e = g.get(v) || [0, 0]; e[0] += scores.get(i); e[1]++; g.set(v, e); }
      const groups = [...g.entries()].filter((e) => e[1][1] >= Math.max(5, test.length * 0.02)).map((e) => ({ value: e[0], avg: e[1][0] / e[1][1], n: e[1][1] })).sort((a, b) => b.avg - a.avg);
      Object.assign(out, { top: groups[0], bottom: groups[groups.length - 1] });
    }
    return out;
  });

  // ---- what-if controls: the top factors, starting at typical values
  result.controls = specs.map((s) => s.kind === "num"
    ? { name: s.name, kind: "num", value: s.median, min: s.min, max: s.max }
    : { name: s.name, kind: "cat", value: s.mode, options: [...s.cats].sort() });
  result.used = specs.map((s) => s.name);
  result.dropped = enc.cols.filter((c) => c.drop).map((c) => ({ name: c.name, why: c.drop }));
  result.unlabelled = enc.unlabelled.length;
  result.seconds = (Date.now() - t0) / 1000;

  STATE = { model, enc, header, targetIdx, regression, classes, posK, baseRate: result.positiveShare || 0 };
  return result;
}

let STATE = null;

export function predictRaw(records) {
  // records: [{column: value}] for any subset of columns; missing ones use typical values
  if (!STATE) throw new Error("Train a model first.");
  const { model, enc, regression, classes, posK } = STATE;
  return records.map((rec) => {
    const bins = enc.specs.map((s) => {
      const raw = rec[s.name];
      return enc.binOf(s, isBlank(raw) ? (s.kind === "num" ? s.median : s.mode) : raw);
    });
    const p = forestPredict(model, (f) => bins[f]);
    if (regression) return { value: p };
    let a = 0; for (let k = 1; k < p.length; k++) if (p[k] > p[a]) a = k;
    const out = { label: classes[a], chance: p[posK], probs: Array.from(p) };
    if (STATE.baseRate) out.risk = p[posK] >= 2 * STATE.baseRate ? "High" : p[posK] >= STATE.baseRate ? "Medium" : "Low";
    return out;
  });
}

export function predictTable(header, rows) {
  const recs = rows.map((r) => Object.fromEntries(header.map((h, j) => [h, r[j]])));
  return predictRaw(recs);
}

export function predictUnlabelled() {
  if (!STATE) throw new Error("Train a model first.");
  return { header: STATE.header, rows: STATE.enc.unlabelled, preds: predictTable(STATE.header, STATE.enc.unlabelled) };
}

// ---------- worker wiring ----------
if (typeof WorkerGlobalScope !== "undefined" && typeof self !== "undefined" && self instanceof WorkerGlobalScope) {
  self.onmessage = (e) => {
    const { id, type, payload } = e.data;
    try {
      let out;
      if (type === "train") out = train(payload);
      else if (type === "predict") out = predictRaw(payload.records);
      else if (type === "predictTable") out = predictTable(payload.header, payload.rows);
      else if (type === "predictUnlabelled") out = predictUnlabelled();
      self.postMessage({ id, ok: true, out });
    } catch (err) {
      self.postMessage({ id, ok: false, error: String((err && err.message) || err) });
    }
  };
}
