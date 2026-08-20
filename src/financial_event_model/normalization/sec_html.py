"""Deterministic SEC HTML normalization with byte-range provenance."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Iterable

from .models import NormalizedDocument, NormalizedSection


_BLOCK_TAGS = {"blockquote", "div", "li", "p", "pre"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_SKIP_TAGS = {"head", "header", "nav", "script", "style", "footer", "ix:hidden"}
_BOILERPLATE_PATTERNS = (
    "forward-looking statement",
    "pursuant to the requirements",
    "safe harbor",
    "signature",
)
_ITEM_HEADING = re.compile(r"^item\s+\d+(?:\.\d+)?\b", re.IGNORECASE)


def _clean_text(value: str) -> str:
    value = html.unescape(value)
    value = unicodedata.normalize("NFKC", value).replace("\xa0", " ")
    value = value.translate(
        str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'})
    )
    return re.sub(r"\s+", " ", value).strip()


@dataclass
class _Block:
    kind: str
    start: int
    end: int
    text: str


@dataclass
class _OpenBlock:
    kind: str
    tag: str
    start: int
    fragments: list[str] = field(default_factory=list)


class _BytePositionParser(HTMLParser):
    def __init__(self, raw: bytes) -> None:
        super().__init__(convert_charrefs=False)
        self.raw = raw
        self.source = raw.decode("latin-1")
        try:
            raw.decode("utf-8")
            self.text_encoding = "utf-8"
        except UnicodeDecodeError:
            self.text_encoding = "windows-1252"
        self.line_starts = [0]
        for match in re.finditer("\n", self.source):
            self.line_starts.append(match.end())
        self.blocks: list[_Block] = []
        self.warnings: set[str] = set()
        self.open_block: _OpenBlock | None = None
        self.skip_tag: str | None = None
        self.skip_same_depth = 0
        self.table_depth = 0
        self.table_start = 0
        self.table_rows: list[list[str]] = []
        self.table_row: list[str] | None = None
        self.table_cell: list[str] | None = None

    def _offset(self) -> int:
        line, column = self.getpos()
        return self.line_starts[line - 1] + column

    def _tag_end(self, start: int) -> int:
        end = self.source.find(">", start)
        return len(self.source) if end < 0 else end + 1

    def _decode(self, value: str) -> str:
        raw_fragment = value.encode("latin-1")
        return raw_fragment.decode(self.text_encoding, errors="replace")

    def _finish_block(self, end: int, *, malformed: bool = False) -> None:
        if self.open_block is None:
            return
        text = _clean_text("".join(self.open_block.fragments))
        if text:
            self.blocks.append(
                _Block(self.open_block.kind, self.open_block.start, end, text)
            )
        if malformed:
            self.warnings.add("malformed_html")
        self.open_block = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.casefold()
        start = self._offset()
        if self.skip_tag is not None:
            if tag == self.skip_tag:
                self.skip_same_depth += 1
            return
        attributes = {name.casefold(): value or "" for name, value in attrs}
        style = attributes.get("style", "").replace(" ", "").casefold()
        styled_heading = tag in {"b", "strong"} or bool(
            re.search(r"font-weight:(?:bold|[6-9]00)", style)
        )
        if tag in _SKIP_TAGS or "display:none" in style or "visibility:hidden" in style:
            self.skip_tag = tag
            self.skip_same_depth = 1
            return
        if tag == "table":
            if self.table_depth == 0:
                self._finish_block(start)
                self.table_start = start
                self.table_rows = []
            self.table_depth += 1
            return
        if self.table_depth:
            if tag == "tr":
                self.table_row = []
            elif tag in {"td", "th"}:
                self.table_cell = []
            return
        if self.open_block is not None and styled_heading:
            self.open_block.kind = "heading"
        if tag in _HEADING_TAGS or tag in _BLOCK_TAGS:
            if self.open_block is not None:
                self._finish_block(start, malformed=self.open_block.tag != "div")
            self.open_block = _OpenBlock(
                "heading" if tag in _HEADING_TAGS or styled_heading else "prose",
                tag,
                start,
            )
        elif tag == "br" and self.open_block is not None:
            self.open_block.fragments.append("\n")

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() == "br" and self.open_block is not None:
            self.open_block.fragments.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        start = self._offset()
        end = self._tag_end(start)
        if self.skip_tag is not None:
            if tag == self.skip_tag:
                self.skip_same_depth -= 1
                if self.skip_same_depth == 0:
                    self.skip_tag = None
            return
        if self.table_depth:
            if tag in {"td", "th"} and self.table_cell is not None:
                if self.table_row is None:
                    self.table_row = []
                self.table_row.append(_clean_text("".join(self.table_cell)))
                self.table_cell = None
            elif tag == "tr" and self.table_row is not None:
                if any(self.table_row):
                    self.table_rows.append(self.table_row)
                self.table_row = None
            elif tag == "table":
                self.table_depth -= 1
                if self.table_depth == 0:
                    text = "\n".join("\t".join(row) for row in self.table_rows)
                    if text:
                        self.blocks.append(_Block("table", self.table_start, end, text))
            return
        if self.open_block is not None and tag == self.open_block.tag:
            self._finish_block(end)

    def handle_data(self, data: str) -> None:
        decoded = self._decode(data)
        if self.skip_tag is not None:
            return
        if self.table_depth and self.table_cell is not None:
            self.table_cell.append(decoded)
        elif self.open_block is not None:
            self.open_block.fragments.append(decoded)

    def handle_entityref(self, name: str) -> None:
        self._append_reference(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._append_reference(f"&#{name};")

    def _append_reference(self, value: str) -> None:
        decoded = html.unescape(value)
        if self.table_depth and self.table_cell is not None:
            self.table_cell.append(decoded)
        elif self.open_block is not None:
            self.open_block.fragments.append(decoded)

    def finish(self) -> tuple[list[_Block], set[str]]:
        if self.open_block is not None:
            self._finish_block(len(self.raw), malformed=True)
        if self.table_depth:
            self.warnings.add("malformed_html")
        if self.skip_tag is not None:
            self.warnings.add("malformed_html")
        return self.blocks, self.warnings


def _is_boilerplate(heading: str | None, text: str) -> bool:
    combined = f"{heading or ''} {text}".casefold()
    return any(pattern in combined for pattern in _BOILERPLATE_PATTERNS)


def _language(sections: Iterable[NormalizedSection]) -> str:
    text = " ".join(section.text for section in sections).casefold()
    words = re.findall(r"[a-z]+", text)
    if len(words) < 5:
        return "unknown"
    common = {"and", "company", "for", "in", "of", "the", "to"}
    return "en" if sum(word in common for word in words) >= 2 else "unknown"


def _build_sections(blocks: list[_Block]) -> tuple[NormalizedSection, ...]:
    sections: list[NormalizedSection] = []
    heading: str | None = None
    heading_start: int | None = None
    prose: list[_Block] = []

    def append_prose() -> None:
        nonlocal prose, heading_start
        if not prose:
            return
        text = "\n\n".join(block.text for block in prose)
        sections.append(
            NormalizedSection(
                section_id=f"section_{len(sections) + 1:03d}",
                heading=heading,
                text=text,
                source_start=heading_start if heading_start is not None else prose[0].start,
                source_end=prose[-1].end,
                is_table=False,
                is_boilerplate=_is_boilerplate(heading, text),
            )
        )
        prose = []
        heading_start = None

    for block in blocks:
        if block.kind == "heading" or (
            block.kind == "prose"
            and len(block.text) <= 180
            and _ITEM_HEADING.match(block.text)
        ):
            append_prose()
            if (
                heading is not None
                and _ITEM_HEADING.match(heading)
                and not _ITEM_HEADING.match(block.text)
            ):
                prose.append(block)
                continue
            heading = block.text
            heading_start = block.start
        elif block.kind == "table":
            append_prose()
            if _ITEM_HEADING.match(block.text):
                heading = _clean_text(block.text.splitlines()[0].replace("\t", " "))
            sections.append(
                NormalizedSection(
                    section_id=f"section_{len(sections) + 1:03d}",
                    heading=heading,
                    text=block.text,
                    source_start=block.start,
                    source_end=block.end,
                    is_table=True,
                    is_boilerplate=_is_boilerplate(heading, block.text),
                )
            )
        else:
            prose.append(block)
    append_prose()
    return tuple(sections)


def normalize_sec_html(
    raw_content: bytes,
    *,
    source_document_id: int,
    accession_number: str,
    source_content_hash: str,
    document_type: str | None,
    filename: str | None,
    parser_version: str,
    parent_document_id: int | None = None,
) -> NormalizedDocument:
    """Normalize one exact Stage 2 SEC document block."""

    parser = _BytePositionParser(raw_content)
    parser.feed(parser.source)
    parser.close()
    blocks, warning_set = parser.finish()
    sections = _build_sections(blocks)
    if not sections:
        warning_set.add("no_text")
    if not any(section.heading for section in sections):
        warning_set.add("missing_headings")
    extracted_characters = sum(len(section.text) for section in sections)
    if raw_content and extracted_characters / len(raw_content) < 0.005:
        warning_set.add("low_text_density")
    penalties = {
        "low_text_density": 0.20,
        "malformed_html": 0.25,
        "missing_headings": 0.15,
        "no_text": 1.00,
    }
    quality = max(0.0, 1.0 - sum(penalties[item] for item in warning_set))
    return NormalizedDocument(
        document_id=f"sec_{source_document_id}_{parser_version}",
        source_document_id=source_document_id,
        accession_number=accession_number,
        source_content_hash=source_content_hash,
        parser_version=parser_version,
        document_type=document_type,
        filename=filename,
        parent_document_id=parent_document_id,
        is_exhibit=(document_type or "").casefold().startswith("ex-"),
        language=_language(sections),
        parsing_quality=quality,
        warnings=tuple(sorted(warning_set)),
        sections=sections,
    )
