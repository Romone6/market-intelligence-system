# Stage 6 Ontology v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define the exact 25-leaf financial-event extraction contract, its annotation semantics, and an auditable two-annotator disagreement gate.

**Architecture:** Replace the Stage 0 label-name scaffold with one canonical, machine-readable YAML annotation guide. Load it into strict Pydantic contracts, validate event attributes against the selected leaf, and calculate leaf/family agreement without treating deterministic fixture annotations as human evidence.

**Tech Stack:** Python 3.11+, Pydantic 2.12.5 in the verified environment, PyYAML 6.0.3 in the verified environment, pytest.

## Global Constraints

- Preserve exactly the six supplied families and 25 supplied leaf labels.
- Every leaf must define its definition, inclusion criteria, exclusion criteria, positive example, difficult counterexample, valid parent, required attributes, and incompatible labels.
- Every event may use the ten supplied shared attributes; contract events may additionally use the nine supplied contract attributes.
- The only disagreement categories are `ambiguous_document`, `missing_ontology_category`, `unclear_definition`, `annotation_error`, and `multiple_valid_events`.
- A fixture audit proves software behavior only. Stage acceptance requires 100 real events independently labelled by two people.
- Do not add annotation UI, model inference, database persistence, or training dependencies in Stage 6.

The existing strict contract pattern is retained. Pydantic documents that setting `extra` to `forbid` means extra data “is not permitted” ([Pydantic models](https://pydantic.dev/docs/validation/latest/concepts/models/#extra-data)). Pydantic 2.12.5 is the installed patch; its release is described as “the fifth 2.12 patch release” ([Pydantic 2.12.5 release](https://github.com/pydantic/pydantic/releases/tag/v2.12.5)).

---

### Task 1: Freeze the canonical ontology guide

**Files:**
- Modify: `configs/ontology.yaml`
- Create: `tests/test_ontology.py`

**Interfaces:**
- Consumes: the exact Stage 6 label and attribute lists in `docs/PROJECT_CHARTER.md` and the source specification.
- Produces: a single YAML definition containing acceptance policy, attribute schemas, 25 complete label guides, and five disagreement categories.

- [x] **Step 1: Write a failing structure test**

```python
# Pydantic/PyYAML grounding: https://pyyaml.org/wiki/PyYAMLDocumentation
ontology = load_ontology(ROOT / "configs" / "ontology.yaml")
assert len(ontology.labels) == 25
assert all(label.definition and label.positive_example for label in ontology.labels)
```

PyYAML documents that `safe_load` “cannot construct an arbitrary Python object,” which is the required trust boundary for configuration loading ([PyYAML documentation](https://pyyaml.org/wiki/PyYAMLDocumentation)).

- [x] **Step 2: Run the focused test and observe the missing loader failure**

Run: `python -m pytest tests/test_ontology.py -q`

Expected: collection/import failure because `financial_event_model.ontology` does not yet expose `load_ontology`.

- [x] **Step 3: Expand `configs/ontology.yaml` into the complete guide**

Every entry must use this complete shape; no definition field may be empty:

```yaml
# Safe loading API: https://pyyaml.org/wiki/PyYAMLDocumentation
- event_type: contracts.awarded
  valid_parent: contracts
  definition: A binding material contract newly awarded to the issuer.
  inclusion_criteria: [The filing identifies a newly awarded binding arrangement.]
  exclusion_criteria: [A non-binding proposal or existing-contract update.]
  positive_example: The issuer signs a five-year supply agreement with Customer A.
  difficult_counterexample: The issuer is selected as a preferred bidder but no contract is executed.
  required_attributes: [certainty, status, source_reliability, counterparty, binding_status]
  incompatible_labels: [contracts.lost, contracts.cancelled]
```

- [x] **Step 4: Verify the YAML parses safely**

Run: `python -c "from pathlib import Path; import yaml; assert yaml.safe_load(Path('configs/ontology.yaml').read_text())['version'] == '0.1'"`

Expected: exit 0.

### Task 2: Implement strict ontology and event-attribute validation

**Files:**
- Delete: `src/financial_event_model/ontology/.gitkeep`
- Create: `src/financial_event_model/ontology/__init__.py`
- Create: `src/financial_event_model/ontology/models.py`
- Create: `src/financial_event_model/ontology/loader.py`
- Modify: `tests/test_ontology.py`

**Interfaces:**
- Consumes: `configs/ontology.yaml`.
- Produces: `load_ontology(path) -> OntologyDefinition` and `OntologyDefinition.validate_event(event_type, attributes)`.

- [x] **Step 1: Add failing tests for unknown labels, missing required attributes, invalid enum values, unknown attributes, and broken label references**

```python
# Pydantic model validation: https://pydantic.dev/docs/validation/latest/concepts/models/
with pytest.raises(ValueError, match="missing required attributes"):
    ontology.validate_event("contracts.awarded", {"certainty": "confirmed"})
```

Pydantic states that `model_validate()` validates an object against the model ([Pydantic models](https://pydantic.dev/docs/validation/latest/concepts/models/#validating-data) — “Validates the given object against”).

- [x] **Step 2: Observe the focused failures**

Run: `python -m pytest tests/test_ontology.py -q`

Expected: failures for the unimplemented models and validation methods.

- [x] **Step 3: Implement the minimal contracts and loader**

```python
# Pydantic validator API: https://pydantic.dev/docs/validation/latest/concepts/validators/#model-validators
class OntologyDefinition(Contract):
    version: Literal["0.1"]
    labels: tuple[LabelDefinition, ...]

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        event_types = {label.event_type for label in self.labels}
        if len(event_types) != len(self.labels):
            raise ValueError("event_type values must be unique")
        return self
```

Pydantic’s documented model validators operate on the whole model after field validation ([Pydantic validators](https://pydantic.dev/docs/validation/latest/concepts/validators/#model-validators) — “validation actions on the whole model”).

- [x] **Step 4: Make the validation tests pass**

Run: `python -m pytest tests/test_ontology.py -q`

Expected: all current ontology tests pass.

### Task 3: Add an agreement audit that preserves the human-evidence boundary

**Files:**
- Create: `src/financial_event_model/ontology/agreement.py`
- Modify: `src/financial_event_model/ontology/__init__.py`
- Modify: `tests/test_ontology.py`

**Interfaces:**
- Consumes: exactly two `AnnotationDecision` records per event plus optional `DisagreementResolution` records.
- Produces: `audit_annotations(..., evidence_kind='fixture'|'human') -> AgreementReport` with exact leaf agreement, family agreement, categorized disagreements, unexplained IDs, contract status, and stage-acceptance status.

- [x] **Step 1: Add a 100-event failing fixture audit**

```python
# StrEnum API: https://docs.python.org/3.13/library/enum.html#enum.StrEnum
report = audit_annotations(decisions, resolutions, ontology, evidence_kind="fixture")
assert report.item_count == 100
assert report.family_agreement == pytest.approx(0.95)
assert report.unexplained_event_ids == ()
assert report.stage_acceptance_passed is False
```

Python documents that `StrEnum` members “are also strings,” allowing stable serialized policy values without another dependency ([Python `StrEnum`](https://docs.python.org/3.13/library/enum.html#enum.StrEnum)).

- [x] **Step 2: Observe the missing audit failure**

Run: `python -m pytest tests/test_ontology.py -q`

Expected: import failure for `audit_annotations`.

- [x] **Step 3: Implement deterministic pairing and disagreement accounting**

Reject missing/extra decisions, duplicate annotators, invalid labels, invalid resolution categories, and resolutions for agreeing events. Stage acceptance is true only for `evidence_kind='human'`, at least 100 paired items, family agreement at or above the configured threshold, and zero unexplained disagreements.

```python
# Unique enum values: https://docs.python.org/3.13/library/enum.html#enum.unique
@unique
class DisagreementCategory(StrEnum):
    AMBIGUOUS_DOCUMENT = "ambiguous_document"
    MISSING_ONTOLOGY_CATEGORY = "missing_ontology_category"
    UNCLEAR_DEFINITION = "unclear_definition"
    ANNOTATION_ERROR = "annotation_error"
    MULTIPLE_VALID_EVENTS = "multiple_valid_events"
```

Python’s `unique` decorator raises when an enum contains aliases ([Python `unique`](https://docs.python.org/3.13/library/enum.html#enum.unique) — “ensures only one name is bound”).

- [x] **Step 4: Make the 100-event audit and error cases pass**

Run: `python -m pytest tests/test_ontology.py -q`

Expected: all ontology tests pass; fixture contract passes while human acceptance remains false.

### Task 4: Record the Stage 6 proof boundary and verify the repository

**Files:**
- Create: `docs/STAGE_6_ONTOLOGY.md`
- Modify: `README.md`
- Modify: `docs/ROADMAP.md`
- Modify: this plan

**Interfaces:**
- Produces: an accurate Stage 6 implementation report and the exact commands needed for the future real dual-annotation gate.

- [x] **Step 1: Document fixture evidence separately from human evidence**

The report must state that a deterministic 100-item audit validates pairing, metrics, and categorization only. It must not claim that two people labelled real filings.

- [x] **Step 2: Run the complete verification gate**

```powershell
# Python/Pydantic environment documented at https://pydantic.dev/docs/validation/latest/concepts/models/
python -m pip install -e ".[dev]"
python -m pytest
python -m compileall -q src tests
git diff --check
```

- [x] **Step 3: Review and commit the exact Stage 6 file set**

Run: `git diff --cached --check`

Commit: `feat(ontology): define event taxonomy and agreement audit`

## Correctness traces

1. `contracts.awarded` plus only `certainty` enters `validate_event`; the label resolves; allowed attributes resolve from shared plus contract-specific definitions; required attributes include `status`, `source_reliability`, `counterparty`, and `binding_status`; validation raises a missing-attributes error.
2. A 100-item fixture has 90 exact matches, five same-family leaf disagreements, and five cross-family disagreements; leaf agreement is `90 / 100 = 0.90`; family agreement is `95 / 100 = 0.95`; all ten resolutions are counted; fixture contract passes but stage acceptance remains false because the evidence is not human.

## Proof boundary

The code can prove schema completeness and deterministic audit behavior. Only a future recorded study involving two independent people and 100 real events can satisfy the Stage 6 exit criterion.
