"""Manual source: dataset ids listed in candidates.txt (the demo safety net).

One entry per line, `openml:<id>` (or a bare OpenML id, or an openml.org/d/<id>
URL). Lines starting with # are ignored. Entries resolve through the OpenML
API, so the same license and target rules apply.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import Candidate
from .openml import API, OpenMLSource, _get_json, _quality, name_family


def parse_line(line: str) -> str | None:
    line = line.split("#", 1)[0].strip()
    if not line:
        return None
    m = re.search(r"(?:openml:|openml\.org/d/|^)(\d+)$", line)
    return m.group(1) if m else None


class ManualSource(OpenMLSource):
    name = "manual"

    def __init__(self, path: Path, cache_dir: Path, log=print):
        super().__init__(cache_dir, log)
        self.path = Path(path)

    def available(self) -> tuple[bool, str]:
        if not self.path.exists():
            return False, f"{self.path.name} not found"
        return True, f"{self.path.name}"

    def discover(self, limit: int) -> list[Candidate]:
        ids = [i for i in (parse_line(l) for l in self.path.read_text().splitlines()) if i]
        out = []
        for did in ids[:limit]:
            qcache = self.cache_dir / f"openml_qual_{did}.json"
            try:
                if qcache.exists():
                    import json
                    entry = json.loads(qcache.read_text())
                else:
                    import json
                    entry = _get_json(f"{API}/data/list/data_id/{did}", timeout=60)["data"]["dataset"][0]
                    qcache.write_text(json.dumps(entry))
            except Exception as exc:  # noqa: BLE001
                self.log(f"manual: could not resolve openml:{did}: {exc}")
                continue
            n_classes = _quality(entry, "NumberOfClasses")
            task = "classification" if n_classes and n_classes >= 2 else ("regression" if n_classes == 0 else "")
            out.append(Candidate(
                source=self.name, source_id=did, title=entry["name"],
                url=f"https://www.openml.org/d/{did}",
                n_rows=int(_quality(entry, "NumberOfInstances") or 0),
                n_features=int((_quality(entry, "NumberOfFeatures") or 1) - 1),
                task_type=task,
                extra={"n_classes": n_classes, "family": name_family(entry["name"])},
            ))
        return out
