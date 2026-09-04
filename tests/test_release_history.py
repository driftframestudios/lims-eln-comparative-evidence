"""Focused checks for the retained release-history entry point."""

from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import verify_release_history as history


class ReleaseHistoryTests(unittest.TestCase):
    def test_history_requires_both_release_observations(self) -> None:
        repository = Path("/comparison")
        prior = {"status": "passed", "tag": "comparison-v0.3.1"}
        current = {"status": "passed", "tag": "comparison-v0.3.2"}
        snapshot = object()
        identity = object()
        with patch.object(
            history,
            "_capture_history_snapshot",
            return_value=(identity, snapshot),
        ) as capture, patch.object(
            history,
            "verify_release_coordinate",
            return_value=prior,
        ) as prior_verifier, patch.object(
            history,
            "verify_promotion_observation",
            return_value=current,
        ) as current_verifier, patch.object(
            history,
            "_require_history_snapshot",
        ) as require_snapshot:
            self.assertEqual(
                history.verify_release_history(repository),
                {"status": "passed", "releases": [prior, current]},
            )
        capture.assert_called_once_with(repository)
        prior_verifier.assert_called_once_with(repository, require_observed=True)
        current_verifier.assert_called_once_with(repository)
        require_snapshot.assert_called_once_with(identity, snapshot)

    def test_history_rechecks_shared_carriers_after_both_verifiers(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparison-history-") as temporary:
            repository = Path(temporary) / "repository"
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--local",
                    "--no-hardlinks",
                    str(Path(__file__).resolve().parents[1]),
                    str(repository),
                ],
                check=True,
                capture_output=True,
            )
            signer_path = repository / "release" / "trusted-release-signers"

            def mutate_shared_signer(*_args, **_kwargs):
                signer_path.write_bytes(
                    signer_path.read_bytes() + b"# changed between release checks\n"
                )
                return {"status": "passed", "tag": "comparison-v0.3.1"}

            with patch.object(
                history,
                "verify_release_coordinate",
                side_effect=mutate_shared_signer,
            ), patch.object(
                history,
                "verify_promotion_observation",
                return_value={"status": "passed", "tag": "comparison-v0.3.2"},
            ), self.assertRaisesRegex(
                history.ReleaseCoordinateError,
                "trusted-release-signers remains at the exact captured bytes",
            ):
                history.verify_release_history(repository)

    def test_history_returns_a_verifier_failure(self) -> None:
        with patch.object(
            history,
            "_capture_history_snapshot",
            return_value=(object(), object()),
        ), patch.object(
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
