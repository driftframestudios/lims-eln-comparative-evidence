from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.contract_v1 import verify_shared_package


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Compare standalone contract snapshots with the authoritative package"
    )
    command.add_argument(
        "--contract-source",
        type=Path,
        help="Optional directory containing the lims_eln_contracts package",
    )
    return command


def main() -> int:
    args = parser().parse_args()
    if args.contract_source is not None:
        sys.path.insert(0, str(args.contract_source.resolve()))
    try:
        summary = verify_shared_package()
    except ModuleNotFoundError:
        print(
            "contract package is available through the private distribution or "
            "--contract-source; provide one path to run cross-repository conformance"
        )
        return 2
    print(json.dumps({"status": "conformant", **summary}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
