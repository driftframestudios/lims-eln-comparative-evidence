"""Behavior-bearing boundaries for the portable finite-job carrier."""
from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "infra" / filename)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


job = module("boundary_container_job", "container_job.py")
runtime = module("boundary_container_runtime", "container_runtime.py")


class ContainerBoundaryTests(unittest.TestCase):
    def source(self, root, dependencies="stdlib"):
        source = root / "source"
        (source / "infra").mkdir(parents=True)
        names = ["LICENSE", "AUTHORS", "infra/container_entry.py", "infra/container_runtime.py"]
        for name in names:
            (source / name).write_text("fixture\n", encoding="utf-8")
        (source / "infra/container-profile.json").write_text(json.dumps({
            "version": "1.0.0", "name": "fixture", "files": names,
            "dependencies": dependencies,
        }), encoding="utf-8")
        return source

    def dependencies(self, root):
        directory = root / "dependencies"
        directory.mkdir()
        name = "fixture-1.0-py3-none-any.whl"
        content = b"boundary fixture; installation is a separate check"
        digest = sha256(content).hexdigest()
        requirements = f"fixture==1.0 \\\n    --hash=sha256:{digest}\n".encode("ascii")
        (directory / name).write_bytes(content)
        (directory / "requirements.lock").write_bytes(requirements)
        manifest = {"version": "1.0.0", "requirementsSha256": sha256(requirements).hexdigest(),
                    "wheels": [{"file": name, "sha256": digest}]}
        (directory / "wheel-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return directory, manifest, name

    def test_restrictive_umask_keeps_staged_inputs_readable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source(root)
            context = root / "context"
            original = os.umask(0o077)
            try:
                job.prepare(source, context)
            finally:
                os.umask(original)
            self.assertEqual(stat.S_IMODE(context.stat().st_mode), 0o700)
            for member in context.rglob("*"):
                with self.subTest(member=member.relative_to(context)):
                    expected = 0o755 if member.is_dir() else 0o644
                    self.assertEqual(stat.S_IMODE(member.stat().st_mode), expected)

    def test_wheel_and_requirements_digest_closure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source(root, "wheels")
            dependencies, _, name = self.dependencies(root)
            (dependencies / "unlisted.txt").write_text("private fixture", encoding="utf-8")
            context = root / "context"
            job.prepare(source, context, dependencies)
            self.assertEqual({item.name for item in (context / "wheels").iterdir()}, {name})
            self.assertEqual((context / "wheels" / name).read_bytes(), (dependencies / name).read_bytes())
            self.assertEqual((context / "requirements.lock").read_bytes(), (dependencies / "requirements.lock").read_bytes())

    def test_changed_dependency_bytes_hold_preparation(self):
        for changed in ("requirements.lock", "wheel"):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = self.source(root, "wheels")
                dependencies, _, name = self.dependencies(root)
                (dependencies / (name if changed == "wheel" else changed)).write_bytes(b"changed")
                context = root / "context"
                with self.assertRaises(job.ContextError):
                    job.prepare(source, context, dependencies)
                self.assertFalse(context.exists())

    def test_dependency_manifest_requires_exact_owned_records(self):
        cases = {
            "empty": lambda value: value.update(wheels=[]),
            "unknown": lambda value: value.update(extra=True),
            "duplicate": lambda value: value["wheels"].append(dict(value["wheels"][0])),
            "traversal": lambda value: value["wheels"][0].update(file="../fixture.whl"),
            "digest_type": lambda value: value["wheels"][0].update(sha256=12),
        }
        for name, change in cases.items():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as temporary:
                dependencies, manifest, _ = self.dependencies(Path(temporary))
                change(manifest)
                (dependencies / "wheel-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(job.ContextError):
                    job.admitted_dependencies(dependencies)

    @staticmethod
    def produce(output):
        (output / "result.json").write_text('{"status":"ready"}\n', encoding="utf-8")

    def test_native_validator_receives_payload_and_receipt_stays_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            calls = []
            def validate(payload):
                calls.append(payload.name)
                self.assertEqual({p.name for p in payload.iterdir()}, {"result.json"})
            observed = runtime.publish(self.produce, root, validate=validate)
            envelope = root / observed["directory"]
            self.assertEqual(calls, ["payload"])
            self.assertEqual({p.name for p in envelope.iterdir()}, {"payload", "job-receipt.json"})
            receipt = json.loads((envelope / "job-receipt.json").read_bytes())
            self.assertEqual(receipt["files"][0]["path"], "payload/result.json")
            self.assertEqual(receipt["files"][0]["sha256"], sha256((envelope / "payload/result.json").read_bytes()).hexdigest())

    def test_validation_failure_preserves_previous_completed_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous = runtime.publish(self.produce, root)
            saved = (root / previous["directory"] / "job-receipt.json").read_bytes()
            def reject(_payload):
                raise ValueError("native-artifact-fixture")
            with self.assertRaisesRegex(ValueError, "native-artifact-fixture"):
                runtime.publish(self.produce, root, validate=reject)
            self.assertEqual({p.name for p in root.iterdir()}, {previous["directory"]})
            self.assertEqual((root / previous["directory"] / "job-receipt.json").read_bytes(), saved)

    def test_directory_error_prevents_partial_receipt(self):
        def fail_after_one_file(top, *, followlinks, onerror):
            self.assertFalse(followlinks)
            yield str(top), [], ["result.json"]
            onerror(PermissionError("directory-fixture"))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous = runtime.publish(self.produce, root)
            with patch.object(runtime.os, "walk", fail_after_one_file):
                with self.assertRaisesRegex(PermissionError, "directory-fixture"):
                    runtime.publish(self.produce, root)
            self.assertEqual({p.name for p in root.iterdir()}, {previous["directory"]})

    def test_receipt_write_and_rename_failure_keep_prior_output(self):
        original_open = Path.open
        def failing_receipt(path, *args, **kwargs):
            if path.name == "job-receipt.json":
                raise OSError("receipt-fixture")
            return original_open(path, *args, **kwargs)
        for phase in ("receipt", "rename"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                previous = runtime.publish(self.produce, root)
                fault = patch.object(Path, "open", failing_receipt) if phase == "receipt" else patch.object(runtime.os, "rename", side_effect=OSError("rename-fixture"))
                with fault, self.assertRaises(OSError):
                    runtime.publish(self.produce, root)
                self.assertEqual({p.name for p in root.iterdir()}, {previous["directory"]})

    def test_termination_cleans_only_owned_pending_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            previous = runtime.publish(self.produce, root)
            code = '''import pathlib, signal, sys
sys.path.insert(0, sys.argv[1])
import container_runtime as runtime
root = pathlib.Path(sys.argv[2])
original = runtime.publish
runtime.publish = lambda producer, **options: original(producer, root, **options)
def produce(output):
    (output / "partial.json").write_text("{}")
    print("ready", flush=True)
    signal.pause()
runtime.run(produce)
'''
            process = subprocess.Popen([sys.executable, "-B", "-c", code, str(ROOT / "infra"), str(root)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertTrue(select.select([process.stdout], [], [], 5)[0], "child readiness deadline")
                self.assertEqual(process.stdout.readline().strip(), "ready")
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 128 + signal.SIGTERM, stderr)
                self.assertNotIn('"completed"', stdout)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)
            self.assertEqual({p.name for p in root.iterdir()}, {previous["directory"]})


    def test_requirements_preserve_logical_package_hash_association(self):
        digest = "a" * 64
        accepted = (
            f"fixture==1.0 --hash=sha256:{digest}\n",
            f"fixture==1.0 \\\n  --hash=sha256:{digest}\n",
        )
        rejected = (
            f"fixture==1.0\n--hash=sha256:{digest}\n",
            f"fixture==1.0 \\\n --hash=sha256:{digest} \\\n",
            f"fixture==1.0 \\\n\n--hash=sha256:{digest}\n",
        )
        for text in accepted:
            with self.subTest(accepted=text):
                self.assertTrue(job.requirements_admitted(text.encode("ascii")))
        for text in rejected:
            with self.subTest(rejected=text):
                self.assertFalse(job.requirements_admitted(text.encode("ascii")))

    def test_staged_bytes_and_receipt_match_independent_source_literals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source(root)
            expected = {
                "LICENSE": b"license\r\n\r\n",
                "AUTHORS": b"holder\n\n",
                "infra/container_entry.py": b"# entry\n\n",
                "infra/container_runtime.py": b"# runtime\r\n",
            }
            for name, content in expected.items():
                (source / name).write_bytes(content)
            context = root / "context"
            job.prepare(source, context)
            receipt = json.loads((context / "context-receipt.json").read_bytes())
            observed = {item["path"]: item for item in receipt["members"]}
            for name, content in expected.items():
                with self.subTest(source=name):
                    relative = "source/" + name
                    self.assertEqual((context / relative).read_bytes(), content)
                    self.assertEqual(observed[relative]["bytes"], len(content))
                    self.assertEqual(observed[relative]["sha256"], sha256(content).hexdigest())

    def test_preparation_termination_removes_only_acquired_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.source(root)
            context = root / "context"
            prior = root / "prior"
            prior.mkdir()
            (prior / "receipt.json").write_bytes(b"retained\n")
            code = '''import pathlib, signal, sys
sys.path.insert(0, sys.argv[1])
import container_job as job
source, destination = sys.argv[2:]
original = job.regular_bytes
def inspect(root, relative):
    if pathlib.Path(destination).exists():
        print("acquired", flush=True)
        signal.pause()
    return original(root, relative)
job.regular_bytes = inspect
sys.argv = ["container-job", destination, "--source", source]
raise SystemExit(job.main())
'''
            process = subprocess.Popen([sys.executable, "-B", "-c", code, str(ROOT / "infra"), str(source), str(context)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertTrue(select.select([process.stdout], [], [], 5)[0], "preparation acquisition deadline")
                self.assertEqual(process.stdout.readline().strip(), "acquired")
                process.send_signal(signal.SIGTERM)
                _stdout, stderr = process.communicate(timeout=5)
                self.assertEqual(process.returncode, 128 + signal.SIGTERM, stderr)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)
            self.assertFalse(context.exists())
            self.assertEqual((prior / "receipt.json").read_bytes(), b"retained\n")


if __name__ == "__main__":
    unittest.main()
