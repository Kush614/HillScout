"""Hill README, written for the agent that will climb it.

Only the two-sentence task description may come from an LLM (anthropic SDK if
ANTHROPIC_API_KEY is set, else `claude -p`). Every number in the README is
filled in from measurements. An LLM reply containing a digit is discarded, so
it cannot slip a number in.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

import pandas as pd

from .build import TIME_LIMIT_S, Prepared
from .sources.base import Candidate

LLM_MODEL = "claude-haiku-5-5"


def _schema_lines(frame: pd.DataFrame, limit: int = 40) -> str:
    cols = [c for c in frame.columns if c not in ("id",)]
    lines = []
    for c in cols[:limit]:
        kind = "number" if pd.api.types.is_numeric_dtype(frame[c]) else "text/category"
        lines.append(f"- {c} ({kind})")
    if len(cols) > limit:
        lines.append(f"- ... and {len(cols) - limit} more")
    return "\n".join(lines)


def _prompt(cand: Candidate, prep: Prepared) -> str:
    source_desc = re.sub(r"\s+", " ", cand.description)[:1200]
    return (
        "Write exactly two plain sentences describing a machine-learning task for an agent that will try to "
        "improve a model on it. Sentence one: what each row is and what must be predicted. Sentence two: why "
        "it is a useful or interesting prediction problem. Do not use any digits or numbers, do not invent "
        "facts not supported below, no markdown, no preamble.\n\n"
        f"Dataset title: {cand.title}\n"
        f"Task: {prep.task_type}, predict the column `target` (originally `{prep.original_target}`).\n"
        f"Source description (may be truncated):\n{source_desc}\n\n"
        f"Columns:\n{_schema_lines(prep.frame)}\n"
    )


def _clean(text: str) -> str | None:
    text = re.sub(r"\s+", " ", (text or "")).strip().strip('"')
    if not text or re.search(r"\d", text) or len(text) > 600:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", text)
    if not 1 <= len(sentences) <= 3:
        return None
    return " ".join(sentences[:2])


def llm_task_sentences(cand: Candidate, prep: Prepared, log=print) -> tuple[str | None, str]:
    prompt = _prompt(cand, prep)
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic

            msg = anthropic.Anthropic().messages.create(
                model=LLM_MODEL, max_tokens=200, messages=[{"role": "user", "content": prompt}])
            out = _clean("".join(b.text for b in msg.content if getattr(b, "type", "") == "text"))
            if out:
                return out, "anthropic SDK"
        except Exception as exc:  # noqa: BLE001
            log(f"describe: anthropic SDK failed ({type(exc).__name__}); trying claude -p")
    if shutil.which("claude"):
        try:
            proc = subprocess.run(["claude", "-p", prompt], capture_output=True, text=True, timeout=120)
            out = _clean(proc.stdout)
            if out:
                return out, "claude -p"
            log("describe: claude -p reply rejected (empty, contained digits, or wrong shape)")
        except Exception as exc:  # noqa: BLE001
            log(f"describe: claude -p failed ({type(exc).__name__})")
    return None, "template"


def is_private(cand: Candidate) -> bool:
    return cand.source == "private"


def source_name(cand: Candidate) -> str:
    """Where the data came from, in words: OpenML, Kaggle or the web."""
    return {"openml": "OpenML", "manual": "OpenML", "kaggle": "Kaggle", "web": "the web"}.get(cand.source, cand.source)


def template_sentences(cand: Candidate, prep: Prepared) -> str:
    what = "the class label" if prep.task_type == "classification" else "a numeric value"
    origin = f"the dataset '{cand.title}' supplied by the hill owner" if is_private(cand) \
        else f"the {source_name(cand)} dataset '{cand.title}'".replace("the the web dataset", "the web dataset")
    return (f"Each row is one record from {origin}, and you predict {what} in the "
            f"column `target` (originally `{prep.original_target}`) from the other columns. The test rows' labels "
            f"are held out, so the score shows how well a model trained on the visible rows works on new ones.")


def subtitle(cand: Candidate, prep: Prepared) -> str:
    """One plain sentence under 200 characters, no markdown: the hill's subtitle on the site."""
    title = re.sub(r"[_-]+", " ", cand.title).strip()
    where = "" if is_private(cand) else f" from {source_name(cand)}"
    if prep.task_type == "classification":
        s = f"Predict the class of each row in the {title} table{where}, scored by balanced accuracy on held-out rows."
    else:
        s = f"Predict a numeric value for each row of the {title} table{where}, scored by RMSE on held-out rows."
    if len(s) >= 200:
        s = f"Predict the target column of a {'private' if is_private(cand) else source_name(cand)} table, scored by {'balanced accuracy' if prep.task_type == 'classification' else 'RMSE'} on held-out rows."
    return s


def fmt(v: float | None) -> str:
    return "pending" if v is None else f"{v:.4f}"


def render_readme(name: str, cand: Candidate, prep: Prepared, parts: dict, task_text: str,
                  baseline: float | None, reference: float | None, eval_seconds: float | None) -> str:
    n_train, n_valid, n_test = len(parts["train"]), len(parts["valid"]), len(parts["test_features"])
    n_feat = parts["test_features"].shape[1] - 1
    if prep.task_type == "classification":
        classes = parts["train"]["target"].nunique()
        metric_line = (f"**Balanced accuracy** (mean per-class recall) over the {classes} classes in `target`. "
                       "Direction: **max** (higher is better).")
    else:
        metric_line = "**RMSE** (root mean squared error) of `prediction` against `target`. Direction: **min** (lower is better)."
    notes = "".join(f"- {n}\n" for n in prep.notes) or "- none\n"
    source_line = (f'- Source: supplied by the hill owner ("{cand.title}"); this hill is private'
                   if is_private(cand) else f'- Source: {cand.url} ({source_name(cand)} dataset {cand.source_id}, "{cand.title}")')
    return f"""# {name}

{subtitle(cand, prep)}

## The task
{task_text}

## Files
```
data/train.csv          {n_train} rows: id, {n_feat} feature columns, target
data/valid.csv          {n_valid} rows, same columns as train (yours to use for tuning or training)
data/test_features.csv  {n_test} rows: id + the same {n_feat} feature columns, no target
data/task.json          task type, metric name and direction
eval.py                 the evaluator (read it; it does not change)
examples/baseline/      majority-class / mean submission
examples/reference/     scikit-learn HistGradientBoosting with default settings
private/                held out, do not read
```

## Submission contract
A submission is a directory containing `predict.py`. The evaluator copies it to a
fresh temporary directory and runs:

```
python predict.py --train data/train.csv --valid data/valid.csv \\
                  --test data/test_features.csv --out <path>/predictions.csv
```

`predict.py` must write `predictions.csv` at the `--out` path with exactly the
columns `id,prediction` and one row for every id in `test_features.csv`. Any
missing file, wrong row count, unknown or duplicate id, or missing value fails
the run with a reason. Available libraries: numpy, pandas, scikit-learn.

## Metric
{metric_line}
Validation mode (the default) scores a fixed public half of the test rows;
`hills eval --final` scores the other, private half. You never learn which row is
in which half, so predict every row as well as you can.

## Time limit
`predict.py` gets **{TIME_LIMIT_S} seconds** (`time_limit_s` param), measured and
enforced by the evaluator. Over the limit counts as a failed run.

## Scores to beat (validation mode)
| submission | {prep.metric} |
|---|---|
| baseline | {fmt(baseline)} |
| reference (HistGradientBoosting, defaults) | {fmt(reference)} |

Reference eval wall time on the build machine: {f'{eval_seconds:.1f}' if eval_seconds else 'pending'} s.

## Source and license
{source_line}
- License: {cand.license}
- Target column was `{prep.original_target}`, renamed to `target`; ids are random and carry no signal.
- Preparation notes:
{notes}
## Held out
The private test labels live in `private/` and are held out: they are never shown to the climber.

_Built automatically by Hill Scout._
"""
