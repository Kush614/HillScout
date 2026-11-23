"""Candidate -> committed hill, via the hills CLI.

Hills are spec_version 2 (the `default` template), not the `dataset` template:
spec-4 dataset hills are git+LFS repos that `hills bundle` refuses to package,
and this build hands bundles to a human for upload. Data under 10 MB per file
lives in the tree; larger files are bound by hash through the `blobs` rule.
"""

from __future__ import annotations

import hashlib

import json
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .sources.base import Candidate, SkipCandidate

TEMPLATE = Path(__file__).resolve().parent / "hill_template"
SEED = 20261122
MAX_CELLS = 2_500_000  # keeps every hill well under the 50 MB cap
MIN_CLASS_ROWS = 10
MAX_CLASSES = 50
TIME_LIMIT_S = 300


@dataclass
class Prepared:
    frame: pd.DataFrame  # columns: id, <features...>, target
    task_type: str
    metric: str
    direction: str
    original_target: str
    notes: list[str] = field(default_factory=list)


def slugify(text: str, n: int = 22) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n].strip("-") or "data"


def hill_name(cand: Candidate) -> str:
    if cand.source == "private":
        return f"private-{slugify(cand.title, 30)}"
    if re.fullmatch(r"[a-z0-9-]+", cand.source_id):
        return f"scout-{slugify(cand.title)}-{cand.source_id}"  # OpenML ids: unchanged names
    tag = {"kaggle": "kg", "web": "web"}.get(cand.source, cand.source[:4])
    digest = hashlib.sha1(cand.key.encode()).hexdigest()[:6]
    return f"scout-{slugify(cand.title)}-{tag}-{digest}"


def prepare(df: pd.DataFrame, cand: Candidate, seed: int = SEED) -> Prepared:
    """Clean a raw frame into id + features + target. Raises SkipCandidate."""
    notes: list[str] = []
    target = cand.target
    if target not in df.columns:
        raise SkipCandidate(f"declared target '{target}' not in the data")
    df = df.copy()
    df = df[df[target].notna()]
    if len(df) < 500:
        raise SkipCandidate(f"only {len(df)} rows with a target")

    task = cand.task_type
    if task == "regression":
        yn = pd.to_numeric(df[target], errors="coerce")
        if yn.notna().all() and yn.nunique() <= 10 and (yn == yn.round()).all():
            task = "classification"
            notes.append(f"OpenML lists the target as numeric, but it has {yn.nunique()} integer values; "
                         "treated as classification")
    if not task:
        task = "regression" if pd.api.types.is_numeric_dtype(df[target]) and df[target].nunique() > 20 else "classification"
    if task == "classification":
        y = df[target].astype(str)
        counts = y.value_counts()
        rare = counts[counts < MIN_CLASS_ROWS]
        if len(rare):
            df = df[~y.isin(rare.index)]
            y = y[~y.isin(rare.index)]
            notes.append(f"dropped {len(rare)} class(es) with fewer than {MIN_CLASS_ROWS} rows")
        if y.nunique() < 2:
            raise SkipCandidate("fewer than two usable classes")
        if y.nunique() > MAX_CLASSES:
            raise SkipCandidate(f"{y.nunique()} classes is more than {MAX_CLASSES}")
        df[target] = y
        metric, direction = "balanced_accuracy", "max"
    else:
        yn = pd.to_numeric(df[target], errors="coerce")
        if yn.isna().any() or yn.nunique() <= 10:
            raise SkipCandidate("regression target is not a continuous number")
        df[target] = yn.astype(float)
        metric, direction = "rmse", "min"

    feats = [c for c in df.columns if c != target]
    # Drop columns that carry nothing: all-null or constant.
    useless = [c for c in feats if df[c].nunique(dropna=True) <= 1]
    if useless:
        notes.append(f"dropped {len(useless)} constant or empty column(s)")
        feats = [c for c in feats if c not in useless]
    if len(feats) < 2:
        raise SkipCandidate("fewer than two usable features")

    # Normalise feature names: unique, never `id` or `target`.
    rename, used = {}, {"id", "target"}
    for c in feats:
        new = re.sub(r"\s+", "_", str(c).strip()) or "col"
        while new in used:
            new = f"{new}_f"
        used.add(new)
        rename[c] = new
    out = df[feats].rename(columns=rename)
    for c in out.columns:
        if isinstance(out[c].dtype, pd.CategoricalDtype) or out[c].dtype == bool:
            out[c] = out[c].astype("string")
    out["target"] = df[target].to_numpy()

    if out.shape[0] * out.shape[1] > MAX_CELLS:
        keep = MAX_CELLS // out.shape[1]
        out = out.sample(n=keep, random_state=seed)
        notes.append(f"subsampled to {keep} rows (seed {seed}) to keep the hill small")

    rng = np.random.default_rng(seed)
    out = out.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    out.insert(0, "id", rng.permutation(len(out)) + 100000)
    return Prepared(out, task, metric, direction, target, notes)


def _stratified_order(y: pd.Series, rng: np.random.Generator) -> np.ndarray:
    """Interleave classes so any prefix slice keeps class proportions."""
    keys = np.empty(len(y))
    for label in y.unique():
        idx = np.flatnonzero((y == label).to_numpy())
        rng.shuffle(idx)
        keys[idx] = (np.arange(len(idx)) + rng.random(len(idx))) / len(idx)
    return np.argsort(keys, kind="stable")


def split(prep: Prepared, seed: int = SEED) -> dict[str, pd.DataFrame]:
    """60/20/20 split, stratified for classification. Test is halved into public/private."""
    df = prep.frame
    rng = np.random.default_rng(seed)
    if prep.task_type == "classification":
        order = _stratified_order(df["target"], rng)
    else:
        order = rng.permutation(len(df))
    # Assign by position in the (stratified) order: every 5th pair of slots to
    # valid/test so each split sees every class.
    slot = np.empty(len(df), dtype=int)
    slot[order] = np.arange(len(df)) % 10
    train = df[slot < 6]
    valid = df[(slot == 6) | (slot == 7)]
    test = df[slot >= 8].copy()
    test["split"] = np.where(slot[slot >= 8] == 8, "public", "private")
    return {
        "train": train.reset_index(drop=True),
        "valid": valid.reset_index(drop=True),
        "test_features": test.drop(columns=["target", "split"]).reset_index(drop=True),
        "test_labels": test[["id", "target", "split"]].reset_index(drop=True),
    }


# -- hills CLI ----------------------------------------------------------------

def run_hills(args: list[str], root: Path, timeout: int = 900) -> tuple[int, str, dict | None, float]:
    started = time.monotonic()
    proc = subprocess.run(["hills", *args], cwd=root, capture_output=True, text=True, timeout=timeout)
    elapsed = time.monotonic() - started
    parsed = None
    if "--json" in args:
        text = proc.stdout.strip()
        start = text.find("{")
        if start >= 0:
            try:
                parsed = json.loads(text[start:])
            except json.JSONDecodeError:
                parsed = None
    return proc.returncode, (proc.stdout + proc.stderr), parsed, elapsed


HILL_YAML = """spec_version: 2
name: {name}
version: 0.1.0

# What the evaluator reports, in ranking order.
metrics:
  - {{name: {metric}, direction: {direction}}}

# Hard kill for a hung evaluator. The real time limit is time_limit_s, enforced in eval.py.
watchdog_timeout_s: 900

params:
  time_limit_s: {{type: int, default: {time_limit}, min: 10, max: 600, help: "seconds predict.py may run before it is killed"}}

# Large assets stay out of git and are bound into the hill's identity by hash.
blobs:
  threshold: 10MB
  track: ["data/**", "private/**"]
"""

PYPROJECT = """[project]
name = "{name}"
version = "0.1.0"
description = "Evaluation environment for {name}"
requires-python = ">=3.11"
dependencies = ["numpy>=1.26", "pandas>=2.2", "scikit-learn>=1.5"]

[dependency-groups]
dev = ["pytest>=8.0"]
"""


def write_hill(root: Path, name: str, cand: Candidate, prep: Prepared, parts: dict[str, pd.DataFrame],
               readme: str) -> Path:
    hill = root / ".autolab" / "hills" / name
    if not hill.exists():
        code, out, _, _ = run_hills(["new", name], root)
        if code != 0:
            raise RuntimeError(f"hills new failed: {out[-500:]}")
    # Replace the scaffold's examples with ours; keep .vc and .gitignore.
    for stale in ("examples", "tests", "data", "private"):
        shutil.rmtree(hill / stale, ignore_errors=True)
    shutil.copytree(TEMPLATE / "examples", hill / "examples", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(TEMPLATE / "tests", hill / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(TEMPLATE / "eval.py", hill / "eval.py")
    (hill / "data").mkdir()
    (hill / "private").mkdir()
    parts["train"].to_csv(hill / "data" / "train.csv", index=False)
    parts["valid"].to_csv(hill / "data" / "valid.csv", index=False)
    parts["test_features"].to_csv(hill / "data" / "test_features.csv", index=False)
    parts["test_labels"].to_csv(hill / "private" / "test_labels.csv", index=False)
    (hill / "data" / "task.json").write_text(json.dumps({
        "task_type": prep.task_type, "metric": prep.metric, "direction": prep.direction,
        "target": "target", "id": "id", "source": cand.url,
    }, indent=2) + "\n")
    (hill / "hill.yaml").write_text(HILL_YAML.format(name=name, metric=prep.metric, direction=prep.direction,
                                                    time_limit=TIME_LIMIT_S))
    (hill / "pyproject.toml").write_text(PYPROJECT.format(name=name))
    (hill / "README.md").write_text(readme)
    return hill


def hill_size_mb(hill: Path) -> float:
    total = sum(p.stat().st_size for p in hill.rglob("*") if p.is_file() and ".vc" not in p.parts)
    return total / 1e6
