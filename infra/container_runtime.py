"""Publish one complete finite-job result in an operator-owned output directory."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import tempfile


def publish(produce, root: Path = Path("/output")) -> dict:
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
        produce(temporary)
        records = []
        total = 0
        for directory, directories, names in os.walk(temporary, followlinks=False):
            parent = Path(directory)
            if len(parent.relative_to(temporary).parts) > 16 or any((parent/name).is_symlink() for name in directories):
                raise ValueError("bounded-output-tree-required")
            for name in names:
                path = parent / name
                info = path.lstat()
                total += info.st_size
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or len(records) >= 256 or total > 32 * 1024 * 1024:
                    raise ValueError("bounded-regular-output-required")
                records.append({"path":path.relative_to(temporary).as_posix(), "bytes":info.st_size, "sha256":sha256(path.read_bytes()).hexdigest()})
        if not records:
            raise ValueError("material-output-required")
        result={"version":"1.0.0", "files":sorted(records,key=lambda item:item["path"])}
        with (temporary / "job-receipt.json").open("x") as stream:
            json.dump(result,stream,sort_keys=True,indent=2)
            stream.write("\n")
        if destination.exists() or destination.is_symlink():
            raise ValueError("fresh-output-required")
        os.rename(temporary,destination)
        return {"status":"completed", "directory":destination.name, "files":len(records)}
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def run(produce) -> None:
    def interrupted(number, _frame):
        raise SystemExit(128 + number)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        result=publish(produce)
    except (ValueError, OSError):
        print(json.dumps({"status":"held", "code":"job-boundary"}))
        raise SystemExit(1)
    print(json.dumps(result,sort_keys=True))
