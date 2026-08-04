from __future__ import annotations

import argparse
import json
from pathlib import Path

from .calibration import score_calibration
from .compare import compare
from .model import EvidenceRecord, strict_json_loads
from .report import write_reports


def _load(path: Path) -> dict:
    value = strict_json_loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON document requires an object at the input boundary")
    return value


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Compare caller-supplied LIMS and ELN evidence records"
    )
    actions = command.add_subparsers(dest="action", required=True)

    comparison = actions.add_parser("compare")
    comparison.add_argument("--profile", type=Path, required=True)
    comparison.add_argument("--reference", type=Path, required=True)
    comparison.add_argument("--candidate", type=Path, required=True)
    comparison.add_argument("--output", type=Path, required=True)

    calibration = actions.add_parser("calibrate")
    calibration.add_argument("--ledger", type=Path, required=True)
    return command


def main() -> None:
    args = parser().parse_args()
    if args.action == "calibrate":
        print(json.dumps(score_calibration(_load(args.ledger)), sort_keys=True))
        return

    report = compare(
        EvidenceRecord.from_dict(_load(args.reference)),
        EvidenceRecord.from_dict(_load(args.candidate)),
        _load(args.profile),
    )
    write_reports(report, args.output)
    print(
        json.dumps(
            {
                "report_digest": report["report_digest"],
                "summary": report["summary"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
