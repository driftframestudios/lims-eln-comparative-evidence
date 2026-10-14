"""Complete legacy artifacts survive candidate, publication and recovery faults."""
from concurrent.futures import ThreadPoolExecutor
import contextlib
import errno
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch

from comparative_evidence import artifact_boundary as boundary
from comparative_evidence import filesystem_publication as publication
from comparative_evidence.cli import main
from comparative_evidence.compare import compare_synthetic_contract
from comparative_evidence.gate import AdmissionError, admit
from comparative_evidence.model import ObservationEnvelope
from comparative_evidence.report import render_html, write_reports
from comparative_evidence.simulated_closure import SimulatedClosureError, admit_simulated_closure
from test_comparative_evidence import load, observed_envelope_value, planned_contract_value


class LegacyPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.target = self.root / "report"
        simulation = ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json"))
        candidate = planned_contract_value()
        profile = load("specification/comparison-profile.json")
        self.report = compare_synthetic_contract(simulation, ObservationEnvelope.from_dict(candidate), profile)
        candidate["result"]["specimen"]["revision"] += 1
        self.changed = compare_synthetic_contract(simulation, ObservationEnvelope.from_dict(candidate), profile)
        self.observed = ObservationEnvelope.from_dict(observed_envelope_value())
        self.bundle = load("fixtures/simulated-closures/future-reality-2028-06-30-v1.json")

    def pending(self):
        return sorted(self.root.rglob(".artifact-pending-*"))

    def observed_admission(self):
        return admit(self.observed, self.root / "observed")

    def simulated_admission(self):
        return admit_simulated_closure(self.bundle, self.root / "simulated")

    def test_fresh_empty_and_identical_report_destinations_preserve_released_bytes(self):
        for existing in (False, True):
            target = self.root / str(existing)
            if existing:
                target.mkdir()
            write_reports(self.report, target)
            expected = boundary.report_artifact_inventory(target)
            write_reports(self.report, target)
            self.assertEqual(expected, boundary.report_artifact_inventory(target))
            self.assertEqual((json.dumps(self.report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(), (target / "comparison.json").read_bytes())
            self.assertEqual(render_html(self.report).encode(), (target / "comparison.html").read_bytes())
        self.assertEqual([], self.pending())

    def test_changed_and_foreign_destinations_preserve_previous_state(self):
        write_reports(self.report, self.target)
        before = boundary.report_artifact_inventory(self.target)
        with self.assertRaisesRegex(publication.PublicationError, "fresh report directory"):
            write_reports(self.changed, self.target)
        self.assertEqual(before, boundary.report_artifact_inventory(self.target))
        for kind in ("file", "directory", "symlink", "dangling_symlink"):
            target = self.root / kind
            if kind == "file":
                target.write_bytes(b"retained")
            elif kind == "directory":
                target.mkdir()
                (target / "retained").write_bytes(b"retained")
            else:
                target.symlink_to(self.target if kind == "symlink" else self.root / "absent")
            with self.subTest(kind=kind), self.assertRaises(publication.PublicationError):
                write_reports(self.report, target)
            self.assertTrue(target.exists() or target.is_symlink())
        self.assertEqual(before, boundary.report_artifact_inventory(self.target))
        self.assertEqual(b"retained", (self.root / "file").read_bytes())
        self.assertEqual(b"retained", (self.root / "directory" / "retained").read_bytes())
        self.assertEqual([], self.pending())

    def test_render_and_verification_failure_preserve_previous_pair(self):
        write_reports(self.report, self.target)
        before = boundary.report_artifact_inventory(self.target)
        with self.assertRaises(ValueError):
            write_reports(self.changed, self.target, canonical_url="http://example.invalid/report")
        invalid = {**self.changed, "report_digest": "sha256:" + "0" * 64}
        with self.assertRaises(publication.PublicationError) as held:
            write_reports(invalid, self.target)
        self.assertEqual("verify", held.exception.stage)
        self.assertEqual(before, boundary.report_artifact_inventory(self.target))
        self.assertEqual([], self.pending())

    def test_alias_parent_compatibility_preserves_final_symlink(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        write_reports(self.report, alias / "report")
        manifest = admit(self.observed, alias / "observed")
        self.assertTrue(manifest.is_file())
        link = alias / "link"
        link.symlink_to(self.target, target_is_directory=True)
        before = boundary.report_artifact_inventory(self.target)
        with self.assertRaises(publication.PublicationError):
            write_reports(self.changed, link)
        self.assertTrue(link.is_symlink())
        self.assertEqual(before, boundary.report_artifact_inventory(self.target))

    def test_partial_writes_and_interruptions_leave_fresh_targets_retryable(self):
        original = publication._write_artifact
        def partial(fd, name, payload):
            original(fd, name, payload[:23])
            raise KeyboardInterrupt("synthetic partial candidate")
        operations = (self.observed_admission, self.simulated_admission, lambda: write_reports(self.report, self.target))
        for operation in operations:
            with self.subTest(operation=operation.__name__), patch.object(publication, "_write_artifact", side_effect=partial):
                with self.assertRaises(KeyboardInterrupt) as held:
                    operation()
            self.assertFalse(held.exception.published)
            self.assertEqual([], self.pending())
            self.assertEqual([], list(self.root.rglob("*.json")))
            result = operation()
            if result:
                json.loads(result.read_bytes())
                result.unlink()
            else:
                boundary.report_artifact_inventory(self.target)
                for member in self.target.iterdir():
                    member.unlink()
                self.target.rmdir()

    def test_candidate_verification_interrupt_allows_retry(self):
        for operation, owner, seam in (
            (self.observed_admission, publication, "_same_bytes"),
            (self.simulated_admission, publication, "_same_bytes"),
            (lambda: write_reports(self.report, self.target), boundary, "_report_inventory_at"),
        ):
            with self.subTest(operation=operation.__name__), patch.object(owner, seam, side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    operation()
            self.assertEqual([], self.pending())
            self.assertEqual([], list(self.root.rglob("*.json")))
            result = operation()
            if result:
                result.unlink()
            else:
                for member in self.target.iterdir():
                    member.unlink()
                self.target.rmdir()

    def test_interruption_before_publication_allows_retry(self):
        for operation, seam in ((self.observed_admission, "link"), (self.simulated_admission, "link")):
            with self.subTest(operation=operation.__name__), patch.object(publication.os, seam, side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    operation()
            self.assertEqual([], self.pending())
            destination = operation()
            json.loads(destination.read_bytes())
        with patch.object(publication, "_exclusive_rename", return_value=lambda *args: (_ for _ in ()).throw(KeyboardInterrupt())):
            with self.assertRaises(KeyboardInterrupt):
                write_reports(self.report, self.target)
        self.assertFalse(self.target.exists())
        self.assertEqual([], self.pending())
        write_reports(self.report, self.target)

    def test_signal_after_native_publication_keeps_complete_visible_identity(self):
        original_link = os.link
        def interrupt_link(*args, **kwargs):
            original_link(*args, **kwargs)
            signal.raise_signal(signal.SIGINT)
        with patch.object(publication.os, "link", side_effect=interrupt_link):
            with self.assertRaises(KeyboardInterrupt) as held:
                self.observed_admission()
        self.assertTrue(held.exception.published)
        accepted = self.observed_admission()
        json.loads(accepted.read_bytes())
        original_rename = publication._exclusive_rename()
        def interrupt_rename(*args):
            original_rename(*args)
            signal.raise_signal(signal.SIGINT)
        with patch.object(publication, "_exclusive_rename", return_value=interrupt_rename):
            with self.assertRaises(KeyboardInterrupt) as held:
                write_reports(self.report, self.target)
        self.assertTrue(held.exception.published)
        boundary.report_artifact_inventory(self.target)
        write_reports(self.report, self.target)
        self.assertEqual([], self.pending())

    def test_cleanup_interrupt_retains_complete_manifest_and_owned_recovery_name(self):
        with patch.object(publication, "_cleanup_owned", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt) as held:
                self.observed_admission()
        self.assertTrue(held.exception.published)
        retained = self.pending()
        self.assertEqual(1, len(retained))
        self.assertEqual(retained[0].name, held.exception.pending_name)
        accepted = self.observed_admission()
        json.loads(accepted.read_bytes())
        self.assertEqual(retained, self.pending())

    def test_primary_fault_preserves_cleanup_diagnostic_and_retry_ownership(self):
        primary = OSError(errno.EIO, "synthetic write failure")
        cleanup = KeyboardInterrupt("synthetic cleanup interruption")
        with patch.object(publication, "_write_artifact", side_effect=primary), patch.object(publication, "_cleanup_owned", side_effect=cleanup):
            with self.assertRaises(publication.PublicationError) as held:
                write_reports(self.report, self.target)
        self.assertIs(primary, held.exception.__cause__)
        self.assertIs(cleanup, held.exception.cleanup_error)
        self.assertFalse(held.exception.published)
        retained = self.pending()
        self.assertEqual(1, len(retained))
        write_reports(self.report, self.target)
        self.assertEqual(retained, self.pending())

    def test_manifest_collisions_keep_generated_bytes_and_reject_foreign_entries(self):
        for operation in (self.observed_admission, self.simulated_admission):
            destination = operation()
            before = destination.read_bytes()
            self.assertEqual(destination, operation())
            self.assertEqual(before, destination.read_bytes())
            for kind in ("changed", "symlink", "fifo", "oversized"):
                destination.unlink()
                if kind == "changed":
                    destination.write_bytes(b"{}\n")
                elif kind == "symlink":
                    destination.symlink_to(self.root / "missing")
                elif kind == "fifo":
                    os.mkfifo(destination)
                else:
                    destination.write_bytes(before + b" " * 100)
                with self.subTest(kind=kind), self.assertRaises((AdmissionError, SimulatedClosureError)):
                    operation()
                self.assertTrue(destination.exists() or destination.is_symlink())
            destination.unlink()
            operation()
        self.assertEqual([], self.pending())

    def test_concurrent_different_reports_keep_one_complete_winner(self):
        for existing in (False, True):
            self.target = self.root / str(existing)
            if existing:
                self.target.mkdir()
            barrier = Barrier(2)
            native = os.rename if existing else publication._exclusive_rename()
            def publish(*args, **kwargs):
                barrier.wait(timeout=10)
                native(*args, **kwargs)
            def attempt(report):
                try:
                    write_reports(report, self.target)
                    return None
                except publication.PublicationError as error:
                    return error
            seam = patch.object(publication.os, "rename", side_effect=publish) if existing else patch.object(publication, "_exclusive_rename", return_value=publish)
            with seam, ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(attempt, (self.report, self.changed)))
            self.assertEqual(1, sum(isinstance(value, publication.PublicationError) for value in results))
            boundary.report_artifact_inventory(self.target)
        self.assertEqual([], self.pending())

    def test_cli_empty_directory_replay_and_changed_destination_action(self):
        self.target.mkdir()
        args = ["compare", "compare-synthetic-contract", "--profile", "specification/comparison-profile.json", "--simulation", "fixtures/pairs/simulation-observation.json", "--contract-candidate", "fixtures/contracts/planned-observation.json", "--output", str(self.target)]
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
            main()
            main()
        before = boundary.report_artifact_inventory(self.target)
        with patch("comparative_evidence.cli.compare_synthetic_contract", return_value=self.changed), patch.object(sys, "argv", args):
            with self.assertRaisesRegex(publication.PublicationError, "fresh report directory"):
                main()
        self.assertEqual(before, boundary.report_artifact_inventory(self.target))
