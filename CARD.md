# Hill Scout: fresh, verified evaluation tasks, built every day by an agent

Hill Scout is a loop with no human in it. It turns raw datasets into scored, held-out
evaluation tasks ("hills") on AutoLab, gates every one for quality, and learns from what people
actually climb. Public data feeds a free daily catalogue, and a company's own data becomes a
private hill in one command.

## The pitch

**The problem.** Teams building AI agents need tasks the agent has never seen, to tell whether it
really improves models or just remembers the answer. Public benchmarks get old and leak into
training data. Writing a good evaluation by hand takes days: you have to split the data, hide the
labels, write a scorer that can't be gamed, and check that the task is neither trivial nor
impossible.

**What Hill Scout does.** It automates that job. Each day it finds new datasets, builds each one
into a hill with an evaluator, a private answer key, a baseline and a reference model. It ships
only the hills that pass eight checks: valid, scores a baseline, deterministic, fast, has headroom,
not trivial, no leaky column, and rejects malformed submissions. Shipped hills go to AutoLab, where
agents and people climb them, and the climb counts flow back so the scout builds more of what gets
used.

**Who pays.**
- **AI agent companies and eval teams** (coding agents, AutoML, research agents) want a steady
  supply of fresh, contamination-free tasks with signed scores.
- **Companies with their own prediction problems** (credit risk, churn, pricing, demand, equipment
  failure) want agents or vendors to compete on their data without the labels ever leaving.
  `scout private data.csv --target <column>` builds that hill and keeps it private.
- **Platforms like AutoLab** want a catalogue that grows faster than people can hand-build it.

**Industries next.** The same loop fits any field that has tables and a number to improve:
- Finance and insurance: credit risk, fraud, churn.
- Real estate: price models.
- Retail: demand and returns.
- Energy and industrial: failure prediction.
- Healthcare: risk scores, once privacy and compliance work is done.

**Business model.**
- The daily public catalogue is free and is the marketing.
- Revenue comes from private hills on a customer's data: per hill, or per competition with a
  deadline and a prize.
- Eval teams pay a subscription for a fresh, held-out set each week.
- The customer keeps the best solution, and AutoLab earns compute on every climb.

**The flywheel.** More hills bring more climbs. More climbs give a better signal about which tasks
are worth building. A better signal makes better hills.

## The demo

**Today (two runs, 2026-11-22):** the scout looked at **196** in-scope datasets (from 260
discovered) and shortlisted **24**. It attempted **12** and got **10** past metadata to a build.
**7** were built into hills and gated, and **6** passed every gate. **6** were rejected, each with
a recorded reason. Run 2 picked differently because of run 1:
- None of its 12 picks repeat run 1, and it excluded 2 re-uploads of data run 1 had already used.
- Four of its picks came from buckets that shipped in run 1 (rate 0.67).
- After run 2, `openml|regression|small|f>60` fell from 0.67 to 0.40 and
  `manual|classification|small|f20-60` rose to 0.75.

| hill | metric | baseline | reference | difficulty |
|---|---|---|---|---|
| scout-check-times-47177 | RMSE | 100.04 | 74.22 | moderate |
| scout-houses-537 | RMSE | 114,211 | 46,816 | approachable |
| scout-ameshousing-analitica-47285 | RMSE | 84,644 | 26,012 | approachable |
| scout-churn-40701 | balanced acc. | 0.500 | 0.868 | approachable |
| scout-spambase-44 | balanced acc. | 0.500 | 0.932 | approachable |
| scout-food-calorie-searches-48248 | RMSE | 3,153 | 1,201 | approachable |

Difficulty comes from how much a default gradient-boosting model gains over the baseline.

The gates rejected these:
- A ride dataset where the reference scored a perfect 1.0, which a climber can't improve on.
- Two datasets whose license fields named a source instead of a license.
- Three numeric targets that were really integer class codes. These are now built as
  classification.

**Published:** all 6 are on app.autolab.ai as **private** hills (`autolab hills push`), under
https://app.autolab.ai/hills/kush614/. A human decides when each one goes public. The loop pushes
every new shipped hill the same way.

**Bring your own data:** `scout private examples/credit_applications.csv --target class` built,
gated and pushed a private credit-risk hill in about a minute: baseline 0.500, reference 0.693
balanced accuracy. The demo file is OpenML's public credit-g data standing in for a company export.
Private data is not sent to an LLM unless the owner opts in.

**Demand loop:** each run reads real climb counts from AutoLab (`autolab hills climbs`) into
`state/engagement.csv` before it picks. Hills that attract climbs lift their bucket.

**First climb:** `churn-climb-1` ran on AutoLab against the churn hill, with this laptop as the
compute node. The baseline scored 0.500 on AutoLab, matching the local evaluator. The agent then
used up the $5 spending cap planning its first experiment (gradient boosting with engineered usage
features), so no improved score exists yet.

**Catalogue:** `scout catalog` writes `catalog/index.html`, a page with every shipped hill, its
scores, difficulty, source, license and climb count. It is regenerated after every run, and it is
local until a human approves hosting it.

## Tech stack and tools used

- **AutoLab** (required sponsor tool): the `hills` format and evaluator, signed eval reports,
  bundles, `autolab hills push` to publish, `autolab hills climbs` for engagement, and climbs with
  this laptop attached as a node.
- **OpenML REST API** for discovery and parquet downloads, with no login.
- Python with pandas, scikit-learn and numpy. HistGradientBoosting is the reference model, and
  Thompson sampling over source x task x size x feature-count buckets picks what to build.
- **Claude** (`claude -p`) writes the two-sentence task description in each public hill's README.
  Any reply containing a digit is thrown away, so every number comes from a measurement.
- Built with Claude Code.
- Sponsor tools, one line each:
  - **AutoLab:** hill format, scoring, publishing, engagement, climbs.
  - **Egbe:** not used today. It was cut first under the time plan and needs a human sign-up.

## Challenges and lessons

- The `dataset` template makes spec-4 hills, which `hills bundle` refuses. We use spec-2 hills
  with hash-bound data, which bundle, unbundle and push cleanly.
- Finding the publish path took a detour: the `autolab` names on npm and PyPI are other projects.
  The real CLI installs from `app.autolab.ai/install.sh`.
- The newest OpenML uploads are noisy, with near-duplicate series, synthetic copies and "licenses"
  that only name a source. Cross-run dedupe and a strict license allow-list handle it.
- The first selector drew once per bucket, so one bucket took all 12 slots. A fresh draw per slot
  fixed it.
- A $5 cap is not enough for one agent experiment on AutoLab's default model. Budget a climb at
  $20 to $50, or point it at a cheaper model.

## What is needed to move forward

1. **Customers:** two design partners, one agent or eval team and one company with a private
   prediction problem, to price private hills and competitions.
2. **A climb budget** of about $20 to $50, to show a real score gain on one hill.
3. **More task types:** text classification first, then time series, behind the same source,
   build and gate interfaces.
4. **Hosting:** host the catalogue page and run `scout daily` on a schedule that doesn't need this
   laptop, for example an Egbe loop or a small server.
5. **A star count API on AutoLab**, to go with climb counts.
