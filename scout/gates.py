"""Quality gates. A hill ships only if every gate passes."""

from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor

from .build import run_hills

GATES = ["valid", "baseline_scores", "deterministic", "fast", "headroom", "not_trivial", "no_leak", "rejects_junk"]
DETERMINISM_TOL = 0.005
FAST_LIMIT_S = 120.0
HEADROOM_BACC = 0.05
HEADROOM_RMSE_FRAC = 0.10
TRIVIAL_BACC = 0.98
TRIVIAL_RMSE_FRAC = 0.01  # reference RMSE under 1% of baseline RMSE counts as "near zero"
LEAK_BACC = 0.02
LEAK_RMSE_FRAC = 0.02

JUNK_PREDICT = """import argparse, pandas as pd
p = argparse.ArgumentParser()
[p.add_argument(f, required=True) for f in ('--train', '--valid', '--test', '--out')]
a = p.parse_args()
t = pd.read_csv(a.test, usecols=['id']).iloc[:-7]
pd.DataFrame({'id': t['id'], 'prediction': 0}).to_csv(a.out, index=False)
"""


@dataclass
class GateReport:
    results: dict = field(default_factory=dict)  # gate -> {"passed": bool|None, "detail": str}
    baseline: float | None = None
    reference: float | None = None
    reference_2: float | None = None
    eval_seconds: float | None = None
    best_single_feature: tuple[str, float] | None = None
    failure_reason: str = ""

    def record(self, gate: str, passed: bool | None, detail: str) -> bool:
        self.results[gate] = {"passed": passed, "detail": detail}
        if passed is False and not self.failure_reason:
            self.failure_reason = f"{gate}: {detail}"
        return bool(passed)

    @property
    def shipped(self) -> bool:
        return all(self.results.get(g, {}).get("passed") is True for g in GATES)

    def skip_rest(self) -> None:
        for g in GATES:
            self.results.setdefault(g, {"passed": None, "detail": "not run (earlier gate failed)"})


def _metric(report: dict | None) -> float | None:
    if not report or not report.get("passed") or not report.get("metrics"):
        return None
    return float(report["metrics"][0]["value"])


def _encode(col: pd.Series, cats: pd.Index | None = None) -> np.ndarray:
    if not pd.api.types.is_numeric_dtype(col):
        cats = cats if cats is not None else pd.Index(col.dropna().astype(str).unique())
        codes = pd.Categorical(col.astype("string"), categories=cats).codes.astype(float)
        codes[codes < 0] = -1.0
        return codes
    return pd.to_numeric(col, errors="coerce").fillna(-9e9).to_numpy(dtype=float)


def single_feature_scores(parts: dict[str, pd.DataFrame], task_type: str, limit_rows: int = 20000) -> dict[str, float]:
    """Score each feature on its own with a shallow tree, on the public test rows."""
    fit = pd.concat([parts["train"], parts["valid"]], ignore_index=True)
    if len(fit) > limit_rows:
        fit = fit.sample(n=limit_rows, random_state=0)
    labels = parts["test_labels"]
    public = labels[labels["split"] == "public"]
    test = parts["test_features"].set_index("id").loc[public["id"]]
    y_fit = fit["target"]
    y_true = public["target"].to_numpy()
    scores = {}
    for col in [c for c in fit.columns if c not in ("id", "target")]:
        cats = None
        if not pd.api.types.is_numeric_dtype(fit[col]):
            cats = pd.Index(pd.concat([fit[col], test[col]]).dropna().astype(str).unique())
        x_fit = _encode(fit[col], cats).reshape(-1, 1)
        x_test = _encode(test[col], cats).reshape(-1, 1)
        if task_type == "classification":
            model = DecisionTreeClassifier(max_depth=8, min_samples_leaf=20, random_state=0)
            model.fit(x_fit, y_fit.astype(str))
            pred = model.predict(x_test)
            recalls = [np.mean(pred[y_true.astype(str) == k] == k) for k in np.unique(y_true.astype(str))]
            scores[col] = float(np.mean(recalls))
        else:
            model = DecisionTreeRegressor(max_depth=8, min_samples_leaf=20, random_state=0)
            model.fit(x_fit, y_fit.astype(float))
            pred = model.predict(x_test)
            scores[col] = float(math.sqrt(np.mean((y_true.astype(float) - pred) ** 2)))
    return scores


def run_gates(root: Path, name: str, hill: Path, parts: dict[str, pd.DataFrame], task_type: str,
              commit_msg: str, log=print) -> GateReport:
    rep = GateReport()
    is_cls = task_type == "classification"

    # 1. Valid: hills check, then commit.
    code, out, parsed, _ = run_hills(["check", name, "--json"], root)
    if code != 0:
        rep.record("valid", False, "hills check failed: " + out.strip().splitlines()[-1][:200] if out.strip() else "hills check failed")
        rep.skip_rest()
        return rep
    code, out, parsed, _ = run_hills(["commit", name, "-m", commit_msg, "--json"], root)
    if code != 0:
        rep.record("valid", False, "hills commit failed: " + (out.strip().splitlines() or [""])[-1][:200])
        rep.skip_rest()
        return rep
    rep.record("valid", True, "hills check passed and commit succeeded")

    # 2. Baseline scores.
    code, out, base, _ = run_hills(["eval", str(hill / "examples" / "baseline"), "-H", name, "--json"], root)
    rep.baseline = _metric(base)
    if rep.baseline is None:
        err = (base or {}).get("details", {}).get("error", out.strip()[-200:])
        rep.record("baseline_scores", False, f"baseline did not pass: {err}")
        rep.skip_rest()
        return rep
    rep.record("baseline_scores", True, f"baseline {rep.baseline:.4f}")

    # 3 + 4. Reference twice: deterministic and fast.
    code, out, ref1, t1 = run_hills(["eval", str(hill / "examples" / "reference"), "-H", name, "--json"], root)
    rep.reference = _metric(ref1)
    rep.eval_seconds = round(t1, 2)
    if rep.reference is None:
        err = (ref1 or {}).get("details", {}).get("error", out.strip()[-200:])
        rep.record("deterministic", False, f"reference did not pass: {err}")
        rep.skip_rest()
        return rep
    code, out, ref2, _ = run_hills(["eval", str(hill / "examples" / "reference"), "-H", name, "--json"], root)
    rep.reference_2 = _metric(ref2)
    if rep.reference_2 is None:
        rep.record("deterministic", False, "second reference eval did not pass")
    else:
        diff = abs(rep.reference - rep.reference_2)
        rep.record("deterministic", diff < DETERMINISM_TOL, f"two reference evals differ by {diff:.5f}")
    rep.record("fast", t1 < FAST_LIMIT_S, f"reference eval took {t1:.1f}s (limit {FAST_LIMIT_S:.0f}s)")

    # 5. Headroom and 6. not trivial.
    if is_cls:
        gain = rep.reference - rep.baseline
        rep.record("headroom", gain >= HEADROOM_BACC,
                   f"reference beats baseline by {gain:.4f} balanced accuracy (need {HEADROOM_BACC})")
        rep.record("not_trivial", rep.reference < TRIVIAL_BACC,
                   f"reference balanced accuracy {rep.reference:.4f} (must be under {TRIVIAL_BACC})")
    else:
        frac = 1 - rep.reference / rep.baseline if rep.baseline else 0.0
        rep.record("headroom", frac >= HEADROOM_RMSE_FRAC,
                   f"reference RMSE is {frac:.1%} lower than baseline (need {HEADROOM_RMSE_FRAC:.0%})")
        rep.record("not_trivial", rep.baseline > 0 and rep.reference > TRIVIAL_RMSE_FRAC * rep.baseline,
                   f"reference RMSE {rep.reference:.4g} vs baseline {rep.baseline:.4g}")

    # 7. No leak: no single feature gets within the margin of the reference.
    try:
        singles = single_feature_scores(parts, task_type)
        if is_cls:
            best_col, best = max(singles.items(), key=lambda kv: kv[1])
            leak = best >= rep.reference - LEAK_BACC
            msg = f"best single feature '{best_col}' scores {best:.4f} vs reference {rep.reference:.4f}"
        else:
            best_col, best = min(singles.items(), key=lambda kv: kv[1])
            leak = best <= rep.reference * (1 + LEAK_RMSE_FRAC)
            msg = f"best single feature '{best_col}' RMSE {best:.4g} vs reference {rep.reference:.4g}"
        rep.best_single_feature = (best_col, round(best, 6))
        rep.record("no_leak", not leak, msg)
    except Exception as exc:  # noqa: BLE001
        rep.record("no_leak", False, f"leak check errored: {type(exc).__name__}: {exc}")

    # 8. Rejects junk: wrong row count must fail.
    with tempfile.TemporaryDirectory(prefix="scout-junk-") as tmp:
        (Path(tmp) / "predict.py").write_text(JUNK_PREDICT)
        code, out, junk, _ = run_hills(["eval", tmp, "-H", name, "--json"], root)
    rejected = junk is not None and junk.get("passed") is False
    err = (junk or {}).get("details", {}).get("error", "no report")
    rep.record("rejects_junk", rejected, f"wrong-row-count submission -> passed={junk.get('passed') if junk else None} ({err})")
    return rep
