# Stage 2: SEC Ingestion

## Implemented boundary

The repository now contains a policy-gated SEC collector that:

- sends a declared organization/contact `User-Agent` and gzip/deflate acceptance headers;
- permits only `https://data.sec.gov` and `https://www.sec.gov` requests;
- throttles to 8 requests per second by default, below the SEC maximum of 10;
- retries temporary network errors and HTTP 429/500/502/503/504 responses;
- records every attempted request in an append-only SQLite manifest;
- preserves raw responses in content-addressed storage without overwriting prior content;
- resumes successful downloads when the manifested file still exists;
- detects a changed response when a URL is deliberately refreshed;
- parses current and historical SEC submissions metadata;
- preserves amended accessions as separate filings;
- downloads each selected filing's primary document, complete submission, and filing index;
- splits complete-submission SGML into exact document blocks linked to the parent accession and source request;
- optionally collects XBRL Company Facts for the filing entity.

The implementation uses the Python standard library and Pydantic. It does not add a crawler framework, queue, service, or model dependency.

## SEC access policy

The configuration follows the SEC's current [Developer Resources](https://www.sec.gov/about/developer-resources), [Webmaster FAQ](https://www.sec.gov/about/webmaster-frequently-asked-questions), and [EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces):

- public data APIs require no API key;
- automated requests must declare the organization and contact address;
- aggregate traffic must not exceed 10 requests per second;
- recent submissions use `https://data.sec.gov/submissions/CIK##########.json`;
- older submission history is referenced through additional JSON files;
- Company Facts uses `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`.

## Required identity

Set a real SEC contact identity before any live run:

```powershell
$env:SEC_USER_AGENT = "Organization Name contact@organization.example"
```

The repository does not contain or invent this value. The collector constructor rejects an undeclared value.

## Programmatic collection

```python
import os
from datetime import date

from financial_event_model.ingestion import SecCollector, SecIngestor

collector = SecCollector(
    raw_root="data/raw",
    manifest_path="data/raw/sec_manifest.sqlite3",
    user_agent=os.environ["SEC_USER_AGENT"],
    collector_version="sec-collector-v0.1",
    max_requests_per_second=8,
)
result = SecIngestor(collector).collect_company(
    cik="320193",
    start=date(2015, 1, 1),
    end=date.today(),
    forms={"8-K", "8-K/A", "10-Q", "10-Q/A"},
)
```

## Provenance manifest

`sec_requests` records the URL, request and receive times, status, content type, source last-modified value, content hash, collector version, local path, accession, role, change flag, and error. `sec_documents` links each exact SGML document block to its accession and the complete-submission request that contained it.

Raw paths are derived from SHA-256 content hashes. A repeated URL/content pair therefore cannot create a duplicate raw object, while changed content receives a new path and manifest row.

## Evidence and open gate

Automated fixtures verify request headers, immutable storage, retry logging, resumption, content-change detection, host/identity rejection, current and historical metadata formats, amendment preservation, archive URL construction, SGML document linkage, and a resumed one-company collection flow.

No live SEC request was made because `SEC_USER_AGENT` was absent on 2026-08-20. Stage 2's real-data acceptance gate remains open until a reviewed 50-company/date manifest is collected and audited for:

- every expected 8-K, 8-K/A, 10-Q, and 10-Q/A accession;
- primary/complete/index source presence;
- primary and exhibit linkage;
- distinct amendment preservation;
- zero unexplained duplicate documents;
- explicit failures and resumability;
- reproducibility from the persisted request manifest.

Fixture success proves the collector engine, not historical coverage or dataset completeness.
