"""`scout run`, `scout daily`, `scout report`."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from . import learn
from .build import SEED, hill_name, hill_size_mb, prepare, run_hills, split, write_hill
from .engagement import refresh as refresh_engagement
from .describe import llm_task_sentences, render_readme, template_sentences
from .gates import GATES, run_gates
from .report import write_report
from .select import bucket_of, load_buckets, load_seen, select
from .sources.base import Candidate, SkipCandidate
from .sources.kaggle import KaggleSource
from .sources.manual import ManualSource
from .sources.openml import OpenMLSource
from .sources.web import WebSource

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
RUNS = ROOT / "runs"
MIN_ROWS, MAX_ROWS, MIN_FEAT, MAX_FEAT = 1000, 200_000, 4, 200
DISCOVER_LIMIT = 250


class Logger:
    def __init__(self, path: Path):
        self.fh = open(path, "a")

    def __call__(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        self.fh.write(line + "\n")
        self.fh.flush()


def next_run_id() -> str:
    today = date.today().isoformat()
    n = 1
    while (RUNS / f"{today}-{n}").exists():
        n += 1
    return f"{today}-{n}"


def latest_run() -> Path | None:
    runs = sorted((p for p in RUNS.glob("*-*") if (p / "run.json").exists()),
                  key=lambda p: json.loads((p / "run.json").read_text()).get("started", ""))
    return runs[-1] if runs else None


def in_range(c: Candidate) -> bool:
    return MIN_ROWS <= c.n_rows <= MAX_ROWS and MIN_FEAT <= c.n_features <= MAX_FEAT


def publish(name: str, log) -> str | None:
    """Push a shipped hill to app.autolab.ai as a PRIVATE hill. Making it public stays a human call.

    Skipped when the `autolab` CLI is missing, not signed in, or SCOUT_PUSH=0. A failed push
    leaves the hill bundled only; the report says so.
    """
    import os
    import re
    import shutil
    import subprocess

    if os.environ.get("SCOUT_PUSH", "1") == "0" or not shutil.which("autolab"):
        log("  publish: skipped (SCOUT_PUSH=0 or no autolab CLI); bundled only")
        return None
    try:
        proc = subprocess.run(["autolab", "hills", "push", name], cwd=ROOT, capture_output=True, text=True,
                              timeout=600)
    except Exception as exc:  # noqa: BLE001
        log(f"  publish: push failed ({exc}); bundled only")
        return None
    m = re.search(r"On the web:\s*(\S+)", proc.stdout + proc.stderr)
    if proc.returncode != 0 or not m:
        log(f"  publish: push failed: {(proc.stdout + proc.stderr).strip()[-300:]}; bundled only")
        return None
    url = m.group(1)
    pub = STATE / "published.csv"
    if not pub.exists():
        pub.write_text("hill,url\n")
    with open(pub, "a") as fh:
        fh.write(f"{name},{url}\n")
    log(f"  publish: pushed {name} as a private hill: {url}")
    return url


def build_one(pick, run_id: str, run_dir: Path, sources: dict, log) -> dict:
    c = pick.cand
    src = sources[c.source]
    rec = {"run_id": run_id, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "bucket": pick.bucket, "bucket_rate_before": round(pick.rate, 4), "thompson_sample": round(pick.sample, 4),
           "shipped": False, "stage": "enrich", "hill": None, "gates": {}, "first_failed_gate": None,
           "baseline": None, "reference": None, "reference_2": None, "eval_seconds": None,
           "failure_reason": "", "notes": [], "bundle": None}
    t0 = time.monotonic()
    try:
        src.enrich(c)
    except SkipCandidate as exc:
        rec.update(failure_reason=str(exc))
        log(f"  skip (metadata): {exc}")
        return {**rec, "candidate": c.to_dict()}
    except Exception as exc:  # noqa: BLE001
        rec.update(failure_reason=f"metadata fetch failed: {type(exc).__name__}: {exc}")
        log(f"  skip (metadata error): {exc}")
        return {**rec, "candidate": c.to_dict()}

    rec["stage"] = "prepare"
    try:
        df = src.load(c)
        prep = prepare(df, c)
        parts = split(prep)
    except SkipCandidate as exc:
        rec.update(failure_reason=f"prepare: {exc}", first_failed_gate="prepare")
        log(f"  skip (data): {exc}")
        return {**rec, "candidate": c.to_dict()}
    except Exception as exc:  # noqa: BLE001
        rec.update(failure_reason=f"prepare: {type(exc).__name__}: {exc}", first_failed_gate="prepare")
        log(f"  skip (data error): {exc}")
        return {**rec, "candidate": c.to_dict()}
    rec["notes"] = prep.notes
    rec["task_type"] = prep.task_type
    rec["metric"] = prep.metric

    rec["stage"] = "gates"
    name = hill_name(c)
    rec["hill"] = name
    try:
        readme = render_readme(name, c, prep, parts, template_sentences(c, prep), None, None, None)
        hill = write_hill(ROOT, name, c, prep, parts, readme)
        rec["hill_mb"] = round(hill_size_mb(hill), 2)
        log(f"  built {name} ({rec['hill_mb']} MB, {len(prep.frame)} rows, {prep.task_type}); running gates")
        rep = run_gates(ROOT, name, hill, parts, prep.task_type, f"scout: {c.source}:{c.source_id}", log)
    except Exception as exc:  # noqa: BLE001
        rec.update(failure_reason=f"build error: {type(exc).__name__}: {exc}", first_failed_gate="valid",
                   gates={"valid": {"passed": False, "detail": str(exc)[:300]}})
        log(f"  build error: {exc}\n{traceback.format_exc()[-800:]}")
        return {**rec, "candidate": c.to_dict()}
    rec.update(gates=rep.results, baseline=rep.baseline, reference=rep.reference, reference_2=rep.reference_2,
               eval_seconds=rep.eval_seconds, failure_reason=rep.failure_reason,
               best_single_feature=rep.best_single_feature)
    rec["first_failed_gate"] = next((g for g in GATES if rep.results.get(g, {}).get("passed") is False), None)
    for g in GATES:
        r = rep.results.get(g, {})
        log(f"    {'PASS' if r.get('passed') else ('skip' if r.get('passed') is None else 'FAIL')} {g}: {r.get('detail')}")

    if rep.shipped:
        if c.source == "private" and not c.extra.get("allow_llm"):
            text, how = None, "template (private data is not sent to an LLM)"
        else:
            text, how = llm_task_sentences(c, prep, log)
        rec["description_source"] = how
        readme = render_readme(name, c, prep, parts, text or template_sentences(c, prep),
                               rep.baseline, rep.reference, rep.eval_seconds)
        (hill / "README.md").write_text(readme)
        code, out, _, _ = run_hills(["commit", name, "-m", "scout: README with measured scores", "--json"], ROOT)
        if code != 0:
            rec.update(failure_reason=f"final commit failed: {out[-200:]}")
            log(f"  final commit failed: {out[-300:]}")
            return {**rec, "candidate": c.to_dict()}
        bundle = run_dir / "bundles" / f"{name}.hill.tar"
        code, out, _, _ = run_hills(["bundle", name, "-o", str(bundle)], ROOT)
        if code != 0:
            rec.update(failure_reason=f"bundle failed: {out[-200:]}")
            log(f"  bundle failed: {out[-300:]}")
            return {**rec, "candidate": c.to_dict()}
        rec["bundle"] = str(bundle.relative_to(ROOT))
        rec["shipped"] = True
        rec["published_url"] = publish(name, log)
        log(f"  SHIPPED {name}: baseline {rep.baseline:.4f} -> reference {rep.reference:.4f}; bundle {rec['bundle']}")
    else:
        log(f"  rejected {name}: {rep.failure_reason}")
    rec["seconds"] = round(time.monotonic() - t0, 1)
    return {**rec, "candidate": c.to_dict()}


def cmd_run(max_hills: int, max_candidates: int, max_builds: int | None, only: list[str] | None = None) -> int:
    RUNS.mkdir(exist_ok=True)
    STATE.mkdir(exist_ok=True)
    learn.ensure_engagement(STATE / "engagement.csv")
    run_id = next_run_id()
    run_dir = RUNS / run_id
    (run_dir / "bundles").mkdir(parents=True)
    (run_dir / "logs").mkdir()
    log = Logger(run_dir / "logs" / "run.log")
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log(f"run {run_id}: max_hills={max_hills} max_candidates={max_candidates}")

    memory_path = STATE / "memory.md"
    memory = memory_path.read_text() if memory_path.exists() else ""
    log("memory.md: " + ("read, lessons below" if memory else "empty (first run)"))
    for line in memory.splitlines():
        if line.startswith("- "):
            log(f"  memory {line}")

    # Demand signal first: real climb counts from AutoLab, then buckets recomputed with them,
    # so a hill that attracted climbs lifts its bucket before this run picks.
    refresh_engagement(STATE, log)
    buckets_before = learn.compute_buckets(learn.read_jsonl(STATE / "outcomes.jsonl"),
                                           learn.read_engagement(STATE / "engagement.csv"))
    stored = load_buckets(STATE / "buckets.json")
    for b, st in buckets_before.items():
        if st.get("engagement_bonus") and st != stored.get(b):
            log(f"engagement: bucket {b} gets +{st['engagement_bonus']} success from climbs (rate {st['rate']:.2f})")
    seen, seen_families = load_seen(STATE / "seen.jsonl")

    sources = {
        "openml": OpenMLSource(STATE / "cache", log),
        "manual": ManualSource(ROOT / "candidates.txt", STATE / "cache", log),
        "kaggle": KaggleSource(STATE / "cache", ROOT / "candidates.txt", log),
        "web": WebSource(ROOT / "candidates.txt", STATE / "cache", log),
    }
    source_status, pool = {}, []
    if only:
        sources = {n: s for n, s in sources.items() if n in only}
        log(f"sources limited to: {', '.join(sources)}")
    for name, src in sources.items():
        ok, why = src.available()
        source_status[name] = {"available": ok, "why": why}
        if not ok:
            log(f"source {name}: skipped ({why})")
            continue
        try:
            found = src.discover(DISCOVER_LIMIT)
        except Exception as exc:  # noqa: BLE001
            source_status[name] = {"available": False, "why": f"discover failed: {exc}"}
            log(f"source {name}: discover failed ({exc})")
            continue
        kept = [c for c in found if in_range(c) and c.task_type in ("classification", "regression")]
        source_status[name]["discovered"] = len(found)
        source_status[name]["in_scope"] = len(kept)
        log(f"source {name}: {len(found)} discovered, {len(kept)} in scope (rows/features/task type)")
        pool += kept
    unseen = [c for c in pool if c.key not in seen]
    log(f"pool: {len(pool)} in scope, {len(unseen)} not seen before")

    rng = np.random.default_rng(int(hashlib.sha256(run_id.encode()).hexdigest()[:8], 16))
    dup = sum(1 for c in unseen if (c.extra.get("family") or c.key) in seen_families)
    log(f"excluding {dup} unseen candidate(s) whose name family was attempted in an earlier run")
    picks = select(unseen, buckets_before, seen, rng, max_candidates, seen_families)
    log(f"picked {len(picks)} candidates (Thompson sampling, one per name family):")
    for i, p in enumerate(picks, 1):
        log(f"  {i:2d}. {p.cand.key} '{p.cand.title}' ({p.cand.n_rows} rows, {p.cand.n_features} feats) -- {p.reason()}")

    max_builds = max_builds or max_candidates
    records, shipped, built = [], 0, 0
    considered = []
    for i, p in enumerate(picks, 1):
        entry = {"rank": i, "key": p.cand.key, "title": p.cand.title, "bucket": p.bucket,
                 "rate": round(p.rate, 4), "sample": round(p.sample, 4), "reason": p.reason(), "attempted": False}
        considered.append(entry)
        if shipped >= max_hills or built >= max_builds:
            continue
        log(f"[{i}/{len(picks)}] {p.cand.key} '{p.cand.title}'")
        rec = build_one(p, run_id, run_dir, sources, log)
        entry["attempted"] = True
        records.append(rec)
        if rec["stage"] != "enrich":
            built += 1
        shipped += int(rec["shipped"])
        learn.append_jsonl(STATE / "outcomes.jsonl", [rec])
        learn.append_jsonl(STATE / "seen.jsonl", [{
            "key": p.cand.key, "family": p.cand.extra.get("family"), "title": p.cand.title, "run_id": run_id,
            "status": "shipped" if rec["shipped"] else (rec["stage"] + ": " + rec["failure_reason"])[:200]}])

    outcomes = learn.read_jsonl(STATE / "outcomes.jsonl")
    buckets_after = learn.compute_buckets(outcomes, learn.read_engagement(STATE / "engagement.csv"))
    (STATE / "buckets.json").write_text(json.dumps(buckets_after, indent=2) + "\n")
    learn.write_memory(memory_path, buckets_after, outcomes, run_id)
    log(f"learned: buckets.json updated ({len(buckets_after)} buckets); memory.md rewritten")

    run = {"run_id": run_id, "started": started,
           "finished": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "args": {"max_hills": max_hills, "max_candidates": max_candidates, "max_builds": max_builds, "sources": only or "all"},
           "sources": source_status, "pool_in_scope": len(pool), "pool_unseen": len(unseen),
           "considered": considered, "buckets_before": buckets_before, "buckets_after": buckets_after,
           "memory_before": memory, "split_seed": SEED}
    (run_dir / "run.json").write_text(json.dumps(run, indent=2, default=str) + "\n")
    path = write_report(run_dir, ROOT)
    try:
        from .catalog import write_catalog
        log(f"catalog: {write_catalog(ROOT).relative_to(ROOT)} regenerated (local file; not hosted publicly)")
    except Exception as exc:  # noqa: BLE001
        log(f"catalog: skipped ({exc})")
    try:
        from .site import write_site
        log(f"site: {write_site(ROOT, ROOT / 'site').relative_to(ROOT)} rebuilt locally; redeploying it is a separate, approved step")
    except Exception as exc:  # noqa: BLE001
        log(f"site: skipped ({exc})")
    log(f"done: {len(records)} attempted, {built} built, {shipped} shipped; report {path.relative_to(ROOT)}")
    return 0


def cmd_private(csv_path: str, target: str, task: str, name: str, description: str, allow_llm: bool) -> int:
    """Bring your own data: one CSV -> a gated, private hill."""
    from .select import Pick
    from .sources.private_csv import PrivateCsvSource

    src = PrivateCsvSource(Path(csv_path))
    ok, why = src.available()
    if not ok:
        print(f"no such file: {why}", file=sys.stderr)
        return 1
    try:
        cand = src.candidate(target, task, name, description, allow_llm)
    except SkipCandidate as exc:
        print(str(exc), file=sys.stderr)
        return 1
    run_id = f"private-{cand.source_id}-{date.today().isoformat()}"
    run_dir = RUNS / run_id
    n = 2
    while run_dir.exists():
        run_dir = RUNS / f"{run_id}-{n}"
        n += 1
    (run_dir / "bundles").mkdir(parents=True)
    (run_dir / "logs").mkdir()
    log = Logger(run_dir / "logs" / "run.log")
    log(f"private hill from {csv_path}: target '{target}', {cand.n_rows} rows, {cand.n_features} columns")
    pick = Pick(cand, bucket_of(cand), 0.5, 0.0, 0)
    rec = build_one(pick, run_dir.name, run_dir, {"private": src}, log)
    # Customer hills are kept out of the public bandit: their own log, not outcomes.jsonl.
    learn.append_jsonl(STATE / "private_outcomes.jsonl", [rec])
    gates = rec.get("gates") or {}
    lines = [f"# Private hill: {rec.get('hill') or cand.title}", "",
             f"- Data: `{csv_path}` ({cand.n_rows} rows), target `{target}`, task {rec.get('task_type', task or '?')}",
             f"- Shipped: **{'yes' if rec['shipped'] else 'no'}**" + ("" if rec["shipped"] else f" ({rec['failure_reason']})"),
             f"- Baseline {rec['baseline']} -> reference {rec['reference']} ({rec.get('metric', '')})",
             f"- Published: {rec.get('published_url') or 'not pushed'} (private; the scout never makes it public)",
             f"- README task text: {rec.get('description_source', '-')}", "", "| gate | result | detail |", "|---|---|---|"]
    for g in GATES:
        r = gates.get(g, {})
        mark = {True: "pass", False: "FAIL", None: "not run"}[r.get("passed")]
        lines.append(f"| {g} | {mark} | {r.get('detail', '')} |")
    (run_dir / "report.md").write_text("\n".join(lines) + "\n")
    log(f"done: {'shipped' if rec['shipped'] else 'not shipped'}; report {(run_dir / 'report.md').relative_to(ROOT)}")
    return 0 if rec["shipped"] else 3


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="scout", description="Discover datasets and build them into Autolab hills")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="one full cycle")
    r.add_argument("--max-hills", type=int, default=3)
    r.add_argument("--max-candidates", type=int, default=12)
    r.add_argument("--max-builds", type=int, default=None, help="stop after this many builds (default: max-candidates)")
    r.add_argument("--sources", default="", help="comma list to draw from, e.g. kaggle (default: all)")
    sub.add_parser("daily", help="one cycle with defaults; safe for cron")
    sub.add_parser("report", help="regenerate report.md for the latest run")
    pv = sub.add_parser("private", help="turn your own CSV into a gated, private hill")
    pv.add_argument("csv")
    pv.add_argument("--target", required=True, help="the column to predict")
    pv.add_argument("--task", choices=["classification", "regression"], default="",
                    help="default: inferred from the target column")
    pv.add_argument("--name", default="", help="title for the hill (default: the file name)")
    pv.add_argument("--description", default="", help="one line about the data, for the README")
    pv.add_argument("--llm", action="store_true", help="allow column names to be sent to an LLM for the README")
    sub.add_parser("catalog", help="write catalog/index.html listing every published hill")
    rq = sub.add_parser("requests", help="list private-hill requests stored by the hosted site (Egbe Postgres)")
    rq.add_argument("--limit", type=int, default=50)
    sp = sub.add_parser("site", help="build the interactive site (Explore, Hill detail, Bring your data, Console)")
    sp.add_argument("--out", default=str(ROOT / "site"))
    sub.add_parser("engagement", help="refresh state/engagement.csv from AutoLab climb counts")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        return cmd_run(args.max_hills, args.max_candidates, args.max_builds,
                       [x.strip() for x in args.sources.split(",") if x.strip()] or None)
    if args.cmd == "daily":
        return cmd_run(3, 12, None)
    if args.cmd == "private":
        return cmd_private(args.csv, args.target, args.task, args.name, args.description, args.llm)
    if args.cmd == "engagement":
        refresh_engagement(STATE)
        return 0
    if args.cmd == "requests":
        import glob
        helper = sorted(glob.glob(str(Path.home() / ".claude/plugins/cache/egbe/egbe/*/skills/egbe-os-quickstart/scripts/egbe-curl.py")))
        if not helper:
            print("Egbe plugin helper not found; install the egbe plugin first")
            return 1
        sql = f"SELECT id, received, status, kind, name, email, payload->>'company' AS company, payload->>'notes' AS notes FROM site_requests ORDER BY received DESC LIMIT {max(1, min(args.limit, 500))}"
        out = subprocess.run([sys.executable, helper[-1], "--egbe-request", "/db/query", "-s", "-H", "Content-Type: application/json",
                              "-d", json.dumps({"sql": sql, "params": []})], cwd=ROOT, capture_output=True, text=True,
                             env={**os.environ, "OS_AGENT_NAME": "Claude Code"})
        try:
            body = json.loads(out.stdout)
        except json.JSONDecodeError:
            print(out.stdout or out.stderr)
            return 1
        rows = body.get("rows") or body.get("data", {}).get("rows") or []
        if not rows:
            print("no requests yet")
        for r in rows:
            print(f"{r.get('received')}  {r.get('id')}  [{r.get('status')}]  {r.get('kind')}  {r.get('name')} <{r.get('email')}>  {r.get('company') or ''}")
            if r.get("notes"):
                print(f"    {r['notes'][:200]}")
        return 0
    if args.cmd == "site":
        from .site import write_site
        print(write_site(ROOT, Path(args.out)))
        return 0
    if args.cmd == "catalog":
        from .catalog import write_catalog
        print(write_catalog(ROOT))
        return 0
    if args.cmd == "report":
        run = latest_run()
        if not run:
            print("no runs yet", file=sys.stderr)
            return 1
        print(write_report(run, ROOT))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
