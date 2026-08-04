from __future__ import annotations

import argparse
import json
from pathlib import Path

from .calibration import score_calibration
from .compare import compare, compare_synthetic_contract
from .gate import admit
from .model import ObservationEnvelope, strict_json_loads
from .report import write_reports
from .simulated_closure import admit_simulated_closure


def _load(path: Path) -> dict:
    value = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON document requires an object at the repository boundary")
    return value


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Compare LIMS/ELN evidence or admit a released evidence envelope"
    )
    actions = command.add_subparsers(dest="action", required=True)

    comparison = actions.add_parser("compare")
    comparison.add_argument("--profile", type=Path, required=True)
    comparison.add_argument("--simulation", type=Path, required=True)
    comparison.add_argument("--actual", type=Path, required=True)
    comparison.add_argument("--output", type=Path, required=True)

    synthetic_contract = actions.add_parser("compare-synthetic-contract")
    synthetic_contract.add_argument("--profile", type=Path, required=True)
    synthetic_contract.add_argument("--simulation", type=Path, required=True)
    synthetic_contract.add_argument(
        "--contract-candidate", type=Path, required=True
    )
    synthetic_contract.add_argument("--output", type=Path, required=True)

    admission = actions.add_parser("admit")
    admission.add_argument("--envelope", type=Path, required=True)
    admission.add_argument("--accepted", type=Path, required=True)

    simulated = actions.add_parser("admit-simulated")
    simulated.add_argument("--closure-bundle", type=Path, required=True)
    simulated.add_argument("--accepted", type=Path, required=True)

    calibration = actions.add_parser("calibrate")
    calibration.add_argument("--ledger", type=Path, required=True)
    return command


def main() -> None:
    args = parser().parse_args()
    if args.action == "compare":
        report = compare(
            ObservationEnvelope.from_dict(_load(args.simulation)),
            ObservationEnvelope.from_dict(_load(args.actual)),
            _load(args.profile),
        )
        write_reports(report, args.output)
        print(json.dumps({"report_digest": report["report_digest"], "summary": report["summary"]}))
        return
    if args.action == "compare-synthetic-contract":
        report = compare_synthetic_contract(
            ObservationEnvelope.from_dict(_load(args.simulation)),
            ObservationEnvelope.from_dict(_load(args.contract_candidate)),
            _load(args.profile),
        )
        write_reports(report, args.output)
        print(
            json.dumps(
                {
                    "comparison_mode": report["comparison_mode"],
                    "report_digest": report["report_digest"],
                    "summary": report["summary"],
                }
            )
        )
        return
    if args.action == "admit-simulated":
        destination = admit_simulated_closure(
            _load(args.closure_bundle),
            args.accepted,
        )
        print(json.dumps({"simulated_closure_manifest": str(destination)}))
        return
    if args.action == "calibrate":
        print(json.dumps(score_calibration(_load(args.ledger)), sort_keys=True))
        return
    destination = admit(ObservationEnvelope.from_dict(_load(args.envelope)), args.accepted)
    print(json.dumps({"accepted_manifest": str(destination)}))


if __name__ == "__main__":
    main()
