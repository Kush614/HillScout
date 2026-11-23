// Predict: the no-code page. Bring a spreadsheet, say what to predict, get plain answers,
// try what-ifs, and download predictions. All modelling runs in the visitor's browser (ml.js).

let ctx = null; // helpers from app.js: { $, esc, parseCSV, track, toast }
let worker = null, seq = 0;
const pending = new Map();
let DATA = null; // { header, rows, name, meta }
let RESULT = null;

function call(type, payload) {
  if (!worker) {
    worker = new Worker(new URL("./ml.js", import.meta.url), { type: "module" });
    worker.onmessage = (e) => { const p = pending.get(e.data.id); if (!p) return; pending.delete(e.data.id); e.data.ok ? p.resolve(e.data.out) : p.reject(new Error(e.data.error)); };
    worker.onerror = (e) => { for (const p of pending.values()) p.reject(new Error(e.message || "the model crashed")); pending.clear(); worker = null; };
  }
  const id = ++seq;
  return new Promise((resolve, reject) => { pending.set(id, { resolve, reject }); worker.postMessage({ id, type, payload }); });
}

const EXAMPLES = [
  { ref: "blastchar/telco-customer-churn", q: "Which customers will leave?", src: "Telecom customers, Kaggle" },
  { ref: "adityadesai13/used-car-dataset-ford-and-mercedes", q: "What will a used car sell for?", src: "UK used cars, Kaggle" },
  { ref: "pavansubhasht/ibm-hr-analytics-attrition-dataset", q: "Which employees might quit?", src: "IBM HR, Kaggle" },
  { ref: "sample", q: "Which loan applicants are risky?", src: "Credit applications, built in" },
];

const num = (v, d = 0, name = "") => {
  if (/year|yr$/i.test(name) && Math.abs(v) >= 1000) return String(Math.round(v)); // 2017, not 2,017
  return Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : Number(v).toFixed(d);
};
const pct = (v) => (v > 0 && v < 0.005 ? "under 1%" : `${Math.round(v * 100)}%`);
const times = (a, b) => (b > 0 ? a / b : 0);

export function renderPredict(app, helpers) {
  ctx = helpers;
  const { esc } = ctx;
  app.innerHTML = `
  <h1>Predict from your spreadsheet.</h1>
  <p class="lede">No code. Bring a table, tell us what you want to predict, and see how well it can be predicted, what drives it, and predictions for new rows you can download. Everything runs in your browser.</p>
  <div class="steps" id="steps"><span class="on">1 · Your data</span><span>2 · What to predict</span><span>3 · Answers</span></div>
  <div class="section panel" id="p-data">
    <h2>Start with an example</h2>
    <div class="examples">${EXAMPLES.map((e) => `<button class="example" data-ref="${esc(e.ref)}"><b>${esc(e.q)}</b><span>${esc(e.src)}</span></button>`).join("")}</div>
    <h2 style="margin-top:22px">Or bring your own</h2>
    <div class="grid2">
      <div><label class="small muted" for="p-ref">A Kaggle dataset, an OpenML id, or a link to a CSV</label>
        <form id="p-imp" class="imp-row" style="margin-top:6px"><input id="p-ref" type="text" inputmode="url" autocomplete="off" spellcheck="false" placeholder="kaggle.com/datasets/owner/name or https://…/data.csv"><button class="btn primary" type="submit">Import</button></form></div>
      <div><span class="small muted">A file on your computer (CSV; for Excel, use File → Save as → CSV)</span>
        <div class="drop small-drop" id="p-drop" style="margin-top:6px"><label class="btn">Choose a file<input type="file" id="p-file" accept=".csv,.tsv,text/csv"></label> <span class="muted small">or drop it here</span></div></div>
    </div>
    <div id="p-status" style="margin-top:12px"></div>
  </div>
  <div id="p-target"></div>
  <div id="p-answers"></div>`;

  const status = (html) => { ctx.$("#p-status").innerHTML = html; };
  const fromText = (text, name, meta = null) => {
    const csv = ctx.parseCSV(text, 20000);
    if (!csv.header.length || !csv.rows.length) { status(`<div class="notice err">That file has no rows we could read.</div>`); return; }
    status("");
    DATA = { header: csv.header, rows: csv.rows, name, meta, total: meta ? meta.total_rows : csv.total };
    ctx.track("predict_data", { kind: meta ? meta.source.kind : name === "sample" ? "sample" : "file" });
    renderTarget(meta && meta.suggested_target);
  };
  const doImport = async (ref) => {
    if (ref === "sample") { const t = await (await fetch("data/sample_credit.csv")).text(); return fromText(t, "Credit applications (sample)"); }
    status(`<div class="notice"><span class="spin"></span> Getting ${esc(ref.slice(0, 80))}… this can take up to a minute for big datasets.</div>`);
    try {
      const r = await fetch(`api/import?ref=${encodeURIComponent(ref)}`);
      const j = await r.json().catch(() => ({ error: `server said ${r.status}` }));
      if (!r.ok) throw new Error(j.error || `server said ${r.status}`);
      fromText(j.csv, j.source.title || j.file, j);
    } catch (err) { status(`<div class="notice err">${esc(err.message)}</div>`); }
  };
  ctx.$("#p-data").querySelectorAll(".example").forEach((b) => b.addEventListener("click", () => doImport(b.dataset.ref)));
  ctx.$("#p-imp").addEventListener("submit", (e) => { e.preventDefault(); const v = ctx.$("#p-ref").value.trim(); if (v) doImport(v); });
  const readFile = (f) => {
    if (!f) return;
    if (/\.(xlsx?|numbers)$/i.test(f.name)) { status(`<div class="notice err">That's a spreadsheet file. In Excel or Google Sheets choose File → Save as / Download → CSV, then use that file.</div>`); return; }
    f.text().then((t) => fromText(t, f.name));
  };
  ctx.$("#p-file").addEventListener("change", (e) => readFile(e.target.files[0]));
  const drop = ctx.$("#p-drop");
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => readFile(e.dataTransfer.files[0]));
}

function setStep(n) {
  ctx.$("#steps").querySelectorAll("span").forEach((s, i) => s.classList.toggle("on", i === n - 1));
}

async function detect(targetIdx) {
  const { header, rows } = DATA;
  const ML = await import("./ml.js");
  return { task: ML.detectTask(rows, targetIdx), cols: ML.describeColumns(header, rows, targetIdx) };
}

async function renderTarget(suggested) {
  const { esc } = ctx;
  setStep(2);
  const { header, rows } = DATA;
  let targetIdx = suggested && header.includes(suggested) ? header.indexOf(suggested) : header.length - 1;
  const skip = new Set();
  const box = ctx.$("#p-target");
  const draw = async () => {
    const { task, cols } = await detect(targetIdx);
    const vals = rows.map((r) => r[targetIdx]).filter((v) => v !== "" && v != null);
    const uniq = [...new Set(vals.map((v) => String(v).trim()))];
    const blanks = rows.length - vals.length;
    const kind = task === "number"
      ? `a <b>number</b> (for example ${esc(vals[0])}). We'll estimate it for each row.`
      : task === "yesno" ? `a <b>yes/no</b> question: ${uniq.slice(0, 2).map((u) => `<b>${esc(u)}</b>`).join(" or ")}. We'll give each row a chance.`
      : `one of <b>${uniq.length}</b> choices (${uniq.slice(0, 4).map(esc).join(", ")}${uniq.length > 4 ? "…" : ""}). We'll pick the likeliest for each row.`;
    box.innerHTML = `
    <div class="section panel">
      <h2>What do you want to predict?</h2>
      <p class="muted small">${esc(DATA.name)} · ${DATA.total.toLocaleString()} rows · ${header.length} columns${DATA.meta && DATA.meta.source.license ? ` · licence: ${esc(DATA.meta.source.license)}` : ""}</p>
      <div class="target-pick"><select id="p-tsel" aria-label="Column to predict">${header.map((h, j) => `<option value="${j}" ${j === targetIdx ? "selected" : ""}>${esc(h)}</option>`).join("")}</select>
        <span>is ${kind}</span></div>
      ${blanks ? `<p class="notice" style="margin-top:12px">${blanks.toLocaleString()} row(s) have no value in this column. We'll learn from the others and <b>predict these for you</b>.</p>` : ""}
      <details style="margin-top:14px"><summary class="small">Columns we'll use (${cols.filter((c) => c.index !== targetIdx && !c.drop).length}) · change</summary>
        <div class="colgrid">${cols.filter((c) => c.index !== targetIdx).map((c) => `<label class="${c.drop ? "muted" : ""}"><input type="checkbox" data-col="${esc(c.name)}" ${c.drop || skip.has(c.name) ? "" : "checked"} ${c.drop ? "disabled" : ""}> ${esc(c.name)}${c.drop ? ` <span class="small">(skipped: ${esc(c.drop)})</span>` : ""}</label>`).join("")}</div>
        <p class="small muted">Untick anything you'd only know after the fact (for example "date cancelled" when predicting cancellations); it would make the answers look better than they are.</p>
      </details>
      <div class="row-btns" style="margin-top:16px"><button class="btn primary big" id="p-go">Find the answers</button></div>
    </div>`;
    ctx.$("#p-tsel").addEventListener("change", (e) => { targetIdx = Number(e.target.value); ctx.$("#p-answers").innerHTML = ""; draw(); });
    box.querySelectorAll("[data-col]").forEach((c) => c.addEventListener("change", () => { c.checked ? skip.delete(c.dataset.col) : skip.add(c.dataset.col); }));
    ctx.$("#p-go").addEventListener("click", () => runModel(targetIdx, task, [...skip]));
  };
  await draw();
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runModel(targetIdx, task, skip) {
  const { esc } = ctx;
  const out = ctx.$("#p-answers");
  out.innerHTML = `<div class="section panel"><span class="spin"></span> Learning from ${DATA.rows.length.toLocaleString()} rows… usually a few seconds.</div>`;
  out.scrollIntoView({ behavior: "smooth", block: "start" });
  ctx.$("#p-go").disabled = true;
  try {
    RESULT = await call("train", { header: DATA.header, rows: DATA.rows, targetIdx, task, skip });
    ctx.track("predict_trained", { task, grade: RESULT.grade });
    setStep(3);
    renderAnswers();
  } catch (err) {
    out.innerHTML = `<div class="section notice err">${esc(err.message)}</div>`;
  } finally { const b = ctx.$("#p-go"); if (b) b.disabled = false; }
}

function headline(r) {
  const word = { strong: "Yes, quite well", useful: "Yes, usefully", weak: "Only a little", none: "Not really" }[r.grade];
  const T = ctx.esc(r.target);
  if (r.task === "number") {
    return { word, lines: [
      `Its estimates of <b>${T}</b> are typically off by about <b>${num(r.mae)}</b>.`,
      `Guessing the average every time would be off by about <b>${num(r.baselineMae)}</b>, so this is <b>${pct(r.skill)} closer</b>.`] };
  }
  if (r.positive !== undefined) {
    const P = ctx.esc(r.positive);
    return { word, lines: [
      `<b>${pct(r.positiveShare)}</b> of rows are <b>${T} = ${P}</b>.`,
      `If you check the <b>20%</b> it rates most likely, you'll find <b>${pct(r.top20Capture)}</b> of all the ${P} cases: <b>${times(r.top20Capture, 0.2).toFixed(1)}×</b> better than picking at random.`,
      `It ranks a real ${P} above a real non-${P} <b>${pct(r.auc)}</b> of the time (a coin flip would be 50%).`] };
  }
  return { word, lines: [
    `It picks the right <b>${T}</b> <b>${Math.round(r.acc * 10)} times out of 10</b>.`,
    `Always guessing the most common answer (<b>${ctx.esc(r.majority)}</b>) is right ${Math.round(r.baselineAcc * 10)} times out of 10.`] };
}

function factorSentence(f, r) {
  const E = ctx.esc;
  const outcome = r.task === "number" ? E(r.target) : r.positive !== undefined ? `chance of ${E(r.positive)}` : "confidence";
  const show = (v) => (r.task === "number" ? num(v) : pct(v));
  if (f.kind === "num") {
    const up = f.high > f.low;
    return `Higher <b>${E(f.name)}</b> (above ${num(f.median, 1, f.name)}) → ${up ? "higher" : "lower"} ${outcome} (${show(f.low)} → ${show(f.high)}).`;
  }
  if (!f.top || !f.bottom || f.top.value === f.bottom.value) return `<b>${E(f.name)}</b> matters.`;
  return `<b>${E(f.name)}</b> = "${E(f.top.value)}" → highest ${outcome} (${show(f.top.avg)}); "${E(f.bottom.value)}" → lowest (${show(f.bottom.avg)}).`;
}

function renderAnswers() {
  const r = RESULT, E = ctx.esc;
  const h = headline(r);
  const top = r.factors.slice(0, 6);
  const controls = r.controls.filter((c) => top.some((f) => f.name === c.name)).slice(0, 6);
  ctx.$("#p-answers").innerHTML = `
  <div class="section panel answer ${r.grade}">
    <p class="kicker">Can ${E(r.target)} be predicted from the other columns?</p>
    <h2 class="verdict">${h.word}.</h2>
    <ul class="plain">${h.lines.map((l) => `<li>${l}</li>`).join("")}</ul>
    <p class="small muted">Checked on ${r.nTest.toLocaleString()} rows the model never saw while learning. Learned from ${(r.n - r.nTest).toLocaleString()} rows in ${r.seconds.toFixed(1)} s.</p>
  </div>
  <div class="grid2 section">
    <div class="panel"><h2>What matters most</h2>
      ${top.length ? `<div class="factors">${top.map((f) => `<div class="factor"><div class="fbar"><span>${E(f.name)}</span><i style="width:${Math.max(4, f.share * 100)}%"></i><b>${pct(f.share)}</b></div><p>${factorSentence(f, r)}</p></div>`).join("")}</div>`
        : `<p class="muted">No single column stands out.</p>`}
      <p class="small muted">Share = how much worse the predictions get when that column is scrambled. It shows what the model relies on, not proof of cause.</p></div>
    <div class="panel"><h2>Try it</h2><p class="small muted">Change a few values and watch the prediction. Other columns stay at typical values.</p>
      <form id="p-whatif" class="whatif">${controls.map((c) => c.kind === "num"
        ? `<label>${E(c.name)}<input type="number" step="any" name="${E(c.name)}" value="${+Number(c.value).toFixed(2)}"><span class="small muted">usually ${num(c.min, 1, c.name)} to ${num(c.max, 1, c.name)}</span></label>`
        : `<label>${E(c.name)}<select name="${E(c.name)}">${c.options.map((o) => `<option ${o === c.value ? "selected" : ""}>${E(o)}</option>`).join("")}</select></label>`).join("")}</form>
      <div class="whatif-out" id="p-wout"></div></div>
  </div>
  <div class="section panel"><h2>Get predictions you can use</h2>
    <div class="grid2">
      <div>${r.unlabelled ? `<p><b>${r.unlabelled.toLocaleString()}</b> row(s) in your file had no ${E(r.target)}. Download them with predictions filled in.</p>
        <button class="btn primary" id="p-dl-blank">Download predictions for those rows</button>` : `<p>Every row in your file already has ${E(r.target)}. To predict new ones, leave that column empty in a copy of your sheet, or upload a file of new rows.</p>`}</div>
      <div><p>Upload new rows (same columns; the ${E(r.target)} column can be missing).</p>
        <label class="btn">Choose a CSV of new rows<input type="file" id="p-new" accept=".csv,text/csv"></label>
        <div id="p-new-status" class="small" style="margin-top:8px"></div></div>
    </div>
    <p class="small muted" style="margin-top:12px">The download keeps your columns and adds ${r.task === "number" ? `<b>predicted_${E(r.target)}</b>` : r.positive !== undefined ? `<b>predicted_${E(r.target)}</b>, <b>chance_${E(r.positive)}</b> and a <b>risk</b> level (High = at least twice the usual rate). Sort by chance to see who to act on first` : `<b>predicted_${E(r.target)}</b> and its <b>confidence</b>`}.</p>
  </div>
  <div class="section panel cta"><div><h2>Want it more accurate?</h2><p class="muted">This quick model is a starting point. We can turn your data into a private challenge where AI agents compete to beat it, and keep your answers hidden from them.</p></div>
    <a class="btn primary" href="#/bring" id="p-cta">Ask AI agents to beat this</a></div>
  ${r.dropped.length ? `<p class="small muted section">Skipped columns: ${r.dropped.map((d) => `${E(d.name)} (${E(d.why)})`).join("; ")}.</p>` : ""}`;

  const form = ctx.$("#p-whatif"), outEl = ctx.$("#p-wout");
  const update = async () => {
    const rec = Object.fromEntries([...new FormData(form).entries()]);
    try {
      const [p] = await call("predict", { records: [rec] });
      outEl.innerHTML = r.task === "number"
        ? `<span class="muted">Predicted ${E(r.target)}</span><b>${num(p.value)}</b>`
        : r.positive !== undefined
          ? `<span class="muted">Chance of ${E(r.target)} = ${E(r.positive)}</span><b>${pct(p.chance)}</b><span class="risk ${p.risk}">${p.risk} risk</span>`
          : `<span class="muted">Most likely ${E(r.target)}</span><b>${E(p.label)}</b><span class="muted">${pct(Math.max(...p.probs))} sure</span>`;
    } catch (err) { outEl.innerHTML = `<span class="notice err">${E(err.message)}</span>`; }
  };
  form.addEventListener("input", () => { clearTimeout(form._t); form._t = setTimeout(update, 120); });
  update();

  const toCSV = (header, rows, preds) => {
    const cols = [...header];
    const extra = r.task === "number" ? [`predicted_${r.target}`] : r.positive !== undefined ? [`predicted_${r.target}`, `chance_${r.positive}`, "risk"] : [`predicted_${r.target}`, "confidence"];
    const q = (v) => { const s = String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
    const lines = [cols.concat(extra).map(q).join(",")];
    rows.forEach((row, i) => {
      const p = preds[i];
      const add = r.task === "number" ? [p.value.toFixed(2)] : r.positive !== undefined ? [p.label, p.chance.toFixed(4), p.risk] : [p.label, Math.max(...p.probs).toFixed(4)];
      lines.push(cols.map((_, j) => q(row[j])).concat(add.map(q)).join(","));
    });
    return lines.join("\n") + "\n";
  };
  const download = (text, name) => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/csv" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
    ctx.toast("Download started");
  };
  const fname = (suffix) => `${String(DATA.name).replace(/\.(csv|tsv)$/i, "").replace(/[^\w.-]+/g, "_").slice(0, 40)}_${suffix}.csv`;
  const blank = ctx.$("#p-dl-blank");
  if (blank) blank.addEventListener("click", async () => {
    const { header, rows, preds } = await call("predictUnlabelled", {});
    download(toCSV(header, rows, preds), fname("predictions"));
    ctx.track("predict_download", { which: "blank_rows", n: rows.length });
  });
  ctx.$("#p-new").addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    const st = ctx.$("#p-new-status");
    const csv = ctx.parseCSV(await f.text(), 200000);
    const missing = r.used.filter((c) => !csv.header.includes(c));
    if (missing.length === r.used.length) { st.innerHTML = `<span style="color:var(--fail)">None of the columns match the data you learned from.</span>`; return; }
    st.textContent = `Predicting ${csv.rows.length.toLocaleString()} rows…`;
    const preds = await call("predictTable", { header: csv.header, rows: csv.rows });
    const hdr = csv.header.filter((h) => !/^(predicted_|chance_|risk$|confidence$)/.test(h));
    const keep = hdr.map((h) => csv.header.indexOf(h));
    download(toCSV(hdr, csv.rows.map((row) => keep.map((j) => row[j])), preds), fname("new_predictions"));
    st.innerHTML = `Done: ${csv.rows.length.toLocaleString()} rows.${missing.length ? ` Missing columns filled with typical values: ${missing.slice(0, 6).map(E).join(", ")}${missing.length > 6 ? "…" : ""}.` : ""}`;
    ctx.track("predict_download", { which: "new_file", n: csv.rows.length });
  });
  ctx.$("#p-cta").addEventListener("click", () => ctx.track("predict_cta", { grade: r.grade }));
}
