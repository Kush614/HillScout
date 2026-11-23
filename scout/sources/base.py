"""Candidate record and the Source interface."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd

from ..remote import ALLOWED_LICENSES, license_allows_redistribution, normalise_license  # noqa: F401  (shared with the site)


@dataclass
class Candidate:
    source: str
    source_id: str
    title: str
    url: str
    license: str = ""
    n_rows: int = 0
    n_features: int = 0
    task_type: str = ""  # classification | regression | "" when unknown
    target: str = ""
    created: str = ""  # ISO date or empty
    popularity: float = 0.0
    tags: list[str] = field(default_factory=list)
    description: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Candidate":
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


class SkipCandidate(Exception):
    """Raised when a candidate cannot be built for a normal, recordable reason."""


class Source(Protocol):
    name: str

    def available(self) -> tuple[bool, str]:
        """Whether this source can run here, and why not if it cannot."""

    def discover(self, limit: int) -> list[Candidate]:
        """Return up to `limit` candidates, newest first, without downloading data."""

    def enrich(self, cand: Candidate) -> Candidate:
        """Fill license, target, description and the like. May raise SkipCandidate."""

    def load(self, cand: Candidate) -> pd.DataFrame:
        """Download the data. May raise SkipCandidate."""
