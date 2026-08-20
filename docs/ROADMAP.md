# Development Roadmap

The source specification is implemented as independently verifiable stages. Work proceeds in this order unless the charter is deliberately amended.

| Stage | Deliverable | Proof boundary |
|---:|---|---|
| 0 | Repository, schemas, configuration, experiment ledger | Install/test commands pass; configs and outputs are versioned |
| 1 | Point-in-time security master | Schema/query verified with fixtures; authoritative historical population and coverage audit remain open |
| 2 | SEC ingestion | Reproducible 50-company manifest preserves filings, exhibits, amendments, failures, and hashes |
| 3 | Normalization and evidence mapping | 100 representative documents remain traceable to raw offsets and parsing failures are flagged |
| 4 | Timestamp discipline and historical knowledge query | 100 sampled events have zero unexplained pre-`tradable_at` violations |
| 5 | Market data and outcome labels | 100 sampled event returns reproduce within tolerance from the correct starting point |
| 6 | Ontology v0.1 and annotation guide | Independent labels have explainable disagreement categories |
| 7 | Annotation application and gold set | Frozen evaluation set, agreement metrics, class reports, and leakage controls exist |
| 8 | Non-neural baselines | Frozen baselines run on the same periods as every later model |
| 9 | Event extraction model | Beats baselines, identifies evidence, calibrates probabilities, and survives robustness splits |
| 10 | Event embeddings and analogue retrieval | Retrieved history is economically comparable and strictly prior to the query event |
| 11 | Novelty and expectations features | High novelty predicts stronger information effects out of sample |
| 12 | Outcome-distribution alignment | Calibrated quantiles/probabilities improve on unconditional and structured baselines |
| 13 | Uncertainty and abstention | Accepted predictions are better calibrated than the complete population |
| 14 | Local research demonstration | Fixed evaluation and failure evidence accompanies every interactive example |
| 15 | Autonomous paper loop and separately gated execution | Forward paper evidence passes frozen criteria; live-capital gate remains explicit |

Stage 15 names the broader system goal described in the charter. It extends the supplied MVP roadmap without moving broker integration into the MVP.
