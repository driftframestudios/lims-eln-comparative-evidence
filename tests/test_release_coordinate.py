"""Focused checks for the signed Comparator release coordinate."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from tools import verify_release_coordinate as verifier


class SignedRepository:
    """Create an isolated signed release and its two receipt states."""

    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="comparison-release-")
        self.root = Path(self.temporary.name)
        self.private_key = self.root / "test-release-key"
        self.public_key = self.root / "test-release-key.pub"
        self.receipt_path = self.root / "receipts" / "promotion-receipt.json"
        self.signers_path = self.root / "release" / "trusted-release-signers"

        self._run("init", "--initial-branch=main")
        self._run("config", "user.name", "Comparator Release Test")
        self._run("config", "user.email", "release@example.invalid")
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(self.private_key),
            ],
            check=True,
            capture_output=True,
        )
        fingerprint = subprocess.run(
            ["ssh-keygen", "-lf", str(self.public_key)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
        self.signing_fingerprint = fingerprint[1]
        self._run("config", "gpg.format", "ssh")
        self._run("config", "user.signingkey", str(self.private_key))

        self.receipt_path.parent.mkdir()
        self.signers_path.parent.mkdir()
        self._write_receipt(self._candidate_receipt())
        key_parts = self.public_key.read_text(encoding="utf-8").split()
        self.signers_path.write_text(
            f'release@example.invalid namespaces="git" {key_parts[0]} {key_parts[1]}\n',
            encoding="utf-8",
        )
        (self.root / "README.md").write_text(
            "comparative release fixture\n",
            encoding="utf-8",
        )
        self._run(
            "add",
            "README.md",
            "receipts/promotion-receipt.json",
            "release/trusted-release-signers",
        )
        self._run("commit", "-m", "Prepare comparison release")
        self._run(
            "tag",
            "-s",
            "-m",
            "Comparative Evidence 0.3.1",
            "comparison-v0.3.1",
        )
        self._run("update-ref", "refs/remotes/origin/main", "HEAD")
        self.coordinate = verifier.observe_release_coordinate(
            self.root,
            tag="comparison-v0.3.1",
            accepted_ref="refs/remotes/origin/main",
            expected_signing_fingerprint=self.signing_fingerprint,
        )
        self.expected_release = {
            field: getattr(self.coordinate, field)
            for field in (
                "tag",
                "tag_object_oid",
                "commit_oid",
                "tree_oid",
                "archive_digest",
            )
        }

    def close(self) -> None:
        self.temporary.cleanup()

    def _run(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def _candidate_receipt(self) -> dict:
        return {
            "$schema": "../schemas/promotion-receipt.schema.json",
            "schema_version": "1.0.0",
            "promotion_receipt_id": "RCP-COMPARATIVE-PROMOTION-003",
            "repository": "driftframestudios/lims-eln-comparative-evidence",
            "target_release": "comparison-v0.3.1",
            "promotion_state": "candidate_ready",
            "release_event_evidence": {
                "evidence_mode": "planned",
                "assurance_stage": "specified",
            },
            "comparison_authority": {
                "evidence_mode": "simulated",
                "assurance_stage": "verified",
                "comparison_mode": "simulated_verification",
                "environment_observed_closure": "separate_unasserted_state",
                "production_authorization_effect": "none",
            },
            "candidate_source": {
                "coordinate_kind": "accepted_develop_merge_source",
                "commit_oid": "daae956379cf00f5008672d19765aee6bec7eb4a",
                "tree_oid": "ba1c8b3dcc7a0c3233b0d5b8c9f74765152dade3",
            },
            "release_subject": None,
            "required_evidence": [
                "The signed release coordinate is reproduced from local Git objects."
            ],
            "accountable_role": "Comparative evidence release stewardship",
        }

    def _write_receipt(self, receipt: dict) -> None:
        self.receipt_path.write_text(
            json.dumps(receipt, indent=2) + "\n",
            encoding="utf-8",
        )

    def record_observed_receipt(self) -> dict:
        receipt = self._candidate_receipt()
        receipt["promotion_state"] = "release_observed"
        receipt["release_event_evidence"] = {
            "evidence_mode": "observed",
            "assurance_stage": "verified",
        }
        receipt["release_subject"] = {
            **self.coordinate.as_dict(),
            "hosted_check_contexts": [
                {
                    "name": "Repository validation",
                    "run_id": "12345",
                    "conclusion": "success",
                }
            ],
            "local_verification_signals": [
                "focused release-coordinate checks passed",
                "signed tag and archive were reproduced locally",
            ],
        }
        self._write_receipt(receipt)
        self._run("add", "receipts/promotion-receipt.json")
        self._run("commit", "-m", "Record release observation")
        self._run("update-ref", "refs/remotes/origin/main", "HEAD")
        return receipt

    def commit_receipt(self, receipt: dict) -> None:
        self._write_receipt(receipt)
        self._run("add", "receipts/promotion-receipt.json")
        self._run("commit", "-m", "Adjust release observation")
        self._run("update-ref", "refs/remotes/origin/main", "HEAD")


class ReleaseCoordinateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = SignedRepository()

    def tearDown(self) -> None:
        self.repository.close()

    def verify(self) -> dict[str, str]:
        return verifier.verify_release_coordinate(
            self.repository.root,
            expected_release=self.repository.expected_release,
            expected_signing_fingerprint=self.repository.signing_fingerprint,
        )

    def test_candidate_ready_returns_a_clear_resting_result(self) -> None:
        self.repository._run("tag", "-d", "comparison-v0.3.1")
        self.repository.signers_path.unlink()
        output = StringIO()
        with redirect_stdout(output):
            result = verifier.main(["--repository", str(self.repository.root)])
        self.assertEqual(0, result)
        self.assertEqual(
            {
                "promotion_state": "candidate_ready",
                "status": "resting",
                "target_release": "comparison-v0.3.1",
            },
            json.loads(output.getvalue()),
        )

    def test_require_observed_rejects_a_resting_candidate(self) -> None:
        self.repository._run("tag", "-d", "comparison-v0.3.1")
        self.repository.signers_path.unlink()
        output = StringIO()
        errors = StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            result = verifier.main(
                [
                    "--repository",
                    str(self.repository.root),
                    "--require-observed",
                ]
            )
        self.assertEqual(1, result)
        self.assertEqual("", output.getvalue())
        self.assertIn("observed signed release coordinate is required", errors.getvalue())

    def test_observed_receipt_matches_signed_tag_tree_and_archive(self) -> None:
        self.repository.record_observed_receipt()
        result = self.verify()
        self.assertEqual("passed", result["status"])
        self.assertEqual(
            self.repository.coordinate.commit_oid,
            result["commit_oid"],
        )

    def test_deleted_tag_after_capture_fails_the_final_snapshot(self) -> None:
        self.repository.record_observed_receipt()
        archive_digest = verifier._archive_digest

        def delete_tag_after_archive(identity, commit_oid):
            digest = archive_digest(identity, commit_oid)
            self.repository._run("tag", "-d", "comparison-v0.3.1")
            return digest

        with patch.object(
            verifier,
            "_archive_digest",
            side_effect=delete_tag_after_archive,
        ), self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "release tag ref .* remains at one exact captured object",
        ):
            self.verify()

    def test_moved_tag_after_capture_fails_the_final_snapshot(self) -> None:
        self.repository.record_observed_receipt()
        archive_digest = verifier._archive_digest

        def move_tag_after_archive(identity, commit_oid):
            digest = archive_digest(identity, commit_oid)
            self.repository._run(
                "update-ref",
                "refs/tags/comparison-v0.3.1",
                "HEAD",
            )
            return digest

        with patch.object(
            verifier,
            "_archive_digest",
            side_effect=move_tag_after_archive,
        ), self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "release tag ref .* remains at one exact captured object",
        ):
            self.verify()

    def test_changed_accepted_ref_after_capture_fails_the_final_snapshot(self) -> None:
        self.repository.record_observed_receipt()
        archive_digest = verifier._archive_digest

        def move_accepted_ref_after_archive(identity, commit_oid):
            digest = archive_digest(identity, commit_oid)
            self.repository._run(
                "update-ref",
                "refs/remotes/origin/main",
                self.repository.coordinate.commit_oid,
            )
            return digest

        with patch.object(
            verifier,
            "_archive_digest",
            side_effect=move_accepted_ref_after_archive,
        ), self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "accepted history ref .* remains at one exact captured object",
        ):
            self.verify()

    def test_receipt_mutation_after_capture_fails_the_final_snapshot(self) -> None:
        self.repository.record_observed_receipt()
        archive_digest = verifier._archive_digest

        def mutate_receipt_after_archive(identity, commit_oid):
            digest = archive_digest(identity, commit_oid)
            self.repository.receipt_path.write_bytes(
                self.repository.receipt_path.read_bytes() + b"\n"
            )
            return digest

        with patch.object(
            verifier,
            "_archive_digest",
            side_effect=mutate_receipt_after_archive,
        ), self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "working promotion receipt remains at the exact captured bytes",
        ):
            self.verify()

    def test_signer_mutation_after_capture_fails_the_final_snapshot(self) -> None:
        self.repository.record_observed_receipt()
        archive_digest = verifier._archive_digest

        def mutate_signer_after_archive(identity, commit_oid):
            digest = archive_digest(identity, commit_oid)
            self.repository.signers_path.write_bytes(
                self.repository.signers_path.read_bytes() + b"# changed policy\n"
            )
            return digest

        with patch.object(
            verifier,
            "_archive_digest",
            side_effect=mutate_signer_after_archive,
        ), self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "working trusted-release-signers remains at the exact captured bytes",
        ):
            self.verify()

    def test_repository_info_attributes_cannot_change_the_archive(self) -> None:
        self.repository.record_observed_receipt()
        attributes = self.repository.root / ".git" / "info" / "attributes"
        attributes.write_text("* export-ignore\n", encoding="utf-8")
        with self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "archive attributes without local info/attributes",
        ):
            self.verify()

    def test_receipt_difference_names_the_exact_coordinate_field(self) -> None:
        receipt = self.repository.record_observed_receipt()
        receipt["release_subject"]["archive_digest"] = "sha256:" + "7" * 64
        self.repository.commit_receipt(receipt)
        with self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "archive_digest: receipt=.*derived=",
        ):
            self.verify()

    def test_accepted_coordinate_difference_fails_closed(self) -> None:
        self.repository.record_observed_receipt()
        expected = deepcopy(self.repository.expected_release)
        expected["tree_oid"] = "7" * 40
        with self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "tree_oid: expected=.*derived=",
        ):
            verifier.verify_release_coordinate(
                self.repository.root,
                expected_release=expected,
                expected_signing_fingerprint=(self.repository.signing_fingerprint),
            )

    def test_trust_carrier_rejects_an_unaccepted_signing_key(self) -> None:
        other_key = self.repository.root / "other-release-key"
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(other_key),
            ],
            check=True,
            capture_output=True,
        )
        key_parts = other_key.with_suffix(".pub").read_text(encoding="utf-8").split()
        self.repository.signers_path.write_text(
            f'other@example.invalid namespaces="git" {key_parts[0]} {key_parts[1]}\n',
            encoding="utf-8",
        )
        self.repository._run("add", "release/trusted-release-signers")
        self.repository._run("commit", "-m", "Carry an unaccepted release key")
        self.repository._run(
            "tag",
            "-f",
            "-s",
            "-m",
            "Comparative Evidence 0.3.1",
            "comparison-v0.3.1",
        )
        self.repository._run("update-ref", "refs/remotes/origin/main", "HEAD")
        with self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "exactly the accepted signing-key fingerprint",
        ):
            verifier.observe_release_coordinate(
                self.repository.root,
                tag="comparison-v0.3.1",
                expected_signing_fingerprint=self.repository.signing_fingerprint,
            )

    def test_allowed_signer_namespace_option_precedes_the_public_key(self) -> None:
        key_parts = self.repository.public_key.read_text(encoding="utf-8").split()
        self.repository.signers_path.write_text(
            f'release@example.invalid {key_parts[0]} {key_parts[1]} '
            'namespaces="git"\n',
            encoding="utf-8",
        )
        self.repository._run("add", "release/trusted-release-signers")
        self.repository._run("commit", "-m", "Carry malformed signer options")
        self.repository._run(
            "tag",
            "-f",
            "-s",
            "-m",
            "Comparative Evidence 0.3.1",
            "comparison-v0.3.1",
        )
        self.repository._run("update-ref", "refs/remotes/origin/main", "HEAD")
        with self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "options before the public key",
        ):
            verifier.observe_release_coordinate(
                self.repository.root,
                tag="comparison-v0.3.1",
                expected_signing_fingerprint=self.repository.signing_fingerprint,
            )

    def test_working_signer_bytes_match_the_head_carrier(self) -> None:
        self.repository.record_observed_receipt()
        self.repository.signers_path.write_bytes(
            self.repository.signers_path.read_bytes() + b"# uncommitted policy text\n"
        )
        with self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "exact trusted-release-signers bytes",
        ):
            self.verify()

    def test_head_signer_bytes_match_the_signed_release_tree(self) -> None:
        self.repository.record_observed_receipt()
        self.repository.signers_path.write_bytes(
            self.repository.signers_path.read_bytes() + b"# later policy text\n"
        )
        self.repository._run("add", "release/trusted-release-signers")
        self.repository._run("commit", "-m", "Change the carried signer policy")
        self.repository._run("update-ref", "refs/remotes/origin/main", "HEAD")
        with self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "signed release tree contain exact trusted-release-signers bytes",
        ):
            self.verify()

    def test_replacement_tag_object_cannot_override_the_recorded_tag(self) -> None:
        self.repository.record_observed_receipt()
        original_tag = self.repository._run(
            "rev-parse",
            "refs/tags/comparison-v0.3.1",
        )
        other_key = self.repository.root / "replacement-tag-key"
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(other_key),
            ],
            check=True,
            capture_output=True,
        )
        self.repository._run("config", "user.signingkey", str(other_key))
        self.repository._run(
            "tag",
            "-f",
            "-s",
            "-m",
            "Different signed payload",
            "comparison-v0.3.1",
            self.repository.coordinate.commit_oid,
        )
        replacement_tag = self.repository._run(
            "rev-parse",
            "refs/tags/comparison-v0.3.1",
        )
        self.assertNotEqual(original_tag, replacement_tag)
        self.repository._run(
            "update-ref",
            "refs/tags/comparison-v0.3.1",
            original_tag,
        )
        self.repository._run("config", "user.signingkey", str(self.repository.private_key))
        self.repository._run("replace", original_tag, replacement_tag)
        self.assertEqual("passed", self.verify()["status"])

    def test_replacement_head_cannot_supply_working_receipt_bytes(self) -> None:
        self.repository.record_observed_receipt()
        carrier = self.repository._run("rev-parse", "HEAD")
        parent = self.repository._run("rev-parse", f"{carrier}^")
        self.repository.receipt_path.write_bytes(
            self.repository.receipt_path.read_bytes() + b"\n"
        )
        self.repository._run("add", "receipts/promotion-receipt.json")
        replacement_tree = self.repository._run("write-tree")
        replacement_commit = self.repository._run(
            "commit-tree",
            replacement_tree,
            "-p",
            parent,
            "-m",
            "Replacement observation carrier",
        )
        self.repository._run("replace", carrier, replacement_commit)
        with self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "exact promotion-receipt bytes",
        ):
            self.verify()

    def test_ambient_ssh_verifier_configuration_is_ignored(self) -> None:
        self.repository.record_observed_receipt()
        self.repository._run(
            "config",
            "gpg.ssh.program",
            str(self.repository.root / "missing-ssh-keygen"),
        )
        self.assertEqual("passed", self.verify()["status"])

    def test_ambient_git_environment_is_ignored(self) -> None:
        self.repository.record_observed_receipt()
        with patch.dict(
            os.environ,
            {
                "GIT_CONFIG_GLOBAL": str(self.repository.root / "missing-config"),
                "GIT_DIR": str(self.repository.root / "missing-git-directory"),
                "GIT_NO_REPLACE_OBJECTS": "0",
                "GIT_WORK_TREE": str(self.repository.root / "missing-worktree"),
            },
        ):
            self.assertEqual("passed", self.verify()["status"])

    def test_working_receipt_bytes_match_the_head_carrier(self) -> None:
        self.repository.record_observed_receipt()
        self.repository.receipt_path.write_bytes(
            self.repository.receipt_path.read_bytes() + b"\n"
        )
        with self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "exact promotion-receipt bytes",
        ):
            self.verify()

    def test_release_commit_belongs_to_accepted_history(self) -> None:
        self.repository.record_observed_receipt()
        orphan = self.repository._run(
            "commit-tree",
            self.repository._run("rev-parse", "HEAD^{tree}"),
            "-m",
            "Independent accepted history",
        )
        self.repository._run(
            "update-ref",
            "refs/remotes/origin/main",
            orphan,
        )
        with self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "outside accepted history",
        ):
            self.verify()

    def test_observation_carrier_head_descends_from_accepted_history(self) -> None:
        self.repository.record_observed_receipt()
        orphan = self.repository._run(
            "commit-tree",
            self.repository._run("rev-parse", "HEAD^{tree}"),
            "-m",
            "Unrelated observation carrier",
        )
        self.repository._run("checkout", "--detach", orphan)
        with self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "carrier HEAD .* descends from accepted history",
        ):
            self.verify()

    def test_local_git_grafts_cannot_supply_carrier_ancestry(self) -> None:
        self.repository.record_observed_receipt()
        accepted = self.repository._run("rev-parse", "refs/remotes/origin/main")
        orphan = self.repository._run(
            "commit-tree",
            self.repository._run("rev-parse", "HEAD^{tree}"),
            "-m",
            "Locally grafted observation carrier",
        )
        self.repository._run("checkout", "--detach", orphan)
        (self.repository.root / ".git" / "info" / "grafts").write_text(
            f"{orphan} {accepted}\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(
            verifier.ReleaseCoordinateError,
            "history without local grafts",
        ):
            self.verify()


if __name__ == "__main__":
    unittest.main()
