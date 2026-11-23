// Run by tests/test_scout.py through node: the browser model must find a known signal,
// ignore an id column, and fill in rows whose answer is blank.
import * as ML from "../../scout/site_template/ml.js";
let s = 3; const r = () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
const header = ["customer_id", "months", "plan", "noise", "left"];
const rows = [];
for (let i = 0; i < 2000; i++) {
  const months = Math.floor(r() * 72), plan = r() < 0.5 ? "monthly" : "yearly";
  const p = (plan === "monthly" ? 0.5 : 0.08) * (months < 12 ? 1.6 : 0.6);
  rows.push([`C${i}`, String(months), plan, String(r()), r() < p ? "Yes" : "No"]);
}
for (let i = 0; i < 40; i++) rows[i][4] = "";
const res = ML.train({ header, rows, targetIdx: 4, task: ML.detectTask(rows, 4) });
const out = ML.predictUnlabelled();
const num = [];
for (let i = 0; i < 1500; i++) { const a = r() * 10, b = r() * 10; num.push([String(a), String(b), String(3 * a - 2 * b + r())]); }
const reg = ML.train({ header: ["a", "b", "y"], rows: num, targetIdx: 2, task: ML.detectTask(num, 2) });
console.log(JSON.stringify({
  task: ML.detectTask(rows, 4), grade: res.grade, auc: res.auc, positive: res.positive,
  dropped: res.dropped.map((d) => d.name), top: res.factors.slice(0, 2).map((f) => f.name),
  unlabelled: res.unlabelled, predicted: out.preds.length, risks: [...new Set(out.preds.map((p) => p.risk))].sort(),
  regTask: ML.detectTask(num, 2), regGrade: reg.grade, regSkill: reg.skill,
}));
