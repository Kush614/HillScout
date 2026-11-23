"""Baseline: predict the majority class (classification) or the mean (regression)."""

import argparse
import json
from pathlib import Path

import pandas as pd

parser = argparse.ArgumentParser()
for flag in ("--train", "--valid", "--test", "--out"):
    parser.add_argument(flag, required=True)
args = parser.parse_args()

task = json.loads((Path(args.train).parent / "task.json").read_text())
is_cls = task["task_type"] == "classification"
dtype = {"target": str} if is_cls else None
train = pd.concat([pd.read_csv(args.train, dtype=dtype), pd.read_csv(args.valid, dtype=dtype)])
test = pd.read_csv(args.test, usecols=["id"])

if is_cls:
    value = train["target"].value_counts().idxmax()
else:
    value = float(train["target"].mean())

pd.DataFrame({"id": test["id"], "prediction": value}).to_csv(args.out, index=False)
