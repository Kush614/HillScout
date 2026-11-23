"""Fast, network-free tests for Hill Scout, on a small synthetic dataframe."""

import importlib.util
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import re

import pytest

from scout import learn
from scout.build import TEMPLATE, prepare, split
from scout.select import bucket_of, select
from scout.sources.base import Candidate, license_allows_redistribution


def _frame(task: str, n: int = 1200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    x1, x2 = rng.normal(size=n), rng.normal(size=n)
    color = rng.choice(["red", "green", "blue"], size=n)
    if task == "classification":
        y = np.where(x1 + 0.5 * x2 + rng.normal(scale=0.5, size=n) > 0, "yes", "no")
    else:
        y = 3 * x1 - x2 + rng.normal(scale=0.3, size=n)
    return pd.DataFrame({"x1": x1, "x2": x2, "color": color, "label": y})


def _cand(task: str, key: str = "1", **kw) -> Candidate:
    return Candidate(source="openml", source_id=key, title=f"synthetic-{key}", url="https://example.org",
                     license="CC0", n_rows=1200, n_features=3, task_type=task, target="label", **kw)


@pytest.fixture(params=["classification", "regression"])
def task(request):
    return request.param


@pytest.fixture
def hill(tmp_path, task):
    """A hill directory laid out as build.write_hill does, without the hills CLI."""
    prep = prepare(_frame(task), _cand(task))
    parts = split(prep)
    h = tmp_path / "hill"
    shutil.copytree(TEMPLATE, h, ignore=shutil.ignore_patterns("__pycache__"))
    (h / "data").mkdir()
    (h / "private").mkdir()
    for k in ("train", "valid", "test_features"):
        parts[k].to_csv(h / "data" / f"{k}.csv", index=False)
    parts["test_labels"].to_csv(h / "private" / "test_labels.csv", index=False)
    (h / "data" / "task.json").write_text(json.dumps(
        {"task_type": prep.task_type, "metric": prep.metric, "direction": prep.direction}))
    return h, prep, parts


def _load_eval(h: Path):
    spec = importlib.util.spec_from_file_location(f"hill_eval_{id(h)}", h / "eval.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.eval


def _write_submission(d: Path, body: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "predict.py").write_text(
        "import argparse, pandas as pd\np = argparse.ArgumentParser()\n"
        "[p.add_argument(f, required=True) for f in ('--train', '--valid', '--test', '--out')]\n"
        "a = p.parse_args()\nt = pd.read_csv(a.test, usecols=['id'])\n" + body)
    return d


# -- split ---------------------------------------------------------------------

def test_split_is_deterministic_and_disjoint(task):
    prep = prepare(_frame(task), _cand(task))
    a, b = split(prep, seed=7), split(prep, seed=7)
    for k in a:
        pd.testing.assert_frame_equal(a[k], b[k])
    ids = [set(a["train"]["id"]), set(a["valid"]["id"]), set(a["test_features"]["id"])]
    assert not (ids[0] & ids[1]) and not (ids[0] & ids[2]) and not (ids[1] & ids[2])
    assert sum(map(len, ids)) == len(prep.frame)
    assert abs(len(ids[0]) / len(prep.frame) - 0.6) < 0.01
    assert set(a["test_labels"]["split"]) == {"public", "private"}


def test_split_changes_with_seed(task):
    prep = prepare(_frame(task), _cand(task))
    assert not split(prep, seed=1)["train"]["id"].equals(split(prep, seed=2)["train"]["id"])


def test_classification_split_is_stratified():
    prep = prepare(_frame("classification"), _cand("classification"))
    parts = split(prep)
    overall = (prep.frame["target"] == "yes").mean()
    for k in ("train", "valid"):
        assert abs((parts[k]["target"] == "yes").mean() - overall) < 0.03
    assert abs((parts["test_labels"]["target"] == "yes").mean() - overall) < 0.03


def test_test_features_have_no_target(task):
    parts = split(prepare(_frame(task), _cand(task)))
    assert "target" not in parts["test_features"].columns
    assert "label" not in parts["test_features"].columns
    assert "id" in parts["test_features"].columns


# -- evaluator -----------------------------------------------------------------

def test_baseline_passes(hill, tmp_path):
    h, prep, _ = hill
    report = _load_eval(h)(h / "examples" / "baseline")
    assert report["passed"], report["details"]
    assert report["metrics"][0]["name"] == prep.metric


def test_missing_file_fails(hill, tmp_path):
    h, _, _ = hill
    empty = tmp_path / "empty"
    empty.mkdir()
    r = _load_eval(h)(empty)
    assert r["passed"] is False and "predict.py" in r["details"]["error"]


def test_missing_predictions_fails(hill, tmp_path):
    h, _, _ = hill
    sub = _write_submission(tmp_path / "noout", "pass\n")
    r = _load_eval(h)(sub)
    assert r["passed"] is False and "predictions.csv" in r["details"]["error"]


def test_wrong_row_count_fails(hill, tmp_path):
    h, _, _ = hill
    sub = _write_submission(tmp_path / "short",
                            "pd.DataFrame({'id': t['id'][:-3], 'prediction': 0}).to_csv(a.out, index=False)\n")
    r = _load_eval(h)(sub)
    assert r["passed"] is False and "rows" in r["details"]["error"]


def test_wrong_ids_fail(hill, tmp_path):
    h, _, _ = hill
    sub = _write_submission(tmp_path / "ids",
                            "pd.DataFrame({'id': t['id'] + 1, 'prediction': 0}).to_csv(a.out, index=False)\n")
    r = _load_eval(h)(sub)
    assert r["passed"] is False and "ids" in r["details"]["error"]


def test_metric_direction_matches_metric(hill):
    h, prep, _ = hill
    r = _load_eval(h)(h / "examples" / "baseline")
    m = r["metrics"][0]
    assert (m["name"], m["direction"]) in {("balanced_accuracy", "max"), ("rmse", "min")}
    assert m["direction"] == prep.direction


def test_final_mode_scores_private_half(hill):
    h, _, parts = hill
    ev = _load_eval(h)
    v, f = ev(h / "examples" / "baseline"), ev(h / "examples" / "baseline", final=True)
    assert v["passed"] and f["passed"]
    n_pub = (parts["test_labels"]["split"] == "public").sum()
    assert v["details"]["rows_scored"] == n_pub
    assert f["details"]["rows_scored"] == len(parts["test_labels"]) - n_pub


def test_time_limit_enforced(hill, tmp_path):
    h, _, _ = hill
    sub = _write_submission(tmp_path / "slow", "import time; time.sleep(30)\n")
    r = _load_eval(h)(sub, time_limit_s=2)
    assert r["passed"] is False and "time limit" in r["details"]["error"]


# -- selection and learning ----------------------------------------------------

def test_selection_never_returns_seen():
    cands = [_cand("classification", key=str(i), extra={"family": f"f{i}"}) for i in range(20)]
    seen = {c.key for c in cands[::2]}
    for s in range(10):
        picks = select(cands, {}, seen, np.random.default_rng(s), 50)
        assert picks and all(p.cand.key not in seen for p in picks)
        assert len(picks) == 10


def test_selection_one_per_family():
    cands = [_cand("classification", key=str(i), extra={"family": "same"}) for i in range(5)]
    assert len(select(cands, {}, set(), np.random.default_rng(0), 5)) == 1


def test_selection_skips_families_from_earlier_runs():
    cands = [_cand("classification", key=str(i), extra={"family": f"f{i % 3}"}) for i in range(6)]
    picks = select(cands, {}, set(), np.random.default_rng(0), 6, seen_families={"f0"})
    assert {p.cand.extra["family"] for p in picks} == {"f1", "f2"}


def _outcome(bucket: str, shipped: bool, hill: str = "h") -> dict:
    return {"bucket": bucket, "stage": "gates", "shipped": shipped, "hill": hill,
            "first_failed_gate": None if shipped else "headroom"}


def test_bucket_pass_raises_and_fail_lowers_rate():
    b = bucket_of(_cand("classification"))
    prior = learn.compute_buckets([_outcome(b, True), _outcome(b, False)], [])[b]["rate"]
    up = learn.compute_buckets([_outcome(b, True), _outcome(b, False), _outcome(b, True)], [])[b]["rate"]
    down = learn.compute_buckets([_outcome(b, True), _outcome(b, False), _outcome(b, False)], [])[b]["rate"]
    assert up > prior > down


def test_engagement_adds_success():
    b = bucket_of(_cand("regression"))
    outs = [_outcome(b, True, "scout-a"), _outcome(b, False)]
    plain = learn.compute_buckets(outs, [])[b]
    climbed = learn.compute_buckets(outs, [{"hill": "scout-a", "climbs": "2", "stars": "0"}])[b]
    assert climbed["engagement_bonus"] == 1 and climbed["rate"] > plain["rate"]


def test_metadata_skips_do_not_move_buckets():
    b = bucket_of(_cand("classification"))
    out = learn.compute_buckets([{"bucket": b, "stage": "enrich", "shipped": False}], [])
    assert b not in out


def test_license_rules():
    assert license_allows_redistribution("CC0")[0]
    assert license_allows_redistribution("Public")[0]
    assert license_allows_redistribution("CC BY 4.0")[0]
    assert not license_allows_redistribution("")[0]
    assert not license_allows_redistribution("CC BY-NC 4.0")[0]
    assert not license_allows_redistribution("Unknown")[0]


def test_integer_coded_numeric_target_becomes_classification():
    df = _frame("classification")
    df["label"] = (df["label"] == "yes").astype("uint8")
    prep = prepare(df, _cand("regression"))
    assert prep.task_type == "classification" and prep.metric == "balanced_accuracy"
    assert any("integer values" in n for n in prep.notes)


def test_difficulty_labels():
    from scout.catalog import difficulty
    assert difficulty({"metric": "balanced_accuracy", "baseline": 0.5, "reference": 0.9})[0] == "approachable"
    assert difficulty({"metric": "balanced_accuracy", "baseline": 0.5, "reference": 0.6})[0] == "hard"
    assert difficulty({"metric": "rmse", "baseline": 100.0, "reference": 70.0})[0] == "moderate"
    assert difficulty({"metric": "rmse", "baseline": None, "reference": 1.0})[0] == "unknown"


def test_engagement_slug_parsing():
    from scout.engagement import slug_from_url
    assert slug_from_url("https://app.autolab.ai/hills/kush614/scout-churn-40701") == "kush614/scout-churn-40701"
    assert slug_from_url("not a url") is None


def test_private_csv_candidate(tmp_path):
    from scout.build import hill_name
    from scout.describe import subtitle
    from scout.sources.private_csv import PrivateCsvSource
    path = tmp_path / "acme_orders.csv"
    _frame("classification").to_csv(path, index=False)
    cand = PrivateCsvSource(path).candidate("label", title="acme orders")
    assert hill_name(cand) == "private-acme-orders"
    assert cand.extra["allow_llm"] is False
    prep = prepare(PrivateCsvSource(path).load(cand), cand)
    sub = subtitle(cand, prep)
    assert "OpenML" not in sub and len(sub) < 200
    with pytest.raises(Exception):
        PrivateCsvSource(path).candidate("no_such_column")


def test_site_export_uses_real_records_and_hides_private_files(tmp_path):
    from scout.site import export, write_site
    root = Path(__file__).resolve().parents[1]
    if not (root / "state" / "outcomes.jsonl").exists():
        pytest.skip("no scout state yet")
    d = export(root)
    assert d["totals"]["shipped"] == len(d["hills"])
    for h in d["hills"]:
        assert "target" in h["preview"][0]
        assert len(h["gates"]) == 8 and all(g["passed"] for g in h["gates"])
        assert not h["hill"].startswith("private-")
    out = write_site(root, tmp_path / "site")
    names = {p.name for p in out.rglob("*")}
    assert {"index.html", "app.js", "scene.js", "server.py", "site.json"} <= names
    assert not any("test_labels" in n for n in names)


# ---- importing from Kaggle, OpenML and web links (scout/remote.py) ----

def test_resolve_understands_kaggle_openml_and_links():
    from scout import remote as R
    assert R.resolve("blastchar/telco-customer-churn") == {"kind": "kaggle", "owner": "blastchar", "slug": "telco-customer-churn"}
    assert R.resolve("https://www.kaggle.com/datasets/uciml/iris?select=Iris.csv")["slug"] == "iris"
    assert R.resolve("openml:537") == {"kind": "openml", "id": "537"}
    assert R.resolve("https://www.openml.org/d/537")["id"] == "537"
    assert R.resolve("https://github.com/a/b/blob/main/x.csv")["url"] == "https://raw.githubusercontent.com/a/b/main/x.csv"
    assert "/resolve/" in R.resolve("https://huggingface.co/datasets/a/b/blob/main/t.csv")["url"]
    with pytest.raises(R.ImportError_, match="competition"):
        R.resolve("https://www.kaggle.com/competitions/titanic")
    with pytest.raises(R.ImportError_):
        R.resolve("hello there")


def test_safe_get_refuses_internal_addresses_and_odd_ports():
    from scout import remote as R
    for url in ("http://localhost/", "http://127.0.0.1/", "http://169.254.169.254/latest/", "http://10.0.0.1/", "ftp://example.org/x"):
        with pytest.raises(R.ImportError_):
            R.safe_get(url)
    with pytest.raises(R.ImportError_, match="ports"):
        R.safe_get("https://example.org:8443/x.csv")


def test_tables_from_zip_gzip_and_semicolon_text():
    import gzip as gz
    import io as _io
    import zipfile as zf
    from scout import remote as R
    body = "a;b;churn\n" + "".join(f"{i};{i*2};{i%2}\n" for i in range(600))
    t, files = R.pick_table(body.encode(), "x.csv")
    assert t["header"] == ["a", "b", "churn"] and t["total_rows"] == 600 and t["delimiter"] == ";"
    assert t["csv"].splitlines()[1] == "0,0,0"  # re-emitted as plain comma CSV
    buf = _io.BytesIO()
    with zf.ZipFile(buf, "w") as z:
        z.writestr("small.csv", "x,y\n1,2\n")
        z.writestr("big.csv", body.replace(";", ","))
        z.writestr("__MACOSX/._big.csv", "junk")
    t, files = R.pick_table(buf.getvalue(), "d.zip")
    assert t["file"] == "big.csv" and len(files) == 2
    assert R.pick_table(buf.getvalue(), "d.zip", "small.csv")[0]["total_rows"] == 1
    assert R.pick_table(gz.compress(body.encode()), "x.csv.gz")[0]["total_rows"] == 600
    with pytest.raises(R.ImportError_, match="web page"):
        R.pick_table(b"<!DOCTYPE html><html>hi</html>", "x")


def test_target_guess_and_kaggle_licences():
    from scout import remote as R
    assert R.guess_target(["id", "age", "Churn"])[0] == "Churn"
    assert R.guess_target(["pclass", "class", "survived"])[0] == "survived"
    assert R.guess_target(["x", "y"])[0] == "y"
    assert R.guess_target(["x", "y"], strict=True)[0] == ""
    assert R.guess_target(["a", "b"], declared="b")[0] == "b"
    ok = lambda n: R.license_allows_redistribution(R.kaggle_license_canonical(n))[0]
    assert ok("CC0: Public Domain") and ok("Attribution 4.0 International (CC BY 4.0)") and ok("CC BY-SA 4.0")
    assert ok("Database: Open Database, Contents: Database Contents")
    assert not ok("CC BY-NC-SA 4.0") and not ok("Data files © Original Authors") and not ok("Other (specified in description)")


def test_candidates_file_lines_for_kaggle_and_web():
    from scout.sources import kaggle, manual, web
    assert kaggle.parse_line("kaggle:harlfoxem/housesalesprediction target=price  # houses") == ("harlfoxem", "housesalesprediction", "price")
    assert kaggle.parse_line("openml:44") is None
    assert web.parse_line("url:https://x.org/d.csv target=y license=CC0") == {"url": "https://x.org/d.csv", "target": "y", "license": "CC0"}
    assert manual.parse_line("kaggle:a/b-2020") is None


def test_hill_names_are_valid_for_every_source():
    from scout.build import hill_name
    from scout.sources.base import Candidate
    for c in (Candidate("kaggle", "harlfoxem/housesalesprediction", "House Sales in King County", "u"),
              Candidate("web", "ab12cd34ef", "penguins", "u"), Candidate("openml", "44", "spambase", "u")):
        assert re.fullmatch(r"[a-z0-9._-]+", hill_name(c)), hill_name(c)
    assert hill_name(Candidate("openml", "44", "spambase", "u")) == "scout-spambase-44"


def test_browser_model_finds_known_signal():
    import shutil, subprocess as sp
    if not shutil.which("node"):
        pytest.skip("node not installed")
    root = Path(__file__).resolve().parents[1]
    out = json.loads(sp.run(["node", str(root / "tests/js/ml_check.mjs")], capture_output=True, text=True, check=True).stdout)
    assert out["task"] == "yesno" and out["positive"] == "Yes"
    assert out["auc"] > 0.7 and out["grade"] in ("useful", "strong")
    assert "customer_id" in out["dropped"] and set(out["top"]) == {"months", "plan"}
    assert out["unlabelled"] == 40 and out["predicted"] == 40 and set(out["risks"]) <= {"High", "Medium", "Low"}
    assert out["regTask"] == "number" and out["regGrade"] == "strong" and out["regSkill"] > 0.6


def test_readme_text_names_the_real_source():
    from types import SimpleNamespace
    from scout.describe import subtitle, template_sentences
    from scout.sources.base import Candidate
    prep = SimpleNamespace(task_type="classification", original_target="Attrition")
    k = Candidate("kaggle", "pavansubhasht/ibm-hr", "IBM HR Analytics", "https://www.kaggle.com/datasets/x/y")
    assert "from Kaggle" in subtitle(k, prep) and "OpenML" not in subtitle(k, prep)
    assert "Kaggle dataset" in template_sentences(k, prep)
    assert "from OpenML" in subtitle(Candidate("openml", "44", "spambase", "u"), prep)


def test_ask_scout_helper_answers_from_real_data(tmp_path):
    """The site's chat helper: pinned questions, typed questions, name lookups, safe fallback."""
    import shutil
    import subprocess as sp
    if not shutil.which("node"):
        pytest.skip("node not installed")
    from scout.site import export
    root = Path(__file__).resolve().parents[1]
    data = tmp_path / "site.json"
    data.write_text(json.dumps(export(root)))
    r = sp.run(["node", str(root / "tests/js/chat_check.mjs"), str(data)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
