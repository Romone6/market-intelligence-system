"""Local-only server-rendered annotation application."""

from __future__ import annotations

import argparse
import html
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import parse_qs, quote
from uuid import uuid4
from wsgiref.simple_server import make_server

from financial_event_model.ontology import OntologyDefinition, load_ontology

from .models import (
    AdjudicationStatus,
    AnnotationPolicy,
    AnnotationRecord,
    AnnotationTask,
    EvidenceSpan,
    load_annotation_policy,
)
from .store import AnnotationStore


StartResponse = Callable[[str, list[tuple[str, str]]], object]


class AnnotationApp:
    def __init__(
        self,
        store: AnnotationStore,
        ontology: OntologyDefinition,
        policy: AnnotationPolicy,
        *,
        csrf_token: str | None = None,
    ) -> None:
        self.store = store
        self.ontology = ontology
        self.policy = policy
        self.csrf_token = csrf_token or secrets.token_urlsafe(32)

    def __call__(self, environ: dict[str, object], start_response: StartResponse) -> Iterable[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))
        if method == "GET" and path == "/":
            return self._show_task(environ, start_response)
        if method == "POST" and path == "/annotations":
            return self._submit(environ, start_response)
        return self._respond(start_response, "404 Not Found", "<h1>Not found</h1>")

    def _show_task(self, environ: dict[str, object], start_response: StartResponse):
        query = parse_qs(str(environ.get("QUERY_STRING", "")), keep_blank_values=True)
        event_id = query.get("event_id", [None])[0]
        annotator_id = query.get("annotator_id", [""])[0]
        task = self.store.get_task(event_id) if event_id else None
        if event_id and task is None:
            return self._respond(
                start_response,
                "404 Not Found",
                self._page("Unknown annotation task", '<p role="alert">Unknown event ID.</p>'),
            )
        if task is None:
            tasks = self.store.list_tasks()
            task = tasks[0] if tasks else None
        if task is None:
            return self._respond(
                start_response,
                "200 OK",
                self._page("Annotation queue", "<h1>Annotation queue is empty</h1>"),
            )
        saved = "saved" in query
        return self._respond(
            start_response,
            "200 OK",
            self._render_form(task, saved=saved, annotator_id=annotator_id),
        )

    def _submit(self, environ: dict[str, object], start_response: StartResponse):
        try:
            length = int(str(environ.get("CONTENT_LENGTH", "0") or "0"))
        except ValueError:
            return self._error(start_response, "400 Bad Request", "Invalid request length.")
        if length < 0 or length > self.policy.max_request_bytes:
            return self._error(
                start_response,
                "413 Payload Too Large",
                "The annotation request is too large.",
            )
        content_type = str(environ.get("CONTENT_TYPE", "")).split(";", 1)[0]
        if content_type != "application/x-www-form-urlencoded":
            return self._error(
                start_response,
                "415 Unsupported Media Type",
                "Use the annotation form to submit records.",
            )
        stream = environ.get("wsgi.input")
        body = stream.read(length) if hasattr(stream, "read") else b""  # type: ignore[union-attr]
        try:
            form = parse_qs(
                body.decode("utf-8"), keep_blank_values=True, max_num_fields=500
            )
        except UnicodeDecodeError:
            return self._error(start_response, "400 Bad Request", "Form data must be UTF-8.")
        except ValueError:
            return self._error(
                start_response,
                "400 Bad Request",
                "Form contains too many fields.",
            )
        submitted_token = form.get("csrf_token", [""])[0]
        if not secrets.compare_digest(submitted_token, self.csrf_token):
            return self._error(
                start_response,
                "403 Forbidden",
                "Security token is missing or expired. Reload the form and try again.",
            )
        event_id = form.get("event_id", [""])[0]
        task = self.store.get_task(event_id)
        if task is None:
            return self._error(start_response, "400 Bad Request", "Unknown event ID.")
        try:
            record = self._record_from_form(form, task)
            self.store.save_annotation(record)
        except (KeyError, TypeError, ValueError) as error:
            return self._respond(
                start_response,
                "400 Bad Request",
                self._render_form(
                    task,
                    error=str(error),
                    annotator_id=form.get("annotator_id", [""])[0],
                ),
            )
        next_task = self.store.next_unannotated_task(record.annotator_id)
        destination = next_task.event_id if next_task is not None else event_id
        location = (
            f"/?event_id={quote(destination)}&saved={quote(record.annotation_id)}"
            f"&annotator_id={quote(record.annotator_id)}"
        )
        return self._respond(
            start_response,
            "303 See Other",
            "<p>Annotation saved.</p>",
            extra_headers=[("Location", location)],
        )

    def _record_from_form(
        self,
        form: dict[str, list[str]],
        task: AnnotationTask,
    ) -> AnnotationRecord:
        annotator_id = form.get("annotator_id", [""])[0].strip()
        if not annotator_id:
            raise ValueError("Annotator ID is required.")
        no_material = "no_material_event" in form
        labels = tuple(dict.fromkeys(form.get("labels", [])))
        attributes: dict[str, dict[str, object]] = {}
        if not no_material:
            for label_name in labels:
                definition = self.ontology.label(label_name)
                allowed = self.ontology.shared_attributes | self.ontology.family_attributes.get(
                    definition.valid_parent, {}
                )
                values: dict[str, object] = {}
                for name, attribute in allowed.items():
                    raw = form.get(f"attribute__{name}", [""])[0].strip()
                    if raw:
                        values[name] = _parse_attribute(raw, attribute.kind)
                attributes[label_name] = values
        spans: list[EvidenceSpan] = []
        if not no_material:
            for raw_span in form.get("evidence_span", []):
                start_text, end_text = raw_span.split(":", 1)
                start, end = int(start_text), int(end_text)
                spans.append(
                    EvidenceSpan(
                        start=start,
                        end=end,
                        text=task.relevant_section[start:end],
                    )
                )
        supersedes = form.get("supersedes_annotation_id", [""])[0].strip() or None
        return AnnotationRecord(
            annotation_id=f"ann-{uuid4()}",
            event_id=task.event_id,
            annotator_id=annotator_id,
            ontology_version=self.ontology.version,
            labels=labels,
            attributes=attributes,
            evidence_spans=tuple(spans),
            confidence=float(form.get("confidence", [""])[0]),
            ambiguity_flag="ambiguity_flag" in form,
            no_material_event=no_material,
            created_at=datetime.now(timezone.utc),
            supersedes_annotation_id=supersedes,
            adjudication_status=AdjudicationStatus(
                form.get("adjudication_status", [AdjudicationStatus.SUBMITTED.value])[0]
            ),
        )

    def _render_form(
        self,
        task: AnnotationTask,
        *,
        saved: bool = False,
        error: str | None = None,
        annotator_id: str = "",
    ) -> str:
        label_controls = []
        for label in self.ontology.labels:
            control_id = f"label-{label.event_type.replace('.', '-')}"
            recommended = " <span class=\"candidate\">candidate</span>" if label.event_type in task.candidate_labels else ""
            label_controls.append(
                f'<div class="choice"><input type="checkbox" id="{control_id}" '
                f'name="labels" value="{html.escape(label.event_type, quote=True)}">'
                f'<label for="{control_id}">{html.escape(label.name)}'
                f'<small>{html.escape(label.event_type)}</small>{recommended}</label></div>'
            )
        attribute_controls = []
        definitions = dict(self.ontology.shared_attributes)
        for family in self.ontology.family_attributes.values():
            definitions.update(family)
        for name, definition in definitions.items():
            control_id = f"attribute-{name.replace('_', '-')}"
            attribute_controls.append(
                _attribute_control(control_id, name, definition.description, definition.kind, definition.allowed_values)
            )
        evidence_controls = []
        for index, span in enumerate(task.candidate_evidence):
            control_id = f"evidence-{index}"
            evidence_controls.append(
                f'<div class="choice"><input type="checkbox" id="{control_id}" '
                f'name="evidence_span" value="{span.start}:{span.end}" checked>'
                f'<label for="{control_id}">{html.escape(span.text)}</label></div>'
            )
        alert = ""
        if saved:
            alert = '<p class="success" role="status">Annotation saved.</p>'
        if error:
            alert = (
                '<div class="error" role="alert" tabindex="-1"><strong>Please correct '
                f'the annotation.</strong><p>{html.escape(error)}</p></div>'
            )
        prior = task.prior_company_disclosure or "No prior disclosure supplied."
        content = f"""
<a class="skip" href="#annotation-form">Skip to annotation form</a>
<header><p class="eyebrow">Stage 7 · {html.escape(task.annotation_round.value)}</p><h1>Event annotation</h1><p class="lede">Evidence-led labeling against ontology {html.escape(self.ontology.version)}.</p></header>
<main>
{alert}
<section class="document" aria-labelledby="document-heading">
  <div class="section-heading"><div><p class="eyebrow">Source document</p><h2 id="document-heading">{html.escape(task.company)}</h2></div><span class="filing">{html.escape(task.filing_type)}</span></div>
  <dl class="metadata"><div><dt>Publication</dt><dd><time>{html.escape(task.source_published_at.isoformat())}</time></dd></div><div><dt>Tradable</dt><dd><time>{html.escape(task.tradable_at.isoformat())}</time></dd></div><div><dt>Event ID</dt><dd><code>{html.escape(task.event_id)}</code></dd></div></dl>
  <h3>Relevant section</h3><blockquote>{_highlighted_text(task)}</blockquote>
  <details><summary>Prior company disclosure</summary><p>{html.escape(prior)}</p></details>
</section>
<form id="annotation-form" method="post" action="/annotations">
  <input type="hidden" name="csrf_token" value="{html.escape(self.csrf_token, quote=True)}">
  <input type="hidden" name="event_id" value="{html.escape(task.event_id, quote=True)}">
  <div class="field"><label for="annotator_id">Annotator ID</label><input id="annotator_id" name="annotator_id" value="{html.escape(annotator_id, quote=True)}" required autocomplete="off"></div>
  <fieldset><legend>Candidate evidence</legend><p class="hint">Keep every span that directly supports the selected label.</p>{''.join(evidence_controls) or '<p>No candidate evidence supplied.</p>'}</fieldset>
  <fieldset><legend>Ontology labels</legend><p class="hint">Select every independently material event in this section.</p><div class="choice-grid">{''.join(label_controls)}</div></fieldset>
  <fieldset><legend>Event attributes</legend><p class="hint">Complete the fields required by each selected label. Unsupported fields are ignored.</p><div class="field-grid">{''.join(attribute_controls)}</div></fieldset>
  <fieldset><legend>Review decision</legend>
    <div class="field"><label for="confidence">Confidence (0 to 1)</label><input id="confidence" name="confidence" type="number" min="0" max="1" step="0.01" value="0.80" required></div>
    <div class="choice"><input id="ambiguity_flag" name="ambiguity_flag" type="checkbox"><label for="ambiguity_flag">Document or event is ambiguous</label></div>
    <div class="choice"><input id="no_material_event" name="no_material_event" type="checkbox"><label for="no_material_event">No material event</label></div>
    <div class="field"><label for="adjudication_status">Adjudication status</label><select id="adjudication_status" name="adjudication_status">{''.join(f'<option value="{status.value}">{status.value.replace("_", " ").title()}</option>' for status in AdjudicationStatus)}</select></div>
    <div class="field"><label for="supersedes_annotation_id">Supersedes annotation ID <span>(corrections only)</span></label><input id="supersedes_annotation_id" name="supersedes_annotation_id" autocomplete="off"></div>
  </fieldset>
  <button type="submit">Save annotation</button>
</form>
</main>
"""
        return self._page(f"Annotate {task.company}", content)

    def _page(self, title: str, content: str) -> str:
        return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{--ink:#14201c;--muted:#55615c;--paper:#f5f1e8;--panel:#fffdf7;--line:#d8d0c1;--accent:#125945;--accent2:#d7ece2;--error:#9c2f24}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,sans-serif}}header,main{{width:min(1120px,calc(100% - 2rem));margin:auto}}header{{padding:3rem 0 1.5rem}}h1,h2,h3,legend{{font-family:Georgia,serif;line-height:1.1}}h1{{font-size:clamp(2.4rem,6vw,4.6rem);margin:.15rem 0}}h2{{font-size:2rem;margin:.2rem 0}}.eyebrow{{color:var(--accent);font-size:.75rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase}}.lede,.hint,small,.field span{{color:var(--muted)}}.document,form{{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:clamp(1rem,3vw,2rem);margin-bottom:1.5rem;box-shadow:0 10px 32px #32280d0d}}.section-heading{{display:flex;justify-content:space-between;gap:1rem;align-items:start}}.filing,.candidate{{background:var(--accent2);border-radius:999px;color:var(--accent);font-size:.75rem;font-weight:700;padding:.35rem .65rem}}.metadata{{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);border:1px solid var(--line);margin:1.5rem 0}}.metadata div{{background:var(--panel);padding:.8rem}}dt{{color:var(--muted);font-size:.72rem;font-weight:800;text-transform:uppercase}}dd{{margin:.25rem 0 0;overflow-wrap:anywhere}}blockquote{{border-left:5px solid var(--accent);font:1.18rem/1.7 Georgia,serif;margin:0;padding:1rem 1.25rem;background:#faf7ef}}mark{{background:#ffe58a;padding:.1em}}details{{margin-top:1rem}}fieldset{{border:0;border-top:1px solid var(--line);margin:1.6rem 0 0;padding:1.6rem 0 0}}legend{{font-size:1.45rem;font-weight:700;padding-right:1rem}}.choice-grid,.field-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.65rem}}.choice{{display:flex;gap:.7rem;align-items:start;padding:.65rem;border-radius:10px}}.choice:hover{{background:#f4f0e7}}.choice input{{margin-top:.3rem}}.choice label{{font-weight:650}}.choice small{{display:block;font-family:monospace;font-weight:400}}.field{{display:grid;gap:.35rem;margin:.8rem 0}}.field label{{font-weight:700}}input,select,textarea{{border:1px solid #8f968f;border-radius:8px;background:white;color:var(--ink);font:inherit;padding:.7rem;width:100%}}input[type=checkbox]{{height:1.15rem;width:1.15rem}}button{{background:var(--accent);border:0;border-radius:9px;color:white;cursor:pointer;font-size:1rem;font-weight:800;margin-top:1.2rem;padding:.9rem 1.3rem}}:focus-visible{{outline:4px solid #e09021;outline-offset:3px}}.skip{{background:var(--ink);color:white;left:1rem;padding:.7rem;position:absolute;top:-5rem;z-index:2}}.skip:focus{{top:1rem}}.error{{background:#fff0ed;border-left:5px solid var(--error);padding:1rem}}.success{{background:var(--accent2);border-left:5px solid var(--accent);padding:1rem}}@media(max-width:760px){{.metadata,.choice-grid,.field-grid{{grid-template-columns:1fr}}header{{padding-top:2rem}}}}
</style></head><body>{content}</body></html>"""

    def _error(self, start_response: StartResponse, status: str, message: str):
        return self._respond(
            start_response,
            status,
            self._page("Annotation error", f'<main><div class="error" role="alert"><h1>Request error</h1><p>{html.escape(message)}</p></div></main>'),
        )

    def _respond(
        self,
        start_response: StartResponse,
        status: str,
        body: str,
        *,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> list[bytes]:
        encoded = body.encode("utf-8")
        headers = [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(encoded))),
            ("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"),
            ("Referrer-Policy", "no-referrer"),
            ("X-Content-Type-Options", "nosniff"),
        ]
        headers.extend(extra_headers or [])
        start_response(status, headers)
        return [encoded]


def _highlighted_text(task: AnnotationTask) -> str:
    output: list[str] = []
    cursor = 0
    for span in sorted(task.candidate_evidence, key=lambda item: (item.start, item.end)):
        if span.start < cursor:
            continue
        output.append(html.escape(task.relevant_section[cursor : span.start]))
        output.append(f"<mark>{html.escape(span.text)}</mark>")
        cursor = span.end
    output.append(html.escape(task.relevant_section[cursor:]))
    return "".join(output)


def _attribute_control(
    control_id: str,
    name: str,
    description: str,
    kind: str,
    allowed_values: tuple[str, ...],
) -> str:
    escaped_name = html.escape(name, quote=True)
    label = html.escape(name.replace("_", " ").title())
    hint = html.escape(description)
    if kind == "enum":
        control = (
            f'<select id="{control_id}" name="attribute__{escaped_name}"><option value="">Not specified</option>'
            + "".join(
                f'<option value="{html.escape(value, quote=True)}">{html.escape(value.replace("_", " ").title())}</option>'
                for value in allowed_values
            )
            + "</select>"
        )
    elif kind == "boolean":
        control = f'<select id="{control_id}" name="attribute__{escaped_name}"><option value="">Not specified</option><option value="true">Yes</option><option value="false">No</option></select>'
    elif kind == "number":
        control = f'<input id="{control_id}" name="attribute__{escaped_name}" type="number" step="any">'
    elif kind == "date":
        control = f'<input id="{control_id}" name="attribute__{escaped_name}" type="date">'
    elif kind == "string_list":
        control = f'<textarea id="{control_id}" name="attribute__{escaped_name}" rows="2"></textarea>'
    else:
        control = f'<input id="{control_id}" name="attribute__{escaped_name}">'
    return f'<div class="field"><label for="{control_id}">{label}</label>{control}<small>{hint}</small></div>'


def _parse_attribute(raw: str, kind: str) -> object:
    if kind == "number":
        return float(raw)
    if kind == "boolean":
        if raw not in {"true", "false"}:
            raise ValueError("Boolean attributes must be yes or no.")
        return raw == "true"
    if kind == "string_list":
        return [item.strip() for item in raw.splitlines() if item.strip()]
    return raw


def serve(database: Path, ontology_path: Path, policy_path: Path) -> None:
    ontology = load_ontology(ontology_path)
    policy = load_annotation_policy(policy_path)
    store = AnnotationStore(database, ontology)
    app = AnnotationApp(store, ontology, policy)
    with make_server(policy.host, policy.port, app) as server:
        print(f"Annotation app: http://{policy.host}:{policy.port}")
        print("Local research server only; press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Annotation app stopped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local annotation application")
    parser.add_argument("--database", type=Path, default=Path("data/labels/annotations.sqlite"))
    parser.add_argument("--ontology", type=Path, default=Path("configs/ontology.yaml"))
    parser.add_argument("--policy", type=Path, default=Path("configs/annotation.yaml"))
    args = parser.parse_args()
    serve(args.database, args.ontology, args.policy)


if __name__ == "__main__":
    main()
