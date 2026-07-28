from __future__ import annotations

import argparse
import json
from pathlib import Path

from .compare import compare
from .gate import admit
from .model import ObservationEnvelope
from .report import write_reports


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Compare LIMS/ELN evidence or admit an observed envelope")
    actions = command.add_subparsers(dest="action", required=True)

    comparison = actions.add_parser("compare")
    comparison.add_argument("--profile", type=Path, required=True)
    comparison.add_argument("--simulation", type=Path, required=True)
    comparison.add_argument("--actual", type=Path, required=True)
    comparison.add_argument("--output", type=Path, required=True)

    admission = actions.add_parser("admit")
    admission.add_argument("--envelope", type=Path, required=True)
    admission.add_argument("--accepted", type=Path, required=True)
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
    destination = admit(ObservationEnvelope.from_dict(_load(args.envelope)), args.accepted)
    print(json.dumps({"accepted_manifest": str(destination)}))


if __name__ == "__main__":
    main()

