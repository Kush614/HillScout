"""Checks on the hill itself, run by `hills check`."""

import json
from pathlib import Path

import pandas as pd
from hills import run_evaluator

HILL = Path(__file__).resolve().parents[1]
EXAMPLES = HILL / "examples"
TASK = json.loads((HILL / "data" / "task.json").read_text())


def test_baseline_scores():
    result = run_evaluator(HILL, EXAMPLES / "baseline")
    assert result["passed"], result["details"]
    metric = result["metrics"][0]
    assert metric["name"] == TASK["metric"]
    assert metric["direction"] == ("max" if TASK["metric"] == "balanced_accuracy" else "min")


def test_primary_config():
    result = run_evaluator(HILL, EXAMPLES / "baseline")
    primary = {c["name"]: c["value"] for c in result["config"] if c["primary"]}
    assert primary == {"mode": "validation", "time_limit_s": 300}


def test_missing_predict_is_rejected(tmp_path):
    result = run_evaluator(HILL, tmp_path)
    assert not result["passed"]
    assert "predict.py" in result["details"]["error"]


def test_wrong_row_count_is_rejected(tmp_path):
    (tmp_path / "predict.py").write_text(
        "import argparse, pandas as pd\n"
        "p = argparse.ArgumentParser()\n"
        "[p.add_argument(f, required=True) for f in ('--train', '--valid', '--test', '--out')]\n"
        "a = p.parse_args()\n"
        "t = pd.read_csv(a.test, usecols=['id']).iloc[:-1]\n"
        "pd.DataFrame({'id': t['id'], 'prediction': 0}).to_csv(a.out, index=False)\n"
    )
    result = run_evaluator(HILL, tmp_path)
    assert not result["passed"]
    assert "rows" in result["details"]["error"]


def test_test_features_have_no_target():
    header = pd.read_csv(HILL / "data" / "test_features.csv", nrows=0).columns
    assert "target" not in header
    assert "id" in header
