"""A released stream loses access before its descriptor can serve another file."""
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from comparative_evidence import artifact_boundary as boundary
from comparative_evidence import filesystem_publication as publication


class StreamOwnershipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def assert_later_owner_preserved(self, stream, descriptor):
        with self.assertRaises(OSError):
            os.fstat(descriptor)
        later = self.root / "later-owner"
        later.write_bytes(b"NEW accepted bytes")
        acquired = os.open(later, os.O_RDWR)
        if acquired != descriptor:
            os.dup2(acquired, descriptor)
        try:
            # Late finalization must preserve both bytes and the next owner's fd.
            stream.close()
            self.assertEqual(b"NEW accepted bytes", later.read_bytes())
            os.fstat(descriptor)
            self.assertTrue(stream.raw.closed)
            with self.assertRaises(ValueError):
                stream.raw.fileno()
        finally:
            os.close(descriptor)
            if acquired != descriptor:
                os.close(acquired)

    def test_manifest_faults_preserve_later_descriptor_owner_and_prior_artifact(self):
        target = self.root / "accepted.json"
        payload = b'{"synthetic":"accepted"}\n'
        publication.publish_manifest(payload, target)
        for buffer_type in (io.BufferedReader, io.BufferedWriter):
            for primary_type, cleanup_type in (
                (OSError, KeyboardInterrupt), (KeyboardInterrupt, OSError),
                (SystemExit, KeyboardInterrupt), (OSError, OSError),
            ):
                primary, cleanup = primary_type("synthetic body"), cleanup_type("synthetic close")
                retained = []
                class Interrupted:
                    def __init__(self, raw):
                        self.stream = buffer_type(raw)
                        retained.append((self.stream, raw.fileno()))
                    def __getattr__(self, name):
                        return getattr(self.stream, name)
                    def read(self, size):
                        self.stream.peek(1)
                        raise primary
                    def flush(self):
                        raise primary
                    def close(self):
                        raise cleanup
                with self.subTest(buffer=buffer_type.__name__, primary=primary_type, cleanup=cleanup_type):
                    expected = publication.PublicationError if primary_type is OSError else primary_type
                    with patch.object(boundary.io, buffer_type.__name__, side_effect=Interrupted):
                        with self.assertRaises(expected) as caught:
                            publication.publish_manifest(payload, target)
                    observed = caught.exception
                    self.assertIs(primary, observed.__cause__ if primary_type is OSError else observed)
                    self.assertIs(cleanup, primary.cleanup_error)
                    self.assertFalse(observed.published)
                    self.assertIsNone(observed.pending_name)
                    self.assertEqual(payload, target.read_bytes())
                    self.assertEqual([], list(self.root.glob(".artifact-pending-*")))
                    self.assert_later_owner_preserved(*retained[0])
                    publication.publish_manifest(payload, target)
                    self.assertEqual(payload, target.read_bytes())

    def test_partial_buffer_construction_invalidates_retained_raw_before_release(self):
        for mode, buffer_type in (("rb", io.BufferedReader), ("wb", io.BufferedWriter)):
            source = self.root / "source"
            source.write_bytes(b"source")
            descriptor = os.open(source, os.O_RDONLY if mode == "rb" else os.O_WRONLY)
            retained = []
            failure = OSError("synthetic buffer constructor")
            def partial(raw):
                retained.append(buffer_type(raw))
                raise failure
            with self.subTest(mode=mode), patch.object(boundary.io, buffer_type.__name__, side_effect=partial):
                with self.assertRaises(OSError) as caught:
                    with boundary._owned_binary_stream(descriptor, mode):
                        self.fail("construction requires completion")
            self.assertIs(failure, caught.exception)
            self.assert_later_owner_preserved(retained[0], descriptor)

    def test_live_raw_retains_descriptor_through_public_error_for_ordered_recovery(self):
        raw_type = io.FileIO
        for control_type in (OSError, KeyboardInterrupt, SystemExit):
            failure = control_type("synthetic invalidation")
            captured = []
            class RetainedRaw(raw_type):
                def close(self):
                    raise failure
            def acquire(fd, mode, *, closefd):
                raw = RetainedRaw(fd, mode, closefd=closefd)
                captured.append((raw, fd))
                return raw
            with self.subTest(control=control_type), patch.object(boundary.io, "FileIO", side_effect=acquire):
                try:
                    # Released publication retains grouped teardown as its cause.
                    with self.assertRaises(publication.PublicationError) as caught:
                        publication.publish_manifest(b"synthetic", self.root / "candidate")
                    error = caught.exception.__cause__
                    # Buffered close and direct raw invalidation can both encounter the same fault.
                    self.assertIsInstance(error, BaseExceptionGroup)
                    self.assertIs(error.retained_stream, captured[0][0])
                    self.assertEqual(error.retained_descriptor, captured[0][1])
                    self.assertFalse(error.retained_stream.closed)
                    os.fstat(error.retained_descriptor)
                    self.assertEqual([], list(self.root.iterdir()))
                finally:
                    for raw, fd in captured:
                        raw_type.close(raw)
                        self.assertTrue(raw.closed)
                        os.close(fd)

    def test_raw_close_after_invalidation_releases_descriptor_once(self):
        raw_type = io.FileIO
        failure = KeyboardInterrupt("synthetic post-invalidation signal")
        captured, released = [], []
        class ClosedRaw(raw_type):
            def close(self):
                raw_type.close(self)
                raise failure
        def acquire(fd, mode, *, closefd):
            raw = ClosedRaw(fd, mode, closefd=closefd)
            captured.append((raw, fd))
            return raw
        descriptor = os.open(self.root / "source", os.O_WRONLY | os.O_CREAT, 0o600)
        real_close = os.close
        def close(fd):
            released.append(fd)
            real_close(fd)
        with patch.object(boundary.io, "FileIO", side_effect=acquire), patch.object(boundary.os, "close", side_effect=close):
            with self.assertRaises(KeyboardInterrupt) as caught:
                with boundary._owned_binary_stream(descriptor, "wb") as stream:
                    stream.write(b"accepted")
        self.assertIs(failure, caught.exception)
        self.assertEqual([descriptor], released)
        self.assertTrue(captured[0][0].closed)
        self.assertFalse(hasattr(failure, "retained_descriptor"))
