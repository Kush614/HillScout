// Node check for the Ask Scout helper: every pinned question answers, typed questions route sensibly,
// hill and rejected-dataset names are looked up, and unknown questions fall back politely.
import fs from "fs";
import { _test } from "../../scout/site_template/chat.js";
const D = JSON.parse(fs.readFileSync(process.argv[2] || "site/data/site.json", "utf8"));
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let fail = 0; const ok = (c, m) => { if (!c) { fail++; console.log("FAIL", m); } };
for (const t of _test.topics(D, esc)) { const r = _test.answer(D, t.q, esc); ok(r.id === t.id, `pinned "${t.q}" -> ${r.id}`); ok(!/undefined|NaN/.test(r.html), `clean ${t.id}`); }
const cases = [["is it safe to upload my customer file?", "safe"], ["why did datasets fail", "rejected"], ["how does it pick which data to use", "learn"],
  ["what does rmse mean", "terms"], ["can I get a forecast from excel", "predict"], ["tell me about red wine quality", "lookup"], ["what happened to uber ride analytics", "lookup"],
  ["where does the data come from", "sources"], ["asdfgh qwerty", "none"]];
for (const [q, want] of cases) { const r = _test.answer(D, q, esc); ok(r.id === want, `"${q}" -> ${r.id} (want ${want})`); }
ok(_test.answer(D, "uber ride analytics", esc).html.includes("rejected"), "uber is reported rejected");
ok(!_test.answer(D, "<img src=x onerror=alert(1)>", esc).html.includes("<img"), "typed text is never echoed as HTML");
console.log(fail ? `${fail} failed` : "chat ok"); process.exit(fail ? 1 : 0);
