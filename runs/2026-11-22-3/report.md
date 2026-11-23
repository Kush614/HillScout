# Hill Scout run 2026-11-22-3

Started 2026-11-23T01:25:56+00:00, finished 2026-11-23T01:30:06+00:00 (UTC).

## Summary

- Datasets looked at: **10** in scope from discovery (10 not seen before), **7** shortlisted by the bandit.
- Attempted: **4**; got past metadata to a build: **4**; hills built and gated: **4**.
- Shipped (passed all 8 gates, bundled): **3**.
- Published on app.autolab.ai: **3**. Published hills are private until a human makes them public; any other shipped hill is **bundled only**.

## Sources

| source | status | discovered | in scope |
|---|---|---|---|
| kaggle | used | 15 | 10 |
| egbe | not a dataset source: hosts the site (hill-scout.egbe.app) and its analytics; redeploys need approval | — | — |

## Picked, and why

Thompson sampling: each slot takes a fresh Beta(successes+1, failures+1) draw per bucket; the highest draw wins the slot. One candidate per name family, and none from a family attempted in an earlier run.

| # | candidate | bucket | rate before | draw | attempted | outcome |
|---|---|---|---|---|---|---|
| 1 | kaggle:uciml/red-wine-quality-cortez-et-al-2009 Red Wine Quality | kaggle|classification|small|f<20 | 0.50 | 0.938 | yes | **shipped** |
| 2 | kaggle:pavansubhasht/ibm-hr-analytics-attrition-dataset IBM HR Analytics Employee Attritio | kaggle|classification|small|f20-60 | 0.50 | 0.932 | yes | **shipped** |
| 3 | kaggle:abdullah1afify/ntl-generations Name That LLM: extra GPT and Gemin | kaggle|classification|small|f<20 | 0.50 | 0.984 | yes | not_trivial: reference balanced accuracy 1.0000 (must be under 0.98) |
| 4 | kaggle:adityadesai13/used-car-dataset-ford-and-mercedes 100,000 UK Used Car Data set | kaggle|regression|medium|f<20 | 0.50 | 0.927 | yes | **shipped** |
| 5 | kaggle:imakash3011/customer-personality-analysis Customer Personality Analysis | kaggle|regression|small|f20-60 | 0.50 | 0.547 | no | not reached (quota met) |
| 6 | kaggle:harlfoxem/housesalesprediction House Sales in King County, USA | kaggle|regression|medium|f20-60 | 0.50 | 0.847 | no | not reached (quota met) |
| 7 | kaggle:arashnic/hr-analytics-job-change-of-data-scientists HR Analytics: Job Change of Data S | kaggle|classification|medium|f<20 | 0.50 | 0.026 | no | not reached (quota met) |

## Built hills and gates

| hill | task | valid | base | det | fast | head | nontriv | leak | junk | baseline | reference | eval s | shipped |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scout-red-wine-quality-kg-408e01 | balanced_accuracy | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 0.1667 | 0.3375 | 24.1 | yes |
| scout-ibm-hr-analytics-emplo-kg-49a2b7 | balanced_accuracy | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 0.5000 | 0.7132 | 24.4 | yes |
| scout-name-that-llm-extra-gp-kg-824a09 | balanced_accuracy | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | 0.1250 | 1.0000 | 24.5 | no |
| scout-100-000-uk-used-car-da-kg-057598 | rmse | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 4652.2521 | 1179.3070 | 25.2 | yes |

✓ pass, ✗ fail, · not run. Gate details are in `state/outcomes.jsonl`.

### Rejected

- `kaggle:abdullah1afify/ntl-generations` Name That LLM: extra GPT and Gemini generations: not_trivial: reference balanced accuracy 1.0000 (must be under 0.98)

## Bundles

- `runs/2026-11-22-3/bundles/scout-red-wine-quality-kg-408e01.hill.tar`: scout-red-wine-quality-kg-408e01 (balanced_accuracy: baseline 0.1667, reference 0.3375); README task text from claude -p
- `runs/2026-11-22-3/bundles/scout-ibm-hr-analytics-emplo-kg-49a2b7.hill.tar`: scout-ibm-hr-analytics-emplo-kg-49a2b7 (balanced_accuracy: baseline 0.5000, reference 0.7132); README task text from claude -p
- `runs/2026-11-22-3/bundles/scout-100-000-uk-used-car-da-kg-057598.hill.tar`: scout-100-000-uk-used-car-da-kg-057598 (rmse: baseline 4652.2521, reference 1179.3070); README task text from claude -p

## Bucket rates: before -> after this run

| bucket | before | after | change |
|---|---|---|---|
| kaggle|classification|small|f20-60 | 0.50 (prior) | 0.67 | +0.17 |
| kaggle|classification|small|f<20 | 0.50 (prior) | 0.50 | 0 |
| kaggle|regression|medium|f<20 | 0.50 (prior) | 0.67 | +0.17 |
| manual|classification|small|f20-60 | 0.80 | 0.80 | 0 |
| manual|regression|medium|f<20 | 0.67 | 0.67 | 0 |
| openml|classification|large|f20-60 | 0.33 | 0.33 | 0 |
| openml|regression|medium|f20-60 | 0.50 | 0.50 | 0 |
| openml|regression|small|f<20 | 0.67 | 0.67 | 0 |
| openml|regression|small|f>60 | 0.40 | 0.40 | 0 |

A bucket with no history starts at the Beta(1,1) prior, a 0.50 rate.

## Publishing status

- scout-red-wine-quality-kg-408e01: **published (private)**, https://app.autolab.ai/hills/kush614/scout-red-wine-quality-kg-408e01
- scout-ibm-hr-analytics-emplo-kg-49a2b7: **published (private)**, https://app.autolab.ai/hills/kush614/scout-ibm-hr-analytics-emplo-kg-49a2b7
- scout-100-000-uk-used-car-da-kg-057598: **published (private)**, https://app.autolab.ai/hills/kush614/scout-100-000-uk-used-car-da-kg-057598

## Human checklist

The loop pushes each shipped hill to app.autolab.ai as a **private** hill (`autolab hills push`, installed from https://app.autolab.ai/install.sh). Making a hill public is a human decision:

- [ ] Review https://app.autolab.ai/hills/kush614/scout-red-wine-quality-kg-408e01, then make it public if it looks right: `autolab hills settings scout-red-wine-quality-kg-408e01 --public`
- [ ] Review https://app.autolab.ai/hills/kush614/scout-ibm-hr-analytics-emplo-kg-49a2b7, then make it public if it looks right: `autolab hills settings scout-ibm-hr-analytics-emplo-kg-49a2b7 --public`
- [ ] Review https://app.autolab.ai/hills/kush614/scout-100-000-uk-used-car-da-kg-057598, then make it public if it looks right: `autolab hills settings scout-100-000-uk-used-car-da-kg-057598 --public`
- [ ] Start one climb to confirm the hill can be climbed (Hills -> Start a climb)
- [ ] After climbs come in, record `hill,climbs,stars,date` in `state/engagement.csv` (the next run learns from it)

