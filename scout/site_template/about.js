// "How it works": a plain-language explainer. A 3D replay of the scout's real runs, then simple
// diagrams: what a hill is, the 8 checks, how the scout chooses and learns, and how Predict works.
// Every example and number comes from data/site.json.
import { STATIONS } from "./about3d.js";

const SRC = (key) => (key.startsWith("kaggle:") ? "Kaggle" : key.startsWith("url:") || key.startsWith("web:") ? "Web" : "OpenML");
const nice = (t) => String(t || "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();

// Rejection reasons, rewritten for someone who has never trained a model.
function plainWhy(p) {
  const w = p.why || "";
  if (p.stage === "enrich" || /licen[cs]e/i.test(w)) return "Its licence doesn't allow sharing it publicly, so the scout skipped it.";
  if (/not a continuous number/.test(w)) return "The \"number\" to predict was really a category code, so it wasn't a fair task.";
  if (w.startsWith("not_trivial")) return "Too easy: an ordinary model already scored a perfect 1.0, so there's nothing left to improve.";
  if (w.startsWith("no_leak")) return "One column gives the answer away, so it would test cheating, not skill.";
  if (w.startsWith("headroom")) return "Too hard to improve on: a good model barely beat guessing.";
  if (w.startsWith("deterministic")) return "Scores changed between identical runs, so results couldn't be trusted.";
  if (w.startsWith("fast")) return "Scoring took too long.";
  return w || "It failed a check.";
}
function stationOf(p) {
  if (p.outcome === "shipped") return -1;
  if (p.stage !== "gates") return 0;
  const g = (p.why || "").split(":")[0];
  const i = STATIONS.findIndex((s) => s.id === g);
  return i < 0 ? 0 : i;
}

const CHECKS = [
  ["valid", "Is it built correctly?", "Files, splits and the scoring script all pass the hills tool's own checks.", "Like checking a board game has all its pieces."],
  ["baseline_scores", "Can a lazy guess be scored?", "Always guessing the most common answer (or the average) must get a score.", "This is the bar every agent has to beat."],
  ["deterministic", "Same answer twice?", "The same model is scored twice; the two scores must agree within 0.005.", "A ruler that gives a different length each time is useless."],
  ["fast", "Quick to score?", "One scoring run must finish in under 2 minutes.", "Agents try many ideas; slow scoring wastes their time and money."],
  ["headroom", "Is there room to improve?", "A standard model must clearly beat the lazy guess.", "If nothing beats guessing, the data probably has no signal."],
  ["not_trivial", "Is it too easy?", "The standard model must not be near-perfect (under 0.98).", "A test everyone aces measures nothing."],
  ["no_leak", "Does one column give the answer away?", "No single column on its own may come close to the standard model.", "Like an exam with the answers printed in the margin."],
  ["rejects_junk", "Does it refuse broken answers?", "A submission with the wrong number of rows must fail.", "The scorer can't be fooled by garbage."],
];

// ---------- diagrams (inline SVG, themed with CSS variables) ----------
const T = (x, y, s, o = {}) => `<text x="${x}" y="${y}" font-size="${o.size || 13}" ${o.anchor ? `text-anchor="${o.anchor}"` : ""} fill="${o.fill || "var(--fg)"}" font-weight="${o.w || 500}">${s}</text>`;

function hillDiagram() {
  const row = (y, cols, last) => cols.map((c, i) => `<rect x="${30 + i * 34}" y="${y}" width="30" height="14" rx="3" fill="${i === cols.length - 1 ? last : "var(--line)"}"/>`).join("");
  const block = (y, n, last) => Array.from({ length: n }, (_, k) => row(y + k * 18, [0, 0, 0, 0, 0], last)).join("");
  return `<svg viewBox="0 0 760 300" class="diagram" role="img" aria-label="A table is split into rows to learn from, rows to check with, and test rows whose answers are hidden. An agent's predictions on the test rows are compared with the hidden answers to give a score.">
  ${T(30, 22, "1. A public table", { w: 650 })}
  ${T(30, 40, "each row is one example; the last column is the answer", { size: 11.5, fill: "var(--muted)" })}
  ${block(52, 4, "var(--accent)")}${T(205, 86, "60% learn from", { size: 12 })}
  ${block(132, 2, "var(--accent)")}${T(205, 150, "20% check with", { size: 12 })}
  ${block(176, 3, "var(--fail)")}${T(205, 204, "20% test", { size: 12 })}
  ${[0, 1, 2].map((k) => T(185, 188 + k * 18, "?", { size: 13, w: 700, fill: "var(--accent-fg)", anchor: "middle" })).join("")}
  ${T(30, 250, "test answers are locked away", { size: 11.5, fill: "var(--fail)" })}
  <path d="M300 150 H360" stroke="var(--muted)" stroke-width="2" marker-end="url(#ah)"/>
  <rect x="370" y="95" width="160" height="110" rx="14" fill="var(--accent-soft)" stroke="var(--accent)"/>
  ${T(450, 128, "2. An AI agent", { anchor: "middle", w: 650 })}
  ${T(450, 150, "learns from the rows,", { anchor: "middle", size: 11.5, fill: "var(--muted)" })}
  ${T(450, 166, "then predicts the", { anchor: "middle", size: 11.5, fill: "var(--muted)" })}
  ${T(450, 182, "test answers", { anchor: "middle", size: 11.5, fill: "var(--muted)" })}
  <path d="M540 150 H600" stroke="var(--muted)" stroke-width="2" marker-end="url(#ah)"/>
  <rect x="610" y="95" width="130" height="110" rx="14" fill="var(--panel)" stroke="var(--line)"/>
  ${T(675, 128, "3. A score", { anchor: "middle", w: 650 })}
  ${T(675, 160, "0.87", { anchor: "middle", size: 26, w: 700, fill: "var(--accent)" })}
  ${T(675, 184, "vs the hidden answers", { anchor: "middle", size: 10.5, fill: "var(--muted)" })}
  <defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="var(--muted)"/></marker></defs>
  ${T(380, 270, "Higher score = better predictions. Agents \"climb\" the hill by beating each other's scores.", { anchor: "middle", size: 12.5, fill: "var(--muted)" })}
</svg>`;
}

function loopDiagram() {
  const steps = [["Find", "lists datasets on OpenML, Kaggle and the web"], ["Choose", "picks a few, mostly from kinds that worked"], ["Build", "splits the data, hides the answers"], ["Check", "8 checks; one fail = rejected"], ["Ship", "publishes to AutoLab (a person makes it public)"], ["Learn", "remembers what passed and what agents climbed"]];
  const cx = 380, cy = 175, r = 120;
  const pos = steps.map((_, i) => { const a = -Math.PI / 2 + (i * 2 * Math.PI) / steps.length; return [cx + Math.cos(a) * r * 1.9, cy + Math.sin(a) * r]; });
  return `<svg viewBox="0 0 760 350" class="diagram" role="img" aria-label="The daily loop: find, choose, build, check, ship, learn, then back to find.">
  <ellipse cx="${cx}" cy="${cy}" rx="${r * 1.9}" ry="${r}" fill="none" stroke="var(--line)" stroke-width="3" stroke-dasharray="6 8"><animate attributeName="stroke-dashoffset" from="0" to="-140" dur="6s" repeatCount="indefinite"/></ellipse>
  ${T(cx, cy - 6, "every day,", { anchor: "middle", size: 13, fill: "var(--muted)" })}
  ${T(cx, cy + 14, "no one at the keyboard", { anchor: "middle", size: 13, fill: "var(--muted)" })}
  ${steps.map(([h, d], i) => { const [x, y] = pos[i]; return `<g><rect x="${x - 98}" y="${y - 30}" width="196" height="62" rx="12" fill="var(--panel)" stroke="${i === 3 ? "var(--fail)" : "var(--accent)"}"/>
    ${T(x, y - 10, `${i + 1}. ${h}`, { anchor: "middle", w: 650 })}${(() => { const cut = d.length > 28 ? d.lastIndexOf(" ", 28) : d.length; return T(x, y + 10, d.slice(0, cut), { anchor: "middle", size: 10.5, fill: "var(--muted)" }) + T(x, y + 23, d.slice(cut + 1), { anchor: "middle", size: 10.5, fill: "var(--muted)" }); })()}</g>`; }).join("")}
</svg>`;
}

function predictDiagram() {
  const box = (x, n, h, d, d2) => `<rect x="${x}" y="40" width="210" height="120" rx="14" fill="var(--panel)" stroke="var(--line)"/>
    <circle cx="${x + 30}" cy="72" r="15" fill="var(--accent)"/>${T(x + 30, 77, n, { anchor: "middle", w: 700, fill: "var(--accent-fg)" })}
    ${T(x + 54, 77, h, { w: 650 })}${T(x + 18, 112, d, { size: 11.5, fill: "var(--muted)" })}${T(x + 18, 130, d2, { size: 11.5, fill: "var(--muted)" })}`;
  return `<svg viewBox="0 0 760 200" class="diagram" role="img" aria-label="Predict in three steps: bring a spreadsheet, choose the column to predict, get plain answers and a downloadable file.">
    ${box(20, "1", "Bring a sheet", "a CSV, a Kaggle link,", "or one of our examples")}
    <path d="M238 100 H268" stroke="var(--muted)" stroke-width="2" marker-end="url(#ah2)"/>
    ${box(275, "2", "Pick a column", "\"Will this customer leave?\"", "\"What will this car sell for?\"")}
    <path d="M493 100 H523" stroke="var(--muted)" stroke-width="2" marker-end="url(#ah2)"/>
    ${box(530, "3", "Get answers", "how reliable, what matters,", "and a file with predictions")}
    ${T(380, 190, "It all runs inside your browser: your file is never uploaded.", { anchor: "middle", size: 12.5, fill: "var(--muted)" })}
    <defs><marker id="ah2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="var(--muted)"/></marker></defs>
  </svg>`;
}

function bucketLabel(b) {
  const [src, task, size, feat] = b.split("|");
  const s = { openml: "OpenML", kaggle: "Kaggle", manual: "OpenML (hand-picked)", web: "Web" }[src] || src;
  const t = task === "classification" ? "categories" : "numbers";
  const f = feat.replace("f<20", "under 20 columns").replace(/f(\d+)-(\d+)/, "$1–$2 columns").replace(/f>?(\d+)\+?/, "$1+ columns");
  return `${s} · ${t} · ${size} · ${f}`;
}

export function renderAbout(app, DATA, { esc, track, mountJourney }) {
  const picks = DATA.runs.flatMap((r) => r.picks.filter((p) => p.outcome).map((p) => ({ ...p, run: r.run_id })));
  const items = picks.map((p) => ({ title: nice(p.title), source: SRC(p.key), gate: stationOf(p), why: plainWhy(p), run: p.run }));
  const t = DATA.totals;
  const examples = Object.fromEntries(CHECKS.map(([id]) => [id, picks.find((p) => p.outcome === "rejected" && (p.why || "").startsWith(id))]));
  const lastRun = DATA.runs[DATA.runs.length - 1];
  const buckets = Object.entries(lastRun.buckets_after).sort((a, b) => b[1].rate - a[1].rate).slice(0, 6);

  app.innerHTML = `
  <h1>How Hill Scout works</h1>
  <p class="lede">In one sentence: a robot scout finds public spreadsheets of data, turns the good ones into fair tests for AI, throws out the bad ones, and gets better at choosing every day. No coding knowledge needed to follow along.</p>

  <div class="about-tldr">
    <div class="panel"><b>1 · It finds data</b><span>Public tables from OpenML, Kaggle and the web, like customer lists, house prices or wine ratings.</span></div>
    <div class="panel"><b>2 · It makes a fair test</b><span>It hides some answers, so an AI can be scored on how well it predicts them.</span></div>
    <div class="panel"><b>3 · It checks the test</b><span>8 checks catch tests that are broken, too easy or leaky. Only survivors are shipped.</span></div>
  </div>

  <section class="section">
    <h2>Why this exists: the problems it tackles</h2>
    <p class="muted about-p">Two groups have the same underlying need, learning from data with known answers, and today both are poorly served.</p>
    <div class="why-grid">
      <div class="panel why-col">
        <div class="why-who">For teams building AI agents</div>
        <h3>"How do we know our agent is actually getting better?"</h3>
        <div class="why-row"><div class="why-p"><b>Benchmarks go stale.</b> Once a test has been public for a while, models have often seen it during training, and everyone scores near the top. The score stops telling you anything.</div><div class="why-s">The scout builds <b>fresh tests every day</b> from newly found datasets.</div></div>
        <div class="why-row"><div class="why-p"><b>Building a test by hand is slow.</b> Cleaning data, splitting it, hiding answers, writing a scorer and checking for mistakes takes an expert days per test.</div><div class="why-s">It's <b>fully automated</b>: dataset to finished, published hill with no one at the keyboard.</div></div>
        <div class="why-row"><div class="why-p"><b>Broken tests give misleading scores.</b> A column that leaks the answer, a task that's too easy or scoring that changes between runs makes a weak agent look strong.</div><div class="why-s"><b>8 automatic checks</b> reject them. ${t.rejected} of ${t.attempted} datasets so far failed.</div></div>
        <div class="why-row"><div class="why-p"><b>Licences are a minefield.</b> Plenty of public data can't legally be shared or reused.</div><div class="why-s">Every dataset's <b>licence is checked</b> against an allow-list before anything is built.</div></div>
      </div>
      <div class="panel why-col">
        <div class="why-who">For everyday business teams</div>
        <h3>"We have the data. We just can't use it."</h3>
        <div class="why-row"><div class="why-p"><b>Data sits in spreadsheets.</b> Customer lists, sales and HR records are full of patterns that could predict who leaves, what sells or what's at risk.</div><div class="why-s"><b>Predict</b> turns any spreadsheet into forecasts in a few clicks.</div></div>
        <div class="why-row"><div class="why-p"><b>Data scientists are scarce and expensive.</b> Most ops, HR and sales teams can't get one, so decisions run on gut feel.</div><div class="why-s"><b>No code, no setup</b>: pick the column you care about and get answers.</div></div>
        <div class="why-row"><div class="why-p"><b>Black-box tools aren't trusted.</b> A number with no explanation, or a tool that oversells itself, gets ignored.</div><div class="why-s">It says <b>plainly how reliable it is</b> ("Not really" when it isn't), and which factors matter, in sentences.</div></div>
        <div class="why-row"><div class="why-p"><b>Privacy worries block adoption.</b> Uploading customer data to a new tool is often not allowed.</div><div class="why-s">The model <b>runs in your browser</b>, so the file never leaves your computer.</div></div>
      </div>
    </div>
    <div class="why-bridge panel"><b>Where they meet:</b> when a team's data matters enough, they can <a href="#/bring">request a private hill</a>, and AI agents compete to beat the model that Predict built.</div>
  </section>

  <section class="section">
    <h2>Watch the real runs</h2>
    <p class="muted about-p">Each box is one dataset the scout actually tried (${t.attempted} so far). It rides past the 9 checkpoints. If it fails one, it turns red and falls off. If it passes them all, it becomes a hill on the mountain. Drag to look around.</p>
    <div class="scene-wrap journey-wrap"><div id="journey"></div>
      <div class="journey-count" id="jcount"></div>
      <div class="scene-legend"><span><i style="background:var(--accent)"></i>OpenML</span><span><i style="background:#20beff"></i>Kaggle</span><span><i style="background:var(--fail)"></i>rejected</span><span><i style="background:var(--pass)"></i>shipped</span></div>
    </div>
    <div class="journey-bar">
      <div class="journey-now" id="jnow" aria-live="polite">Starting the replay…</div>
      <div class="seg" id="jctl"><button type="button" data-a="pause">Pause</button><button type="button" data-a="fast">2× speed</button><button type="button" data-a="restart">Restart</button></div>
    </div>
    <ol class="journey-log" id="jlog"></ol>
  </section>

  <section class="section panel">
    <h2>What is a "hill"?</h2>
    <p class="about-p">A hill is a <b>fair test for AI</b>. Take a table where we know the right answers. Show the AI most of it, hide the answers for the rest, and ask it to fill them in. Comparing its guesses with the hidden answers gives a score. The better the predictions, the higher it climbs.</p>
    <div class="diagram-wrap">${hillDiagram()}</div>
  </section>

  <section class="section">
    <h2>The 8 checks, in plain words</h2>
    <p class="muted about-p">A test is only useful if it's fair. One failed check and the dataset is rejected, with the reason written down. So far these checks rejected <b>${t.rejected} of ${t.attempted}</b> datasets.</p>
    <div class="checks">
      ${CHECKS.map(([id, q, rule, why], i) => {
        const ex = examples[id];
        return `<div class="panel check"><div class="check-n">${i + 1}</div><div><h3>${q}</h3><p>${rule}</p><p class="muted small">${why}</p>
          ${ex ? `<p class="check-ex"><b>Real rejection:</b> ${esc(nice(ex.title))}. ${esc(plainWhy(ex))}</p>` : ""}</div></div>`;
      }).join("")}
    </div>
    <p class="small muted">Before the 8 checks there's also a licence and data check. Datasets whose licence doesn't allow public sharing, or whose target column is unusable, never get built.</p>
  </section>

  <section class="section grid2">
    <div class="panel">
      <h2>How it chooses: a trail-picking scout</h2>
      <p class="about-p">Imagine a hiker choosing trails. Mostly they pick kinds of trail that led somewhere good before, but now and then they try a new kind, in case it's better. The scout does the same with kinds of datasets (where they come from, size, number of columns). This method is called <b>Thompson sampling</b>.</p>
      <p class="about-p">After every run, each kind gets a success rate from what actually happened. A hill that real AI agents climbed counts extra.</p>
    </div>
    <div class="panel">
      <h3 style="margin-top:0">What it has learned so far</h3>
      <div class="bk">${buckets.map(([k, v]) => `<div class="bk-row"><span>${esc(bucketLabel(k))}</span><div class="bk-bar"><i style="width:${Math.round(v.rate * 100)}%"></i></div><b>${Math.round(v.rate * 100)}%</b></div>`).join("")}</div>
      <p class="small muted">Estimated chance that a dataset of this kind makes a good hill, after ${DATA.runs.length} runs. Kinds it hasn't tried start at 50%, so it stays curious.</p>
    </div>
  </section>

  <section class="section panel">
    <h2>The daily loop</h2>
    <p class="about-p">Every day the scout runs this loop on its own. What it learns at the end changes what it chooses at the start of the next run.</p>
    <div class="diagram-wrap">${loopDiagram()}</div>
  </section>

  <section class="section panel">
    <h2>Predict: the same idea, for your own spreadsheet</h2>
    <p class="about-p">You don't need to build AI tests to get value. The <a href="#/predict">Predict</a> page uses the same idea of learning from rows with known answers to forecast new ones: who might cancel, what a house might sell for.</p>
    <div class="diagram-wrap">${predictDiagram()}</div>
    <div class="about-tldr" style="margin-top:12px">
      <div class="panel"><b>Honest about quality</b><span>It's tested on rows it never saw, then tells you plainly: "Yes, usefully", "A little" or "Not really".</span></div>
      <div class="panel"><b>Explains itself</b><span>"Month-to-month contracts leave most (42%); two-year contracts least (4%)."</span></div>
      <div class="panel"><b>Ready to act on</b><span>Download your rows with a chance and a High/Medium/Low risk for each. Sort and call the top ones first.</span></div>
    </div>
  </section>

  <section class="section grid2">
    <div class="panel">
      <h2>What a person decides</h2>
      <p class="about-p">The scout works on its own, but some decisions are always left to a human:</p>
      <ul class="about-list">
        <li><b>Making a hill public.</b> New hills start private. ${t.public} of ${t.shipped} have been approved as public.</li>
        <li><b>Building a requested hill.</b> Requests from <a href="#/bring">Bring your data</a> are read by a person first.</li>
        <li><b>Any spending, emails or posts.</b> Nothing goes out automatically.</li>
      </ul>
    </div>
    <div class="panel">
      <h2>Words you'll see</h2>
      <dl class="gloss">
        <dt>Baseline</dt><dd>The lazy guess: always the most common answer, or the average.</dd>
        <dt>Reference</dt><dd>A standard, untuned model. Shows there's room to do better than guessing.</dd>
        <dt>Climb</dt><dd>An AI agent's attempt to beat the best score on a hill.</dd>
        <dt>Balanced accuracy</dt><dd>How often it's right, counting each category equally (1.0 = perfect).</dd>
        <dt>RMSE</dt><dd>The typical size of the error when predicting a number (lower = better).</dd>
      </dl>
    </div>
  </section>

  <section class="section panel faq">
    <h2>Questions</h2>
    <details><summary>Why throw away so many datasets?</summary><p>A test that's broken, too easy or leaky gives AI agents a misleading score. It's better to ship fewer, trustworthy hills. The <a href="#/console">Console</a> lists every rejection and its reason.</p></details>
    <details><summary>Where does the data come from, and is it allowed?</summary><p>From public sources: OpenML, Kaggle's public datasets and direct CSV links. Each licence is checked against an allow-list (for example CC0, CC BY or ODbL). Non-commercial or "no derivatives" licences are skipped.</p></details>
    <details><summary>Can the AI see the test answers?</summary><p>No. Test answers live in a private folder that agents can't read, and half of them are only used for the final score.</p></details>
    <details><summary>Is my data safe on the Predict page?</summary><p>Yes. The model trains inside your browser, so your file isn't sent anywhere. Links you paste are fetched by our server only to read the table, and nothing is kept.</p></details>
    <details><summary>Is this live?</summary><p>Yes. Every number on this site is built from the scout's own records${DATA.generated ? `, last updated ${esc(DATA.generated.slice(0, 10))}` : ""}. The hills are real and can be opened on AutoLab.</p></details>
  </section>

  <div class="panel cta section"><div><h2>Try it</h2><p class="muted">Explore the hills the scout has shipped, or get predictions from your own spreadsheet.</p></div>
    <div class="row"><a class="btn primary" href="#/predict">Predict from a spreadsheet</a><a class="btn" href="#/explore">Explore the hills</a></div></div>`;

  // ---------- replay wiring ----------
  const log = app.querySelector("#jlog"), now = app.querySelector("#jnow"), count = app.querySelector("#jcount");
  const stopName = (it) => STATIONS[it.gate]?.short;
  const ctl = mountJourney(app.querySelector("#journey"), items, {
    onCount(s, r, n) {
      count.innerHTML = `<b>${s}</b> shipped · <b>${r}</b> rejected · ${n} tried`;
      if (s === 0 && r === 0) log.innerHTML = "";
    },
    onItem(it, ev) {
      if (ev === "start") { now.innerHTML = `<b>${esc(it.title)}</b> from ${it.source} is heading through the checks…`; return; }
      const ok = ev === "shipped";
      now.innerHTML = ok ? `<b>${esc(it.title)}</b> passed all 8 checks and became a hill.`
        : `<b>${esc(it.title)}</b> stopped at <b>${esc(stopName(it))}</b>. ${esc(it.why)}`;
      log.insertAdjacentHTML("afterbegin", `<li class="${ok ? "ok" : "no"}"><span class="dot"></span><b>${esc(it.title)}</b> <span class="muted">(${it.source})</span>: ${ok ? "shipped" : esc(it.why)}</li>`);
    },
  });
  let speed = 1, playing = !matchMedia("(prefers-reduced-motion: reduce)").matches;
  const pauseBtn = app.querySelector('[data-a="pause"]');
  pauseBtn.textContent = playing ? "Pause" : "Play";
  app.querySelector("#jctl").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.a === "pause") { playing = !playing; ctl.setPlaying(playing); b.textContent = playing ? "Pause" : "Play"; }
    if (b.dataset.a === "fast") { speed = speed === 1 ? 2 : 1; ctl.setSpeed?.(speed); b.textContent = speed === 1 ? "2× speed" : "1× speed"; b.classList.toggle("on", speed === 2); }
    if (b.dataset.a === "restart") { ctl.restart(); playing = true; ctl.setPlaying(true); pauseBtn.textContent = "Pause"; }
    track("about_control", { action: b.dataset.a });
  });
  return ctl;
}
