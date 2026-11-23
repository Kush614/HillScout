"""A company's own CSV, turned into a private hill (`scout private`).

The owner supplies the data, so there is no public license to check. The hill is
pushed private and never made public by the scout. Column names and the
description are not sent to an LLM unless the owner passes --llm.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import Candidate, SkipCandidate


class PrivateCsvSource:
    name = "private"

    def __init__(self, path: Path):
        self.path = Path(path)

    def available(self) -> tuple[bool, str]:
        return (self.path.exists(), str(self.path))

    def candidate(self, target: str, task_type: str = "", title: str = "", description: str = "",
                  allow_llm: bool = False) -> Candidate:
        head = pd.read_csv(self.path, nrows=5)
        if target not in head.columns:
            raise SkipCandidate(f"target column '{target}' not in {self.path.name} "
                                f"(columns: {', '.join(map(str, head.columns[:15]))})")
        n_rows = sum(1 for _ in open(self.path)) - 1
        return Candidate(
            source=self.name, source_id=self.path.stem, title=title or self.path.stem,
            url=f"file://{self.path.resolve()}", license="owner's data (private hill)",
            n_rows=n_rows, n_features=len(head.columns) - 1, task_type=task_type, target=target,
            description=description, extra={"allow_llm": allow_llm, "family": f"private:{self.path.stem}"},
        )

    def discover(self, limit: int) -> list[Candidate]:
        return []

    def enrich(self, cand: Candidate) -> Candidate:
        return cand

    def load(self, cand: Candidate) -> pd.DataFrame:
        return pd.read_csv(self.path)
