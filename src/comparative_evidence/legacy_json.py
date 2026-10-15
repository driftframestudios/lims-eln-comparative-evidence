"""Receiver-owned representation capacities for the legacy JSON families.

Wire semantics remain in contract_v1. This owner bounds preparation before
recursive consumers, detached copies, integer conversion and serialization.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any


class ContractBoundaryError(ValueError):
    """A value returns to the named contract-completion path."""


class RepresentationCapacityError(ContractBoundaryError):
    """A fixed, value-safe category identifies the exceeded representation bound."""

    def __init__(self, category: str):
        self.code = 'legacy_' + category
        super().__init__(self.code + ': supply evidence within the declared representation capacity')


@dataclass(frozen=True)
class JsonBudget:
    bytes: int
    values: int
    depth: int
    string_bytes: int
    text_bytes: int
    key_bytes: int = 256
    integer_bits: int = 2048


# Supported input fixtures currently peak below 22 KiB; this allowance retains
# space for caller-owned result detail. Reports have a separate expansion budget.
INPUT_BUDGET = JsonBudget(1024 * 1024, 20_000, 32, 64 * 1024, 256 * 1024)
REPORT_BUDGET = JsonBudget(16 * 1024 * 1024, 400_000, 40, 64 * 1024, 8 * 1024 * 1024)
HTML_BYTES = 64 * 1024 * 1024
_NO_KEY = object()


def preflight_json(content: str | bytes, budget: JsonBudget) -> str:
    """Bound encoded input and nesting before the standard JSON decoder runs."""
    if not isinstance(content, (str, bytes)):
        raise ContractBoundaryError('JSON input requires UTF-8 text or bytes')
    if len(content) > budget.bytes:
        raise RepresentationCapacityError('bytes')
    try:
        if isinstance(content, bytes):
            text = content.decode('utf-8', errors='strict')
        else:
            text = content
        if len(text.encode('utf-8', errors='strict')) > budget.bytes:
            raise RepresentationCapacityError('bytes')
    except UnicodeError as error:
        raise RepresentationCapacityError('unicode') from error
    depth = 0
    quoted = escaped = False
    for character in text:
        if quoted:
            if escaped:
                escaped = False
            elif character == '\\':
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in '[{':
            depth += 1
            if depth > budget.depth:
                raise RepresentationCapacityError('depth')
        elif character in ']}':
            depth -= 1
    return text


def bounded_integer(text: str, budget: JsonBudget) -> int:
    # The digit check precedes int(), including Python's configurable conversion cap.
    digits = len(text) - text.startswith('-')
    if digits > budget.integer_bits * 30103 // 100000 + 1:
        raise RepresentationCapacityError('integer')
    value = int(text)
    if value.bit_length() > budget.integer_bits:
        raise RepresentationCapacityError('integer')
    return value


def validate_representation(value: Any, budget: JsonBudget = INPUT_BUDGET, *, allow_frozen: bool = False) -> None:
    """Count the serialized expansion with O(depth) traversal state.

    Active ancestors detect cycles. Each repeated reference is visited again,
    charging its expanded values and text before any detached copy is made.
    """
    object_types = (dict, Mapping) if allow_frozen else (dict,)
    array_types = (list, tuple) if allow_frozen else (list,)
    active: set[int] = set()
    stack = [(iter([(_NO_KEY, value)]), None, 0)]
    values = text_bytes = encoded_bytes = 0
    while stack:
        iterator, identity, depth = stack[-1]
        try:
            key, item = next(iterator)
        except StopIteration:
            stack.pop()
            if identity is not None:
                active.remove(identity)
            continue
        if key is not _NO_KEY and not isinstance(key, str):
            raise ContractBoundaryError("JSON objects require textual member names")
        values += 1 + (key is not _NO_KEY)
        if values > budget.values:
            raise RepresentationCapacityError('values')
        for text, limit in ((None if key is _NO_KEY else key, budget.key_bytes), (item if isinstance(item, str) else None, budget.string_bytes)):
            if text is None:
                continue
            if not isinstance(text, str):
                raise ContractBoundaryError('JSON objects require textual member names')
            if len(text) > limit:
                raise RepresentationCapacityError('string')
            try:
                size = len(text.encode('utf-8', errors='strict'))
            except UnicodeError as error:
                raise RepresentationCapacityError('unicode') from error
            if size > limit:
                raise RepresentationCapacityError('string')
            text_bytes += size
            encoded_bytes += size + 2 + sum(
                1 if character in '\\"\b\f\n\r\t' else 5 if ord(character) < 32 else 0
                for character in text
            )
            if text_bytes > budget.text_bytes:
                raise RepresentationCapacityError('text')
        if key is not _NO_KEY:
            encoded_bytes += 1  # colon after a member name
        if isinstance(item, object_types + array_types):
            encoded_bytes += 2 + max(0, len(item) - 1)
            if depth + 1 > budget.depth:
                raise RepresentationCapacityError('depth')
            identity = id(item)
            if identity in active:
                raise RepresentationCapacityError('cycle')
            active.add(identity)
            children = iter(item.items()) if isinstance(item, object_types) else ((_NO_KEY, child) for child in item)
            stack.append((children, identity, depth + 1))
        elif isinstance(item, bool):
            encoded_bytes += 4 if item else 5
        elif item is None:
            encoded_bytes += 4
        elif isinstance(item, str):
            pass
        elif isinstance(item, int):
            if item.bit_length() > budget.integer_bits:
                raise RepresentationCapacityError('integer')
            encoded_bytes += len(str(item))
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise ContractBoundaryError('JSON numeric value carries a finite JSON number')
            encoded_bytes += len(repr(item))
        else:
            raise ContractBoundaryError('JSON values require the released compatible types')
        if encoded_bytes > budget.bytes:
            raise RepresentationCapacityError('bytes')
