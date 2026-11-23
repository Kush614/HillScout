"""report.md for one run, built only from run.json and outcomes.jsonl."""

from __future__ import annotations

import json
from pathlib import Path

from .gates import GATES
from .learn import read_jsonl

SHORT = {"valid": "valid", "baseline_scores": "base", "deterministic": "det", "fast": "fast",
         "headroom": "head", "not_trivial": "nontriv", "no_leak": "leak", "rejects_junk": "junk"}


def _mark(g: dict | None) -> str:
    if not g:
        return "·"
    return {True: "✓", False: "✗", None: "·"}[g.get("passed")]


def _f(v, digits=4):
    return "—" if v is None else f"{v:.{digits}f}"


def published_hills(root: Path) -> dict[str, str]:
    """state/published.csv (hill,url), maintained by the human who uploads. Empty = nothing published."""
    p = root / "state" / "published.csv"
    out = {}
    if p.exists():
        for line in p.read_text().splitlines()[1:]:
            if "," in line:
                hill, url = line.split(",", 1)
                out[hill.strip()] = url.strip()
    return out


def write_report(run_dir: Path, root: Path) -> Path:
    run = json.loads((run_dir / "run.json").read_text())
    rid = run["run_id"]
    recs = [o for o in read_jsonl(root / "state" / "outcomes.jsonl") if o.get("run_id") == rid]
    shipped = [o for o in recs if o.get("shipped")]
    built = [o for o in recs if o.get("stage") in ("prepare", "gates")]
    gated = [o for o in recs if o.get("stage") == "gates"]
    published = published_hills(root)

    L = [f"# Hill Scout run {rid}", "",
         f"Started {run['started']}, finished {run['finished']} (UTC).", "",
         "## Summary", "",
         f"- Datasets looked at: **{run['pool_in_scope']}** in scope from discovery "
         f"({run['pool_unseen']} not seen before), **{len(run['considered'])}** shortlisted by the bandit.",
         f"- Attempted: **{len(recs)}**; got past metadata to a build: **{len(built)}**; "
         f"hills built and gated: **{len(gated)}**.",
         f"- Shipped (passed all {len(GATES)} gates, bundled): **{len(shipped)}**.",
         f"- Published on app.autolab.ai: **{sum(1 for o in shipped if o['hill'] in published)}**. "
         f"Published hills are private until a human makes them public; any other shipped hill is "
         f"**bundled only**.", ""]

    L += ["## Sources", "", "| source | status | discovered | in scope |", "|---|---|---|---|"]
    for name, st in run["sources"].items():
        L.append(f"| {name} | {'used' if st['available'] else 'skipped: ' + st['why']} | "
                 f"{st.get('discovered', '—')} | {st.get('in_scope', '—')} |")
    L += ["| egbe | not a dataset source: hosts the site (hill-scout.egbe.app) and its analytics; redeploys need approval | — | — |", ""]

    L += ["## Picked, and why", "",
          "Thompson sampling: each slot takes a fresh Beta(successes+1, failures+1) draw per bucket; the highest draw wins the slot. One candidate per name family, and none from a family attempted in an earlier run.", "",
          "| # | candidate | bucket | rate before | draw | attempted | outcome |", "|---|---|---|---|---|---|---|"]
    by_key = {o["candidate"]["source"] + ":" + o["candidate"]["source_id"]: o for o in recs}
    for e in run["considered"]:
        o = by_key.get(e["key"])
        outcome = "not reached (quota met)" if not o else ("**shipped**" if o["shipped"] else o["failure_reason"][:90])
        L.append(f"| {e['rank']} | {e['key']} {e['title'][:34]} | {e['bucket']} | {e['rate']:.2f} | {e['sample']:.3f} | "
                 f"{'yes' if e['attempted'] else 'no'} | {outcome} |")
    L.append("")

    L += ["## Built hills and gates", "",
          "| hill | task | " + " | ".join(SHORT[g] for g in GATES) + " | baseline | reference | eval s | shipped |",
          "|---|---|" + "---|" * len(GATES) + "---|---|---|---|"]
    for o in gated:
        L.append(f"| {o['hill']} | {o.get('metric', '')} | " + " | ".join(_mark(o["gates"].get(g)) for g in GATES)
                 + f" | {_f(o['baseline'])} | {_f(o['reference'])} | {_f(o['eval_seconds'], 1)} | "
                 f"{'yes' if o['shipped'] else 'no'} |")
    L += ["", "✓ pass, ✗ fail, · not run. Gate details are in `state/outcomes.jsonl`.", ""]
    rejected = [o for o in recs if not o.get("shipped")]
    if rejected:
        L += ["### Rejected", ""]
        for o in rejected:
            L.append(f"- `{o['candidate']['source']}:{o['candidate']['source_id']}` {o['candidate']['title']}: "
                     f"{o['failure_reason'] or 'not shipped'}")
        L.append("")

    L += ["## Bundles", ""]
    if shipped:
        for o in shipped:
            L.append(f"- `{o['bundle']}`: {o['hill']} ({o.get('metric')}: baseline {_f(o['baseline'])}, "
                     f"reference {_f(o['reference'])}); README task text from {o.get('description_source', 'template')}")
    else:
        L.append("- none this run")
    L.append("")

    L += ["## Bucket rates: before -> after this run", "", "| bucket | before | after | change |", "|---|---|---|---|"]
    before, after = run["buckets_before"], run["buckets_after"]
    for b in sorted(set(before) | set(after)):
        rb = before.get(b, {}).get("rate", 0.5)
        ra = after.get(b, {}).get("rate", 0.5)
        if b in before or b in after:
            mark = f"{ra - rb:+.2f}" if abs(ra - rb) > 1e-9 else "0"
            L.append(f"| {b} | {rb:.2f}{'' if b in before else ' (prior)'} | {ra:.2f} | {mark} |")
    L += ["", "A bucket with no history starts at the Beta(1,1) prior, a 0.50 rate.", ""]

    L += ["## Publishing status", ""]
    if shipped:
        for o in shipped:
            url = published.get(o["hill"])
            L.append(f"- {o['hill']}: " + (f"**published (private)**, {url}" if url else "**bundled only, not published**"))
    L += ["", "## Human checklist", "",
          "The loop pushes each shipped hill to app.autolab.ai as a **private** hill "
          "(`autolab hills push`, installed from https://app.autolab.ai/install.sh). "
          "Making a hill public is a human decision:", ""]
    for o in shipped:
        url = published.get(o["hill"])
        if url:
            L.append(f"- [ ] Review {url}, then make it public if it looks right: "
                     f"`autolab hills settings {o['hill']} --public`")
        else:
            L.append(f"- [ ] Push failed or was skipped: run `autolab hills push {o['hill']}` "
                     f"(bundle: `{o['bundle']}`)")
    L += ["- [ ] Start one climb to confirm the hill can be climbed (Hills -> Start a climb)",
          "- [ ] After climbs come in, record `hill,climbs,stars,date` in `state/engagement.csv` "
          "(the next run learns from it)", ""]
    path = run_dir / "report.md"
    path.write_text("\n".join(L) + "\n")
    return path
