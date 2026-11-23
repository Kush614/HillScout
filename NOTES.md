# NOTES: what M0 found about `hills` (verified 2026-11-22, hills 0.12.1)

## Install
- `uv tool install hills` -> hills 0.12.1. The tool runs evaluators in uv-managed
  envs under `~/.autolab/hills/envs/<hill>/<tree-hash>/` (Python 3.14 here), built from the
  hill's own `pyproject.toml`. The first eval of each new tree hash pays about 20 s to build the env.
- No Homebrew on this Mac. git-lfs 3.8.1 was installed from the GitHub release binary into
  `~/.local/bin`, then `git lfs install`.
- The PyPI page lists a `setup` command. **It is not in 0.12.1**: the subcommands are new, check,
  status, commit, log, describe, eval, attempts, verify, list, examples, bundle, unbundle, home.
- Templates (`hills examples`): `circle-packing`, `dataset`, `default`, `nanogpt-10min`.
- The circle-packing hello world works: check -> commit -> eval gives sum_radii=2.5414, PASSED.

## Real `hill.yaml` fields (from the templates, nothing invented)
| field | seen in | notes |
|---|---|---|
| `spec_version` | all | 2 = default/circle-packing, 3 = container image, 4 = dataset (git+LFS) |
| `name`, `version` | all | |
| `metrics: [{name, direction}]` | all | every passing report must lead with these, in order |
| `watchdog_timeout_s` | all | hard kill only; the semantic time limit belongs in eval.py |
| `params: {k: {type, default, min, max, help}}` | all | typed, passed to `eval()` as kwargs, overridable with `-p` |
| `blobs: {threshold, track}` | default (commented) | large files bound by hash, kept out of git |
| `exclusive: gpu` | default (commented) | |
| `environment: {image}` | default (commented) | spec 3 only |

So the hill's time limit is a typed param, `time_limit_s` (default 300), enforced by eval.py,
which launches the submission as a subprocess and owns the clock.

## Layout and contract (as found)
- `hills new` makes `.autolab/hills/<name>/` with hill.yaml, pyproject.toml, README.md, eval.py,
  examples/baseline, tests/test_hill.py, private/, and `.vc/` (or `.git/` for spec 4).
- `hills commit` runs the check (including `tests/`), writes `uv.lock`, `private.lock` and
  `blobs.lock`, and freezes a tree hash.
- `hills eval` scores HEAD, and a dirty tree is an error unless you pass `--force` or `--current`.
  `--final` = the held-out test mode, `-p k=v` overrides a param, and `--json` prints a signed report.
- In tests, `from hills import run_evaluator` -> `run_evaluator(hill, submission, **params)`.

## Important: the `dataset` template does not fit this build
- The `dataset` template is **spec 4: a git+LFS repo**. `hills bundle` refuses it with:
  "probe-ds is a spec-4 hill: it is distributed as a git repository with git-LFS, not a bundle.
  Push it to AutoLab (or `git clone` + `git lfs pull`) instead of `hills bundle`."
- The template's own `data/dataset.json` is an unsmudged LFS pointer, so its own test fails
  out of the box.
- **Decision:** scout hills use the **spec-2 `default` template**, with `data/` and `private/`
  under the `blobs` rule. `hills bundle` packs them into a `.hill.tar` that contains git.bundle,
  locked/data/*.csv and locked/private/test_labels.csv (checked by hand).

## Publish path (resolved later on 2026-11-22)
- The `hills` CLI has no publish command. Its bundled skill names `autolab hills push`.
- First search, which came up empty: npm `autolab@0.2.0` is a Claude prompt wrapper, PyPI
  `autolab` is an unrelated lab-automation package, and PyPI `autolab-ai` belongs to autolab.sh.
- **The real CLI is served by the control node:** `curl -fsSL https://app.autolab.ai/install.sh | sh`
  installs `autolab` (0.1.0.post1795037379 here) from https://app.autolab.ai/pkg/latest.
  Sign in with `autolab --url https://app.autolab.ai login` (browser) and add the skill with
  `autolab install claude`.
- `autolab hills check/commit/push` run the OSS `hills` at a pinned version. The scout's spec-2
  hills pass `autolab hills check` unchanged.
- `autolab hills push <name>` uploads the latest commit and prints `On the web: <url>`. New hills
  are **private**. `autolab hills settings <name> --public` lists one on the hub.
- All 6 shipped hills are pushed (private) under `kush614/`. `scout run` now pushes every newly
  shipped hill as private (set `SCOUT_PUSH=0` to turn it off). Making a hill public stays a human call.
- The hub uses a README's first paragraph as the hill's subtitle: one plain sentence under 200
  characters. `describe.subtitle()` writes it.
- Climb and star counts: no read API has been found yet. `autolab hills climbs <owner/name>`
  lists climbs and could feed `state/engagement.csv` later.

## OpenML
- `openml` 0.15.1 is installed, but `openml.tasks.list_tasks(...)` paged the whole catalogue and
  was still running after 5 minutes. Discovery therefore calls the filtered REST listing directly:
  `/api/v1/json/data/list/status/active/number_instances/1000..200000/number_features/4..200/limit/1000/offset/N`.
  That is about 2,600 datasets at about 35 s per page of 1,000, cached per day in `state/cache/`.
- The per-dataset description (`/data/<id>`) gives licence, default_target_attribute,
  ignore_attribute, row_id_attribute and parquet_url. It takes about 6 s each, also cached.
- The newest uploads (highest ids) are noisy: series of near-duplicates
  (`estudios-buscadores-*-loteN-2026`) and synthetic copies of classic sets (`TabClustPFN-*`).
  The scout takes at most one per name family per run, and the gates do the rest.

## Gotchas hit while building
- pandas 3 in the hill env loads strings with the `str` dtype, not `object`. Use `is_numeric_dtype`.
- Kaggle: there are no credentials on this machine, so that source reports itself unavailable.
- `ANTHROPIC_API_KEY` is not set, so the README sentences come from `claude -p`, with a template
  fallback.
