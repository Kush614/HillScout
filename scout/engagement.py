"""Fill state/engagement.csv from AutoLab: how many climbs each published hill has.

Uses `autolab hills climbs <owner/name>`, which lists one climb per line. Stars have
no CLI read path yet, so the stars column keeps whatever a human last wrote there.
Without the autolab CLI or a sign-in, the file is left as it is.
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path


def published(state: Path) -> dict[str, str]:
    p = state / "published.csv"
    out = {}
    if p.exists():
        for row in csv.DictReader(open(p)):
            if row.get("hill") and row.get("url"):
                out[row["hill"]] = row["url"]
    return out


def slug_from_url(url: str) -> str | None:
    m = re.search(r"/hills/([^/]+/[^/?#]+)", url)
    return m.group(1) if m else None


def count_climbs(slug: str) -> int | None:
    try:
        proc = subprocess.run(["autolab", "hills", "climbs", slug], capture_output=True, text=True, timeout=60)
    except Exception:  # noqa: BLE001
        return None
    if proc.returncode != 0:
        return None
    return sum(1 for line in proc.stdout.splitlines() if line.strip().startswith("·"))


def refresh(state: Path, log=print) -> dict[str, int]:
    """Update engagement.csv in place. Returns {hill: climbs} for the hills it could read."""
    path = state / "engagement.csv"
    rows = {}
    if path.exists():
        for row in csv.DictReader(open(path)):
            if row.get("hill"):
                rows[row["hill"]] = row
    if not shutil.which("autolab"):
        log("engagement: autolab CLI not found; engagement.csv left as is")
        return {}
    counts = {}
    for hill, url in published(state).items():
        slug = slug_from_url(url)
        n = count_climbs(slug) if slug else None
        if n is None:
            continue
        counts[hill] = n
        old = rows.get(hill, {})
        rows[hill] = {"hill": hill, "climbs": str(n), "stars": old.get("stars", "0") or "0",
                      "date": date.today().isoformat()}
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["hill", "climbs", "stars", "date"])
        w.writeheader()
        for row in rows.values():
            w.writerow(row)
    log(f"engagement: read climb counts for {len(counts)} published hill(s): "
        + (", ".join(f"{h}={n}" for h, n in counts.items() if n) or "none climbed yet"))
    return counts
