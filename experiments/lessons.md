# Experiment Lessons

## Lessons

- 2026-08-21 Stage 8: The global no-event rule reaches 0.545455 exact-set accuracy, so exact accuracy alone rewards class imbalance. Source: `stage8-baselines-v0.1`.
- 2026-08-21 Stage 8: Filing type improves materiality Brier to 0.165432 without improving label micro-F1, making it the frozen calibration floor rather than the label floor. Source: `stage8-baselines-v0.1`.
- 2026-08-21 Stage 8: Sparse lexical Naive Bayes raises micro-F1 to 0.472727 but worsens Brier to 0.409092; later models must improve discrimination and calibration together. Source: `stage8-baselines-v0.1`.
- 2026-08-21 Stage 8: Candidate evidence reaches only 0.040225 character-overlap F1 and must not be treated as extraction truth. Source: `stage8-baselines-v0.1`.
- 2026-08-21 Stage 8: Label-conditional modal attributes reach 0.731707 cell F1 but 0.000000 full-record exact accuracy, so a learned head must improve complete structured records rather than only common categorical fields. Source: `stage8-baselines-v0.2`.
- 2026-08-21 Stage 9: The unweighted frozen ModernBERT probe collapsed to micro-F1 0 despite 0.687500 exact-set accuracy; balanced weighting recovered only one of six validation positives for micro-F1 0.181818. Exact-set accuracy remains misleading and the probe is not promotable. Source: `stage9-linear-probe-v0.1/v0.2`.

## Rules

- NEVER promote on exact-set accuracy alone because the no-event majority already reaches 0.545455.
- ALWAYS compare learned extraction against lexical micro-F1 0.472727, filing-type Brier 0.165432, and evidence F1 0.040225 on the frozen Stage 8 split.
- ALWAYS require attribute cell F1 above 0.731707 and material-record exact accuracy above 0.000000 on the same frozen split.
- NEVER open the 22 Stage 9 release-evaluation labels to rescue a weak internal-validation result.
