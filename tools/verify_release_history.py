#!/usr/bin/env python3
"""Verify every retained signed Comparative Evidence release coordinate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.verify_promotion_observation import verify_promotion_observation  # noqa: E402
from tools.verify_release_coordinate import verify_release_coordinate  # noqa: E402


def verify_release_history(repository: Path) -> dict[str, object]:
    """Verify the immutable 0.3.1 receipt and additive 0.3.2 observation."""
    prior = verify_release_coordinate(repository, require_observed=True)
    current = verify_promotion_observation(repository)
    return {
        "status": "passed",
        "releases": [prior, current],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, default=ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = verify_release_history(args.repository)
    except (OSError, ValueError) as error:
        print(
            f"Release-history verification requires attention: {error}",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
