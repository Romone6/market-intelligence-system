"""Safe loader for the canonical ontology guide."""

from pathlib import Path

import yaml

from .models import OntologyDefinition


def load_ontology(path: str | Path) -> OntologyDefinition:
    source = Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("ontology YAML must contain a mapping")
    return OntologyDefinition.model_validate(payload)
