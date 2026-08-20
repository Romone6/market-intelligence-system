# Stage 6: Event Ontology v0.1

## Demonstrated boundary

Ontology v0.1 is now a strict, machine-readable annotation guide with 25 leaf labels across earnings, guidance, contracts, capital allocation, management, and corporate actions. The loader validates the guide, event attributes, label references, and the supplied five-category disagreement taxonomy.

The deterministic audit fixture proves that the software can pair exactly two independent decisions per event, calculate leaf and family agreement, require explanations for every disagreement, and distinguish fixture evidence from human evidence. It does not prove that two people have independently annotated 100 real events.

## Canonical guide

[`configs/ontology.yaml`](../configs/ontology.yaml) is the single source of truth for annotators and code. Each leaf contains:

- definition;
- inclusion and exclusion criteria;
- positive example and difficult counterexample;
- valid parent family;
- required attributes;
- incompatible labels.

The guide contains exactly the 25 supplied leaf labels. Adding or removing a leaf requires a new ontology version rather than silently changing version `0.1`.

## Annotation unit

The unit is one economically distinct event, not one filing. A filing may yield zero, one, or several event records. For example, a CEO departure and CEO appointment are separate compatible events even when disclosed together.

Annotators must use only evidence available in the source disclosure and point-in-time context. Subsequent price movement, later commentary, later amendments, and outcome labels cannot resolve the event label or its attributes.

Labels listed as incompatible apply to the same economic subject, metric, period, and basis. Separate metrics or contracts may legitimately produce labels that would be incompatible if applied to one subject. For example, revenue guidance can be raised while EPS guidance is lowered; these are two distinct event records.

## Shared attributes

Every label permits:

- `certainty`
- `status`
- `effective_date`
- `economic_direction`
- `materiality`
- `novelty`
- `time_horizon`
- `affected_financial_channels`
- `conditions_remaining`
- `source_reliability`

`economic_direction` describes the disclosed economic effect. It is not sentiment, predicted return, or a trading instruction. `materiality` and `novelty` must be evidence-based; use `unknown` where the guide permits it instead of inferring certainty.

Contract labels additionally permit `counterparty`, `value`, `currency`, `duration`, `government_customer`, `binding_status`, `revenue_start`, `renewal_option`, and `percentage_of_trailing_revenue`. Preserve disclosed units. Do not manufacture a contract value or trailing-revenue percentage when the inputs are absent.

## Comparison rules

Beat/miss and guidance-change labels require a defensible comparison on the same metric, period, and accounting basis. Revenue growth alone is not a revenue beat. Positive EPS alone is not an EPS beat. Guidance silence is not reaffirmation, and qualitative optimism is not initiated guidance.

Contract awards require evidence of a binding award or executed arrangement. Preferred-bidder status, negotiations, and memoranda of understanding remain outside `contracts.awarded` unless a binding commitment is separately evidenced.

## Disagreement resolution

Every leaf-label disagreement must be assigned exactly one primary cause:

1. `ambiguous_document`
2. `missing_ontology_category`
3. `unclear_definition`
4. `annotation_error`
5. `multiple_valid_events`

The audit rejects duplicate or unrelated resolutions and flags every unresolved disagreement by event ID. A `missing_ontology_category` or repeated `unclear_definition` finding is evidence to revise a future ontology version; it is not permission to silently reinterpret v0.1.

## Acceptance policy

The frozen provisional policy is:

- at least 100 event items;
- exactly two distinct annotators per item;
- family agreement of at least `0.80`;
- every leaf disagreement categorized;
- evidence explicitly recorded as human, not fixture-generated.

The 0.80 threshold is a project policy, not a claim that any particular statistical convention makes the ontology valid. Leaf agreement and the full disagreement distribution remain visible even when the family threshold passes.

## Current evidence

The test fixture contains 100 paired items:

- 90 exact leaf matches;
- five different leaves within the same family;
- five cross-family disagreements;
- ten categorized disagreements;
- 0.90 exact-leaf agreement;
- 0.95 family agreement;
- zero unexplained fixture disagreements.

The fixture contract passes. `stage_acceptance_passed` remains false because the evidence kind is `fixture`.

## Open exit gate

Stage 6 requires two people to label the same 100 real, point-in-time events independently. Their decision records and adjudication categories must be supplied to `audit_annotations(..., evidence_kind="human")`. Until that study exists and passes, the ontology implementation is ready for calibration but the Stage 6 exit criterion remains open.
