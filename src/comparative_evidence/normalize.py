from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import re
from typing import Any


_PATH_TOKEN = re.compile(r"\.([^.[\]]+)|\[(0|[1-9][0-9]*)\]")


def normalize(value: Any, ignored_paths: set[str], path: str = "$") -> Any:
    if path in ignored_paths:
        return {"comparison_disposition": "declared_nondeterminism"}
    if isinstance(value, Mapping):
        return {
            key: normalize(item, ignored_paths, f"{path}.{key}")
            for key, item in sorted(value.items())
        }
    if isinstance(value, (list, tuple)):
        return [
            normalize(item, ignored_paths, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    return deepcopy(value)


def path_value(value: dict[str, Any], path: str) -> Any:
    tokens = comparison_path_tokens(path)
    current: Any = value
    for field, index in tokens:
        if field is not None:
            if not isinstance(current, Mapping):
                raise TypeError(f"comparison path {path!r} expected an object")
            current = current[field]
        else:
            if not isinstance(current, (list, tuple)):
                raise TypeError(f"comparison path {path!r} expected an array")
            if index is None:
                raise ValueError(
                    f"comparison path {path!r} uses the released path grammar"
                )
            current = current[index]
    return current


def comparison_path_tokens(
    path: str,
) -> tuple[tuple[str | None, int | None], ...]:
    """Parse the released, canonical comparison-path subset."""

    if not isinstance(path, str):
        raise ValueError("comparison path requires text")
    if path == "$":
        return ()
    if not path.startswith("$"):
        raise ValueError(f"comparison path {path!r} starts at $")
    position = 1
    tokens: list[tuple[str | None, int | None]] = []
    for match in _PATH_TOKEN.finditer(path, position):
        if match.start() != position:
            raise ValueError(f"comparison path {path!r} uses the released path grammar")
        field, index = match.groups()
        if field is not None:
            tokens.append((field, None))
        else:
            tokens.append((None, int(index)))
        position = match.end()
    if position != len(path):
        raise ValueError(f"comparison path {path!r} uses the released path grammar")
    return tuple(tokens)
