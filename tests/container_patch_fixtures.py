"""Small admission fixtures; package installation has separate image evidence."""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "infra"))
import container_patch


@contextmanager
def patch_inputs():
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        records = []
        for artifact in container_patch.patch_artifacts("arm64"):
            content = ("independent unit fixture: " + artifact.filename + "\r\n").encode("ascii")
            (root / artifact.filename).write_bytes(content)
            records.append(container_patch.PatchArtifact(
                artifact.filename, len(content), sha256(content).hexdigest(), artifact.url,
            ))
        with patch.object(container_patch, "patch_artifacts", return_value=tuple(records)):
            yield root
