"""Boundary fixtures for the shared offline security patch layer."""

import hashlib
import importlib.metadata
import importlib.util
from types import SimpleNamespace
from pathlib import Path
import sys
import subprocess
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "infra"))
import container_patch as subject


class ContainerPatchTests(unittest.TestCase):
    def test_each_platform_has_exact_native_repair_and_installer_inputs(self):
        installer = subject.PatchArtifact(
            "pip-26.2.1-py3-none-any.whl", 1816632,
            "71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e",
            "https://files.pythonhosted.org/packages/f3/6e/1736e5b4ae2b778ef2f81c47d797de9f891d4d8acb047a24ca37a60294dd/pip-26.2.1-py3-none-any.whl",
        )
        native = {
            "arm64": (302984, "88f3aa499dc30edf01b9209ab40f11e37edfbecef971f84f4721de1874ed4827"),
            "amd64": (309696, "b38acab30f295bf1066a6632e31cbd0a1980f2924b38040cda131d5dea5384ec"),
        }
        for architecture in ("arm64", "amd64"):
            with self.subTest(architecture=architecture):
                size, digest = native[architecture]
                filename = f"liblzma5_5.8.1-1+deb13u2_{architecture}.deb"
                package = subject.PatchArtifact(filename, size, digest, "https://security.debian.org/debian-security/pool/updates/main/x/xz-utils/" + filename)
                self.assertEqual(subject.patch_artifacts(architecture), (package, installer))

    def test_architecture_boundary(self):
        for operation in (subject.patch_artifacts, subject.dockerfile_base_guard):
            for value in (None, [], True, "", "x86_64", "arm64; echo bad"):
                with self.subTest(operation=operation.__name__, value=value):
                    with self.assertRaisesRegex(ValueError, "architecture"):
                        operation(value)

    def test_native_repair_checks_identity_before_install_and_installed_state_after(self):
        for architecture in ("arm64", "amd64"):
            with self.subTest(architecture=architecture):
                result = subject.dockerfile_base_guard(architecture)
                self.assertIn(f'test "$(dpkg --print-architecture)" = {architecture}', result)
                self.assertIn('. /etc/os-release', result)
                self.assertIn('test "$ID" = debian', result)
                self.assertIn('test "$VERSION_ID" = 13', result)
                self.assertLess(result.index('. /etc/os-release'), result.index('test "$ID"'))
                self.assertIn('RUN --network=none --mount=type=bind,source=security-patches', result)
                self.assertIn('/opt/security-patches,ro', result)
                self.assertIn(f'liblzma5_5.8.1-1+deb13u2_{architecture}.deb', result)
                self.assertIn(f'install ok installed 5.8.1-1+deb13u2 {architecture}', result)
                self.assertLess(result.index('sha256sum --check'), result.index('dpkg-deb --field'))
                self.assertLess(result.index('dpkg-deb --field'), result.index('dpkg --install'))
                self.assertLess(result.index('dpkg --install'), result.index('dpkg-query'))
                self.assertIn('native decode', result)
                self.assertNotIn('apt-get', result)
                self.assertNotIn('--force', result)
                other = 'amd64' if architecture == 'arm64' else 'arm64'
                self.assertNotIn(f'_{other}.deb', result)

    def test_native_guard_preserves_fixed_decode_and_both_round_trip_formats(self):
        import lzma
        for status, accepted in (("install ok installed 5.8.1-1+deb13u2", True), ("install ok installed 5.8.1-1+deb13u1", False), ("install ok unpacked 5.8.1-1+deb13u2", False)):
            with self.subTest(status=status), patch.object(subprocess, "check_output", return_value=status) as query, patch.object(lzma, "compress", wraps=lzma.compress) as compress:
                if accepted:
                    exec(subject.runtime_native_guard(), {})
                    self.assertEqual([call.kwargs["format"] for call in compress.call_args_list], [lzma.FORMAT_XZ, lzma.FORMAT_ALONE])
                else:
                    with self.assertRaisesRegex(AssertionError, "native package state"):
                        exec(subject.runtime_native_guard(), {})
                    compress.assert_not_called()
                query.assert_called_once_with(["dpkg-query", "--show", "--showformat=${Status} ${Version}", "liblzma5"], text=True)
        with patch.object(subprocess, "check_output", return_value="install ok installed 5.8.1-1+deb13u2"), patch.object(lzma, "decompress", return_value=b"changed"):
            with self.assertRaisesRegex(AssertionError, "native decode"):
                exec(subject.runtime_native_guard(), {})
        self.assertIn("native package state", subject.dockerfile_runtime_guard())
        self.assertIn("native round trip", subject.dockerfile_runtime_guard())

    def test_admission_and_literal_pip_lock(self):
        data = b"fixture bytes\r\n"
        artifact = subject.PatchArtifact("fixture.whl", len(data), hashlib.sha256(data).hexdigest(), "https://example.org/fixture.whl")
        with patch.object(subject, "patch_artifacts", return_value=(artifact,)):
            observed = subject.admit_patch_files("arm64", lambda name: data)
        self.assertEqual(observed["security-patches/fixture.whl"], data)
        self.assertEqual(observed["security-patches/pip.lock"], b"pip==26.2.1 --hash=sha256:71138adf1f4ca900cdb7d289c21b7494329f2332b6d85f0e1c42108c0384ed3e\n")

    def test_changed_size_digest_and_nonbytes_are_rejected(self):
        original = b"abc"
        artifact = subject.PatchArtifact("fixture.whl", 3, hashlib.sha256(original).hexdigest(), "https://example.org/fixture.whl")
        for data, expected in ((b"ab", "size"), (b"abd", "digest"), ("abc", "size")):
            with self.subTest(data=data), patch.object(subject, "patch_artifacts", return_value=(artifact,)):
                with self.assertRaisesRegex(ValueError, expected):
                    subject.admit_patch_files("arm64", lambda name: data)

    def test_reader_failure_propagates(self):
        def unavailable(name):
            raise OSError("fixture unavailable")
        with self.assertRaisesRegex(OSError, "unavailable"):
            subject.admit_patch_files("arm64", unavailable)

    def test_runtime_guard_accepts_application_metadata_and_rejects_installer_routes(self):
        application = SimpleNamespace(metadata={"Name": "lims-eln-program-specification"})
        pip = SimpleNamespace(metadata={"Name": "pip"})
        cases = (
            ("application", None, [application], False, True),
            ("pip module", "pip", [application], False, False),
            ("ensurepip module", "ensurepip", [application], False, False),
            ("pip metadata", None, [application, pip], False, False),
            ("pip executable", None, [application], True, False),
        )
        for name, module, distributions, executable, accepted in cases:
            with self.subTest(case=name), patch.object(importlib.util, "find_spec", side_effect=lambda value: object() if value == module else None), patch.object(importlib.metadata, "distributions", return_value=distributions), patch.object(Path, "exists", return_value=executable):
                if accepted:
                    exec(subject.runtime_tooling_guard(), {})
                else:
                    with self.assertRaises(AssertionError):
                        exec(subject.runtime_tooling_guard(), {})

    def test_runtime_cleanup_is_bound_to_the_pinned_base(self):
        result = subject.dockerfile_runtime_cleanup()
        self.assertIn("25.0.1", result)
        self.assertIn("site-packages/pip-25.0.1.dist-info", result)
        self.assertIn("/usr/local/lib/python3.12/ensurepip", result)
        self.assertIn("rm /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.12", result)
        self.assertNotIn("rm -rf", result)
        self.assertNotIn("*", result)

    def test_layer_bootstraps_from_patched_pip_with_offline_mount(self):
        for architecture in ("arm64", "amd64"):
            with self.subTest(architecture=architecture):
                result = subject.dockerfile_base_guard(architecture) + subject.dockerfile_installer()
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
                for stage in (subject.dockerfile_base_guard(architecture), subject.dockerfile_installer()):
                    for line in stage.splitlines()[:-1]:
                        self.assertTrue(line.endswith("\\"), line)


if __name__ == "__main__":
    unittest.main()
