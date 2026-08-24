# Experiment Journal

### 2026-08-21 — Stage 8 label-conditional attribute-frequency baseline

**Status**: COMPLETED

**Hypothesis**: Predicting the most frequent training value for each attribute within each canonical event label will establish a non-trivial attribute-decoding floor while keeping event-label discrimination outside the attribute score.
**Change**: Add exact attribute-cell micro precision/recall/F1 and full material-record attribute accuracy; event labels are supplied from the canonical record for this attribute-only baseline.
**Config**:
- release: `stage7-ai-panel-v0.1`
- split: frozen 78 train / 22 evaluation
- prediction: most frequent canonical JSON value by label and attribute
- tie break: lexicographically smallest canonical JSON value
**Expected outcome**: Non-zero attribute-cell F1 and lower full-record exact accuracy because the baseline cannot adapt attributes to document evidence.
**Baseline**: None; first frozen attribute-output floor.
**Actual outcome**: Attribute-cell precision 0.750000, recall 0.714286 and F1 0.731707; full material-record exact accuracy 0.000000.
**Delta**: The partial-cell floor is substantial, while the expected inability to reproduce a complete record was confirmed.
**Duration**: Shared Stage 8 v0.2 run completed in 0.7 seconds wall time.
**Learning**: Frequent categorical attributes are easy to copy by label, but no evaluation record matched the full modal attribute bundle exactly.
**Next**: Require the learned attribute head to exceed both cell F1 0.731707 and material-record exact accuracy 0.000000 on the identical evaluation records.

### 2026-08-21 01:41 +10:00 — Stage 8 global-frequency baseline

**Status**: COMPLETED

**Hypothesis**: Predicting the most frequent training label set will establish a strong no-event floor because material disclosures are the minority, but it will have poor material-label recall.
**Change**: Evaluate the frozen global-frequency rule without inspecting or tuning on evaluation labels.
**Config**:
- release: `stage7-ai-panel-v0.1`
- split: frozen 78 train / 22 evaluation
- prediction: most frequent exact label set in training
**Expected outcome**: High exact-set accuracy relative to its simplicity, near-zero material-event recall.
**Baseline**: None; first Stage 8 floor.
**Actual outcome**: Exact-set accuracy 0.545455, micro-F1 0.436364, materiality Brier 0.287191, evidence F1 0.000000.
**Delta**: Established the expected strong no-event floor and zero evidence capability.
**Duration**: Shared three-baseline run completed in 0.7 seconds wall time.
**Learning**: Majority behavior is difficult to beat on exact-set accuracy in this small, imbalanced panel release.
**Next**: Compare filing-type and lexical rules on the identical frozen evaluation IDs.

### 2026-08-21 01:41 +10:00 — Stage 8 filing-type frequency baseline

**Status**: COMPLETED

**Hypothesis**: Conditioning the frequency rule on SEC filing type may improve exact-set accuracy over the global rule because exhibits and current reports have different event mixtures.
**Change**: Replace only the global lookup with a filing-type lookup; unseen types fall back to global frequency.
**Config**:
- release: `stage7-ai-panel-v0.1`
- split: frozen 78 train / 22 evaluation
- feature: filing type only
**Expected outcome**: Exact-set accuracy at least equal to global frequency, with limited material-label recall.
**Baseline**: Frozen global-frequency rule.
**Actual outcome**: Exact-set accuracy 0.545455 and micro-F1 0.436364 matched global frequency; Brier improved from 0.287191 to 0.165432; evidence F1 was 0.040225.
**Delta**: Label discrimination did not improve, but materiality calibration improved by 0.121759 and candidate evidence supplied a small non-zero floor.
**Duration**: Shared three-baseline run completed in 0.7 seconds wall time.
**Learning**: Filing type carries materiality-rate information but is insufficient to separate the exact event labels.
**Next**: Preserve this as the Stage 8 calibration and evidence baseline.

### 2026-08-21 01:41 +10:00 — Stage 8 sparse lexical Naive Bayes baseline

**Status**: COMPLETED

**Hypothesis**: A bag-of-words multinomial Naive Bayes classifier will recover some event-label signal from explicit disclosure language and improve micro-F1 over both frequency rules without pretrained representations.
**Change**: Add lowercase alphanumeric token counts with Laplace alpha 1.0; all release, split and metric choices remain fixed.
**Config**:
- release: `stage7-ai-panel-v0.1`
- split: frozen 78 train / 22 evaluation
- target: exact label-set class
- tokenizer: lowercase ASCII alphanumeric, minimum length 2
- alpha: 1.0
**Expected outcome**: Higher micro-F1 than both frequency baselines; calibration may remain weak because the dataset is small.
**Baseline**: Best frozen frequency baseline.
**Actual outcome**: Micro-F1 improved from 0.436364 to 0.472727; exact-set accuracy remained 0.545455; Brier worsened to 0.409092 and evidence F1 was 0.000000.
**Delta**: The micro-F1 hypothesis passed by +0.036364, while exact-set and calibration did not improve.
**Duration**: Shared three-baseline run completed in 0.7 seconds wall time.
**Learning**: Sparse lexical signal helps partial label recovery but its posterior probabilities are not trustworthy on this dataset.
**Next**: Require the learned model to beat lexical micro-F1 and filing-type calibration without evaluation tuning.

### 2026-08-21 01:41 +10:00 — Stage 8 candidate-evidence baseline

**Status**: COMPLETED

**Hypothesis**: Returning all deterministic task candidate spans for predicted-material records will provide non-zero source-evidence recall but modest precision.
**Change**: Score the existing candidate spans against canonical evidence offsets; do not learn span selection.
**Config**:
- release: `stage7-ai-panel-v0.1`
- split: frozen 78 train / 22 evaluation
- evidence prediction: all task candidate spans when the associated label baseline predicts material
**Expected outcome**: Non-zero character-overlap recall and lower precision than a trained evidence head.
**Baseline**: None; first evidence-span floor.
**Actual outcome**: Best candidate-span evidence precision 0.125461, recall 0.023952 and F1 0.040225 under the filing-type materiality rule; the other two label rules produced evidence F1 0.
**Delta**: The non-zero-recall hypothesis passed, but coverage is extremely weak.
**Duration**: Shared three-baseline run completed in 0.7 seconds wall time.
**Learning**: Deterministic candidate spans are navigation aids, not adequate extraction evidence.
**Next**: A learned evidence head must exceed F1 0.040225 on the identical evaluation records.

### 2026-08-21 — Stage 9 ModernBERT one-batch systems gate

**Status**: COMPLETED

**Hypothesis**: The pinned ModernBERT-base snapshot can complete one CUDA forward/backward pass at 512 tokens on the local RTX 4070 SUPER and survive a safetensors checkpoint save/reload without changing a sampled parameter.
**Change**: Load only the frozen checkpoint revision, attach an untrained multilabel sequence-classification head, run one development batch, and round-trip the resulting model through a temporary directory.
**Config**:
- encoder: `answerdotai/ModernBERT-base@8949b909ec900327062f0ebf497f51aef5e6f0c8`
- weights SHA-256: `340ac08b74eef0d7bdec2d7981a6a3d4249bf0e6aab60634b72ad02c2b8023a9`
- device: NVIDIA GeForce RTX 4070 SUPER
- batch: 1 development record, maximum 512 tokens
- head: multilabel sequence classification over the frozen ontology label count
- optimization: none; backward validation only
**Expected outcome**: Finite loss and gradients, peak allocated VRAM below 12,282 MiB, and identical sampled parameter before and after safetensors round-trip.
**Baseline**: No learned-model systems proof exists yet.
**Actual outcome**: The first attempt failed before model loading because the installed `torch 2.13.0+cpu` build exposed no CUDA device. After replacing only torch with the official `2.11.0+cu128` wheel, the unchanged gate passed with loss 0.733343, finite gradients on all 138 tensors, 1,456.73 MiB peak allocated VRAM, and an identical sampled embedding parameter after save/reload.
**Delta**: Systems proof advanced from none to a passing CUDA and safetensors round-trip gate. No optimizer step or evaluation-label access occurred.
**Duration**: Successful model gate completed in 3.0 seconds after environment remediation.
**Learning**: GPU hardware visibility through `nvidia-smi` is insufficient; `torch.version.cuda` and `torch.cuda.is_available()` must both be checked before training. The new task head is expectedly absent from base weights and is initialized from scratch.
**Next**: Precompute frozen development embeddings and train only a linear multilabel head against the 62/16 internal split.

### 2026-08-21 — Stage 9 frozen-encoder linear probe

**Status**: COMPLETED

**Hypothesis**: Frozen ModernBERT CLS embeddings plus independent L2-regularized logistic heads will recover non-zero material-label signal on the 16-record internal validation split without any encoder updates or release-evaluation access.
**Change**: Precompute one embedding per development record at the frozen 3,072-token boundary, fit one deterministic logistic head per observed binary label, and use a constant head for labels with only one training class.
**Config**:
- data: frozen Stage 9 package hash `f2bacf5138367f9855daeb8b92389060bbaa83e9f603274e80fe8712fb18e88d`
- split: 62 fit / 16 internal validation / 22 release evaluation sealed
- encoder: exact frozen ModernBERT-base snapshot; no gradients
- pooling: first-token representation
- head: independent logistic regression, L2, C 1.0, threshold 0.5, random seed 17
**Expected outcome**: Finite probabilities and non-zero validation micro-F1; no claim against the Stage 8 release-evaluation bars yet.
**Baseline**: No learned Stage 9 artifact exists.
**Actual outcome**: The probe produced validation exact-set accuracy 0.687500 and label-cell Brier 0.016078, but micro-precision, recall and F1 were all 0. It predicted three positive cells, all false positives, and missed all six true positive cells. The maximum true-positive probability was 0.475841.
**Delta**: A reproducible learned artifact now exists, but the expected non-zero material-label signal failed. The high exact-set score reflects dominant empty label sets and is not promotion evidence.
**Duration**: Frozen embeddings for all 78 records completed in 3.07 seconds at 744.45 MiB peak allocated VRAM; total command time was 13.3 seconds including imports and weight hashing.
**Learning**: An unweighted 0.5-threshold linear head collapses under the small, highly imbalanced development split. Exact-set accuracy alone is actively misleading here.
**Next**: Change only logistic class weighting to `balanced`, retain C 1.0 and threshold 0.5, and test whether minority-label recovery improves.

### 2026-08-21 — Stage 9 balanced frozen-encoder linear probe

**Status**: COMPLETED

**Hypothesis**: Balanced per-label class weights will recover at least one of the six positive validation cells and produce micro-F1 above zero while retaining the identical frozen embeddings, C 1.0 and threshold 0.5.
**Change**: Add `class_weight=balanced` to non-constant logistic heads; no other data, representation, regularization, threshold, or split setting changes.
**Config**:
- parent: Stage 9 frozen-encoder linear probe v0.1
- class weight: balanced
- C: 1.0
- threshold: 0.5
- seed: 17
**Expected outcome**: Validation micro-F1 above 0; exact-set accuracy may fall as minority recall increases.
**Baseline**: Unweighted v0.1 micro-F1 0.0, exact-set accuracy 0.687500.
**Actual outcome**: Validation micro-F1 reached 0.181818 with precision 0.200000 and recall 0.166667. The probe recovered one of six true positive cells, made four false-positive predictions, and retained exact-set accuracy 0.687500. Label-cell Brier worsened from 0.016078 to 0.019891.
**Delta**: Micro-F1 improved by 0.181818 over the unweighted probe, passing the narrow hypothesis, but absolute minority-label recovery remains weak and calibration deteriorated.
**Duration**: Frozen embeddings completed in 3.10 seconds at 744.45 MiB peak allocated VRAM; total command time was 13.4 seconds.
**Learning**: Frozen ModernBERT representations contain some event-label signal, but a linear head on 62 records is not sufficient. Balanced weighting is retained as a development diagnostic, not a promotion candidate.
**Next**: Design a bounded encoder fine-tuning experiment with label, attribute, and evidence objectives; do not open release-evaluation labels until the development configuration is frozen.
