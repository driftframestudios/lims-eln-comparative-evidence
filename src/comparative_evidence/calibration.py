from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

from .model import digest
from .safety import validate_digest, validate_repository_safe_content


LEDGER_VERSION = "1.0.0"


class CalibrationError(ValueError):
    """A calibration ledger receives a precise correction requirement."""


def score_calibration(ledger: dict[str, Any]) -> dict[str, Any]:
    """Score independently resolved forecasts while preserving an empty baseline."""

    if set(ledger) != {
        "ledger_version",
        "forecast_family",
        "entries",
        "empty_state",
    }:
        raise CalibrationError(
            "calibration ledger requires version, family, entries, and empty-state posture"
        )
    if ledger["ledger_version"] != LEDGER_VERSION:
        raise CalibrationError(
            f"calibration ledger requires the released {LEDGER_VERSION} contract"
        )
    if not isinstance(ledger["forecast_family"], str) or not ledger[
        "forecast_family"
    ].strip():
        raise CalibrationError("forecast_family requires a bounded textual identity")
    entries = ledger["entries"]
    if not isinstance(entries, list):
        raise CalibrationError("calibration entries require an array")
    empty_state = ledger["empty_state"]
    if not isinstance(empty_state, dict) or set(empty_state) != {
        "status",
        "statement",
    }:
        raise CalibrationError(
            "empty_state requires a status and an explanatory statement"
        )
    if empty_state["status"] != "awaiting_independently_observed_outcomes":
        raise CalibrationError(
            "empty_state requires awaiting_independently_observed_outcomes"
        )
    if not isinstance(empty_state["statement"], str) or len(
        empty_state["statement"].strip()
    ) < 20:
        raise CalibrationError("empty_state requires an explanatory statement")

    identities: set[str] = set()
    squared_errors: list[float] = []
    for entry in entries:
        squared_errors.append(_score_entry(entry, identities))

    validate_repository_safe_content(ledger)
    result: dict[str, Any] = {
        "calibration_contract_version": LEDGER_VERSION,
        "forecast_family": ledger["forecast_family"],
        "resolved_forecast_count": len(squared_errors),
        "status": (
            "scored"
            if squared_errors
            else "awaiting_independently_observed_outcomes"
        ),
        "brier_score": (
            sum(squared_errors) / len(squared_errors)
            if squared_errors
            else None
        ),
        "interpretation": (
            "Lower scores indicate closer probabilistic fit; zero is perfect."
            if squared_errors
            else "An observed resolution will activate calibration scoring."
        ),
        "ledger_digest": digest(ledger),
    }
    result["calibration_result_digest"] = digest(result)
    return result


def _score_entry(entry: Any, identities: set[str]) -> float:
    if not isinstance(entry, dict):
        raise CalibrationError("each calibration entry requires an object")
    required = {
        "forecast_id",
        "event",
        "probability",
        "outcome",
        "forecasted_at",
        "resolved_at",
        "resolution_mode",
        "resolution_evidence_digest",
    }
    if set(entry) != required:
        raise CalibrationError(
            "calibration entry fields require the released ledger definition"
        )
    identity = entry["forecast_id"]
    if not isinstance(identity, str) or not identity.strip():
        raise CalibrationError("forecast_id requires a bounded textual identity")
    if identity in identities:
        raise CalibrationError(f"forecast_id {identity!r} requires one resolution")
    identities.add(identity)
    if not isinstance(entry["event"], str) or len(entry["event"].strip()) < 10:
        raise CalibrationError("forecast event requires a substantive statement")

    probability = entry["probability"]
    if (
        not isinstance(probability, (int, float))
        or isinstance(probability, bool)
        or not math.isfinite(probability)
        or not 0 <= probability <= 1
    ):
        raise CalibrationError("forecast probability requires a finite value from 0 to 1")
    outcome = entry["outcome"]
    if not isinstance(outcome, int) or isinstance(outcome, bool) or outcome not in {
        0,
        1,
    }:
        raise CalibrationError("forecast outcome requires observed binary value 0 or 1")
    if entry["resolution_mode"] != "observed":
        raise CalibrationError(
            "calibration resolution requires independently observed evidence"
        )
    forecasted_at = _canonical_utc(entry["forecasted_at"], "forecasted_at")
    resolved_at = _canonical_utc(entry["resolved_at"], "resolved_at")
    if resolved_at <= forecasted_at:
        raise CalibrationError("resolved_at requires a time after forecasted_at")
    validate_digest(
        entry["resolution_evidence_digest"],
        "resolution_evidence_digest",
    )
    return (float(probability) - outcome) ** 2


def _canonical_utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CalibrationError(f"{field} requires canonical UTC text ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise CalibrationError(f"{field} requires an ISO-8601 timestamp") from error
    if parsed.tzinfo != timezone.utc:
        raise CalibrationError(f"{field} requires UTC")
    return parsed
