"""Boundary fixtures for the shared offline security patch layer."""

import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "infra"))
import container_patch as subject


class ContainerPatchTests(unittest.TestCase):
    def test_each_platform_has_exact_three_public_inputs(self):
        for architecture in ("arm64", "amd64"):
            with self.subTest(architecture=architecture):
                records = subject.patch_artifacts(architecture)
                self.assertEqual(len(records), 3)
                self.assertTrue(records[0].filename.endswith(f"_{architecture}.deb"))
                self.assertTrue(records[1].filename.endswith(f"_{architecture}.deb"))
                self.assertEqual(records[2].filename, "pip-26.2.1-py3-none-any.whl")
                for record in records:
                    self.assertRegex(record.sha256, r"^[0-9a-f]{64}$")
                    self.assertGreater(record.size, 0)
                    self.assertTrue(record.url.startswith("https://"))

    def test_architecture_boundary(self):
        for value in (None, [], True, "", "x86_64", "arm64; echo bad"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "architecture"):
                subject.patch_artifacts(value)

    def test_admission_and_literal_pip_lock(self):
        data = b"fixture bytes\r\n"
        artifact = subject.PatchArtifact("fixture.deb", len(data), hashlib.sha256(data).hexdigest(), "https://example.org/fixture.deb")
        with patch.object(subject, "patch_artifacts", return_value=(artifact,)):
            observed = subject.admit_patch_files("arm64", lambda name: data)
        self.assertEqual(observed["security-patches/fixture.deb"], data)
        self.assertEqual(observed["security-patches/pip.lock"], b"pip==26.2.1 --hash=sha256:71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e\n")

    def test_changed_size_digest_and_nonbytes_are_rejected(self):
        original = b"abc"
        artifact = subject.PatchArtifact("fixture.deb", 3, hashlib.sha256(original).hexdigest(), "https://example.org/fixture.deb")
        for data, expected in ((b"ab", "size"), (b"abd", "digest"), ("abc", "size")):
            with self.subTest(data=data), patch.object(subject, "patch_artifacts", return_value=(artifact,)):
                with self.assertRaisesRegex(ValueError, expected):
                    subject.admit_patch_files("arm64", lambda name: data)

    def test_reader_failure_propagates(self):
        def unavailable(name):
            raise OSError("fixture unavailable")
        with self.assertRaisesRegex(OSError, "unavailable"):
            subject.admit_patch_files("arm64", unavailable)

    def test_layer_bootstraps_from_patched_pip_with_offline_mount(self):
        for architecture in ("arm64", "amd64"):
            with self.subTest(architecture=architecture):
                result = subject.dockerfile_patch(architecture)
                self.assertIn("RUN --network=none --mount=type=bind,source=security-patches", result)
                self.assertIn("/opt/security-patches,ro", result)
                self.assertIn(f'= {architecture}', result)
                self.assertIn("sha256sum --check --strict", result)
                self.assertIn("sys.path.insert(0,", result)
                self.assertIn("pip-26.2.1-py3-none-any.whl", result)
                self.assertIn("runpy.run_module", result)
                self.assertIn("--require-hashes", result)
                self.assertIn("--no-index", result)
                self.assertIn("--no-deps", result)
                self.assertNotIn("apt-get update", result)
                self.assertNotIn("python -m pip", result)
                for line in result.splitlines()[:-1]:
                    self.assertTrue(line.endswith("\\"), line)


if __name__ == "__main__":
    unittest.main()
