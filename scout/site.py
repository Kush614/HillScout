"""`scout site`: build the interactive Hill Scout site (Explore, Hill detail, Bring your data, Console).

Everything the site shows comes from the scout's own records:
state/outcomes.jsonl (attempts, gates, scores), runs/*/run.json (picks and bandit),
state/published.csv, state/engagement.csv, state/climbs.json and each hill's public files
(train.csv head, column types, the reference predict.py). Private customer hills and
anything under a hill's private/ folder are never exported.
"""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .catalog import difficulty
from .learn import read_jsonl

TEMPLATE = Path(__file__).resolve().parent / "site_template"
GATE_LABELS = {
    "valid": ("Valid", "hills check passes and the commit succeeds"),
    "baseline_scores": ("Baseline scores", "the majority-class or mean submission passes"),
    "deterministic": ("Deterministic", "two reference evals differ by less than 0.005"),
    "fast": ("Fast", "one reference eval takes under 120 s"),
    "headroom": ("Headroom", "the reference clearly beats the baseline"),
    "not_trivial": ("Not trivial", "the reference is not near perfect"),
    "no_leak": ("No leak", "no single column gets close to the reference on its own"),
    "rejects_junk": ("Rejects junk", "a wrong-row-count submission fails"),
}


def _csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [r for r in csv.DictReader(open(path)) if any(r.values())]


def _readme_parts(readme: str) -> dict:
    parts = readme.split("\n\n")
    subtitle = parts[1].strip() if len(parts) > 1 else ""
    task = ""
    if "## The task" in readme:
        task = readme.split("## The task", 1)[1].split("\n## ", 1)[0].strip()
    return {"subtitle": subtitle, "task": task}


def _hill_record(root: Path, o: dict, published: dict, climbs: dict, attempts: dict) -> dict:
    hill = o["hill"]
    hdir = root / ".autolab" / "hills" / hill
    cand = o["candidate"]
    train = pd.read_csv(hdir / "data" / "train.csv", nrows=2000)
    n_train = sum(1 for _ in open(hdir / "data" / "train.csv")) - 1
    n_valid = sum(1 for _ in open(hdir / "data" / "valid.csv")) - 1
    n_test = sum(1 for _ in open(hdir / "data" / "test_features.csv")) - 1
    cols = []
    for c in train.columns:
        if c == "id":
            continue
        num = pd.api.types.is_numeric_dtype(train[c])
        cols.append({"name": c, "type": "number" if num else "category",
                     "unique": int(train[c].nunique()), "missing": int(train[c].isna().sum()),
                     "is_target": c == "target"})
    preview = train.head(12).copy()
    preview = preview.astype(object).where(preview.notna(), None)
    label, why = difficulty(o)
    target_summary = {}
    if o.get("metric") == "balanced_accuracy":
        vc = train["target"].astype(str).value_counts(normalize=True).head(10)
        target_summary = {"classes": [{"label": k, "share": round(float(v), 4)} for k, v in vc.items()]}
    else:
        t = pd.to_numeric(train["target"], errors="coerce")
        target_summary = {"mean": float(t.mean()), "std": float(t.std()), "min": float(t.min()), "max": float(t.max()),
                          "hist": [int(x) for x in pd.cut(t, 24).value_counts(sort=False).tolist()]}
    gates = []
    for g, (name, rule) in GATE_LABELS.items():
        r = o.get("gates", {}).get(g, {})
        gates.append({"id": g, "name": name, "rule": rule, "passed": r.get("passed"), "detail": r.get("detail", "")})
    readme = (hdir / "README.md").read_text()
    return {
        "hill": hill, "title": cand["title"], **_readme_parts(readme),
        "task_type": o.get("task_type") or ("classification" if o.get("metric") == "balanced_accuracy" else "regression"),
        "metric": o.get("metric"), "direction": "max" if o.get("metric") == "balanced_accuracy" else "min",
        "baseline": o.get("baseline"), "reference": o.get("reference"), "eval_seconds": o.get("eval_seconds"),
        "difficulty": label, "difficulty_why": why,
        "rows": {"train": n_train, "valid": n_valid, "test": n_test}, "n_features": len(cols) - 1,
        "columns": cols, "preview": json.loads(preview.to_json(orient="records")),
        "target_summary": target_summary, "gates": gates, "notes": o.get("notes", []),
        "source": {"url": cand["url"], "title": cand["title"], "license": cand.get("license"), "id": cand["source_id"]},
        "bucket": o.get("bucket"), "run_id": o.get("run_id"), "shipped_at": o.get("ts"),
        "url": published.get(hill), "climbs": int(climbs.get(hill, 0) or 0),
        "climb_history": attempts.get(hill, []),
        "starter": (hdir / "examples" / "reference" / "predict.py").read_text(),
        "baseline_code": (hdir / "examples" / "baseline" / "predict.py").read_text(),
        "time_limit_s": 300,
    }


def export(root: Path) -> dict:
    state = root / "state"
    outcomes = read_jsonl(state / "outcomes.jsonl")
    published = {r["hill"]: r["url"] for r in _csv_rows(state / "published.csv") if r.get("hill")}
    climbs = {r["hill"]: r.get("climbs", 0) for r in _csv_rows(state / "engagement.csv") if r.get("hill")}
    # visibility on AutoLab, recorded when a person changes it (new pushes start private)
    visibility = {r["hill"]: r.get("visibility", "private") for r in _csv_rows(state / "visibility.csv") if r.get("hill")}
    attempts = {}
    if (state / "climbs.json").exists():
        for c in json.loads((state / "climbs.json").read_text()):
            attempts.setdefault(c["hill"], []).append(c)
    hills = [_hill_record(root, o, published, climbs, attempts) for o in outcomes if o.get("shipped")]
    for h in hills:
        h["public"] = bool(h["url"]) and visibility.get(h["hill"]) == "public"

    runs = []
    for rj in sorted((root / "runs").glob("*/run.json")):
        r = json.loads(rj.read_text())
        if not r.get("run_id", "").startswith("20"):
            continue
        recs = [o for o in outcomes if o.get("run_id") == r["run_id"]]
        by_key = {f"{o['candidate']['source']}:{o['candidate']['source_id']}": o for o in recs}
        picks = []
        for e in r["considered"]:
            o = by_key.get(e["key"])
            picks.append({**{k: e[k] for k in ("rank", "key", "title", "bucket", "rate", "sample", "reason", "attempted")},
                          "outcome": None if not o else ("shipped" if o["shipped"] else "rejected"),
                          "stage": o.get("stage") if o else None,
                          "why": (o.get("failure_reason") or "") if o else "not reached (quota met)",
                          "hill": o.get("hill") if o else None})
        runs.append({
            "run_id": r["run_id"], "started": r["started"], "finished": r["finished"],
            "pool_in_scope": r["pool_in_scope"], "pool_unseen": r["pool_unseen"],
            "sources": r["sources"], "picks": picks,
            "attempted": len(recs), "built": sum(1 for o in recs if o.get("stage") in ("prepare", "gates")),
            "gated": sum(1 for o in recs if o.get("stage") == "gates"), "shipped": sum(1 for o in recs if o.get("shipped")),
            "buckets_before": r["buckets_before"], "buckets_after": r["buckets_after"],
        })

    spend = read_jsonl(root / "runs" / "egbe" / "egbe_spend.jsonl")
    memory = (state / "memory.md").read_text() if (state / "memory.md").exists() else ""
    lessons = [l[2:] for l in memory.splitlines() if l.startswith("- ")]
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hills": hills, "runs": runs, "lessons": lessons,
        "totals": {
            "attempted": len(outcomes), "shipped": len(hills),
            "rejected": sum(1 for o in outcomes if not o.get("shipped")),
            "published": sum(1 for h in hills if h["url"]),
            "public": sum(1 for h in hills if h.get("public")),
            "climbs": sum(h["climbs"] for h in hills),
            "discovered": max((r["pool_in_scope"] for r in runs), default=0),
        },
        "spend": {"egbe_usd": round(sum(float(s.get("cost_usd") or 0) for s in spend), 2), "egbe_cap_usd": 15,
                  "autolab_climb_cap_usd": 5},
    }


def write_site(root: Path, out: Path) -> Path:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for item in TEMPLATE.iterdir():
        dest = out / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy(item, dest)
    shutil.copy(Path(__file__).resolve().parent / "remote.py", out / "importer.py")
    (out / "data").mkdir(exist_ok=True)
    (out / "data" / "site.json").write_text(json.dumps(export(root), indent=1, default=str) + "\n")
    stale = out / "hills.json"
    if stale.exists():
        stale.unlink()
    return out
