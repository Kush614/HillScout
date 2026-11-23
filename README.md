<p align="center"><img src="docs/screenshots/banner.png" alt="Hill Scout: public data in, verified AI challenges out" width="100%"></p>

# Hill Scout

**Public data in. Verified AI challenges out.**

Hill Scout is an autonomous agent that finds public tabular datasets on OpenML, Kaggle and the open web, turns each one into a scored prediction challenge (a **hill**) for AI agents on [AutoLab](https://app.autolab.ai), and ships it only if it passes **eight quality checks**. A companion website shows the catalogue as an interactive 3D hill range. It also gives non-technical users **no-code predictions** from any spreadsheet, with the model running in their browser.

- 🌐 **Live site:** https://hill-scout.egbe.app
- 🧮 **No-code Predict:** https://hill-scout.egbe.app/#/predict
- ⛰️ **Public hills on AutoLab:** for example [scout-churn-40701](https://app.autolab.ai/hills/kush614/scout-churn-40701) (all 9 are listed [below](#the-hills-it-has-shipped))

| | |
|---|---|
| Runs so far | 3 |
| Datasets attempted | 16 |
| Hills shipped (passed all 8 gates) | **9**, all public on AutoLab |
| Rejected by the gates | 7 (leaks, trivially easy tasks, licences, unusable targets) |
| Sources | OpenML, Kaggle (public API, no login), CSV links |
| Hosting spend (Egbe) | $0 against a self-imposed $15 cap |
| Tests | 43 (`uv run pytest`) |

---

## Contents

- [Why](#why)
- [What it does](#what-it-does)
- [The website](#the-website)
- [The hills it has shipped](#the-hills-it-has-shipped)
- [How it works](#how-it-works)
- [Quick start](#quick-start)
- [Commands](#commands)
- [Configuration and data sources](#configuration-and-data-sources)
- [Safety and privacy](#safety-and-privacy)
- [Repository layout](#repository-layout)
- [Deploying the site](#deploying-the-site)
- [Testing](#testing)
- [Lessons learned](#lessons-learned)
- [Roadmap](#roadmap)

---

## Why

AI agents need fresh, trustworthy tasks to be measured on, and hand-building evaluations is slow. Many public datasets also make bad tests:
- **Leaks:** one column gives the answer away.
- **Trivial:** a default model scores almost perfectly.
- **Unusable:** the licence doesn't allow redistribution.

Meanwhile, the people who own data (a shop owner, an HR lead, a loan officer) can't use any of these tools without writing code. Hill Scout tackles both problems: it builds **gated, verified challenges** automatically, and it gives anyone **plain-English predictions** from a spreadsheet.

## What it does

Each run of the scout goes through six steps:

```mermaid
flowchart LR
    A[Discover<br/>OpenML · Kaggle · CSV links] --> B[Pick<br/>Thompson-sampling bandit]
    B --> C[Build<br/>60/20/20 split, hidden labels,<br/>baseline + reference, evaluator]
    C --> D{8 gates}
    D -- all pass --> E[Ship<br/>bundle + push to AutoLab]
    D -- any fail --> F[Reject<br/>reason recorded]
    E --> G[Learn<br/>bucket rates, climb counts, lessons]
    F --> G
    G --> B
```

1. **Discover:** list in-scope candidates (1,000 to 200,000 rows, 4 to 200 features, classification or regression) from every available source.
2. **Pick:** a Thompson-sampling bandit draws from Beta(successes+1, failures+1) for each **bucket** (source × task × size band × feature band). It takes one candidate per name family and never repeats a family tried in an earlier run.
3. **Build:**
   - Rename the target to `target`, add a random `id`, and drop rare classes.
   - Split 60/20/20 with a fixed seed. Half of the test rows are scored during validation and the other half only at `--final`.
   - Write the evaluator, a baseline submission (majority class or mean) and a reference submission (default gradient boosting).
4. **Gate:** run all 8 checks (see the next section).
5. **Ship:**
   - Bundle the hill and push it to AutoLab. New hills start private; making one public is a human decision.
   - The README's task sentences are written by `claude -p`, with a filter that rejects any text containing digits so the model can't invent numbers.
6. **Learn:** recompute bucket success rates from every outcome so far, add a bonus for hills that real climbers have attempted, and write lessons to `state/memory.md`.

### The 8 gates

| Gate | Passes when |
|---|---|
| **Valid** | `hills check` passes and the commit succeeds |
| **Baseline scores** | the majority-class / mean submission is evaluated successfully |
| **Deterministic** | two reference evaluations differ by less than 0.005 |
| **Fast** | one reference evaluation takes under 120 s |
| **Headroom** | the reference beats the baseline by ≥ 0.05 balanced accuracy, or ≥ 10% lower RMSE |
| **Not trivial** | reference balanced accuracy < 0.98, or RMSE > 1% of the baseline's |
| **No leak** | no single feature (depth-8 tree) gets within 0.02 balanced accuracy / 2% RMSE of the reference |
| **Rejects junk** | a submission with the wrong row count is marked as failed |

Real rejections from these runs:
- **Uber Ride Analytics:** the reference scored a perfect 1.0, so it failed *not trivial*.
- **"Name That LLM" (Kaggle):** one column, `model_seen`, matched the reference's perfect score on its own, so it failed *no leak*.
- **Three OpenML regression sets:** the target was really integer class codes, so they were stopped at data preparation.
- **MedMCQA and Melbourne Airbnb:** their licences weren't on the redistribution allow-list.

## The website

Built by `scout site` from the scout's own records. Every number on it comes from `state/` and `runs/`.

### Explore: a 3D hill range (three.js)
Each peak is a shipped hill. Its **height** is the room to improve (the reference model's gain over the baseline), its **colour** is the difficulty, and the snow cap marks the reference score. You can orbit, hover for scores, click a peak to open the hill, and filter or sort the cards below. A plain-text fallback appears when WebGL is off.

![Explore: 3D hill range](docs/screenshots/explore-3d.png)

### Hill detail
This page shows:
- a **score ladder** (baseline → reference → each AutoLab climb attempt);
- the **8 gate results** with the numbers each one measured;
- a data preview with the target highlighted and the test labels never shown;
- the submission rules, with copy buttons for the starter `predict.py` and the eval command.

![Hill detail](docs/screenshots/hill-detail.png)

### Predict: no code, for anyone with a spreadsheet
1. **Bring data:** click an example, paste a Kaggle or CSV link, or drop a CSV.
2. **Pick what to predict:** the page says what kind of question it is, e.g. "a yes/no question: No or Yes", and skips id and empty columns automatically.
3. **Get answers:** a from-scratch random forest trains **in a Web Worker in your browser**, so your data is never uploaded.

![Predict: plain verdict](docs/screenshots/predict-answers.png)

The answers include:
- a **plain verdict**, e.g. "check the top 20% it flags and you'll find 47% of the customers who leave (2.4× better than random)";
- **what matters most**, as sentences;
- a live **what-if** panel;
- **downloadable predictions** with a chance and a High/Medium/Low **risk** level.

On 300 held-out telco customers, **68% of "High" actually left versus 5% of "Low"**.

![Predict: what matters, what-if, downloads](docs/screenshots/predict-factors-whatif.png)

### Bring your data
Import a dataset from Kaggle, OpenML or any CSV link, or drop a file. The page shows the licence, says whether that licence allows a **public** hill or only a **private** one, and runs the scout's size, class and leak checks. Visitors can then request a private hill where AI agents compete to beat their baseline. Requests are stored in Postgres for human review.

![Bring your data: Kaggle import](docs/screenshots/bring-import.png)

### Console
Every run's picks with the bandit's draw, why each candidate was shipped or rejected, a before/after chart of bucket rates, the lessons learned, and spend against the caps.

![Console](docs/screenshots/console.png)

### On AutoLab
Each shipped hill is a real AutoLab hill. Public ones can be opened, downloaded and climbed by anyone.

![A public hill on AutoLab](docs/screenshots/autolab-public-hill.png)

## The hills it has shipped

| Hill | Source | Task | Baseline → reference |
|---|---|---|---|
| [scout-churn-40701](https://app.autolab.ai/hills/kush614/scout-churn-40701) | OpenML | classification | 0.500 → 0.868 balanced accuracy |
| [scout-spambase-44](https://app.autolab.ai/hills/kush614/scout-spambase-44) | OpenML | classification | 0.500 → 0.932 |
| [scout-houses-537](https://app.autolab.ai/hills/kush614/scout-houses-537) | OpenML | regression | RMSE 114,211 → 46,816 |
| [scout-ameshousing-analitica-47285](https://app.autolab.ai/hills/kush614/scout-ameshousing-analitica-47285) | OpenML | regression | RMSE 84,644 → 26,012 |
| [scout-check-times-47177](https://app.autolab.ai/hills/kush614/scout-check-times-47177) | OpenML | regression | RMSE 100.0 → 74.2 |
| [scout-food-calorie-searches-48248](https://app.autolab.ai/hills/kush614/scout-food-calorie-searches-48248) | OpenML | regression | RMSE 3,153 → 1,201 |
| [scout-red-wine-quality-kg-408e01](https://app.autolab.ai/hills/kush614/scout-red-wine-quality-kg-408e01) | Kaggle | classification | 0.167 → 0.338 |
| [scout-ibm-hr-analytics-emplo-kg-49a2b7](https://app.autolab.ai/hills/kush614/scout-ibm-hr-analytics-emplo-kg-49a2b7) | Kaggle | classification | 0.500 → 0.713 |
| [scout-100-000-uk-used-car-da-kg-057598](https://app.autolab.ai/hills/kush614/scout-100-000-uk-used-car-da-kg-057598) | Kaggle | regression | RMSE 4,652 → 1,179 |

## How it works

```mermaid
flowchart TB
    subgraph Scout["Scout (Python, runs daily)"]
        S1[sources/openml.py] --> SEL[select.py<br/>Thompson sampling]
        S2[sources/kaggle.py] --> SEL
        S3[sources/web.py + manual.py] --> SEL
        SEL --> BLD[build.py]
        BLD --> GT[gates.py]
        GT --> PUB[autolab hills push]
        GT --> LRN[learn.py → state/]
        R[remote.py<br/>safe fetcher] -.-> S2 & S3
    end
    subgraph Site["Site (built by scout site, hosted on Egbe)"]
        UI[app.js · scene.js three.js · predict.js]
        ML[ml.js<br/>random forest in a Web Worker]
        SRV[server.py<br/>/api/import · /api/request]
        UI --> ML
        UI --> SRV
        SRV --> R2[importer.py = remote.py]
        SRV --> PG[(Egbe Postgres)]
    end
    LRN --> UI
    PUB --> AL[(AutoLab hills)]
```

- **Scout:** Python 3.11+, pandas, scikit-learn, numpy, pyarrow, the [`hills`](https://pypi.org/project/hills/) CLI and the AutoLab CLI.
- **Hills:** spec-2 format. A submission is a folder with `predict.py`. The evaluator runs it in a fresh temp directory under a time limit (`time_limit_s`, default 300 s) and expects `predictions.csv` with `id,prediction` for every test id. Classification is scored by balanced accuracy (higher is better) and regression by RMSE (lower is better).
- **Site:** vanilla JavaScript ES modules with no build step. It uses [three.js 0.160](https://threejs.org/) for the 3D range and hand-written SVG charts. `ml.js` contains a from-scratch random forest (histogram splits, bootstrap with feature subsampling, permutation importance, AUC, top-20% capture).
- **Server:** `server.py` uses only the standard library plus `pg8000`. It serves the static files, `GET /api/import` (via `importer.py`, a copy of `scout/remote.py`) and `POST /api/request` (Postgres when `DATABASE_URL` is set). It refuses to serve its own source code.
- **Hosting:** [Egbe](https://egbe.dev) runs the Docker image on `*.egbe.app`, with Umami analytics (custom events such as `hill_click`, `predict_trained` and `predict_download`) and managed Postgres.

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/), `hills` (`uv tool install hills`) and `git-lfs` on PATH. To publish hills you also need the AutoLab CLI (`curl -fsSL https://app.autolab.ai/install.sh | sh`, then `autolab login`).

```bash
git clone https://github.com/Kush614/HillScout.git
cd HillScout
uv sync
uv run pytest                         # 43 tests, fast

# one full cycle: discover, pick, build, gate, ship (pushes are private)
SCOUT_PUSH=0 uv run scout run --max-hills 3 --max-candidates 12

# only from Kaggle
SCOUT_PUSH=0 uv run scout run --sources kaggle --max-hills 3

# build the website and preview it locally
uv run scout site
cd site && PORT=8090 REQUESTS_FILE=/tmp/requests.jsonl python3 server.py
# open http://localhost:8090
```

`SCOUT_PUSH=0` only bundles hills locally. Leave it unset to push them to AutoLab as private hills.

## Commands

| Command | What it does |
|---|---|
| `scout run [--max-hills N] [--max-candidates N] [--sources kaggle,openml,…]` | One full cycle; writes `runs/<date>-<n>/report.md` and rebuilds the site locally |
| `scout daily` | The same, with defaults; safe for cron |
| `scout report` | Rebuild `report.md` for the latest run |
| `scout private data.csv --target <col>` | Run your own CSV through the same pipeline into a gated **private** hill (logged separately, so it never moves the public bandit) |
| `scout site [--out DIR]` | Build the interactive site (Explore, Hill detail, Predict, Bring your data, Console) |
| `scout catalog` | Legacy single-page catalogue (`catalog/index.html`) |
| `scout engagement` | Refresh climb counts from AutoLab into `state/engagement.csv` |
| `scout requests` | List private-hill requests stored by the hosted site (Egbe Postgres) |

### Schedule it

```cron
# Every day at 06:15 local time. Cron has a bare PATH, so set it.
15 6 * * * cd $HOME/HillScout && PATH=$HOME/.local/bin:/usr/bin:/bin uv run scout daily >> runs/cron.log 2>&1
```

Every candidate ever attempted is recorded in `state/seen.jsonl` and is never rebuilt. Failures are recorded and skipped, not retried in a loop.

## Configuration and data sources

- **OpenML:** active datasets via the REST API (the listing is cached for the day), using each dataset's declared target and its parquet download.
- **Kaggle:** public datasets via Kaggle's public API, with **no login**.
  - Each run lists popular CSV datasets under open licence families and inspects up to 20 small ones (≤ 20 MB).
  - For each one it downloads the zip, picks the largest table, and keeps it only if a column has a clear target name (`churn`, `price`, `survived`, `target`…). Generic names like `y` are skipped in unattended discovery.
  - Competitions are never fetched, because they require accepting rules on the website.
- **`candidates.txt`:** a manual list, one entry per line:
  ```
  openml:40701
  kaggle:harlfoxem/housesalesprediction target=price
  url:https://example.org/data.csv target=label license=CC-BY-4.0
  ```
  A web link carries no licence metadata, so a `url:` line must state one.
- **Licences:** every source goes through the same allow-list: CC0, CC BY, CC BY-SA, ODbL, ODC-BY, PDDL, MIT, Apache-2.0 and public domain. Non-commercial (NC), no-derivatives (ND) and "© original authors" licences are rejected.

## Safety and privacy

- **Human approval:**
  - New hills are pushed **private**; a person makes them public (`autolab hills settings <name> --public`).
  - Private-hill requests from the site are stored for **human review**. Nothing is built or emailed automatically.
- **Hidden labels stay hidden:** test labels live only in each hill's `private/` folder. Hill folders and `.hill.tar` bundles are **not** in this repository (see `.gitignore`).
- **Safe fetching (`scout/remote.py`):** the hosted site fetches URLs that visitors type, so the fetcher:
  - allows only http/https on ports 80 and 443;
  - resolves each hostname and refuses private or internal addresses, re-checking every redirect;
  - pins the connection to the checked IP, so there's no DNS-rebinding window;
  - caps downloads at 60 MB and enforces time limits;
  - rate-limits each visitor;
  - refuses HTML pages, Parquet files and competition links with a plain message.
- **Predict is client-side:** files dropped on the Predict page never leave the browser.
- **No secrets in the repo:** Egbe keys live in an untracked `.env.local`. The database URL is injected at runtime.

## Repository layout

```
scout/
  cli.py              commands: run, daily, report, private, site, catalog, engagement, requests
  sources/
    base.py           Candidate, SkipCandidate, Source protocol
    openml.py         OpenML REST discovery + parquet load
    kaggle.py         Kaggle public API discovery, inspection, licence mapping
    web.py            url: lines from candidates.txt
    manual.py         openml: lines from candidates.txt
    private_csv.py    your own CSV -> private hill
  remote.py           safe fetcher shared with the site (Kaggle, OpenML, CSV links, zip/gzip)
  select.py           buckets + Thompson sampling
  build.py            prepare, split, write the hill (hills new / commit)
  gates.py            the 8 gates
  describe.py         README for climbers (LLM writes only two task sentences, no numbers)
  learn.py            outcomes -> buckets -> lessons (state/memory.md)
  engagement.py       climb counts from AutoLab
  report.py           runs/<id>/report.md
  site.py             exports state/ + runs/ to site/data/site.json and copies the template
  site_template/      index.html, style.css, app.js, scene.js (three.js), predict.js, ml.js,
                      server.py, Dockerfile, vendored pg8000 wheels, sample CSV
  hill_template/      eval.py, baseline + reference submissions, hill tests
tests/                pytest suite (+ tests/js/ml_check.mjs for the browser model)
state/                seen, outcomes, buckets, memory, engagement, published, visibility
runs/<date>-<n>/      report.md, run.json, logs/ (bundles are git-ignored)
docs/screenshots/     images used in this README
media/                thumbnail source (HTML) and renders
CARD.md               project pitch card
NOTES.md              verified facts about the hills tool and design decisions
```

## Deploying the site

```bash
uv run scout site --out site
cd site
docker build -t hill-scout-site .
docker run -p 8080:8080 -e DATABASE_URL=postgresql://user:pass@host:5432/db hill-scout-site
```

The image is `python:3.12-alpine`. The database driver is installed from wheels vendored in the image, so the build doesn't need PyPI. The server also works where the platform runs it as a non-root user on a read-only filesystem, as Egbe does. Without `DATABASE_URL`, requests are written to `REQUESTS_FILE`. If storage isn't writable, the form tells visitors that requests are paused rather than failing silently.

The live site is deployed on Egbe from a separate repository that holds only the built `site/` folder.

## Testing

```bash
uv run pytest
```

Covered:
- bandit selection and family de-duplication;
- target-type handling and splits;
- licence rules, including Kaggle licence names;
- hill names for every source;
- README source wording;
- the safe fetcher: internal addresses, odd ports, zip/gzip/semicolon tables, and HTML refusal;
- `candidates.txt` parsing and the site export;
- the browser model, run under Node on synthetic data with a known signal (`tests/js/ml_check.mjs`).

## Lessons learned

- **Most public datasets aren't good tests.** 7 of 16 attempts were rejected. The gates are the product.
- **Kaggle datasets declare no target.** Name-based detection works for about a quarter of popular datasets. Generic names like `y` were too often a coordinate rather than a real target.
- **Accuracy hides signal on imbalanced yes/no questions.** HR attrition looked like "no signal" by accuracy, yet the top 20% of picks caught 59% of the leavers. The Predict page grades yes/no questions by ranking quality (AUC).
- **Integer-coded "regression" targets** are really classes, so they're converted and the change is noted in the README.
- **Read-only hosting:** request storage moved to managed Postgres, with a clear "paused" message as the fallback.

## Roadmap

- Run the scout daily on its own and redeploy the site after each run.
- Turn incoming requests that include a dataset link into private hills automatically, held for human review.
- Funded climbs: the first AutoLab climb hit its $5 cap after the baseline. Next is proving each new hill is climbable.
- Leaderboards and competitions with deadlines for sponsored hills.

---

Built with Python, scikit-learn, three.js, AutoLab and Egbe.
