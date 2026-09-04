"""Focused checks for the retained release-history entry point."""

from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

from tools import verify_release_history as history


class ReleaseHistoryTests(unittest.TestCase):
    def test_history_requires_both_release_observations(self) -> None:
        repository = Path("/comparison")
        prior = {"status": "passed", "tag": "comparison-v0.3.1"}
        current = {"status": "passed", "tag": "comparison-v0.3.2"}
        with patch.object(
            history,
            "verify_release_coordinate",
            return_value=prior,
        ) as prior_verifier, patch.object(
            history,
            "verify_promotion_observation",
            return_value=current,
        ) as current_verifier:
            self.assertEqual(
                history.verify_release_history(repository),
                {"status": "passed", "releases": [prior, current]},
            )
        prior_verifier.assert_called_once_with(repository, require_observed=True)
        current_verifier.assert_called_once_with(repository)

    def test_history_returns_a_verifier_failure(self) -> None:
        with patch.object(
            history,
            "verify_release_coordinate",
            side_effect=ValueError("prior release differs"),
        ), patch.object(
            history,
            "verify_promotion_observation",
        ) as current_verifier, redirect_stderr(StringIO()):
            result = history.main(["--repository", "/comparison"])
        self.assertEqual(result, 1)
        current_verifier.assert_not_called()


if __name__ == "__main__":
    unittest.main()
