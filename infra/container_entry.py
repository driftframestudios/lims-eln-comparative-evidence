"""Preserve native evidence admission and deterministic report validation."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_runtime import run
from comparative_evidence.artifact_boundary import report_artifact_inventory
from comparative_evidence.cli import _load as native_load
from comparative_evidence.compare import compare_synthetic_contract
from comparative_evidence.model import ObservationEnvelope
from comparative_evidence.report import write_reports


def load(path: str | Path) -> dict:
    """Share the native CLI's strict ingress boundary within this source tree."""
    return native_load(Path(path))


def produce(output: Path) -> None:
    report = compare_synthetic_contract(
        ObservationEnvelope.from_dict(load(ROOT / "fixtures/pairs/simulation-observation.json")),
        ObservationEnvelope.from_dict(load(ROOT / "fixtures/contracts/planned-observation.json")),
        load(ROOT / "specification/comparison-profile.json"),
    )
    write_reports(report, output)


if __name__ == "__main__":
    run(produce, validate=report_artifact_inventory)
