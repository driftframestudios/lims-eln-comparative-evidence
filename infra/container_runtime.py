"""Publish one complete finite-job result in an operator-owned output directory."""
from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import tempfile

MAX_OUTPUT_FILES = 256
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_DEPTH = 16
Producer = Callable[[Path], None]
Validator = Callable[[Path], object]


def traversal_failed(error: OSError) -> None:
    """A complete receipt requires every admitted directory to be readable."""
    raise error


def output_inventory(payload: Path) -> list[dict]:
    """Inspect a quiescent producer result in O(bytes + paths), O(paths + file)."""
    records = []
    total = 0
    for directory, directories, names in os.walk(
        payload, followlinks=False, onerror=traversal_failed
    ):
        parent = Path(directory)
        if len(parent.relative_to(payload).parts) > MAX_OUTPUT_DEPTH:
            raise ValueError("bounded-output-tree-required")
        if any((parent / name).is_symlink() for name in directories):
            raise ValueError("bounded-output-tree-required")
        for name in names:
            path = parent / name
            info = path.lstat()
            total += info.st_size
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or len(records) >= MAX_OUTPUT_FILES
                or total > MAX_OUTPUT_BYTES
            ):
                raise ValueError("bounded-regular-output-required")
            records.append({
                "path": path.relative_to(payload.parent).as_posix(),
                "bytes": info.st_size,
                "sha256": sha256(path.read_bytes()).hexdigest(),
            })
    if not records:
        raise ValueError("material-output-required")
    return records


def publish(
    produce: Producer,
    root: Path = Path("/output"),
    *,
    validate: Validator | None = None,
) -> dict:
    """O(emitted bytes + P log P); output count/bytes are checked before return.

    Each invocation owns a fresh directory. Accepted prior runs retain their
    names and bytes. A renamed directory contains the complete result set.
    """
    if os.getuid() == 0:
        raise ValueError("ordinary-runtime-identity-required")
    info = root.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("operator-owned-output-required")
    temporary = Path(tempfile.mkdtemp(prefix=".pending-", dir=root))
    destination = root / ("run-" + temporary.name.removeprefix(".pending-"))
    try:
        payload = temporary / "payload"
        payload.mkdir(mode=0o700)
        produce(payload)
        records = output_inventory(payload)
        if validate is not None:
            validate(payload)
        result = {"version": "1.0.0", "files": sorted(records, key=lambda item: item["path"])}
        with (temporary / "job-receipt.json").open("x", encoding="utf-8") as stream:
            json.dump(result, stream, sort_keys=True, indent=2)
            stream.write("\n")
        if destination.exists() or destination.is_symlink():
            raise ValueError("fresh-output-required")
        os.rename(temporary, destination)
        return {"status": "completed", "directory": destination.name, "files": len(records)}
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def run(produce: Producer, *, validate: Validator | None = None) -> None:
    def interrupted(number: int, _frame) -> None:
        raise SystemExit(128 + number)
    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        result = publish(produce, validate=validate)
    except (ValueError, OSError):
        print(json.dumps({"status":"held", "code":"job-boundary"}))
        raise SystemExit(1)
    finally:
        signal.signal(signal.SIGTERM, previous)
    print(json.dumps(result, sort_keys=True))
