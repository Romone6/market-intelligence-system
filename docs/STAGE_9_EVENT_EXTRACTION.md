# Stage 9: Event Extraction Model

## Current boundary

The credential-independent Stage 9 data package is complete. It derives only from the 78 development members of frozen release `stage7-ai-panel-v0.1` and creates a second group-safe split for model fitting and hyperparameter selection. The 22 release-evaluation annotations are not opened by the packager and remain forbidden for tuning.

The development encoder and tokenizer provenance are now frozen in [`configs/stage9_model.yaml`](../configs/stage9_model.yaml). The selected base is `answerdotai/ModernBERT-base` at revision `8949b909ec900327062f0ebf497f51aef5e6f0c8`: an encoder-only, Apache-2.0 checkpoint with native 8,192-token context and no remote-code requirement. Its configuration, tokenizer metadata, and exact safetensors weight file have been downloaded and hashed. A development-only frozen-encoder probe has run; encoder fine-tuning has not started.

## Frozen development package

- Source release/hash: `stage7-ai-panel-v0.1` / `6cd6233f32b761dfdf047f58530e9f53d59c621985d624f0459642ffbed114db`
- Internal split seed: `stage9-development-v0.1`
- Fit/validation: 62 / 16 records
- Release evaluation: 22 sealed records; labels unread during packaging
- Company leakage: zero
- Related-event leakage: zero
- Package hash: `f2bacf5138367f9855daeb8b92389060bbaa83e9f603274e80fe8712fb18e88d`
- Config: [`configs/stage9_data.yaml`](../configs/stage9_data.yaml)
- Generated package: `data/model/stage9-development-v0.1/`

Each model input includes the relevant filing text, filing type, point-in-time timestamps, and any prior-company disclosure. Company name and entity ID are excluded from model inputs, although the packager uses them to enforce group separation. Targets contain no-event status, event labels, structured attributes, exact character evidence spans, and the ambiguity flag.

## Proof controls

The packager:

- validates the frozen release ID, hash, evidence kind, and counts;
- reads tasks and annotations only for `release.train_event_ids`;
- reproduces every task hash, including non-ASCII filing text;
- keeps connected company and related-event groups on one side of the internal split;
- writes deterministic JSONL files and content hashes;
- records only the sealed evaluation count and membership hash, never evaluation labels.

## Frozen encoder boundary

- Hardware snapshot: NVIDIA GeForce RTX 4070 SUPER (12,282 MiB), Ryzen 5 7600X, and 31.2 GiB RAM.
- Runtime snapshot: Python 3.13.14, PyTorch 2.11.0+cu128, CUDA 12.8, Transformers 5.15.0, and Tokenizers 0.22.2.
- Tokenizer: exact ModernBERT revision above, fast offsets enabled, maximum development length 3,072 tokens.
- Corpus scan: 78 records; p50 600, p90 2,299, p95 2,658, maximum 2,916; zero records exceed 3,072.
- Evidence check: all existing character evidence spans aligned under the frozen tokenizer scan.
- Weight snapshot: `model.safetensors`, 598,635,032 bytes and 137 tensors, SHA-256 `340ac08b74eef0d7bdec2d7981a6a3d4249bf0e6aab60634b72ad02c2b8023a9`.
- Systems gate: a 512-token CUDA forward/backward pass produced finite loss 0.733343 and finite gradients on 138 tensors at 1,456.73 MiB peak allocated VRAM; a temporary safetensors checkpoint round-trip preserved the sampled parameter exactly.

The 3,072-token development limit covers the full current corpus without truncation while leaving memory headroom for the first probe. The encoder's 8,192-token capacity remains available for a later, separately justified configuration.

## Linear-probe result

The unweighted v0.1 probe failed with micro-F1 0.000000 despite exact-set accuracy 0.687500. Changing only per-label class weights to `balanced` in v0.2 recovered one of six true positive validation cells:

- micro-precision 0.200000, recall 0.166667, and F1 0.181818;
- exact-set accuracy 0.687500;
- label-cell Brier 0.019891;
- 62 fit / 16 validation records, 22 release-evaluation labels unread;
- artifact SHA-256 `6ea6352ea299174fa42a1c46b779031043ca420b0522e0382481d01c197f80f1`.

This is evidence of limited representation signal, not a promotable model. It has not been compared with Stage 8 because those bars belong to the still-sealed release-evaluation split.

## Next work

1. Define and test bounded label, attribute, and evidence heads for encoder fine-tuning.
2. Select the development configuration using only the 16-record internal validation split.
3. Freeze the complete configuration, then evaluate once on the 22 sealed records against every Stage 8 bar.

Human gold remains mandatory before final model approval and is triggered early if this development release cannot support the frozen performance targets.

## Reproduce

```powershell
python -m financial_event_model.stage9_data
python -m pytest -o addopts='' -q tests/test_stage9_data.py
python -m financial_event_model.stage9_probe
```
