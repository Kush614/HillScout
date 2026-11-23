"""catalog/index.html: every shipped public-source hill, with scores and a difficulty label.

Built only from state/outcomes.jsonl, state/published.csv and state/engagement.csv.
Private customer hills (state/private_outcomes.jsonl) are never listed.

Difficulty comes from how much the default reference model gains over the
baseline: a big gain means an off-the-shelf model already gets far (approachable),
a small gain means the easy signal is thin and progress takes real work (hard).
"""

from __future__ import annotations

import csv
import html
import json
from datetime import datetime
from pathlib import Path

from .learn import read_jsonl


def difficulty(o: dict) -> tuple[str, str]:
    base, ref = o.get("baseline"), o.get("reference")
    if base is None or ref is None:
        return "unknown", ""
    if o.get("metric") == "balanced_accuracy":
        gain = ref - base
        why = f"reference gains {gain:.2f} balanced accuracy over the baseline"
        label = "approachable" if gain >= 0.30 else ("moderate" if gain >= 0.15 else "hard")
    else:
        frac = 1 - ref / base if base else 0.0
        why = f"reference cuts RMSE by {frac:.0%}"
        label = "approachable" if frac >= 0.50 else ("moderate" if frac >= 0.20 else "hard")
    return label, why


def _subtitle(hill_dir: Path) -> str:
    try:
        return (hill_dir / "README.md").read_text().split("\n\n")[1].strip()
    except (OSError, IndexError):
        return ""


def _num(v: float | None, metric: str) -> str:
    if v is None:
        return "-"
    return f"{v:.3f}" if metric == "balanced_accuracy" else f"{v:,.4g}" if abs(v) < 1000 else f"{v:,.0f}"


CSS = """
:root { --bg:#fbfaf7; --fg:#1d1d1b; --muted:#6b6a65; --line:#e4e1d8; --card:#ffffff;
        --accent:#2f5d50; --easy:#2f7d4f; --mid:#a86a12; --hard:#a63d2f; }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --bg:#151513; --fg:#ecebe6; --muted:#a3a198; --line:#2e2d29;
        --card:#1d1d1a; --accent:#7fb8a4; --easy:#6cc08d; --mid:#e0a54a; --hard:#e57c6c; } }
:root[data-theme="dark"] { --bg:#151513; --fg:#ecebe6; --muted:#a3a198; --line:#2e2d29;
        --card:#1d1d1a; --accent:#7fb8a4; --easy:#6cc08d; --mid:#e0a54a; --hard:#e57c6c; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
       font:16px/1.5 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width:960px; margin:0 auto; padding:40px 16px 64px; }
h1 { font-size:28px; margin:0 0 4px; letter-spacing:-0.01em; }
.lede { color:var(--muted); margin:0 0 28px; max-width:640px; }
.stats { display:flex; gap:28px; flex-wrap:wrap; margin:0 0 32px; padding:16px 0;
         border-top:1px solid var(--line); border-bottom:1px solid var(--line); }
.stat b { display:block; font-size:24px; font-variant-numeric:tabular-nums; }
.stat span { color:var(--muted); font-size:13px; }
.grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:16px; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:18px;
        display:flex; flex-direction:column; gap:10px; }
.card h2 { font-size:16px; margin:0; word-break:break-word; }
.card p { margin:0; color:var(--muted); font-size:14px; }
.row { display:flex; justify-content:space-between; font-size:14px; font-variant-numeric:tabular-nums; }
.row span:first-child { color:var(--muted); }
.tag { display:inline-block; font-size:12px; padding:2px 8px; border-radius:99px; border:1px solid currentColor; }
.approachable { color:var(--easy); } .moderate { color:var(--mid); } .hard { color:var(--hard); }
a { color:var(--accent); }
.foot { margin-top:36px; color:var(--muted); font-size:13px; }
"""


# Egbe analytics (Umami) for the hosted page at https://hill-scout.egbe.app. Each "Open on
# AutoLab" link records a hill_click event with the hill's name, which engagement can read back.
ANALYTICS = ('<script async defer data-website-id="95fb35e8-28df-4ec7-bde2-a381b7a8bbe6" '
             'data-performance="true" data-host-url="https://analytics.hz.egbe.dev" '
             'src="https://analytics.hz.egbe.dev/script.js"></script>')


def write_catalog(root: Path) -> Path:
    state = root / "state"
    outcomes = [o for o in read_jsonl(state / "outcomes.jsonl") if o.get("shipped")]
    published = {}
    if (state / "published.csv").exists():
        published = {r["hill"]: r["url"] for r in csv.DictReader(open(state / "published.csv")) if r.get("hill")}
    climbs = {}
    if (state / "engagement.csv").exists():
        climbs = {r["hill"]: r.get("climbs", "0") for r in csv.DictReader(open(state / "engagement.csv")) if r.get("hill")}
    attempted = len(read_jsonl(state / "outcomes.jsonl"))

    cards = []
    for o in outcomes:
        hill, metric = o["hill"], o.get("metric", "")
        label, why = difficulty(o)
        cand = o["candidate"]
        url = published.get(hill)
        link = (f'<a href="{html.escape(url)}" data-umami-event="hill_click" data-umami-event-hill="{html.escape(hill)}">'
                f'Open on AutoLab</a> (private for now)') if url else "bundled, not published"
        cards.append(f"""
<article class="card">
  <h2>{html.escape(hill)}</h2>
  <p>{html.escape(_subtitle(root / '.autolab' / 'hills' / hill))}</p>
  <div><span class="tag {label}" title="{html.escape(why)}">{label}</span></div>
  <div class="row"><span>metric</span><span>{'balanced accuracy, higher is better' if metric == 'balanced_accuracy' else 'RMSE, lower is better'}</span></div>
  <div class="row"><span>baseline</span><span>{_num(o.get('baseline'), metric)}</span></div>
  <div class="row"><span>reference model</span><span>{_num(o.get('reference'), metric)}</span></div>
  <div class="row"><span>climbs</span><span>{html.escape(str(climbs.get(hill, '0')))}</span></div>
  <p>Source: <a href="{html.escape(cand['url'])}">{html.escape(cand['title'])}</a>, license {html.escape(cand.get('license') or '?')}</p>
  <p>{link}</p>
</article>""")

    n_pub = sum(1 for o in outcomes if o["hill"] in published)
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hill Scout Catalogue</title><style>{CSS}</style>{ANALYTICS}</head>
<body><main>
<h1>Hill Scout catalogue</h1>
<p class="lede">Fresh tabular prediction tasks, built every day from public datasets and checked by eight
quality gates before they ship. Each one has held-out labels, a baseline and a reference score to beat.</p>
<div class="stats">
  <div class="stat"><b>{attempted}</b><span>candidates attempted</span></div>
  <div class="stat"><b>{len(outcomes)}</b><span>hills passed every gate</span></div>
  <div class="stat"><b>{n_pub}</b><span>on AutoLab (private)</span></div>
  <div class="stat"><b>{sum(int(v or 0) for v in climbs.values())}</b><span>climbs so far</span></div>
</div>
<section class="grid">{''.join(cards)}</section>
<p class="foot">Difficulty: approachable means a default gradient-boosting model already gains a lot over the
baseline; hard means it gains little, so progress takes real modelling work. Updated
{datetime.now().strftime('%Y-%m-%d %H:%M')}.</p>
</main></body></html>
"""
    out = root / "catalog" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page)
    (root / "catalog" / "hills.json").write_text(json.dumps([
        {"hill": o["hill"], "metric": o.get("metric"), "baseline": o.get("baseline"), "reference": o.get("reference"),
         "difficulty": difficulty(o)[0], "url": published.get(o["hill"]), "source": o["candidate"]["url"],
         "license": o["candidate"].get("license"), "climbs": int(climbs.get(o["hill"], 0) or 0)}
        for o in outcomes], indent=2) + "\n")
    return out
