# Stage 8: Frozen Non-Neural Baselines

## Demonstrated boundary

Stage 8 has frozen development-only extraction baselines on release `stage7-ai-panel-v0.1`. The configuration was written and each hypothesis was logged before evaluation. All models fit only the 78 frozen training records and were measured once on the 22 frozen evaluation records. No evaluation-label or attribute distribution was inspected to choose features, smoothing, metrics or promotion thresholds.

The source labels are an adjudicated AI panel, not human gold. These results authorize model development and failure analysis only. Human-gold work remains frozen as a mandatory pre-finalization gate.

## Frozen contract

- Release: `stage7-ai-panel-v0.1`
- Release hash: `6cd6233f32b761dfdf047f58530e9f53d59c621985d624f0459642ffbed114db`
- Ontology/policy: `0.1` / `0.1`
- Source period: 2024-01-02 through 2024-03-28 UTC
- Split: 78 training / 22 evaluation
- Leakage: zero shared companies and zero shared related-event groups
- Evaluation tuning: forbidden
- Config: [`configs/stage8_baselines.yaml`](../configs/stage8_baselines.yaml)
- Report: `reports/stage8_baselines_v0.2.json`
- Experiment run: `stage8-baselines-v0.2`
- Config hash: `7fc496a0a073bc6bd23fcb7cdab25cba240c528d717090a4e3e84de17a4dbdb8`
- Report SHA-256: `97bd059bf6b6f1e8cb6869cd370d279ebbcef21d70e121bef87b6b3212272d2c`

## Baselines

1. Global frequency predicts the most common training label set and uses the empirical training materiality rate.
2. Filing-type frequency applies the same rule within filing type and falls back to the global rule for unseen types.
3. Sparse lexical Naive Bayes predicts an exact label-set class from lowercase alphanumeric token counts with Laplace alpha 1.0.
4. Candidate evidence returns all deterministic task candidate spans when the associated baseline predicts a material record.
5. Label-conditional attribute frequency receives the canonical event labels only for attribute-head isolation, then predicts the most frequent training value for every label/attribute pair. Ties use the lexicographically smallest canonical JSON value.

The implementation uses the Python standard library and existing project dependencies. No pretrained representation, external corpus, hyperparameter search or evaluation-set selection is involved.

## Frozen results

| Baseline | Exact-set accuracy | Micro-F1 | Materiality Brier | Evidence F1 |
|---|---:|---:|---:|---:|
| Global frequency | 0.545455 | 0.436364 | 0.287191 | 0.000000 |
| Filing-type frequency | 0.545455 | 0.436364 | **0.165432** | **0.040225** |
| Sparse lexical Naive Bayes | 0.545455 | **0.472727** | 0.409092 | 0.000000 |

Exact-set accuracy alone is misleading because the no-event rule already reaches 0.545455. Lexical features improve partial label recovery but not exact-set accuracy and produce poor probabilities. Filing type improves materiality calibration without improving label discrimination. Candidate evidence is a weak navigation floor, not an extraction solution.

The label-conditional attribute baseline reaches precision `0.750000`, recall `0.714286`, and cell F1 `0.731707`. Its complete material-record exact accuracy is `0.000000`. Common categorical values are therefore a strong partial floor, but copying modal values cannot reconstruct a complete evidence-specific event record.

## Frozen promotion bars

A later learned extraction model must use the identical release and memberships and satisfy all of the following without evaluation tuning:

- exact-set accuracy greater than 0.545455;
- micro-F1 greater than 0.472727;
- materiality Brier lower than 0.165432;
- evidence character-overlap F1 greater than 0.040225;
- label-conditional attribute-cell F1 greater than 0.731707;
- material-record attribute exact accuracy greater than 0.000000;
- zero company and related-event leakage;
- human-gold completion before final model approval.

Beating one number cannot compensate for regressing another. In particular, a model cannot trade calibration or evidence grounding for label micro-F1.

## Open outcome tranche

No real outcome baseline was produced because authenticated consolidated market bars remain unavailable under the Stage 5 gate. The Stage 8 report records this as `unavailable`. Outcome labels must not be fabricated from IEX-only data, later price sources or placeholder values. Once Stage 5 closes, unconditional and structured outcome baselines must run on the same frozen event memberships before Stage 12 promotion.

## Reproduce

```powershell
python -m financial_event_model.baselines
```

The command fails closed if the release hash, evidence kind, ontology, policy, counts or leakage contract drifts. It snapshots the exact configuration in `data/experiments/experiments.sqlite3` and writes the ignored generated report under `reports/`. Version `v0.2` adds the predeclared attribute floor; the earlier `v0.1` result remains historical evidence.
