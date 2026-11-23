"""Kaggle source: public datasets through Kaggle's public API (no login needed).

Discovery lists recent CSV datasets under open licence families, then inspects a capped
number of small ones per day: it downloads the zip, picks the largest table, counts rows
and columns, and keeps only tables whose target column is recognisable by name (Kaggle
datasets declare no target). Inspections are cached per day, so a re-run downloads nothing.

`kaggle:owner/slug` lines in candidates.txt are inspected first; add `target=<column>` to
name the target yourself. Competition data is never fetched: it needs a person to accept
the rules on the website.
"""

from __future__ import annotations

import io
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from .. import remote
from .base import Candidate, SkipCandidate
from .openml import name_family

LIST_URL = "https://www.kaggle.com/api/v1/datasets/list"
MAX_DATASET_BYTES = 20 * 1024 * 1024
INSPECT_PER_RUN = 20


def parse_line(line: str) -> tuple[str, str, str] | None:
    """`kaggle:owner/slug [target=col]` -> (owner, slug, target)."""
    line = line.split("#", 1)[0].strip()
    m = re.match(r"^kaggle:([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)(?:\s+target=(\S+))?$", line)
    return (m.group(1), m.group(2), m.group(3) or "") if m else None


def infer_task(values: pd.Series) -> str:
    v = values.dropna()
    num = pd.to_numeric(v, errors="coerce")
    if len(v) and num.notna().all():
        if (num == num.round()).all() and num.nunique() <= 10:
            return "classification"
        return "regression" if num.nunique() > 20 else "classification"
    return "classification" if 2 <= v.astype(str).nunique() <= 50 else ""


class KaggleSource:
    name = "kaggle"

    def __init__(self, cache_dir: Path | None = None, candidates: Path | None = None, log=print,
                 inspect_per_run: int = INSPECT_PER_RUN):
        self.cache_dir = Path(cache_dir) if cache_dir else Path(".")
        self.candidates = Path(candidates) if candidates else None
        self.log = log
        self.inspect_per_run = inspect_per_run

    def available(self) -> tuple[bool, str]:
        return True, "public Kaggle API, no login"

    # -- cache helpers
    def _zip_path(self, owner: str, slug: str) -> Path:
        return self.cache_dir / f"kaggle_{owner}__{slug}.zip"

    def _info_path(self, owner: str, slug: str) -> Path:
        return self.cache_dir / f"kaggle_{owner}__{slug}.json"

    def _listing(self) -> list[dict]:
        cache = self.cache_dir / f"kaggle_list_{date.today().isoformat()}.json"
        if cache.exists():
            return json.loads(cache.read_text())
        rows: list[dict] = []
        for lic, sort in (("cc", "votes"), ("cc", "hottest"), ("odb", "votes")):
            for page in (1, 2):
                url = (f"{LIST_URL}?filetype=csv&license={lic}&sortBy={sort}&page={page}"
                       f"&minSize=20000&maxSize={MAX_DATASET_BYTES}")
                try:
                    got = remote.get_json(url)
                except remote.ImportError_ as exc:
                    self.log(f"kaggle: listing failed ({exc})")
                    got = []
                rows.extend(got if isinstance(got, list) else [])
        seen, out = set(), []
        for r in rows:
            ref = r.get("ref")
            if ref and ref not in seen:
                seen.add(ref)
                out.append({"ref": ref, "title": r.get("titleNullable") or r.get("title") or ref,
                            "license": r.get("licenseNameNullable") or "", "bytes": r.get("totalBytesNullable") or 0,
                            "updated": str(r.get("lastUpdated") or "")[:10], "votes": r.get("voteCount") or 0,
                            "subtitle": r.get("subtitleNullable") or ""})
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(out))
        return out

    def _inspect(self, owner: str, slug: str, meta: dict, target: str = "") -> dict | None:
        info_path = self._info_path(owner, slug)
        if info_path.exists():
            info = json.loads(info_path.read_text())
            if info.get("day") == date.today().isoformat() and (not target or info.get("target") == target):
                return info
        zpath = self._zip_path(owner, slug)
        try:
            blob = zpath.read_bytes() if zpath.exists() else remote.kaggle_download(owner, slug, MAX_DATASET_BYTES)
            zpath.write_bytes(blob)
            table, files = remote.pick_table(blob, f"{slug}.csv")
        except remote.ImportError_ as exc:
            info = {"day": date.today().isoformat(), "ok": False, "why": str(exc)}
            info_path.write_text(json.dumps(info))
            return info
        try:
            frame = pd.read_csv(io.StringIO(table["csv"]), low_memory=False)
        except Exception as exc:  # noqa: BLE001 - a messy table is a normal skip, never a crash
            info = {"day": date.today().isoformat(), "ok": False, "why": f"unreadable table: {type(exc).__name__}"}
            info_path.write_text(json.dumps(info))
            return info
        tgt, why = (target, "named in candidates.txt") if target else remote.guess_target(table["header"], strict=True)
        info = {"day": date.today().isoformat(), "ok": bool(tgt) and tgt in frame.columns,
                "why": why if tgt else "no recognisable target column", "file": table["file"],
                "delimiter": table["delimiter"], "rows": table["total_rows"], "cols": len(table["header"]),
                "target": tgt, "task": infer_task(frame[tgt]) if tgt in frame.columns else "",
                "n_classes": int(frame[tgt].nunique()) if tgt in frame.columns else 0, **meta}
        info_path.write_text(json.dumps(info))
        return info

    def discover(self, limit: int) -> list[Candidate]:
        pinned = []
        if self.candidates and self.candidates.exists():
            pinned = [p for p in (parse_line(l) for l in self.candidates.read_text().splitlines()) if p]
        todo = [(o, s, t, {}) for o, s, t in pinned]
        for r in self._listing():
            o, s = r["ref"].split("/", 1)
            todo.append((o, s, "", r))
        out, downloads = [], 0
        for owner, slug, target, meta in todo:
            if len(out) >= limit:
                break
            cached = self._info_path(owner, slug).exists()
            if not cached and not target and downloads >= self.inspect_per_run:
                continue
            if not meta:
                try:
                    m = remote.kaggle_meta(owner, slug)
                except remote.ImportError_ as exc:
                    self.log(f"kaggle: {owner}/{slug}: {exc}")
                    continue
                meta = {"ref": f"{owner}/{slug}", "title": m["title"], "license": m["license"], "bytes": m["bytes"],
                        "updated": "", "votes": m["votes"], "subtitle": m["subtitle"]}
            if meta.get("bytes", 0) > MAX_DATASET_BYTES:
                continue
            downloads += 0 if cached else 1
            try:
                info = self._inspect(owner, slug, meta, target)
            except Exception as exc:  # noqa: BLE001
                self.log(f"kaggle: {owner}/{slug}: inspect failed ({type(exc).__name__}: {exc})")
                continue
            if not info or not info.get("ok"):
                continue
            out.append(Candidate(
                source=self.name, source_id=f"{owner}/{slug}", title=meta["title"],
                url=f"https://www.kaggle.com/datasets/{owner}/{slug}", license=meta.get("license", ""),
                n_rows=int(info["rows"]), n_features=int(info["cols"]) - 1, task_type=info["task"],
                target=info["target"], created=meta.get("updated", ""), popularity=float(meta.get("votes") or 0),
                description=meta.get("subtitle", ""),
                extra={"file": info["file"], "n_classes": info["n_classes"], "family": name_family(meta["title"]),
                       "target_reason": info["why"]},
            ))
        return out

    def enrich(self, cand: Candidate) -> Candidate:
        lic = remote.kaggle_license_canonical(cand.license)
        ok, why = remote.license_allows_redistribution(lic)
        if not ok:
            raise SkipCandidate(why)
        if not cand.target:
            raise SkipCandidate("no recognisable target column")
        return cand

    def load(self, cand: Candidate) -> pd.DataFrame:
        owner, slug = cand.source_id.split("/", 1)
        zpath = self._zip_path(owner, slug)
        try:
            blob = zpath.read_bytes() if zpath.exists() else remote.kaggle_download(owner, slug, MAX_DATASET_BYTES)
        except remote.ImportError_ as exc:
            raise SkipCandidate(f"download failed: {exc}") from exc
        members = remote._members(blob, f"{slug}.csv")
        want = cand.extra.get("file")
        member = next((m for m in members if m[0] == want), None) or (max(members, key=lambda m: m[1]) if members else None)
        if not member:
            raise SkipCandidate("no CSV table in the download")
        with member[2]() as fh:
            return pd.read_csv(fh, sep=None, engine="python", encoding_errors="replace")
