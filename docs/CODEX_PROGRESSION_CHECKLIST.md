# Codex Progression Checklist

This is the ordered engineering path from the current Stage 7 implementation to a proven paper research system and, only after a separate authorization gate, possible live execution. A checked box means the stated proof exists—not merely that code was scaffolded.

## Confirmed foundation

- [x] Stage 0: repository, contracts, configuration, experiment ledger, install and test commands.
- [x] Stage 1 engine: point-in-time security-master schema and fixture queries.
- [x] Stage 2: SEC collector and live 50-company Q1 2024 acceptance evidence.
- [x] Stage 3: normalized SEC documents with byte-range source traceability.
- [x] Stage 4: conservative `tradable_at` policy and historical knowledge query.
- [x] Stage 5 engine: market-data storage and deterministic 1/5/20-session outcomes.
- [x] Stage 6 engine: ontology v0.1, strict event validation, and agreement audit.
- [x] Stage 7 development release: local annotation application, append-only history, leakage-safe releases, the real calibration queue, and frozen `stage7-ai-panel-v0.1` release.
- [x] Current repository verification: 113 tests pass after Stage 8 attribute baselines, Stage 9 packaging, token alignment, and linear-probe operationalization.

Open proof boundaries remain recorded in `docs/ROADMAP.md`; the checked engine boxes do not erase those gates.

## Immediate engineering sequence

### 1. Operationalize the real calibration queue

- [x] Add a deterministic selector for 100 representative real SEC documents from the accepted ingestion/normalization corpus.
- [x] Preserve company, entity, related-event group, publication time, tradable time, filing type, exact section, evidence candidates, and prior disclosure in every task.
- [x] Add an import command that idempotently loads those tasks into `data/labels/annotations.sqlite`.
- [x] Add per-annotator progress and a genuine queue-complete state to the local application.
- [x] Add an agreement/disagreement report command so users do not need to write Python.
- [x] Test selection, import, progress, completion, and report generation with fixtures.
- [x] Run the real import and report **“calibration queue ready.”**

**Exit:** exactly 100 traceable real tasks are available to both nominated annotators, with no generated label presented as truth.

### 2. Create the dashboard visual foundation in parallel

- [x] Receive the user's initial dark-mode direction and nine component references.
- [x] Inventory reusable supplied components and source/licence status; record the user's explicit RareUI-use direction.
- [x] Freeze the initial dashboard information hierarchy and chart/data semantics in `docs/DASHBOARD_DESIGN_BRIEF.md`.
- [ ] Produce a dark-mode desktop visual prototype using conspicuously marked fixture/paper data.
- [ ] Review typography, colour, table density, chart treatment, responsive behaviour, keyboard navigation, and contrast with the user.
- [ ] Implement only the approved shell and shared visual tokens; do not add broker or order routes.

**Exit:** the user approves a coherent dark-mode dashboard shell. Holdings are clearly marked fixture, imported, read-only, or paper data.

### 3. Complete the real Stage 6 calibration evidence

**FROZEN 2026-08-21:** preserve this checklist but do not schedule annotation work now. Unfreeze before model finalization, or earlier if the embedding model does not meet its frozen evaluation targets.

- [ ] Wait for two independent 100-document annotation passes.
- [ ] Freeze both original decision sets before revealing disagreements.
- [ ] Calculate leaf and family agreement.
- [ ] Generate the disagreement queue with one of the five permitted causes required for every item.
- [ ] Record adjudications without overwriting original annotations.
- [ ] Revise the ontology under a new version if evidence shows missing or unclear definitions.

**Frozen by user:** two nominated annotators are intentionally deferred; the queue and application remain ready.

**Exit:** 100 real events have two independent human labels, threshold agreement, and zero unexplained disagreements.

### 4. Close the real Stage 5 market-data gate

- [ ] Add a safe command-line acceptance runner around the existing Alpaca collector and outcome engine.
- [ ] Fail closed when credentials, SIP entitlement, horizons, or source coverage are missing.
- [ ] Receive confirmation that consolidated SIP or licensed equivalent access exists.
- [ ] Run the authenticated daily-bar collection without persisting secrets.
- [ ] Generate outcomes for 100 real filings and manually reproduce the selected source-price calculations.
- [ ] Record coverage, missingness, corporate-action, sector-history, halt, and delisting limitations.

**Blocked by:** consolidated market-data access supplied by the user.

**Exit:** the 100-real-filing outcome audit passes against authenticated consolidated bars. An IEX-only run cannot satisfy this gate.

### 5. Build and freeze the real gold dataset

**FROZEN 2026-08-21:** this remains a mandatory pre-finalization evidence gate, not deleted scope.

- [ ] Generate the 500–1,000-event Round 2 queue after calibration definitions are frozen.
- [ ] Assign at least 20% to two independent annotators, targeting 30%.
- [ ] Monitor class coverage and prioritize missing/rare labels without leaking evaluation outcomes.
- [ ] Adjudicate every disagreement.
- [ ] Freeze exact task hashes and annotation IDs.
- [ ] Build separate train and evaluation memberships using connected company/related-event components.
- [ ] Verify zero company leakage, zero related-event leakage, class distribution, rare labels, and agreement metrics.

**Blocked by:** Steps 3 and 4 plus human annotation capacity.

**Exit:** a genuine human gold release sets `stage_acceptance_passed=true`; fixture evidence cannot satisfy it.

### Frozen human-gold gate before model finalization

- [x] Preserve the 100-document queue, ontology, local application, AI-panel originals, adjudications, canonical records, and frozen non-human release.
- [ ] Unfreeze this gate before final model approval, or immediately if embedding performance is below the predeclared target.
- [ ] Nominate two people and freeze two genuinely independent decisions for all 100 calibration documents.
- [ ] Calculate leaf/family agreement and adjudicate every disagreement without overwriting either original pass.
- [ ] Revise the ontology under a new version when disagreement evidence demonstrates a missing or unclear definition.
- [ ] Build a 500–1,000-event Round 2 human queue.
- [ ] Double-label at least 20% of Round 2, targeting 30%, and adjudicate every observed disagreement.
- [ ] Freeze task hashes, annotation IDs, and leakage-safe train/evaluation memberships.
- [ ] Require `evidence_kind="human"`, zero company/related-event leakage, and `stage_acceptance_passed=true` before final model promotion.

**Current development authority:** `stage7-ai-panel-v0.1` may be used for baselines, embedding experiments and failure analysis. It may not be represented as human gold or used to waive the checklist above.

## Model progression

### 6. Stage 8: non-neural baselines

- [x] Freeze time periods, train/evaluation IDs, metrics, and promotion rules before fitting.
- [x] Implement majority/frequency, sparse lexical, and filing-type structured baselines.
- [x] Produce evidence-span, label, and materiality-calibration baselines on the frozen 78/22 split.
- [x] Record every hypothesis, configuration, result and distilled lesson in the experiment journal and ledger.
- [ ] Produce unconditional and structured outcome baselines after authenticated consolidated Stage 5 market data exists.

**Current boundary:** extraction baselines are frozen and reproducible. The outcome tranche remains blocked by Stage 5. Learned extraction may begin, but final Stage 8/12 outcome promotion remains open.

**Frozen extraction bars:** exact-set accuracy `> 0.545455`, micro-F1 `> 0.472727`, materiality Brier `< 0.165432`, and evidence F1 `> 0.040225` on the identical evaluation IDs.

### 7. Stage 9: event extraction model

- [x] Freeze a 62/16 group-safe internal fit/validation package from only the 78 development records; keep all 22 evaluation annotations sealed.
- [x] Exclude company/entity identity from model inputs while retaining it for leakage checks.
- [x] Preserve deterministic character-level evidence targets and package hashes before tokenizer selection.
- [x] Select ModernBERT-base and freeze the exact repository revision, tokenizer hashes, Apache-2.0 licence, runtime, hardware, and 3,072-token development boundary.
- [x] Download the exact frozen safetensors weight snapshot and record its byte count, tensor count, and SHA-256 before training.
- [x] Convert all 35 development evidence spans to token spans with exact quote checks and whitespace-only tokenizer-boundary trims; zero failures.
- [x] Pass a 512-token CUDA forward/backward and safetensors checkpoint round-trip systems gate.
- [x] Train unweighted and balanced frozen-encoder label probes on 62/16 only; retain the balanced micro-F1 0.181818 result as a weak development diagnostic, not a promotion candidate.
- [ ] Train label, attribute, and evidence-span heads without using evaluation outcomes for tuning.
- [ ] Compare against all Stage 8 baselines.
- [ ] Measure probability calibration, robustness by time/company/filing type, and failure cases.
- [ ] Reject promotion unless extraction and evidence quality improve together.

**Exit:** the model beats frozen baselines, identifies supporting evidence, calibrates probabilities, and survives robustness splits.

### 8. Stages 10–13: retrieval, novelty, outcomes, and abstention

- [ ] Stage 10: train/evaluate event embeddings and strictly-prior analogue retrieval.
- [ ] Stage 11: build point-in-time novelty and expectations features and test information-effect hypotheses out of sample.
- [ ] Stage 12: align event representations with 1/5/20-day outcome distributions without degrading semantic extraction.
- [ ] Stage 13: calibrate epistemic/aleatoric uncertainty, OOD detection, and fail-closed abstention.
- [ ] Retain complete model, data, ontology, calibration, and policy versions for every output.

**Exit:** accepted predictions are better calibrated and more useful than the complete population; weak/OOD cases abstain.

## Product and autonomous-loop progression

### 9. Stage 14: connect real research outputs to the dashboard

- [ ] Replace dashboard fixtures with versioned read-only research outputs.
- [ ] Show events, evidence, analogues, distributions, uncertainty, abstentions, and model/data health.
- [ ] Add paper holdings, P&L, exposure, risk, and decision/audit history only when those records exist.
- [ ] Preserve a visible distinction between facts, model estimates, paper decisions, and failures.
- [ ] Validate desktop/mobile accessibility and fixed evaluation examples.

**Exit:** the dashboard is a truthful local research demonstration, not a decorative mock or unexplained trade generator.

### 10. Stage 15: autonomous paper loop

- [ ] Automate ingestion, validation, extraction, retrieval, scoring, calibration, paper decisions, reconciliation, and monitoring.
- [ ] Add transaction-cost, liquidity, position, exposure, loss, and data-freshness constraints.
- [ ] Add idempotent paper orders, audit logs, alerts, and a tested kill switch.
- [ ] Freeze forward-test promotion criteria before observing results.
- [ ] Run the required forward paper period and publish both success and failure evidence.

**Exit:** the autonomous paper loop passes frozen forward criteria. No live order route exists yet.

### 11. Separate live-capital gate

- [ ] Receive explicit live-trading authorization and supplied capital.
- [ ] Approve broker/account configuration and secret handling.
- [ ] Approve position, exposure, liquidity, loss, and transaction-cost limits.
- [ ] Verify pre-trade validation, idempotent orders, reconciliation, audit logs, and kill switch.
- [ ] Bind every decision to named model, data, ontology, calibration, and policy versions.
- [ ] Enable live routes only after every gate passes; fail closed otherwise.

**Exit:** live trading is separately authorized and technically gated. Elevated filesystem permissions alone never satisfy this step.

## Known maintenance work

- [ ] Close authoritative historical-universe and sector-history coverage gaps.
- [ ] Add authoritative historical halt and delisting-return coverage.
- [ ] Remove Python 3.13 SQLite resource warnings from older Stage 1–5 stores; Stage 7 is already warning-clean.
- [ ] Resolve the unrelated global `aicomp-sdk`/`gymnasium` environment conflict if that SDK becomes part of this project; it currently does not block the 96 project tests.
