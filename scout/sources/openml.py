"""OpenML source, via the public REST API (no login).

The `openml` Python package's list_tasks() pages through the whole catalogue and
took over five minutes here, so discovery uses the filtered REST listing
directly and caches it for the day. Data is read from the dataset's parquet URL.
"""

from __future__ import annotations

import io
import json
import re
import time
import urllib.request
from datetime import date
from pathlib import Path

import pandas as pd

from .base import Candidate, SkipCandidate, license_allows_redistribution

API = "https://www.openml.org/api/v1/json"
LIST_FILTER = "status/active/number_instances/1000..200000/number_features/4..200"
PAGE = 1000


def _get_json(url: str, timeout: int = 120) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "hill-scout/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _quality(entry: dict, name: str) -> float | None:
    for q in entry.get("quality", []):
        if q["name"] == name:
            try:
                return float(q["value"])
            except (TypeError, ValueError):
                return None
    return None


def name_family(name: str) -> str:
    """Collapse series like 'foo-lote7-2026' / 'foo-lote8-2026' or 'X-v1-6c4e' to one family."""
    base = name.lower()
    if len(re.findall(r"[-_ ]", base)) >= 3:  # long generated names: the first token is the series
        return re.split(r"[-_ ]", base)[0]
    base = re.sub(r"[-_ ]?(v\d+|lote\d+|\d{4}|[0-9a-f]{8})\b", "", base)
    return re.sub(r"[-_ ]?\d+$", "", base)


class OpenMLSource:
    name = "openml"

    def __init__(self, cache_dir: Path, log=print):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.log = log

    def available(self) -> tuple[bool, str]:
        return True, "public API, no login"

    # -- discovery -------------------------------------------------------
    def _listing(self) -> list[dict]:
        today = date.today().isoformat()
        cached = self.cache_dir / f"openml_list_{today}.json"
        if cached.exists():
            return json.loads(cached.read_text())
        rows: list[dict] = []
        offset = 0
        while True:
            url = f"{API}/data/list/{LIST_FILTER}/limit/{PAGE}/offset/{offset}"
            try:
                page = _get_json(url)["data"]["dataset"]
            except urllib.error.HTTPError as exc:  # 412 "No results" ends the listing
                if exc.code == 412:
                    break
                raise
            rows.extend(page)
            if len(page) < PAGE:
                break
            offset += PAGE
        # Fallback: the raw pages fetched by hand at M0 (state/cache/openml_list_<offset>.json)
        cached.write_text(json.dumps(rows))
        return rows

    def discover(self, limit: int) -> list[Candidate]:
        try:
            listing = self._listing()
        except Exception as exc:  # noqa: BLE001
            self.log(f"openml: live listing failed ({exc}); using raw page cache")
            listing = []
            for p in sorted(self.cache_dir.glob("openml_list_*.json"), reverse=True):
                data = json.loads(p.read_text())
                if isinstance(data, list):  # a previous day's processed listing
                    listing = data
                    break
                listing += data["data"]["dataset"]
        listing = [d for d in listing if d.get("format", "").lower() == "arff"]
        listing.sort(key=lambda d: int(d["did"]), reverse=True)  # higher id = more recent upload
        out = []
        for d in listing[:limit]:
            n_classes = _quality(d, "NumberOfClasses")
            task = "classification" if n_classes and n_classes >= 2 else ("regression" if n_classes == 0 else "")
            out.append(Candidate(
                source=self.name,
                source_id=str(d["did"]),
                title=d["name"],
                url=f"https://www.openml.org/d/{d['did']}",
                n_rows=int(_quality(d, "NumberOfInstances") or 0),
                n_features=int((_quality(d, "NumberOfFeatures") or 1) - 1),
                task_type=task,
                popularity=0.0,
                extra={"n_classes": n_classes, "family": name_family(d["name"]),
                       "missing_values": _quality(d, "NumberOfMissingValues")},
            ))
        return out

    # -- per-candidate ---------------------------------------------------
    def enrich(self, cand: Candidate) -> Candidate:
        cache = self.cache_dir / f"openml_desc_{cand.source_id}.json"
        if cache.exists():
            desc = json.loads(cache.read_text())
        else:
            desc = _get_json(f"{API}/data/{cand.source_id}", timeout=60)["data_set_description"]
            cache.write_text(json.dumps(desc))
        cand.license = desc.get("licence", "") or ""
        cand.created = (desc.get("upload_date") or "")[:10]
        cand.description = (desc.get("description") or "")[:2000]
        tags = desc.get("tag") or []
        cand.tags = tags if isinstance(tags, list) else [tags]
        cand.extra["parquet_url"] = desc.get("parquet_url", "")
        cand.extra["ignore"] = [c for c in (desc.get("ignore_attribute") or "").split(",") if c] \
            if isinstance(desc.get("ignore_attribute"), str) else list(desc.get("ignore_attribute") or [])
        if desc.get("row_id_attribute"):
            cand.extra["ignore"].append(desc["row_id_attribute"])
        target = desc.get("default_target_attribute") or ""
        ok, why = license_allows_redistribution(cand.license)
        if not ok:
            raise SkipCandidate(why)
        if not target:
            raise SkipCandidate("no declared target attribute")
        if "," in target:
            raise SkipCandidate("multi-target dataset")
        cand.target = target
        if not cand.extra["parquet_url"]:
            raise SkipCandidate("no parquet download available")
        return cand

    def load(self, cand: Candidate) -> pd.DataFrame:
        path = self.cache_dir / f"openml_{cand.source_id}.parquet"
        if not path.exists():
            url = cand.extra["parquet_url"]
            for attempt in range(3):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "hill-scout/0.1"})
                    with urllib.request.urlopen(req, timeout=180) as resp:
                        path.write_bytes(resp.read())
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt == 2:
                        raise SkipCandidate(f"download failed: {exc}") from exc
                    time.sleep(2)
        df = pd.read_parquet(io.BytesIO(path.read_bytes()))
        drop = [c for c in cand.extra.get("ignore", []) if c in df.columns and c != cand.target]
        return df.drop(columns=drop)
