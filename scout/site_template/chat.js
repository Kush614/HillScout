// "Ask Scout": a helper chat with pinned questions. It answers from data/site.json and a built-in
// knowledge base, entirely in the browser: no model calls, no cost, and it never invents numbers.
// Typed questions are matched to the closest topic; dataset and hill names are looked up live.

const STOP = new Set("a an the is are was were do does did i you it its of to in on for and or how what why which who can my me we our this that with be about from at as by any".split(" "));
const words = (s) => String(s).toLowerCase().replace(/[^a-z0-9%]+/g, " ").split(" ").filter((w) => w && !STOP.has(w));
const nice = (t) => String(t || "").replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
const pct = (x) => `${Math.round(x * 100)}%`;

function plainWhy(p) {
  const w = p.why || "";
  if (p.stage === "enrich" || /licen[cs]e/i.test(w)) return "its licence doesn't allow sharing it publicly";
  if (/not a continuous number/.test(w)) return "the number to predict was really a category code, so it wasn't a fair task";
  if (w.startsWith("not_trivial")) return "it was too easy: an ordinary model already scored a perfect 1.0";
  if (w.startsWith("no_leak")) return "one column gave the answer away";
  if (w.startsWith("headroom")) return "a good model barely beat guessing, so there was no room to improve";
  return w || "it failed a check";
}

// Each topic: id, the pinned wording, keywords (weighted by match), and an answer built from live data.
function topics(D, esc) {
  const t = D.totals, hills = D.hills;
  const picks = D.runs.flatMap((r) => r.picks.filter((p) => p.outcome));
  const rejected = picks.filter((p) => p.outcome === "rejected");
  const link = (h, label) => `<a href="${h}">${label}</a>`;
  const easiest = [...hills].sort((a, b) => (a.difficulty === "approachable" ? -1 : 1) - (b.difficulty === "approachable" ? -1 : 1) || a.n_features - b.n_features)[0];
  return [
    { id: "what", q: "What is Hill Scout?", k: ["hill scout", "what", "about", "project", "explain", "overview", "does"],
      a: () => `Hill Scout is a robot scout that finds public data tables, turns the good ones into fair tests for AI agents (called <b>hills</b>), and throws out the bad ones using 8 checks. So far it has tried <b>${t.attempted}</b> datasets and shipped <b>${t.shipped}</b>. It also lets anyone get predictions from a spreadsheet, no code needed. ${link("#/about", "See how it works →")}` },
    { id: "hill", q: "What is a hill?", k: ["hill", "hills", "challenge", "test", "task", "benchmark", "climb"],
      a: () => `A hill is a <b>fair test for AI</b>. Take a table where the right answers are known, show the AI most of it, and hide the answers for the rest. The AI predicts the hidden answers and gets a score. Agents "climb" the hill by beating each other's scores. ${link("#/explore", "Browse the hills →")}` },
    { id: "predict", q: "How do I get predictions from my spreadsheet?", k: ["predict", "prediction", "spreadsheet", "csv", "excel", "forecast", "my data", "file", "upload", "no code"],
      a: () => `Open ${link("#/predict", "Predict")}, then:<ol><li>Pick an example, paste a Kaggle link or drop a CSV.</li><li>Choose the column you want to predict, e.g. "Churn" or "Price".</li><li>Press <b>Find the answers</b>.</li></ol>You get a plain verdict on how reliable it is, what matters most, a what-if panel, and a file of predictions with a High/Medium/Low risk for each row.` },
    { id: "safe", q: "Is my data safe?", k: ["safe*", "safety*", "privacy*", "secure*", "private", "stored", "keep", "gdpr", "leave", "sent"],
      a: () => `Yes. On ${link("#/predict", "Predict")} the model trains <b>inside your browser</b>, so your file is never sent anywhere. If you paste a link, our server fetches it only to read the table and keeps nothing. Requests you send from ${link("#/bring", "Bring your data")} store only what you type, and a person reads them.` },
    { id: "rejected", q: "Why were some datasets rejected?", k: ["reject", "rejected", "fail", "failed", "thrown", "why not", "bad", "leak", "easy"],
      a: () => `${rejected.length} of ${t.attempted} were rejected. Real examples:<ul>${rejected.slice(0, 5).map((p) => `<li><b>${esc(nice(p.title))}</b>: ${esc(plainWhy(p))}.</li>`).join("")}</ul>Every reason is listed in the ${link("#/console", "Console")}.` },
    { id: "checks", q: "What are the 8 checks?", k: ["checks", "check", "gates", "gate", "quality", "8", "eight", "rules"],
      a: () => `Every hill must pass all 8:<ol><li><b>Valid</b>: built correctly</li><li><b>Baseline</b>: a lazy guess can be scored</li><li><b>Repeatable</b>: same score twice</li><li><b>Fast</b>: scored in under 2 minutes</li><li><b>Room to improve</b>: a standard model beats guessing</li><li><b>Not too easy</b>: under 0.98</li><li><b>No leak</b>: no column gives the answer away</li><li><b>Rejects junk</b>: broken answers fail</li></ol>${link("#/about", "Plain-language version →")}` },
    { id: "first", q: "Which hill should I try first?", k: ["first", "start", "begin", "easy", "easiest", "recommend", "beginner", "try"],
      a: () => easiest ? `Try <b>${esc(nice(easiest.title))}</b>: it's rated <b>${easiest.difficulty}</b> with ${easiest.n_features} columns, and a standard model gets ${easiest.metric === "balanced_accuracy" ? easiest.reference.toFixed(3) : "RMSE " + Math.round(easiest.reference).toLocaleString()} (lazy guess: ${easiest.metric === "balanced_accuracy" ? easiest.baseline.toFixed(3) : Math.round(easiest.baseline).toLocaleString()}). ${link(`#/hill/${encodeURIComponent(easiest.hill)}`, "Open it →")}` : "No hills yet." },
    { id: "learn", q: "How does the scout choose datasets?", k: ["choose*", "pick*", "select*", "bandit*", "thompson*", "sampling", "learn", "learns", "decide*"],
      a: () => { const b = Object.entries(D.runs[D.runs.length - 1].buckets_after).sort((x, y) => y[1].rate - x[1].rate)[0];
        return `Like a hiker choosing trails: mostly kinds that worked before, sometimes a new kind in case it's better. This is called <b>Thompson sampling</b>. After ${D.runs.length} runs, its favourite kind is <b>${esc(b[0].replace(/\|/g, " · "))}</b> at ${pct(b[1].rate)}. Hills that real agents climb count extra.`; } },
    { id: "sources", q: "Where does the data come from?", k: ["source", "sources", "where", "kaggle", "openml", "web", "licence", "license", "come"],
      a: () => `From public sources: <b>OpenML</b>, <b>Kaggle</b> (public datasets only) and direct CSV links. Each licence is checked first. Open licences like CC0, CC BY and ODbL are fine; non-commercial or "no derivatives" licences are skipped.` },
    { id: "request", q: "Can AI agents work on my data?", k: ["request", "private", "my data", "company", "agents", "compete", "hire", "business", "custom"],
      a: () => `Yes. On ${link("#/bring", "Bring your data")}, import or drop your table. It runs the same checks, then you can <b>request a private hill</b>. A person reviews every request, and agents then compete to beat your baseline. Your rows aren't sent with the request unless you choose to.` },
    { id: "numbers", q: "How many hills are there?", k: ["how many", "count", "number", "total", "stats", "shipped", "public", "far"],
      a: () => `<b>${t.shipped}</b> hills shipped from <b>${t.attempted}</b> datasets attempted (${t.rejected} rejected), across ${D.runs.length} runs. ${t.public} are public on AutoLab. ${link("#/console", "Run-by-run detail →")}` },
    { id: "terms", q: "What do baseline and reference mean?", k: ["baseline", "reference", "rmse", "balanced", "accuracy", "metric", "score", "mean", "difficulty", "approachable", "moderate", "hard"],
      a: () => `<b>Baseline</b>: the lazy guess, i.e. always the most common answer or the average.<br><b>Reference</b>: a standard, untuned model.<br><b>Balanced accuracy</b>: how often it's right, counting each category equally (1.0 = perfect).<br><b>RMSE</b>: the typical error when predicting a number (lower is better).<br>Difficulty (approachable, moderate, hard) is how far the reference gets above the baseline.` },
  ];
}

// pinned questions per page
const PINNED = {
  predict: ["predict", "safe", "request", "what"],
  explore: ["what", "first", "hill", "numbers"],
  hill: ["terms", "checks", "first", "hill"],
  bring: ["request", "safe", "sources", "checks"],
  console: ["rejected", "learn", "numbers", "checks"],
  about: ["what", "hill", "rejected", "predict"],
};

const GENERIC = new Set("check checks times quality dataset datasets analytics performance employee searches score scores model hills data table".split(" "));
function nameMatch(title, q, qw) {
  const n = nice(title).toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
  if (n.length > 3 && (" " + q + " ").includes(" " + n + " ")) return true;
  return n.split(" ").some((w) => w.length >= 5 && !GENERIC.has(w) && qw.has(w));
}
function lookup(D, text, esc) {
  const q = text.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim(), qw = new Set(q.split(" "));
  const hill = D.hills.find((h) => nameMatch(h.title, q, qw));
  if (hill) {
    const f = (v) => hill.metric === "balanced_accuracy" ? v.toFixed(3) : Math.round(v).toLocaleString();
    return `<b>${esc(nice(hill.title))}</b> is a shipped hill (${hill.task_type}, ${hill.difficulty}). It has ${hill.rows.train.toLocaleString()} rows to learn from and ${hill.n_features} columns. Lazy guess: ${f(hill.baseline)}; standard model: ${f(hill.reference)} (${hill.metric === "balanced_accuracy" ? "higher" : "lower"} is better). It's ${hill.public ? "public" : "private"} on AutoLab. <a href="#/hill/${encodeURIComponent(hill.hill)}">Open it →</a>`;
  }
  const pick = D.runs.flatMap((r) => r.picks.filter((p) => p.outcome === "rejected")).find((p) => nameMatch(p.title, q, qw));
  if (pick) return `<b>${esc(nice(pick.title))}</b> was tried but <b>rejected</b>: ${esc(plainWhy(pick))}. The scout writes down every rejection so it never wastes time on it again.`;
  return null;
}

function answer(D, text, esc) {
  const direct = lookup(D, text, esc); if (direct) return { html: direct, id: "lookup" };
  const T = topics(D, esc), ws = words(text), joined = " " + ws.join(" ") + " ";
  let best = null, bestScore = 0;
  for (const tp of T) {
    let s = 0;
    for (const raw of tp.k) { const strong = raw.endsWith("*"), k = strong ? raw.slice(0, -1) : raw;
      if (k.includes(" ") ? joined.includes(" " + k + " ") || text.toLowerCase().includes(k) : ws.includes(k)) s += strong ? 3 : k.includes(" ") ? 2.5 : 1; }
    if (text.trim().toLowerCase() === tp.q.toLowerCase()) s += 10;
    if (s > bestScore) { bestScore = s; best = tp; }
  }
  if (best && bestScore >= 1) return { html: best.a(), id: best.id };
  return { html: `I'm not sure about that one. I can answer questions about Hill Scout, the hills, the 8 checks, and getting predictions from a spreadsheet. Try one of the questions below, or see <a href="#/about">How it works</a>.`, id: "none" };
}

export function mountChat(D, { esc, track }) {
  const root = document.createElement("div");
  root.className = "chat";
  root.innerHTML = `
    <button class="chat-fab" type="button" aria-expanded="false" aria-controls="chat-panel"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg><span>Ask Scout</span></button>
    <section class="chat-panel" id="chat-panel" role="dialog" aria-label="Ask Scout" hidden>
      <header><div><b>Ask Scout</b><span>Answers from the scout's own records</span></div><button type="button" class="chat-x" aria-label="Close">×</button></header>
      <div class="chat-log" aria-live="polite"></div>
      <div class="chat-pins" aria-label="Pinned questions"></div>
      <form class="chat-form"><input type="text" placeholder="Ask about hills, checks, predictions…" aria-label="Your question" maxlength="200" autocomplete="off"><button type="submit" aria-label="Send">↑</button></form>
    </section>`;
  document.body.appendChild(root);
  const fab = root.querySelector(".chat-fab"), panel = root.querySelector(".chat-panel"), log = root.querySelector(".chat-log"),
    pins = root.querySelector(".chat-pins"), form = root.querySelector(".chat-form"), input = form.querySelector("input");
  const T = topics(D, esc), byId = Object.fromEntries(T.map((t) => [t.id, t]));
  const page = () => (location.hash.replace(/^#\/?/, "") || "explore").split("/")[0];
  const add = (who, html) => { log.insertAdjacentHTML("beforeend", `<div class="msg ${who}">${html}</div>`); log.scrollTop = log.scrollHeight; };
  const drawPins = () => { pins.innerHTML = (PINNED[page()] || PINNED.explore).map((id) => `<button type="button" data-id="${id}">📌 ${esc(byId[id].q)}</button>`).join(""); };
  let greeted = false;
  const open = (v) => {
    panel.hidden = !v; fab.setAttribute("aria-expanded", String(v)); root.classList.toggle("open", v);
    if (v) { drawPins(); if (!greeted) { add("bot", `Hi! I'm Scout's helper. Pick a pinned question or type your own.`); greeted = true; } setTimeout(() => input.focus(), 50); track("chat_open", { page: page() }); }
  };
  const ask = (text, how) => {
    add("me", esc(text));
    const r = answer(D, text, esc);
    setTimeout(() => add("bot", r.html), 220);
    track("chat_ask", { how, topic: r.id, page: page() }); // the topic only, never the typed text
  };
  fab.addEventListener("click", () => open(panel.hidden));
  root.querySelector(".chat-x").addEventListener("click", () => open(false));
  pins.addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) ask(byId[b.dataset.id].q, "pinned"); });
  form.addEventListener("submit", (e) => { e.preventDefault(); const v = input.value.trim(); if (!v) return; input.value = ""; ask(v, "typed"); });
  log.addEventListener("click", (e) => { if (e.target.closest("a[href^='#/']")) { if (matchMedia("(max-width: 560px)").matches) open(false); } });
  addEventListener("keydown", (e) => { if (e.key === "Escape" && !panel.hidden) open(false); });
  addEventListener("hashchange", () => { if (!panel.hidden) drawPins(); });
}

export const _test = { answer, topics, lookup };
