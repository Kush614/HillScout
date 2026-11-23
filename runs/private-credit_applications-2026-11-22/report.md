# Private hill: private-credit-applications

- Data: `examples/credit_applications.csv` (1000 rows), target `class`, task classification
- Shipped: **yes**
- Baseline 0.5 -> reference 0.692939 (balanced_accuracy)
- Published: https://app.autolab.ai/hills/kush614/private-credit-applications (private; the scout never makes it public)
- README task text: template (private data is not sent to an LLM)

| gate | result | detail |
|---|---|---|
| valid | pass | hills check passed and commit succeeded |
| baseline_scores | pass | baseline 0.5000 |
| deterministic | pass | two reference evals differ by 0.00000 |
| fast | pass | reference eval took 28.7s (limit 120s) |
| headroom | pass | reference beats baseline by 0.1929 balanced accuracy (need 0.05) |
| not_trivial | pass | reference balanced accuracy 0.6929 (must be under 0.98) |
| no_leak | pass | best single feature 'credit_amount' scores 0.5509 vs reference 0.6929 |
| rejects_junk | pass | wrong-row-count submission -> passed=False (predictions.csv has 193 rows; expected one per row of test_features.csv (200)) |
