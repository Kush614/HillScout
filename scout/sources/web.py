"""Web source: direct CSV links listed in candidates.txt.

One entry per line:
    url:https://example.org/data.csv target=<column> license=<licence>
A web link carries no licence metadata, so the line must state one (the person adding
it vouches for it); the same allow-list as every other source then applies.
"""

from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

import pandas as pd

from .. import remote
from .base import Candidate, SkipCandidate, license_allows_redistribution
from .kaggle import infer_task


def parse_line(line: str) -> dict | None:
    line = line.split(" #", 1)[0].strip()
    m = re.match(r"^url:(https?://\S+)(.*)$", line)
    if not m:
        return None
    opts = dict(re.findall(r"(\w+)=(\S+)", m.group(2)))
    return {"url": m.group(1), "target": opts.get("target", ""), "license": opts.get("license", "")}


class WebSource:
    name = "web"

    def __init__(self, candidates: Path, cache_dir: Path, log=print):
        self.candidates = Path(candidates)
        self.cache_dir = Path(cache_dir)
        self.log = log

    def available(self) -> tuple[bool, str]:
        if not self.candidates.exists() or not any(parse_line(l) for l in self.candidates.read_text().splitlines()):
            return False, "no url: lines in candidates.txt"
        return True, "url: lines in candidates.txt"

    def _blob(self, url: str) -> bytes:
        path = self.cache_dir / f"web_{hashlib.sha1(url.encode()).hexdigest()[:16]}.bin"
        if path.exists():
            return path.read_bytes()
        blob, _ = remote.safe_get(remote.resolve(url).get("url", url))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        return blob

    def discover(self, limit: int) -> list[Candidate]:
        out = []
        for entry in (parse_line(l) for l in self.candidates.read_text().splitlines()):
            if not entry or len(out) >= limit:
                continue
            try:
                table, _ = remote.pick_table(self._blob(entry["url"]), entry["url"].rsplit("/", 1)[-1])
            except remote.ImportError_ as exc:
                self.log(f"web: {entry['url']}: {exc}")
                continue
            frame = pd.read_csv(io.StringIO(table["csv"]), low_memory=False)
            target = entry["target"] or remote.guess_target(table["header"])[0]
            name = entry["url"].rsplit("/", 1)[-1].split("?")[0]
            out.append(Candidate(
                source=self.name, source_id=hashlib.sha1(entry["url"].encode()).hexdigest()[:10], title=re.sub(r"\.\w+$", "", name),
                url=entry["url"], license=entry["license"], n_rows=table["total_rows"], n_features=len(table["header"]) - 1,
                task_type=infer_task(frame[target]) if target in frame.columns else "", target=target,
                extra={"family": f"web:{name}"},
            ))
        return out

    def enrich(self, cand: Candidate) -> Candidate:
        ok, why = license_allows_redistribution(cand.license)
        if not ok:
            raise SkipCandidate(why + " (add license=<licence> to the url: line if you know it)")
        if not cand.target:
            raise SkipCandidate("no target column; add target=<column> to the url: line")
        return cand

    def load(self, cand: Candidate) -> pd.DataFrame:
        try:
            blob = self._blob(cand.url)
        except remote.ImportError_ as exc:
            raise SkipCandidate(f"download failed: {exc}") from exc
        members = remote._members(blob, cand.url.rsplit("/", 1)[-1])
        if not members:
            raise SkipCandidate("no table in the download")
        with max(members, key=lambda m: m[1])[2]() as fh:
            return pd.read_csv(fh, sep=None, engine="python", encoding_errors="replace")
