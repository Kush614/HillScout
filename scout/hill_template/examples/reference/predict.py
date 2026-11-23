"""Reference: scikit-learn histogram gradient boosting with default settings.

Text columns are ordinal-encoded over train+valid+test categories. Trains on
train + valid together.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

parser = argparse.ArgumentParser()
for flag in ("--train", "--valid", "--test", "--out"):
    parser.add_argument(flag, required=True)
args = parser.parse_args()

task = json.loads((Path(args.train).parent / "task.json").read_text())
is_cls = task["task_type"] == "classification"
dtype = {"target": str} if is_cls else None
train = pd.concat([pd.read_csv(args.train, dtype=dtype), pd.read_csv(args.valid, dtype=dtype)], ignore_index=True)
test = pd.read_csv(args.test)

y = train["target"]
X = train.drop(columns=["id", "target"])
Xt = test.drop(columns=["id"])[X.columns]

categorical = []
for col in X.columns:
    if not (pd.api.types.is_numeric_dtype(X[col]) and pd.api.types.is_numeric_dtype(Xt[col])):
        cats = pd.Index(pd.concat([X[col], Xt[col]]).dropna().astype(str).unique())
        X[col] = pd.Categorical(X[col].astype("string"), categories=cats).codes.astype(float)
        Xt[col] = pd.Categorical(Xt[col].astype("string"), categories=cats).codes.astype(float)
        X.loc[X[col] < 0, col] = np.nan
        Xt.loc[Xt[col] < 0, col] = np.nan
        categorical.append(len(cats) <= 255)
    else:
        categorical.append(False)

Model = HistGradientBoostingClassifier if is_cls else HistGradientBoostingRegressor
model = Model(random_state=0, categorical_features=np.array(categorical) if any(categorical) else None)
model.fit(X, y)
pd.DataFrame({"id": test["id"], "prediction": model.predict(Xt)}).to_csv(args.out, index=False)
