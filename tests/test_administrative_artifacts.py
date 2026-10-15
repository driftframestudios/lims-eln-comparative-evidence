"""Complete administrative bundles retain their evidence through publication faults."""

from concurrent.futures import ThreadPoolExecutor
import contextlib
import errno
from html import unescape
from importlib.util import find_spec
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from threading import Barrier
import unittest
from unittest.mock import patch


def administrative_profile_available():
    if any(find_spec(name) is None for name in ("lims_eln_contracts", "lims_eln_sim")):
        return False
    return all(find_spec(name) is not None for name in (
        "lims_eln_contracts.administrative_study",
        "lims_eln_contracts.study_interpretation",
        "lims_eln_sim.administrative_pack",
    ))


HAS_PROFILE = administrative_profile_available()
if HAS_PROFILE:
    from lims_eln_contracts.administrative_study import admit_administrative_study
    from lims_eln_contracts.canonical import canonical_json_bytes, canonical_sha256
    from lims_eln_sim.administrative_pack import build_pack
    from comparative_evidence import administrative_artifacts as artifacts
    from comparative_evidence.administrative_evaluation import demonstration_study, evaluate, main
    from comparative_evidence.administrative_report import (
        MAX_REPORT_BYTES, MAX_REPORT_VALUES, admit_evaluation_report,
    )


@unittest.skipUnless(HAS_PROFILE, "administrative-study profile supplies the bounded source contracts")
class AdministrativeArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = build_pack(repeats=1)
        cls.study = demonstration_study(cls.pack)
        cls.report = evaluate(cls.pack, cls.study, evidence_mode="fixture_demonstration")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.target = self.root / "comparison"

    def publish(self, target=None):
        return artifacts.publish_administrative_bundle(
            self.pack, self.study, self.report, target or self.target,
        )

    def test_complete_nonempty_bundle_and_isolated_replay(self):
        first = self.publish()
        second = self.publish(self.root / "replay")
        self.assertEqual({"study.json", "comparison.json", "comparison.html"}, set(first))
        self.assertEqual(first, second)
        self.assertEqual(first, artifacts.administrative_artifact_inventory(self.target, self.pack))
        document = json.loads((self.target / "comparison.json").read_bytes())
        self.assertEqual(72, document["planned_runs"])
        self.assertEqual(64, document["scored_coverage"]["numerator"])
        self.assertEqual(2, document["scientific_oracle_disagreements"])
        self.assertEqual([14, 14, 0], [group["independent_subjects"] for group in document["groups"]])
        html = (self.target / "comparison.html").read_text()
        self.assertIn("64 scored runs of 72 planned", html)
        self.assertIn("Scientific oracle disagreements: 2", html)
        self.assertEqual([], list(self.root.glob(".administrative-pending-*")))

    def test_max_repeat_and_label_outputs_roundtrip_through_complete_bundle(self):
        pack = build_pack(repeats=4)
        document = demonstration_study(pack).model_dump(mode="json", by_alias=True)
        for index, observation in enumerate(document["observations"]):
            if observation["status"] == "completed":
                actual = json.loads(observation["administrative_output"]["text"])
                actual["labels"] = [f"SYN-PREDICTION-{index}-{label}" for label in range(16)]
                text = canonical_json_bytes(actual).decode()
                observation["administrative_output"].update(text=text, digest=canonical_sha256(text))
        study = admit_administrative_study(canonical_json_bytes(document))
        report = evaluate(pack, study)
        payload = canonical_json_bytes(report)
        self.assertEqual((288, 256, 4099),
                         (len(report.runs), report.scored_coverage.numerator, len(report.labels)))
        # Count the wire representation independently of the intake helper.
        pending, values = [json.loads(payload)], 0
        while pending:
            item = pending.pop()
            values += 1
            if isinstance(item, dict):
                values += len(item)
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
        self.assertGreater(values, 100000)
        self.assertLessEqual(values, MAX_REPORT_VALUES)
        self.assertLess(len(payload), MAX_REPORT_BYTES)
        self.assertEqual(payload, canonical_json_bytes(admit_evaluation_report(payload)))
        inventory = artifacts.publish_administrative_bundle(pack, study, report, self.target)
        self.assertEqual(inventory, artifacts.administrative_artifact_inventory(self.target, pack))
        self.assertEqual(payload + b"\n", (self.target / "comparison.json").read_bytes())
        embedded = (self.target / "comparison.html").read_text().split('<pre id="report-json">', 1)[1].split("</pre>", 1)[0]
        self.assertEqual(json.loads(payload), json.loads(unescape(embedded)))
        self.assertEqual([], list(self.root.glob(".administrative-pending-*")))

    def test_verifier_rejects_changed_members_shapes_and_links(self):
        def change_score(root):
            path = root / "comparison.json"
            report = json.loads(path.read_bytes())
            report["exact_label_agreement"].update(numerator=63, value=63 / 64)
            path.write_bytes(canonical_json_bytes(report) + b"\n")

        def change_study(root):
            path = root / "study.json"
            document = json.loads(path.read_bytes())
            document["observations"] = []
            path.write_bytes(canonical_json_bytes(document) + b"\n")

        def replace(root, kind):
            path = root / "comparison.json"
            path.unlink()
            if kind == "symlink":
                path.symlink_to(root / "study.json")
            elif kind == "hardlink":
                os.link(root / "study.json", path)
            elif kind == "fifo":
                os.mkfifo(path)
            else:
                path.mkdir()

        cases = {
            "missing": lambda root: (root / "study.json").unlink(),
            "truncated": lambda root: (root / "comparison.json").write_bytes(b'{"planned_runs":'),
            "duplicate_key": lambda root: (root / "comparison.json").write_bytes(b'{"x":1,"x":2}'),
            "encoding": lambda root: (root / "comparison.json").write_bytes(b"\xef\xbb\xbf{}"),
            "extra_file": lambda root: (root / "extra.json").write_bytes(b"{}"),
            "extra_directory": lambda root: (root / "extra").mkdir(),
            "score": change_score,
            "study": change_study,
            "html": lambda root: (root / "comparison.html").write_text("<!doctype html><p>Different result</p>"),
            **{kind: lambda root, kind=kind: replace(root, kind) for kind in ("symlink", "hardlink", "fifo", "directory")},
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                target = self.root / name
                self.publish(target)
                change(target)
                with self.assertRaises(artifacts.AdministrativeArtifactError):
                    artifacts.administrative_artifact_inventory(target, self.pack)

    def test_receiver_enforces_member_byte_budget(self):
        self.publish()
        limits = {**artifacts.ADMINISTRATIVE_ARTIFACT_LIMITS, "comparison.html": 32}
        with patch.object(artifacts, "ADMINISTRATIVE_ARTIFACT_LIMITS", limits):
            with self.assertRaises(artifacts.AdministrativeArtifactError):
                artifacts.administrative_artifact_inventory(self.target, self.pack)

    def test_fixture_mode_binds_exact_demonstration_and_caller_mode_accepts_changed_study(self):
        document = self.study.model_dump(mode="json", by_alias=True)
        observation = next(row for row in document["observations"] if row["status"] == "completed")
        science = json.loads(observation["scientific_output"]["text"])
        science["facts"] = ["SYN-CHANGED-FACT"]
        changed_text = canonical_json_bytes(science).decode()
        observation["scientific_output"].update(text=changed_text, digest=canonical_sha256(changed_text))
        study = admit_administrative_study(canonical_json_bytes(document))
        fixture_report = evaluate(self.pack, study, evidence_mode="fixture_demonstration")
        with self.assertRaises(artifacts.AdministrativePublicationError) as held:
            artifacts.publish_administrative_bundle(self.pack, study, fixture_report, self.target)
        self.assertEqual("bundle_verify", held.exception.code)
        self.assertEqual("bundle_fixture_identity", held.exception.__cause__.code)
        self.assertEqual([], list(self.root.iterdir()))
        report = evaluate(self.pack, study, evidence_mode="caller_supplied_synthetic")
        self.assertEqual(3, report.scientific_oracle_disagreements)
        inventory = artifacts.publish_administrative_bundle(self.pack, study, report, self.target)
        self.assertEqual(inventory, artifacts.administrative_artifact_inventory(self.target, self.pack))

    def test_each_file_write_failure_retains_prior_bundle_and_allows_retry(self):
        prior = self.root / "accepted"
        accepted = self.publish(prior)
        original = artifacts._write_artifact
        for name in ("study.json", "comparison.json", "comparison.html"):
            with self.subTest(member=name):
                target = self.root / ("retry-" + name)
                def fail_after_write(fd, member, payload):
                    original(fd, member, payload)
                    if member == name:
                        raise OSError(errno.EIO, "synthetic interruption")
                with patch.object(artifacts, "_write_artifact", side_effect=fail_after_write):
                    with self.assertRaises(artifacts.AdministrativePublicationError) as held:
                        self.publish(target)
                self.assertEqual("bundle_write", held.exception.code)
                self.assertFalse(held.exception.published)
                self.assertFalse(target.exists())
                self.assertEqual([], list(self.root.glob(".administrative-pending-*")))
                self.assertEqual(accepted, artifacts.administrative_artifact_inventory(prior, self.pack))
                self.assertEqual(accepted, self.publish(target))

    def test_partial_acquisition_releases_its_own_directory(self):
        original = os.open
        failed = False
        def fail_first_staging_open(path, *args, **kwargs):
            nonlocal failed
            if str(path).startswith(".administrative-pending-") and not failed:
                failed = True
                raise OSError(errno.EMFILE, "synthetic acquisition failure")
            return original(path, *args, **kwargs)
        with patch.object(artifacts.os, "open", side_effect=fail_first_staging_open):
            with self.assertRaises(artifacts.AdministrativePublicationError) as held:
                self.publish()
        self.assertEqual("bundle_acquire", held.exception.code)
        self.assertEqual([], list(self.root.iterdir()))
        self.publish()

    def test_verification_and_publication_failures_allow_retry(self):
        for stage in ("verify", "publish"):
            target = self.root / stage
            seam = "_inventory_at" if stage == "verify" else "_exclusive_rename"
            replacement = {"side_effect": ValueError("synthetic verification failure")} if stage == "verify" else {"return_value": lambda *args: (_ for _ in ()).throw(OSError(errno.EIO, "synthetic rename failure"))}
            with self.subTest(stage=stage), patch.object(artifacts, seam, **replacement):
                with self.assertRaises(artifacts.AdministrativePublicationError) as held:
                    self.publish(target)
            self.assertEqual("bundle_" + stage, held.exception.code)
            self.assertFalse(target.exists())
            self.assertEqual([], list(self.root.glob(".administrative-pending-*")))
            self.publish(target)

    def test_sync_failure_distinguishes_visible_bundle(self):
        original = os.fsync
        for failing_directory in (1, 2):
            target = self.root / ("sync-" + str(failing_directory))
            directory_syncs = 0
            def sync(fd):
                nonlocal directory_syncs
                if stat.S_ISDIR(os.fstat(fd).st_mode):
                    directory_syncs += 1
                    if directory_syncs == failing_directory:
                        raise OSError(errno.EIO, "synthetic directory sync failure")
                return original(fd)
            with self.subTest(sync=failing_directory), patch.object(artifacts.os, "fsync", side_effect=sync):
                with self.assertRaises(artifacts.AdministrativePublicationError) as held:
                    self.publish(target)
            self.assertEqual("bundle_sync", held.exception.code)
            self.assertEqual(failing_directory == 2, held.exception.published)
            self.assertEqual(failing_directory == 2, target.exists())
            if target.exists():
                artifacts.administrative_artifact_inventory(target, self.pack)
            else:
                self.publish(target)

    def test_cleanup_failure_preserves_primary_cause_and_retry_ownership(self):
        failure = OSError(errno.EIO, "synthetic write failure")
        cleanup = OSError(errno.EACCES, "synthetic cleanup failure")
        with patch.object(artifacts, "_write_artifact", side_effect=failure), patch.object(artifacts, "_cleanup_owned", side_effect=cleanup):
            with self.assertRaises(artifacts.AdministrativePublicationError) as held:
                self.publish()
        self.assertIs(failure, held.exception.__cause__)
        self.assertIs(cleanup, held.exception.cleanup_error)
        pending = list(self.root.glob(".administrative-pending-*"))
        self.assertEqual(1, len(pending))
        self.publish()
        self.assertEqual(pending, list(self.root.glob(".administrative-pending-*")))

    def test_descriptor_close_failure_still_releases_staging_and_preserves_cause(self):
        primary = OSError(errno.EIO, "synthetic write failure")
        close_error = OSError(errno.EIO, "synthetic close observation")
        real_close = os.close
        staging_fd = None
        failed = False
        def write(fd, name, payload):
            nonlocal staging_fd
            staging_fd = fd
            raise primary
        def close(fd):
            nonlocal failed
            real_close(fd)
            if fd == staging_fd and not failed:
                failed = True
                raise close_error
        with patch.object(artifacts, "_write_artifact", side_effect=write), patch.object(artifacts.os, "close", side_effect=close):
            with self.assertRaises(artifacts.AdministrativePublicationError) as held:
                self.publish()
        self.assertIs(primary, held.exception.__cause__)
        self.assertIs(close_error, held.exception.cleanup_error)
        self.assertEqual([], list(self.root.iterdir()))
        self.publish()

    def test_stream_acquisition_releases_the_raw_descriptor_once(self):
        from comparative_evidence.artifact_boundary import _read_regular_file
        source = self.root / "source"
        source.write_bytes(b"owned source")
        for operation in ("read", "write", "partial_wrap"):
            real_close = os.close
            acquired, closed = [], []
            failure = OSError(errno.ENOMEM, "synthetic stream acquisition failure")
            def wrap(fd, *args, **kwargs):
                acquired.append(fd)
                self.assertFalse(kwargs["closefd"])
                if operation == "partial_wrap":
                    # FileIO cleanup during a later wrapper failure retains our raw fd.
                    io.FileIO(fd, args[0], closefd=kwargs["closefd"]).close()
                raise failure
            def close(fd):
                closed.append(fd)
                real_close(fd)
            with self.subTest(operation=operation), artifacts._directory(self.root) as parent_fd:
                with patch.object(artifacts.os, "fdopen", side_effect=wrap), patch.object(artifacts.os, "close", side_effect=close):
                    with self.assertRaises(OSError) as held:
                        if operation == "read":
                            _read_regular_file(source, "source", max_bytes=64)
                        else:
                            artifacts._write_artifact(parent_fd, "candidate-" + operation, b"candidate bytes")
            self.assertIs(failure, held.exception)
            self.assertEqual(1, len(acquired))
            self.assertEqual(acquired, closed)

    def test_stream_close_interrupt_releases_raw_descriptor_and_preserves_primary(self):
        from comparative_evidence.artifact_boundary import _owned_binary_stream
        for primary in (None, ValueError("synthetic body failure")):
            descriptor = os.open(self.root / "stream", os.O_WRONLY | os.O_CREAT, 0o600)
            interruption = KeyboardInterrupt("synthetic stream teardown interruption")
            class BorrowedStream:
                def close(self):
                    raise interruption
            closed = []
            real_close = os.close
            def close(fd):
                closed.append(fd)
                real_close(fd)
            expected = primary or interruption
            with self.subTest(primary=primary is not None):
                with patch.object(artifacts.os, "fdopen", return_value=BorrowedStream()), patch.object(artifacts.os, "close", side_effect=close):
                    with self.assertRaises(type(expected)) as held:
                        with _owned_binary_stream(descriptor, "wb"):
                            if primary is not None:
                                raise primary
                self.assertIs(expected, held.exception)
                self.assertEqual([descriptor], closed)
                if primary is not None:
                    self.assertIs(interruption, primary.cleanup_error)
                with self.assertRaises(OSError):
                    os.fstat(descriptor)

    def test_directory_acquisition_closes_child_after_previous_close_failure(self):
        real_open, real_close = os.open, os.close
        opened, closed = [], []
        def acquire(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd
        def close(fd):
            real_close(fd)
            closed.append(fd)
            if len(closed) == 1:
                raise OSError(errno.EIO, "synthetic prior descriptor close observation")
        with patch.object(artifacts.os, "open", side_effect=acquire), patch.object(artifacts.os, "close", side_effect=close):
            with self.assertRaises(OSError):
                with artifacts._directory(self.root):
                    self.fail("acquisition stopped at the observed close error")
        self.assertEqual(2, len(opened))
        self.assertEqual(opened, closed)

    def test_directory_final_close_preserves_body_failure(self):
        primary = ValueError("synthetic body failure")
        cleanup = OSError(errno.EIO, "synthetic final close observation")
        real_close = os.close
        final_fd = None
        def close(fd):
            real_close(fd)
            if fd == final_fd:
                raise cleanup
        with patch.object(artifacts.os, "close", side_effect=close):
            with self.assertRaises(ValueError) as held:
                with artifacts._directory(self.root) as fd:
                    final_fd = fd
                    raise primary
        self.assertIs(primary, held.exception)
        self.assertIs(cleanup, held.exception.cleanup_error)

    def test_replaced_staging_name_keeps_the_replacement_available(self):
        original = artifacts._inventory_at
        displaced = self.root / "displaced-owned-staging"
        replacement = None
        def replace_after_verification(fd, pack):
            nonlocal replacement
            inventory = original(fd, pack)
            replacement = next(self.root.glob(".administrative-pending-*"))
            replacement.rename(displaced)
            replacement.mkdir()
            (replacement / "retained").write_bytes(b"another owner's bytes")
            return inventory
        with patch.object(artifacts, "_inventory_at", side_effect=replace_after_verification):
            with self.assertRaises(artifacts.AdministrativePublicationError) as held:
                self.publish()
        self.assertEqual("bundle_publish", held.exception.code)
        self.assertIsNotNone(held.exception.cleanup_error)
        self.assertEqual(b"another owner's bytes", (replacement / "retained").read_bytes())
        self.assertFalse(self.target.exists())
        artifacts.administrative_artifact_inventory(displaced, self.pack)

    def test_existing_destinations_and_parent_symlinks_retain_owned_state(self):
        for kind in ("directory", "file", "symlink", "dangling_symlink"):
            target = self.root / kind
            if kind == "directory":
                target.mkdir()
            elif kind == "file":
                target.write_bytes(b"accepted")
            else:
                target.symlink_to(self.root if kind == "symlink" else self.root / "absent")
            with self.subTest(kind=kind), self.assertRaises(artifacts.AdministrativePublicationError) as held:
                self.publish(target)
            self.assertEqual("bundle_destination_exists", held.exception.code)
            self.assertTrue(target.exists() or target.is_symlink())
        self.assertEqual(b"accepted", (self.root / "file").read_bytes())
        alias = self.root / "parent-alias"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(artifacts.AdministrativePublicationError):
            self.publish(alias / "unpublished")
        self.assertFalse((self.root / "unpublished").exists())
        with self.assertRaises(artifacts.AdministrativePublicationError):
            self.publish(alias / ".." / "lexically-rewritten")
        self.assertFalse((self.root.parent / "lexically-rewritten").exists())
        with self.assertRaises(artifacts.AdministrativeArtifactError):
            artifacts.administrative_artifact_inventory(alias, self.pack)

    def test_native_exclusive_publication_admits_one_concurrent_winner(self):
        barrier = Barrier(2)
        native = artifacts._exclusive_rename()
        def concurrent(parent, source, target):
            barrier.wait(timeout=10)
            native(parent, source, target)
        def attempt():
            try:
                return self.publish()
            except artifacts.AdministrativePublicationError as error:
                return error
        with patch.object(artifacts, "_exclusive_rename", return_value=concurrent), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        errors = [value for value in results if isinstance(value, artifacts.AdministrativePublicationError)]
        self.assertEqual(1, len(errors))
        self.assertEqual("bundle_destination_exists", errors[0].code)
        self.assertFalse(errors[0].published)
        artifacts.administrative_artifact_inventory(self.target, self.pack)
        self.assertEqual([], list(self.root.glob(".administrative-pending-*")))

    def test_cli_write_failure_then_same_destination_retry(self):
        pack_path = self.root / "pack.json"
        pack_path.write_bytes(canonical_json_bytes(self.pack))
        args = ["administrative_evaluation", "--pack", str(pack_path), "--fixture-demo", "--output", str(self.target)]
        original = artifacts._write_artifact
        def interrupt(fd, name, payload):
            if name == "comparison.json":
                raise OSError(errno.EIO, "synthetic write failure")
            original(fd, name, payload)
        with patch.object(sys, "argv", args), contextlib.redirect_stderr(io.StringIO()):
            with patch.object(artifacts, "_write_artifact", side_effect=interrupt):
                with self.assertRaises(SystemExit) as held:
                    main()
            self.assertEqual(2, held.exception.code)
            self.assertFalse(self.target.exists())
            with contextlib.redirect_stdout(io.StringIO()) as output:
                main()
        self.assertIn("72 planned; 64 scored; 2 scientific oracle disagreements", output.getvalue())
        artifacts.administrative_artifact_inventory(self.target, self.pack)


class AdministrativeProfileSelectionTests(unittest.TestCase):
    def test_absent_profile_skips_while_nested_import_errors_remain_visible(self):
        with patch(__name__ + ".find_spec", return_value=None):
            self.assertFalse(administrative_profile_available())
        with patch(__name__ + ".find_spec", side_effect=[object(), object(), None]):
            self.assertFalse(administrative_profile_available())
        missing = ModuleNotFoundError("synthetic installed dependency failure", name="nested_dependency")
        with patch(__name__ + ".find_spec", side_effect=[object(), object(), missing]):
            with self.assertRaises(ModuleNotFoundError) as held:
                administrative_profile_available()
        self.assertIs(missing, held.exception)


if __name__ == "__main__":
    unittest.main()
