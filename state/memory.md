# Hill Scout memory

_Rewritten after run 2026-11-22-3. Read at the start of every run._

## Bucket success rates

| bucket | shipped | failed | climb bonus | rate |
|---|---|---|---|---|
| manual|classification|small|f20-60 | 2 | 0 | 1 | 0.80 |
| kaggle|classification|small|f20-60 | 1 | 0 | 0 | 0.67 |
| kaggle|regression|medium|f<20 | 1 | 0 | 0 | 0.67 |
| manual|regression|medium|f<20 | 1 | 0 | 0 | 0.67 |
| openml|regression|small|f<20 | 1 | 0 | 0 | 0.67 |
| kaggle|classification|small|f<20 | 1 | 1 | 0 | 0.50 |
| openml|regression|medium|f20-60 | 1 | 1 | 0 | 0.50 |
| openml|regression|small|f>60 | 1 | 2 | 0 | 0.40 |
| openml|classification|large|f20-60 | 0 | 1 | 0 | 0.33 |

## Lessons

- datasets under 10k rows shipped 6 of 9 attempts
- regression datasets shipped 5 of 8 attempts
- datasets with 20-60 features shipped 4 of 6 attempts
- classification datasets shipped 4 of 6 attempts
- datasets with under 20 features shipped 4 of 5 attempts
- datasets of 10k-50k rows shipped 3 of 4 attempts
- Kaggle candidates shipped 3 of 4 attempts
- Manual candidates shipped 3 of 3 attempts
- datasets with over 60 features failed at data preparation 2 of 3 times
- 2 candidates were skipped before download: license
