# Hill Scout run 2026-11-22-1

Started 2026-11-22T22:02:35+00:00, finished 2026-11-22T22:06:03+00:00 (UTC).

## Summary

- Datasets looked at: **196** in scope from discovery (196 not seen before), **12** shortlisted by the bandit.
- Attempted: **3**; got past metadata to a build: **3**; hills built and gated: **3**.
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
| 1 | openml:47177 check_times | openml|regression|medium|f20-60 | 0.50 | 0.972 | yes | **shipped** |
| 2 | manual:537 houses | manual|regression|medium|f<20 | 0.50 | 0.996 | yes | **shipped** |
| 3 | openml:47285 AmesHousing_Analitica_Kag | openml|regression|small|f>60 | 0.50 | 0.986 | yes | **shipped** |
| 4 | openml:47023 MedMCQA | openml|classification|large|f<20 | 0.50 | 0.933 | no | not reached (quota met) |
| 5 | openml:46908 APSFailure | openml|classification|large|f>60 | 0.50 | 0.987 | no | not reached (quota met) |
| 6 | manual:4534 PhishingWebsites | manual|classification|medium|f20-60 | 0.50 | 0.974 | no | not reached (quota met) |
| 7 | manual:1590 adult | manual|classification|medium|f<20 | 0.50 | 0.968 | no | not reached (quota met) |
| 8 | openml:47108 bkd1kmc1Dataset5 | openml|regression|small|f>60 | 0.50 | 1.000 | no | not reached (quota met) |
| 9 | openml:46947 online_shoppers_intention | openml|classification|medium|f<20 | 0.50 | 0.964 | no | not reached (quota met) |
| 10 | openml:46935 HR_Analytics_Job_Change_of_Data_Sc | openml|classification|medium|f<20 | 0.50 | 0.843 | no | not reached (quota met) |
| 11 | openml:48185 TabClustPFN-openml-16-v1-6c4e5550 | openml|classification|small|f>60 | 0.50 | 0.970 | no | not reached (quota met) |
| 12 | manual:42225 diamonds | manual|regression|large|f<20 | 0.50 | 0.973 | no | not reached (quota met) |

## Built hills and gates

| hill | task | valid | base | det | fast | head | nontriv | leak | junk | baseline | reference | eval s | shipped |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| scout-check-times-47177 | rmse | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 100.0426 | 74.2182 | 22.9 | yes |
| scout-houses-537 | rmse | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 114210.6445 | 46815.7237 | 22.5 | yes |
| scout-ameshousing-analitica-47285 | rmse | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 84644.3357 | 26012.2509 | 22.7 | yes |

✓ pass, ✗ fail, · not run. Gate details are in `state/outcomes.jsonl`.

## Bundles

- `runs/2026-11-22-1/bundles/scout-check-times-47177.hill.tar`: scout-check-times-47177 (rmse: baseline 100.0426, reference 74.2182); README task text from claude -p
- `runs/2026-11-22-1/bundles/scout-houses-537.hill.tar`: scout-houses-537 (rmse: baseline 114210.6445, reference 46815.7237); README task text from claude -p
- `runs/2026-11-22-1/bundles/scout-ameshousing-analitica-47285.hill.tar`: scout-ameshousing-analitica-47285 (rmse: baseline 84644.3357, reference 26012.2509); README task text from claude -p

## Bucket rates: before -> after this run

| bucket | before | after | change |
|---|---|---|---|
| manual|regression|medium|f<20 | 0.50 (prior) | 0.67 | +0.17 |
| openml|regression|medium|f20-60 | 0.50 (prior) | 0.67 | +0.17 |
| openml|regression|small|f>60 | 0.50 (prior) | 0.67 | +0.17 |

A bucket with no history starts at the Beta(1,1) prior, a 0.50 rate.

## Publishing status

- scout-check-times-47177: **published (private)**, https://app.autolab.ai/hills/kush614/scout-check-times-47177
- scout-houses-537: **published (private)**, https://app.autolab.ai/hills/kush614/scout-houses-537
- scout-ameshousing-analitica-47285: **published (private)**, https://app.autolab.ai/hills/kush614/scout-ameshousing-analitica-47285

## Human checklist

The loop pushes each shipped hill to app.autolab.ai as a **private** hill (`autolab hills push`, installed from https://app.autolab.ai/install.sh). Making a hill public is a human decision:

- [ ] Review https://app.autolab.ai/hills/kush614/scout-check-times-47177, then make it public if it looks right: `autolab hills settings scout-check-times-47177 --public`
- [ ] Review https://app.autolab.ai/hills/kush614/scout-houses-537, then make it public if it looks right: `autolab hills settings scout-houses-537 --public`
- [ ] Review https://app.autolab.ai/hills/kush614/scout-ameshousing-analitica-47285, then make it public if it looks right: `autolab hills settings scout-ameshousing-analitica-47285 --public`
- [ ] Start one climb to confirm the hill can be climbed (Hills -> Start a climb)
- [ ] After climbs come in, record `hill,climbs,stars,date` in `state/engagement.csv` (the next run learns from it)

