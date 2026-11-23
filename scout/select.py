"""Candidate scoring: Thompson sampling over buckets.

bucket = source x task_type x size band x feature band. Each bucket keeps
Beta(successes + 1, failures + 1); one draw per bucket per run ranks its
candidates, so untried buckets (Beta(1,1)) still get explored. Ties break by
popularity, then recency.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .sources.base import Candidate


def size_band(n_rows: int) -> str:
    if n_rows < 10_000:
        return "small"
    if n_rows <= 50_000:
        return "medium"
    return "large"


def feature_band(n_features: int) -> str:
    if n_features < 20:
        return "f<20"
    if n_features <= 60:
        return "f20-60"
    return "f>60"


def bucket_of(c: Candidate) -> str:
    return f"{c.source}|{c.task_type or 'unknown'}|{size_band(c.n_rows)}|{feature_band(c.n_features)}"


def load_buckets(path: Path) -> dict:
    if Path(path).exists():
        return json.loads(Path(path).read_text())
    return {}


def bucket_rate(stats: dict | None) -> float:
    s = (stats or {}).get("successes", 0) + (stats or {}).get("engagement_bonus", 0)
    f = (stats or {}).get("failures", 0)
    return (s + 1) / (s + f + 2)


def load_seen(path: Path) -> tuple[set[str], set[str]]:
    keys, families = set(), set()
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                keys.add(rec["key"])
                if rec.get("family"):
                    families.add(rec["family"])
    return keys, families


@dataclass
class Pick:
    cand: Candidate
    bucket: str
    rate: float  # posterior mean before this run
    sample: float  # the Thompson draw that ranked it
    trials: int

    def reason(self) -> str:
        tried = f"{self.trials} prior attempt(s)" if self.trials else "untried bucket (explore)"
        return f"bucket {self.bucket}: rate {self.rate:.2f}, {tried}, sampled {self.sample:.3f}"


def select(cands: list[Candidate], buckets: dict, seen: set[str], rng: np.random.Generator,
           max_n: int, seen_families: set[str] | None = None) -> list[Pick]:
    """Fill each slot by a fresh Thompson draw over buckets that still have candidates.

    Within the winning bucket the candidate with the highest popularity, then the
    most recent id, is taken. At most one candidate per name family, and never a
    family already attempted in an earlier run (re-uploads of the same data).
    """
    def recency(c: Candidate) -> int:
        try:
            return int(c.source_id)
        except ValueError:
            return 0

    queues: dict[str, list[Candidate]] = {}
    for c in cands:
        if c.key not in seen:
            queues.setdefault(bucket_of(c), []).append(c)
    for q in queues.values():
        q.sort(key=lambda c: (c.popularity, recency(c)), reverse=True)

    picks, families = [], set(seen_families or ())
    while len(picks) < max_n:
        live = {}
        for b, q in queues.items():
            while q and (q[0].extra.get("family") or q[0].key) in families:
                q.pop(0)
            if q:
                live[b] = q
        if not live:
            break
        draws = {}
        for b in sorted(live):
            st = buckets.get(b, {})
            draws[b] = float(rng.beta(st.get("successes", 0) + st.get("engagement_bonus", 0) + 1,
                                      st.get("failures", 0) + 1))
        best = max(draws, key=lambda b: draws[b])
        c = live[best].pop(0)
        families.add(c.extra.get("family") or c.key)
        st = buckets.get(best, {})
        picks.append(Pick(c, best, bucket_rate(st), draws[best], st.get("successes", 0) + st.get("failures", 0)))
    return picks
