from __future__ import annotations

from copy import deepcopy
from typing import Any


def normalize(value: Any, ignored_paths: set[str], path: str = "$") -> Any:
    if path in ignored_paths:
        return {"comparison_disposition": "declared_nondeterminism"}
    if isinstance(value, dict):
        return {
            key: normalize(item, ignored_paths, f"{path}.{key}")
            for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        return [normalize(item, ignored_paths, f"{path}[{index}]") for index, item in enumerate(value)]
    return deepcopy(value)


def path_value(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for segment in path.removeprefix("$.").split("."):
        if segment:
            current = current[int(segment)] if isinstance(current, list) else current[segment]
    return current
