# User Manual Inputs and Walkthroughs

Use this as the authoritative list of work that requires your judgement, account access, design material, or human annotation. You do not need to write code. Check an item only when the described evidence exists.

> **Human-gold freeze — 2026-08-21:** Sections 2, 4, 5 and 6 are preserved but require no action now. Codex must not repeatedly request this work. Unfreeze them before model finalization, or earlier if the embedding model misses its frozen evaluation target.

## Do now

### 1. Send the dashboard design package

- [x] Attach 3–10 visual references: screenshots, sketches, Figma frames, websites, component examples, colour palettes, fonts, or existing source files.
- [x] For every reference, state what you want retained. Examples: “use this left navigation,” “this table density,” “this chart treatment,” or “this glow, but less saturated.”
- [ ] Complete the dashboard decision template below.
- [ ] Confirm whether the first dashboard release should use a paper portfolio. **Recommended default: yes.**
- [x] Identify the likely eventual holdings source: IBKR.

#### Walkthrough

1. Attach the reference material directly to the Codex task. If a reference is a website, send its exact URL and name the relevant screen.
2. Mark each reference with one of: `must use`, `inspiration`, or `avoid`.
3. Copy this template into your reply and fill in what you already know. `Undecided` is acceptable.

```text
Dashboard/product name:
Primary user: just me / team / undecided
First data mode: paper portfolio / imported holdings / live read-only holdings
Likely future broker or holdings source:

Overall feeling (three words):
Preferred accent colour(s):
Colours to avoid:
Preferred font or font style:
Compact data-dense or spacious:

Must-have overview cards:
Must-have holdings columns:
Must-have charts:
Must-have navigation items:
Mobile support: essential / useful / desktop first

Reference 1 and what I like:
Reference 2 and what I like:
Reference 3 and what I like:
Anything I explicitly do not want:
```

4. Do not invent risk or model metrics just to fill the template. The first visual prototype can use conspicuously marked fixture data.
5. Approval of the visual prototype will authorize its implementation, but it will not authorize broker connectivity or live orders.

### 2. FROZEN — choose the two calibration annotators before finalization

- [ ] Nominate two people who can independently review financial disclosures. You may be one of them.
- [ ] Choose a stable, non-secret ID for each person, such as `romone` and `annotator-b`.
- [ ] Confirm that both people can review the same 100 documents without comparing answers during the first pass.
- [ ] Send only the two IDs to Codex. Do not send passwords or personal identity documents.

#### Walkthrough

1. Pick annotators who can distinguish explicit disclosure evidence from inference.
2. Give each person the [Stage 6 ontology guide](STAGE_6_ONTOLOGY.md) before annotation begins.
3. Agree that neither annotator will use subsequent price movement, later news, or the other person's answers.
4. Reply with:

```text
Calibration annotator A ID:
Calibration annotator B ID:
Both can independently label the same 100 documents: yes / no
```

5. Codex has reported **“calibration queue ready.”** Once the two stable IDs are chosen, both independent passes can begin.

### 3. Arrange consolidated US market-data access

- [ ] Choose Alpaca SIP or provide details of a licensed equivalent daily-bar source.
- [ ] Confirm that the account is entitled to consolidated US exchange data, not only the IEX feed.
- [ ] Obtain the API key ID and secret, but do not paste either credential into chat or commit them to Git.
- [ ] Tell Codex only the provider name and whether consolidated access is active.

#### Walkthrough for Alpaca

1. Open your Alpaca market-data account and inspect its subscription or entitlement page.
2. Confirm the feed includes consolidated SIP data. If it only says IEX, mark this checklist item incomplete.
3. Keep the key and secret in your password manager.
4. When Codex reports **“market acceptance runner ready,”** open a fresh PowerShell window in `C:\QUANI HOOTT` and set session-only variables without writing the secret into command history:

```powershell
$env:APCA_API_KEY_ID = Read-Host "Alpaca API key ID"
$alpacaSecret = Read-Host "Alpaca API secret" -AsSecureString
$env:APCA_API_SECRET_KEY = [System.Net.NetworkCredential]::new("", $alpacaSecret).Password
Get-ChildItem Env:APCA_API_* | Select-Object Name
```

5. The last command must show both variable names but not their values.
6. Run the acceptance command Codex supplies in that same PowerShell window. Closing the window removes those session variables.

## Frozen until pre-finalization or an embedding-performance trigger

### 4. FROZEN — complete the independent 100-document calibration round

- [ ] Annotator A labels all 100 documents using only ID A.
- [ ] Annotator B independently labels the same 100 documents using only ID B.
- [ ] Both annotators use `No material event` when the source contains no qualifying event.
- [ ] Both annotators use the ambiguity flag when the evidence genuinely cannot support a clean decision.
- [ ] Neither annotator treats highlighted candidate evidence or candidate labels as ground truth.
- [ ] Both annotators tell Codex when their independent pass is complete.

#### Walkthrough for each annotator

1. Open PowerShell in `C:\QUANI HOOTT`.
2. Start the local application:

```powershell
python -m financial_event_model.annotation serve
```

3. Open `http://127.0.0.1:8765/?annotator_id=YOUR_ASSIGNED_ID` in a browser. Do not expose this local research server to a network.
4. Use only your assigned annotator ID. Reusing the other person's ID invalidates the independence audit.
5. Read the company, filing type, publication time, tradable time, relevant section, highlighted evidence, and prior disclosure.
6. Select every independently material event supported by the section. The calibration queue intentionally contains no preselected candidate labels.
7. Complete every required attribute using only disclosed or defensibly point-in-time information.
8. Keep only evidence spans that directly support the label.
9. Set confidence between `0` and `1`; use the ambiguity flag rather than pretending certainty.
10. Select `No material event` only when no ontology event is materially supported. Do not combine it with event labels.
11. Leave adjudication status as `Submitted` during the independent pass.
12. Save. The application advances to the next unlabelled task for your ID.
13. When the completion page appears, stop and tell Codex your annotator ID is complete.

You can check progress at any time without changing data:

```powershell
python -m financial_event_model.annotation status --annotator-id YOUR_ASSIGNED_ID
```

### 5. FROZEN — resolve calibration disagreements

- [ ] Review only the disagreement queue produced after both independent passes finish.
- [ ] Assign one primary cause to every disagreement.
- [ ] Agree on the final label or exclusion for every disputed event.
- [ ] Approve an ontology revision when disagreements reveal a missing or unclear definition.

#### Walkthrough

1. Wait for Codex to produce the agreement report and disagreement IDs.
2. Meet with the second annotator only after both independent submissions are frozen.
3. For each disagreement, select exactly one cause:
   - `ambiguous_document`
   - `missing_ontology_category`
   - `unclear_definition`
   - `annotation_error`
   - `multiple_valid_events`
4. Record a final adjudicated annotation or exclude the item with a written reason.
5. If a definition changes, approve a new ontology version; do not silently reinterpret ontology `0.1`.

## Frozen human-gold expansion

### 6. FROZEN — complete the gold-set round before final model approval

- [ ] Review 500–1,000 real events.
- [ ] Ensure at least 20% are independently double-labelled; target 30%.
- [ ] Adjudicate every observed disagreement.
- [ ] Approve the frozen evaluation/train split only after the leakage report shows zero shared companies and zero shared related-event groups.

Codex will prepare the queue, reports, and frozen release. Your role is to supply honest human decisions and approve the resulting evidence—not to run dataset-building code manually.

### 7. Supply live-capital decisions only at the final gate

- [ ] Do not provide broker secrets or capital authorization during the current stages.
- [ ] Later, specify position, exposure, liquidity, loss, and transaction-cost limits.
- [ ] Later, approve the broker/account configuration, tested kill switch, and explicit live-trading authorization.

Until those final items exist, dashboard holdings remain fixture, imported, read-only, or paper positions, and all order routes remain disabled.
