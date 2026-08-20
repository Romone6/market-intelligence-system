import hashlib
import json
import sqlite3
from pathlib import Path

import pytest


def _seed_sec_document_manifest(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    primary = (
        b"<DOCUMENT>\n<TYPE>8-K\n<SEQUENCE>1\n<FILENAME>primary.htm\n<TEXT>"
        b"<html><body><h1>Item 1.01 Agreement</h1><p>Primary evidence.</p>"
        b"</body></html></TEXT></DOCUMENT>"
    )
    exhibit = (
        b"<DOCUMENT>\n<TYPE>EX-99.1\n<SEQUENCE>2\n<FILENAME>release.htm\n<TEXT>"
        b"<html><body><h1>Press Release</h1><p>Exhibit evidence.</p>"
        b"</body></html></TEXT></DOCUMENT>"
    )
    bodies = (primary, exhibit)
    paths = [raw_dir / "primary.htm", raw_dir / "release.htm"]
    paths[0].write_bytes(primary)
    paths[1].write_bytes(exhibit)
    manifest = tmp_path / "sec.sqlite3"
    with sqlite3.connect(manifest) as connection:
        connection.execute(
            """
            CREATE TABLE sec_documents (
                document_id INTEGER PRIMARY KEY,
                accession_number TEXT NOT NULL,
                document_type TEXT,
                sequence TEXT,
                filename TEXT,
                description TEXT,
                content_hash TEXT NOT NULL,
                local_path TEXT NOT NULL,
                source_request_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        for document_id, (body, path, document_type, sequence) in enumerate(
            zip(bodies, paths, ("8-K", "EX-99.1"), ("1", "2")),
            start=1,
        ):
            connection.execute(
                """
                INSERT INTO sec_documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    "0000000001-24-000001",
                    document_type,
                    sequence,
                    path.name,
                    None,
                    hashlib.sha256(body).hexdigest(),
                    str(path),
                    1,
                    "2026-08-20T00:00:00+00:00",
                ),
            )
    return manifest, paths, bodies


def test_normalized_section_rejects_an_empty_source_range() -> None:
    from financial_event_model.normalization import NormalizedSection

    with pytest.raises(ValueError, match="source_end"):
        NormalizedSection(
            section_id="section_001",
            heading=None,
            text="evidence",
            source_start=10,
            source_end=10,
            is_table=False,
            is_boilerplate=False,
        )


def test_parser_preserves_prose_offsets_and_typed_table_rows() -> None:
    from financial_event_model.normalization import normalize_sec_html

    raw = (
        b"<html><head><title>Ignored</title></head><body>"
        b"<h1>Item 1.01 Agreement</h1><p>Alpha &amp; Beta signed.</p>"
        b"<table><tr><th>Year</th><th>Value</th></tr>"
        b"<tr><td>2024</td><td>10</td></tr></table>"
        b"</body></html>"
    )

    document = normalize_sec_html(
        raw,
        source_document_id=7,
        accession_number="0000000001-24-000001",
        source_content_hash="a" * 64,
        document_type="8-K",
        filename="filing.htm",
        parser_version="sec-html-v0.1",
    )

    assert document.sections[0].heading == "Item 1.01 Agreement"
    assert document.sections[0].text == "Alpha & Beta signed."
    assert b"Alpha &amp; Beta signed." in raw[
        document.sections[0].source_start : document.sections[0].source_end
    ]
    assert document.sections[1].is_table is True
    assert document.sections[1].text == "Year\tValue\n2024\t10"
    assert b"<table>" in raw[
        document.sections[1].source_start : document.sections[1].source_end
    ]
    assert "Ignored" not in " ".join(section.text for section in document.sections)


@pytest.mark.parametrize(
    "case",
    json.loads(
        (Path(__file__).parent / "fixtures" / "sec_normalization_cases.json").read_text(
            encoding="utf-8"
        )
    ),
    ids=lambda case: case["name"],
)
def test_manually_inspected_normalization_cases(case: dict[str, object]) -> None:
    from financial_event_model.normalization import normalize_sec_html

    raw_text = str(case["raw"])
    repeat = int(case.get("repeat_paragraph", 1))
    if repeat > 1:
        raw_text = raw_text.replace(
            "<p>Long filing evidence.</p>",
            "<p>Long filing evidence.</p>" * repeat,
        )
    raw = raw_text.encode("utf-8")
    arguments = {
        "source_document_id": 11,
        "accession_number": "0000000001-24-000002",
        "source_content_hash": "b" * 64,
        "document_type": str(case["document_type"]),
        "filename": "fixture.htm",
        "parser_version": "sec-html-v0.1",
    }

    first = normalize_sec_html(raw, **arguments)
    second = normalize_sec_html(raw, **arguments)
    combined_text = "\n".join(section.text for section in first.sections)

    assert str(case["expected_text"]) in combined_text
    assert first.model_dump_json() == second.model_dump_json()
    assert all(
        0 <= section.source_start < section.source_end <= len(raw)
        for section in first.sections
    )
    if "expected_heading" in case:
        assert first.sections[0].heading == case["expected_heading"]
    if "expected_warning" in case:
        assert case["expected_warning"] in first.warnings
    if "expected_table_count" in case:
        assert sum(section.is_table for section in first.sections) == case[
            "expected_table_count"
        ]
    if "expected_is_exhibit" in case:
        assert first.is_exhibit is case["expected_is_exhibit"]


def test_parser_normalizes_unicode_and_flags_boilerplate() -> None:
    from financial_event_model.normalization import normalize_sec_html

    raw = (
        "<html><body><header>Repeated banner</header>"
        "<h2>Signatures</h2><p>Pursuant to the requirements, the company\u2019s officers signed.</p>"
        "<footer>Repeated footer</footer></body></html>"
    ).encode("utf-8")

    document = normalize_sec_html(
        raw,
        source_document_id=12,
        accession_number="0000000001-24-000003",
        source_content_hash="c" * 64,
        document_type="8-K",
        filename="unicode.htm",
        parser_version="sec-html-v0.1",
    )

    assert document.sections[0].text.endswith("company's officers signed.")
    assert document.sections[0].is_boilerplate is True
    assert "Repeated banner" not in document.sections[0].text
    assert "Repeated footer" not in document.sections[0].text


def test_parser_recognizes_sec_styled_bold_headings() -> None:
    from financial_event_model.normalization import normalize_sec_html

    raw = (
        b'<html><body><div><font style="font-size:15pt;font-weight:700">'
        b"Quarterly Results</font></div><div>Revenue increased.</div></body></html>"
    )

    document = normalize_sec_html(
        raw,
        source_document_id=13,
        accession_number="0000000001-24-000004",
        source_content_hash="d" * 64,
        document_type="EX-99.1",
        filename="release.htm",
        parser_version="sec-html-v0.1",
    )

    assert document.sections[0].heading == "Quarterly Results"
    assert document.sections[0].text == "Revenue increased."
    assert "missing_headings" not in document.warnings


def test_parser_recognizes_a_bold_block_as_an_item_heading() -> None:
    from financial_event_model.normalization import normalize_sec_html

    raw = (
        b'<html><body><div style="font-weight:bold">Item 5.02 Departure of Officers</div>'
        b"<div>The chief executive resigned.</div></body></html>"
    )

    document = normalize_sec_html(
        raw,
        source_document_id=14,
        accession_number="0000000001-24-000005",
        source_content_hash="e" * 64,
        document_type="8-K",
        filename="filing.htm",
        parser_version="sec-html-v0.1",
    )

    assert document.sections[0].heading == "Item 5.02 Departure of Officers"
    assert document.sections[0].text == "The chief executive resigned."


def test_parser_recognizes_style_on_the_block_itself() -> None:
    from financial_event_model.normalization import normalize_sec_html

    raw = (
        b'<html><body><div style="font-weight:700">Quarterly Results</div>'
        b"<div>Revenue increased.</div></body></html>"
    )

    document = normalize_sec_html(
        raw,
        source_document_id=17,
        accession_number="0000000001-24-000008",
        source_content_hash="2" * 64,
        document_type="EX-99.1",
        filename="release.htm",
        parser_version="sec-html-v0.1",
    )

    assert document.sections[0].heading == "Quarterly Results"
    assert document.sections[0].text == "Revenue increased."


def test_parser_promotes_an_item_table_row_to_the_section_heading() -> None:
    from financial_event_model.normalization import normalize_sec_html

    raw = (
        b"<html><body><table><tr><td><b>Item 2.02.</b></td>"
        b"<td><b>Results of Operations</b></td></tr></table>"
        b"<p>Quarterly revenue increased.</p></body></html>"
    )

    document = normalize_sec_html(
        raw,
        source_document_id=15,
        accession_number="0000000001-24-000006",
        source_content_hash="f" * 64,
        document_type="8-K",
        filename="filing.htm",
        parser_version="sec-html-v0.1",
    )

    assert document.sections[0].is_table is True
    assert document.sections[0].heading == "Item 2.02. Results of Operations"
    assert document.sections[1].heading == "Item 2.02. Results of Operations"


def test_item_heading_survives_an_immediate_bold_subheading() -> None:
    from financial_event_model.normalization import normalize_sec_html

    raw = (
        b'<html><body><div style="font-weight:bold">Item 5.07 Shareholder Vote</div>'
        b'<div><strong>Annual meeting results</strong></div>'
        b"<div>Shareholders approved the proposal.</div></body></html>"
    )

    document = normalize_sec_html(
        raw,
        source_document_id=16,
        accession_number="0000000001-24-000007",
        source_content_hash="1" * 64,
        document_type="8-K",
        filename="filing.htm",
        parser_version="sec-html-v0.1",
    )

    assert document.sections[0].heading == "Item 5.07 Shareholder Vote"
    assert document.sections[0].text == (
        "Annual meeting results\n\nShareholders approved the proposal."
    )


def test_pipeline_persists_reuses_and_links_exhibits_without_changing_raw(tmp_path) -> None:
    from financial_event_model.normalization import SecNormalizationPipeline

    sec_manifest, raw_paths, raw_before = _seed_sec_document_manifest(tmp_path)
    normalization_manifest = tmp_path / "normalized.sqlite3"
    pipeline = SecNormalizationPipeline(
        sec_manifest_path=sec_manifest,
        output_root=tmp_path / "normalized",
        normalization_manifest_path=normalization_manifest,
        parser_version="sec-html-v0.1",
    )

    first = pipeline.run(limit=2)
    second = pipeline.run(limit=2)

    assert first.completed == 2
    assert first.reused == 0
    assert first.failed == 0
    assert second.completed == 0
    assert second.reused == 2
    assert [path.read_bytes() for path in raw_paths] == list(raw_before)
    with sqlite3.connect(normalization_manifest) as connection:
        rows = connection.execute(
            """
            SELECT source_document_id, parent_document_id, is_exhibit,
                   success, local_path, output_hash
            FROM normalized_documents
            ORDER BY source_document_id
            """
        ).fetchall()
    assert rows[0][0:4] == (1, None, 0, 1)
    assert rows[1][0:4] == (2, 1, 1, 1)
    assert all(Path(row[4]).is_file() for row in rows)
    assert all(len(row[5]) == 64 for row in rows)


def test_pipeline_records_a_source_hash_failure_and_continues(tmp_path) -> None:
    from financial_event_model.normalization import SecNormalizationPipeline

    sec_manifest, raw_paths, _ = _seed_sec_document_manifest(tmp_path)
    raw_paths[1].write_bytes(b"changed after Stage 2")
    normalization_manifest = tmp_path / "normalized.sqlite3"
    pipeline = SecNormalizationPipeline(
        sec_manifest_path=sec_manifest,
        output_root=tmp_path / "normalized",
        normalization_manifest_path=normalization_manifest,
        parser_version="sec-html-v0.1",
    )

    result = pipeline.run(limit=2)

    assert result.completed == 1
    assert result.failed == 1
    assert result.failed_document_ids == (2,)
    with sqlite3.connect(normalization_manifest) as connection:
        failed = connection.execute(
            """
            SELECT success, error
            FROM normalized_documents
            WHERE source_document_id = 2
            """
        ).fetchone()
    assert failed[0] == 0
    assert "source content hash" in failed[1]


def test_pipeline_excludes_xbrl_renderer_support_pages(tmp_path) -> None:
    from financial_event_model.normalization import SecNormalizationPipeline

    sec_manifest, _, _ = _seed_sec_document_manifest(tmp_path)
    renderer = tmp_path / "raw" / "R1.htm"
    body = b"<html><body><table><tr><td>Renderer support page</td></tr></table></body></html>"
    renderer.write_bytes(body)
    with sqlite3.connect(sec_manifest) as connection:
        connection.execute(
            """
            INSERT INTO sec_documents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                3,
                "0000000001-24-000001",
                "XML",
                "3",
                "R1.htm",
                "XBRL renderer support page",
                hashlib.sha256(body).hexdigest(),
                str(renderer),
                1,
                "2026-08-20T00:00:00+00:00",
            ),
        )
    pipeline = SecNormalizationPipeline(
        sec_manifest_path=sec_manifest,
        output_root=tmp_path / "normalized",
        normalization_manifest_path=tmp_path / "normalized.sqlite3",
        parser_version="sec-html-v0.1",
    )

    result = pipeline.run(limit=3)

    assert result.selected == 2
    assert result.source_document_ids == (1, 2)


def test_normalization_migration_has_a_working_down_script(tmp_path) -> None:
    from financial_event_model.normalization import NormalizationStore

    manifest = tmp_path / "normalized.sqlite3"
    store = NormalizationStore(tmp_path / "normalized", manifest)
    down = (
        Path(__file__).parents[1]
        / "src"
        / "financial_event_model"
        / "normalization"
        / "migrations"
        / "0001_normalized_documents.down.sql"
    ).read_text(encoding="utf-8")

    with store._connect() as connection:
        connection.executescript(down)
        table = connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name = 'normalized_documents'
            """
        ).fetchone()

    assert table is None
