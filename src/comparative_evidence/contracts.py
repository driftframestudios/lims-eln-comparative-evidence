from __future__ import annotations

from importlib.resources import files
import json
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


class ContractError(ValueError):
    """A structured input receives a schema-specific correction message."""


def load_schema(name: str) -> dict[str, Any]:
    resource = files("comparative_evidence").joinpath("schemas", name)
    value = json.loads(resource.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return value


def validate_document(value: Any, schema_name: str) -> None:
    validator = Draft202012Validator(
        load_schema(schema_name),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(value), key=lambda item: list(item.path))
    if errors:
        error = errors[0]
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        raise ContractError(f"{schema_name} at {path}: {error.message}")
