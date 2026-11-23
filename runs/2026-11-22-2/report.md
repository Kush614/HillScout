# Hill Scout run 2026-11-22-2

Started 2026-11-22T22:07:02+00:00, finished 2026-11-22T22:11:42+00:00 (UTC).

## Summary

- Datasets looked at: **196** in scope from discovery (193 not seen before), **12** shortlisted by the bandit.
- Attempted: **9**; got past metadata to a build: **7**; hills built and gated: **4**.
- Shipped (passed all 8 gates, bundled): **3**.
- Published on app.autolab.ai: **3**. Published hills are private until a human makes them public; any other shipped hill is **bundled only**.

## Sources

| source | status | discovered | in scope |
|---|---|---|---|
| openml | used | 250 | 186 |
| manual | used | 10 | 10 |
| kaggle | skipped: no Kaggle credentials (~/.kaggle/kaggle.json or KAGGLE_USERNAME/KAGGLE_KEY) | — | — |
| egbe | skipped: not connected (needs a human sign-up and approval; optional per spec 9.2) | — | — |

## Picked, and why

Thompson sampling: each slot takes a fresh Beta(successes+1, failures+1) draw per bucket; the highest draw wins the slot. One candidate per name family, and none from a family attempted in an earlier run.

| # | candidate | bucket | rate before | draw | attempted | outcome |
|---|---|---|---|---|---|---|
| 1 | openml:47108 bkd1kmc1Dataset5 | openml|regression|small|f>60 | 0.67 | 0.955 | yes | prepare: regression target is not a continuous number |
| 2 | openml:47171 Uber_Ride_Analytics | openml|classification|large|f20-60 | 0.50 | 0.995 | yes | not_trivial: reference balanced accuracy 1.0000 (must be under 0.98) |
| 3 | openml:47023 MedMCQA | openml|classification|large|f<20 | 0.50 | 0.991 | yes | license 'Hugging Face' not on the redistribution allow-list |
| 4 | manual:40701 churn | manual|classification|small|f20-60 | 0.50 | 0.977 | yes | **shipped** |
| 5 | openml:47107 bkd1kmc1 | openml|regression|small|f>60 | 0.67 | 0.897 | yes | prepare: regression target is not a continuous number |
| 6 | openml:47003 melbourne_airbnb | openml|classification|medium|f>60 | 0.50 | 0.995 | yes | license 'Kaggle and Melbourne Airbnb Open Data' not on the redistribution allow-list |
| 7 | manual:44 spambase | manual|classification|small|f20-60 | 0.50 | 0.842 | yes | **shipped** |
| 8 | openml:47016 TRS_SCZ | openml|regression|medium|f20-60 | 0.67 | 0.978 | yes | prepare: regression target is not a continuous number |
| 9 | openml:48248 food_calorie_searches_36_languages | openml|regression|small|f<20 | 0.50 | 0.983 | yes | **shipped** |
| 10 | manual:1590 adult | manual|classification|medium|f<20 | 0.50 | 0.994 | no | not reached (quota met) |
| 11 | openml:48199 TabClustPFN-uci-spambase-v1-b86e23 | openml|classification|small|f20-60 | 0.50 | 0.963 | no | not reached (quota met) |
| 12 | openml:46908 APSFailure | openml|classification|large|f>60 | 0.50 | 0.971 | no | not reached (quota met) |

## Built hills and gates

| hill | task | valid | base | det | fast | head | nontriv | leak | junk | baseline | reference | eval s | shipped |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scout-uber-ride-analytics-47171 | balanced_accuracy | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ | ✓ | 0.2000 | 1.0000 | 24.8 | no |
| scout-churn-40701 | balanced_accuracy | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 0.5000 | 0.8682 | 22.8 | yes |
| scout-spambase-44 | balanced_accuracy | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 0.5000 | 0.9320 | 22.6 | yes |
| scout-food-calorie-searches-48248 | rmse | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 3152.8752 | 1200.7621 | 23.1 | yes |

✓ pass, ✗ fail, · not run. Gate details are in `state/outcomes.jsonl`.

### Rejected

- `openml:47108` bkd1kmc1Dataset5: prepare: regression target is not a continuous number
- `openml:47171` Uber_Ride_Analytics: not_trivial: reference balanced accuracy 1.0000 (must be under 0.98)
- `openml:47023` MedMCQA: license 'Hugging Face' not on the redistribution allow-list
- `openml:47107` bkd1kmc1: prepare: regression target is not a continuous number
- `openml:47003` melbourne_airbnb: license 'Kaggle and Melbourne Airbnb Open Data' not on the redistribution allow-list
- `openml:47016` TRS_SCZ: prepare: regression target is not a continuous number

## Bundles

- `runs/2026-11-22-2/bundles/scout-churn-40701.hill.tar`: scout-churn-40701 (balanced_accuracy: baseline 0.5000, reference 0.8682); README task text from template
- `runs/2026-11-22-2/bundles/scout-spambase-44.hill.tar`: scout-spambase-44 (balanced_accuracy: baseline 0.5000, reference 0.9320); README task text from claude -p
- `runs/2026-11-22-2/bundles/scout-food-calorie-searches-48248.hill.tar`: scout-food-calorie-searches-48248 (rmse: baseline 3152.8752, reference 1200.7621); README task text from claude -p

## Bucket rates: before -> after this run

| bucket | before | after | change |
|---|---|---|---|
| manual|classification|small|f20-60 | 0.50 (prior) | 0.75 | +0.25 |
| manual|regression|medium|f<20 | 0.67 | 0.67 | 0 |
| openml|classification|large|f20-60 | 0.50 (prior) | 0.33 | -0.17 |
| openml|regression|medium|f20-60 | 0.67 | 0.50 | -0.17 |
| openml|regression|small|f<20 | 0.50 (prior) | 0.67 | +0.17 |
| openml|regression|small|f>60 | 0.67 | 0.40 | -0.27 |

A bucket with no history starts at the Beta(1,1) prior, a 0.50 rate.

## Publishing status

- scout-churn-40701: **published (private)**, https://app.autolab.ai/hills/kush614/scout-churn-40701
- scout-spambase-44: **published (private)**, https://app.autolab.ai/hills/kush614/scout-spambase-44
- scout-food-calorie-searches-48248: **published (private)**, https://app.autolab.ai/hills/kush614/scout-food-calorie-searches-48248

## Human checklist

The loop pushes each shipped hill to app.autolab.ai as a **private** hill (`autolab hills push`, installed from https://app.autolab.ai/install.sh). Making a hill public is a human decision:

- [ ] Review https://app.autolab.ai/hills/kush614/scout-churn-40701, then make it public if it looks right: `autolab hills settings scout-churn-40701 --public`
- [ ] Review https://app.autolab.ai/hills/kush614/scout-spambase-44, then make it public if it looks right: `autolab hills settings scout-spambase-44 --public`
- [ ] Review https://app.autolab.ai/hills/kush614/scout-food-calorie-searches-48248, then make it public if it looks right: `autolab hills settings scout-food-calorie-searches-48248 --public`
- [ ] Start one climb to confirm the hill can be climbed (Hills -> Start a climb)
- [ ] After climbs come in, record `hill,climbs,stars,date` in `state/engagement.csv` (the next run learns from it)

