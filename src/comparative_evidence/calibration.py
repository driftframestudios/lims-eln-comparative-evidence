from __future__ import annotations

from datetime import datetime
from typing import Any

from .contracts import validate_document
from .model import digest


class CalibrationError(ValueError):
    """A forecast ledger receives a precise temporal correction."""


def score_calibration(ledger: dict[str, Any]) -> dict[str, Any]:
    """Calculate a Brier score for independently observed binary outcomes."""

    validate_document(ledger, "calibration-ledger.schema.json")
    identities: set[str] = set()
    squared_errors: list[float] = []
    for entry in ledger["entries"]:
        identity = entry["forecast_id"]
        if identity in identities:
            raise CalibrationError(f"forecast_id {identity!r} requires one resolution")
        identities.add(identity)
        forecasted_at = datetime.fromisoformat(
            entry["forecasted_at"].replace("Z", "+00:00")
        )
        resolved_at = datetime.fromisoformat(
            entry["resolved_at"].replace("Z", "+00:00")
        )
        if resolved_at <= forecasted_at:
            raise CalibrationError("resolved_at requires a time after forecasted_at")
        squared_errors.append(
            (float(entry["probability"]) - int(entry["outcome"])) ** 2
        )

    result: dict[str, Any] = {
        "calibration_contract_version": ledger["ledger_version"],
        "forecast_family": ledger["forecast_family"],
        "resolved_forecast_count": len(squared_errors),
        "status": "scored" if squared_errors else ledger["empty_state"]["status"],
        "brier_score": (
            sum(squared_errors) / len(squared_errors)
            if squared_errors
            else None
        ),
        "interpretation": (
            "Lower scores indicate closer probabilistic fit; zero is perfect."
            if squared_errors
            else ledger["empty_state"]["statement"]
        ),
        "ledger_digest": digest(ledger),
    }
    result["calibration_result_digest"] = digest(result)
    return result
