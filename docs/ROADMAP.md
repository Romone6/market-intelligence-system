# Development Roadmap

The source specification is implemented as independently verifiable stages. Work proceeds in this order unless the charter is deliberately amended.

| Stage | Deliverable | Proof boundary |
|---:|---|---|
| 0 | Repository, schemas, configuration, experiment ledger | Install/test commands pass; configs and outputs are versioned |
| 1 | Point-in-time security master | Schema/query verified with fixtures; authoritative historical population and coverage audit remain open |
| 2 | SEC ingestion | 50-company Q1 2024 collection and zero-network resume audit preserve 161 filings, 483 source objects, and 3,683 embedded documents without duplicates |
| 3 | Normalization and evidence mapping | 100 representative documents have deterministic byte-range traceability, typed tables, raw-hash integrity, exhibit links, and explicit parser warnings |
| 4 | Timestamp discipline and historical knowledge query | 100 filing-evidence records pass exact-boundary and timestamp-order audits; downstream feature replay remains a continuous gate |
| 5 | Market data and outcome labels | Engine and 100-fixture reproduction pass; authenticated consolidated bars and the 100-real-filing audit remain open |
| 6 | Ontology v0.1 and annotation guide | Schema, real 100-document AI-panel calibration and user adjudication pass; two-human agreement is frozen until pre-finalization or an embedding-performance trigger |
| 7 | Annotation application and gold set | Development stage complete on frozen non-human release `stage7-ai-panel-v0.1`; the 500–1,000-event human-gold gate is preserved as mandatory pre-finalization work |
| 8 | Non-neural baselines | Label, calibration, evidence, and attribute baselines are frozen on `stage7-ai-panel-v0.1`; the real outcome tranche remains blocked by authenticated Stage 5 data |
| 9 | Event extraction model | 62/16 group-safe development package is frozen while 22 evaluation labels remain sealed; encoder selection, training, and proof remain open |
| 10 | Event embeddings and analogue retrieval | Retrieved history is economically comparable and strictly prior to the query event |
| 11 | Novelty and expectations features | High novelty predicts stronger information effects out of sample |
| 12 | Outcome-distribution alignment | Calibrated quantiles/probabilities improve on unconditional and structured baselines |
| 13 | Uncertainty and abstention | Accepted predictions are better calibrated than the complete population |
| 14 | Local research demonstration | Fixed evaluation and failure evidence accompanies every interactive example |
| 15 | Autonomous paper loop and separately gated execution | Forward paper evidence passes frozen criteria; live-capital gate remains explicit |

Stage 15 names the broader system goal described in the charter. It extends the supplied MVP roadmap without moving broker integration into the MVP.
