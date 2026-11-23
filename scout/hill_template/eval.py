"""Evaluator for a Hill Scout tabular hill.

The climber can read this file. Nothing here reveals an answer: the held-out
labels live in private/test_labels.csv and are only read after the submission
has finished running.

How a submission is scored:
1. The submission directory is copied into a fresh temporary working directory.
2. `python predict.py --train data/train.csv --valid data/valid.csv
   --test data/test_features.csv --out <tmp>/predictions.csv` is launched as a
   subprocess, with the evaluator owning the clock (`time_limit_s`).
3. predictions.csv must have columns `id,prediction` and exactly one row per id
   in test_features.csv.
4. Validation mode scores the public half of the test rows; `--final` scores the
   private half. The submission never learns which row is in which half.
"""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd

HILL = Path(__file__).resolve().parent
DATA = HILL / "data"
PRIVATE = HILL / "private"
TASK = json.loads((DATA / "task.json").read_text())


def _config(final: bool, time_limit_s: int) -> list:
    return [
        {"name": "mode", "value": "test" if final else "validation", "primary": True},
        {"name": "time_limit_s", "value": time_limit_s, "primary": True},
        {"name": "metric", "value": TASK["metric"], "primary": False},
    ]


def _fail(final: bool, time_limit_s: int, error: str, **extra) -> dict:
    return {
        "passed": False,
        "metrics": [],
        "config": _config(final, time_limit_s),
        "details": {"error": error, **extra},
    }


def _balanced_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    recalls = []
    for label in np.unique(y_true):
        mask = y_true == label
        recalls.append(float(np.mean(y_pred[mask] == label)))
    return float(np.mean(recalls))


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(math.sqrt(np.mean((y_true - y_pred) ** 2)))


def eval(submission: Path, *, final: bool = False, time_limit_s: int = 300) -> dict:
    submission = Path(submission)
    if not (submission / "predict.py").is_file():
        return _fail(final, time_limit_s, "submission must contain predict.py")

    test_ids = pd.read_csv(DATA / "test_features.csv", usecols=["id"])["id"].to_numpy()

    with tempfile.TemporaryDirectory(prefix="hill-scout-") as work:
        work = Path(work)
        sub = work / "submission"
        shutil.copytree(submission, sub, ignore=shutil.ignore_patterns("predictions.csv", "__pycache__"))
        out = work / "predictions.csv"
        cmd = [
            sys.executable, "predict.py",
            "--train", str(DATA / "train.csv"),
            "--valid", str(DATA / "valid.csv"),
            "--test", str(DATA / "test_features.csv"),
            "--out", str(out),
        ]
        env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "TMPDIR")}
        env["PYTHONHASHSEED"] = "0"
        env["OMP_NUM_THREADS"] = env.get("OMP_NUM_THREADS", "4")
        started = time.monotonic()
        try:
            proc = subprocess.run(cmd, cwd=sub, env=env, capture_output=True, text=True, timeout=time_limit_s)
        except subprocess.TimeoutExpired:
            return _fail(final, time_limit_s, f"predict.py exceeded the {time_limit_s}s time limit")
        elapsed = time.monotonic() - started
        if proc.returncode != 0:
            return _fail(final, time_limit_s, f"predict.py exited with code {proc.returncode}",
                         stderr_tail=proc.stderr[-1500:])
        if not out.is_file():
            return _fail(final, time_limit_s, "predict.py did not write predictions.csv at the --out path")
        try:
            preds = pd.read_csv(out, dtype={"prediction": str} if TASK["task_type"] == "classification" else None)
        except Exception as exc:  # noqa: BLE001 - any parse failure is a contract violation
            return _fail(final, time_limit_s, f"predictions.csv could not be parsed: {type(exc).__name__}")

    if list(preds.columns[:2]) != ["id", "prediction"] or len(preds.columns) != 2:
        return _fail(final, time_limit_s, "predictions.csv must have exactly the columns id,prediction")
    if len(preds) != len(test_ids):
        return _fail(final, time_limit_s,
                     f"predictions.csv has {len(preds)} rows; expected one per row of test_features.csv ({len(test_ids)})")
    if preds["id"].duplicated().any():
        return _fail(final, time_limit_s, "predictions.csv has duplicate ids")
    if set(preds["id"].tolist()) != set(test_ids.tolist()):
        return _fail(final, time_limit_s, "predictions.csv ids do not match the ids in test_features.csv")
    if preds["prediction"].isna().any():
        return _fail(final, time_limit_s, "predictions.csv has missing predictions")

    labels = pd.read_csv(PRIVATE / "test_labels.csv",
                         dtype={"target": str} if TASK["task_type"] == "classification" else None)
    labels = labels[labels["split"] == ("private" if final else "public")]
    merged = labels.merge(preds, on="id", how="left")

    if TASK["task_type"] == "classification":
        value = _balanced_accuracy(merged["target"].astype(str).to_numpy(),
                                   merged["prediction"].astype(str).to_numpy())
    else:
        pred = pd.to_numeric(merged["prediction"], errors="coerce").to_numpy(dtype=float)
        if not np.all(np.isfinite(pred)):
            return _fail(final, time_limit_s, "predictions must be finite numbers for a regression hill")
        value = _rmse(merged["target"].to_numpy(dtype=float), pred)

    return {
        "passed": True,
        "metrics": [{"name": TASK["metric"], "value": round(value, 6), "direction": TASK["direction"]}],
        "config": _config(final, time_limit_s),
        "details": {"predict_seconds": round(elapsed, 2), "rows_scored": int(len(merged))},
    }
