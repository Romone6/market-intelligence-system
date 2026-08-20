# Stage 3: Normalization and Evidence Mapping

## Implemented boundary

Stage 3 converts exact Stage 2 SEC document blocks into deterministic JSON without changing the raw object. Each normalized document records:

- the Stage 2 document ID, accession, source hash, type, and filename;
- parser version and deterministic normalized-document ID;
- exhibit status and the parent primary-document ID;
- detected language, parsing-quality score, and explicit warnings;
- ordered prose and table sections with headings, boilerplate flags, and exact source ranges.

`source_start` and `source_end` are half-open byte offsets into the exact bytes at `sec_documents.local_path`. The parser reads a Latin-1 view solely so every parser character position maps one-to-one to a source byte, then decodes text fragments as UTF-8 or Windows-1252 for normalized output.

## Parser behavior

The standard-library parser:

- removes `head`, `script`, `style`, `header`, `footer`, `nav`, hidden elements, and inline-XBRL hidden content;
- detects semantic headings, SEC `Item` headings, bold styled headings, and `Item` rows embedded in tables;
- groups paragraphs under the active heading;
- preserves tables as separate sections with newline-delimited rows and tab-delimited cells;
- normalizes entities, Unicode compatibility forms, smart quotes, and whitespace;
- flags forward-looking, safe-harbor, signature, and filing-requirement boilerplate;
- reports `malformed_html`, `missing_headings`, `low_text_density`, and `no_text` deterministically;
- assigns a transparent quality score from those warnings;
- labels sufficiently supported English text as `en` and short/unsupported text as `unknown`.

Only stored `.htm`, `.html`, and `.txt` primary filings and exhibits are selected. XBRL renderer support pages, images, archives, schemas, stylesheets, and scripts remain preserved in Stage 2 raw storage but are not treated as disclosure prose.

## Separate persistence

Normalized JSON lives under `data/normalized/sec/` and is addressed by its SHA-256 output hash. `data/normalized/normalization_manifest.sqlite3` records source and output hashes, parser version, artifact path, parent document, language, quality, warnings, success, and error.

The normalized manifest is separate from the SEC request manifest. Its migration is additive and reversible. Reusing `(source_document_id, source_hash, parser_version)` makes reruns network-free and idempotent; a source-hash mismatch becomes a recorded failure rather than being parsed.

## Programmatic use

```python
from financial_event_model.normalization import SecNormalizationPipeline

pipeline = SecNormalizationPipeline(
    sec_manifest_path="data/raw/sec_manifest.sqlite3",
    output_root="data/normalized",
    normalization_manifest_path="data/normalized/normalization_manifest.sqlite3",
    parser_version="sec-html-v0.1",
)
result = pipeline.run(limit=100)
```

The committed defaults are in `configs/normalization.yaml`. Generated normalized objects, manifests, superseded audit artifacts, and acceptance JSON remain ignored.

## 100-document acceptance evidence

The 2026-08-20 acceptance run selected 100 documents across CIKs from the frozen Stage 2 cohort:

- 60 primary filings: 56 `8-K`, 2 `8-K/A`, and 2 `10-Q`;
- 40 exhibits, including 31 `EX-99.1` documents;
- 100 successes and zero unrecorded or recorded parser failures;
- 100 reused artifacts on the immediate rerun;
- 1,028 separately typed table sections;
- 122 boilerplate-flagged sections;
- 100 English detections;
- mean quality `0.996`, minimum quality `0.60`;
- zero invalid source ranges;
- zero normalized-output hash mismatches;
- zero fresh-versus-stored deterministic mismatches;
- zero raw-source hash mismatches;
- zero new SEC requests;
- zero primary filings without a detected SEC `Item` heading.

One AMD `EX-99.2` earnings-slide document has malformed presentation markup and no recoverable heading structure. It is retained with `malformed_html` and `missing_headings` warnings at quality `0.60`; it is not silently promoted as a clean parse.

## Proof boundary

This evidence proves deterministic structural normalization, byte-range traceability, typed-table preservation, exhibit linkage, source immutability, and visible parser failures for the frozen 100-document cohort. The quality score is a parser diagnostic, not a learned or externally validated measure of economic relevance. Event extraction, evidence-span supervision, and semantic recall are later-stage claims.
