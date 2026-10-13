"""Independent input, ownership, confinement, and retained-output fixtures."""
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from container_patch_fixtures import patch_inputs

ROOT=Path(__file__).resolve().parents[1]

def load(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module

context=load("container_job",ROOT/"infra/container_job.py")
runtime=load("container_runtime",ROOT/"infra/container_runtime.py")

class ContainerBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.patch_directory = self.enterContext(patch_inputs())

    def fixture(self,root):
        source=root/"source"
        (source/"infra").mkdir(parents=True)
        files=["infra/container_entry.py","infra/container_runtime.py","LICENSE","AUTHORS"]
        for name in files:
            (source/name).write_text("fixture\n")
        (source/"infra/container-profile.json").write_text(json.dumps({"version":"1.0.0","name":"fixture","files":files,"dependencies":"stdlib"}))
        return source

    def test_path_and_profile_boundaries(self):
        for value in ("", "/absolute", "../escape", "a//b", "a/./b", "a/.git/config", "a\\b", "a\x00b", 3):
            with self.subTest(value=repr(value)), self.assertRaises(context.ContextError):
                context.relative_path(value)
        base={"version":"1.0.0","name":"fixture","files":["infra/container_entry.py","infra/container_runtime.py","LICENSE","AUTHORS"],"dependencies":"stdlib"}
        for change in ({"files":[]},{"files":base["files"]+["license"]},{"files":None},{"dependencies":"remote"},{"extra":True}):
            with self.subTest(change=change), self.assertRaises(context.ContextError):
                context.admitted_profile({**base,**change})
        with self.assertRaises(context.ContextError):
            context.strict_document(b'{"name":1,"name":2}')

    def test_context_carries_exact_files_and_retains_existing_destination(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            source=self.fixture(root)
            canary="generated-"+os.urandom(16).hex()
            (source/"private-local-value").write_text(canary)
            target=root/"context"
            result=context.prepare(source,target,patches=self.patch_directory,architecture="arm64")
            receipt=json.loads((target/"context-receipt.json").read_text())
            expected={"source/infra/container_entry.py","source/infra/container_runtime.py","source/LICENSE","source/AUTHORS","requirements.lock","Dockerfile",
                      "security-patches/pip-26.2.1-py3-none-any.whl","security-patches/pip.lock",
                      "security-patches/liblzma5_5.8.1-1+deb13u2_arm64.deb"}
            self.assertEqual({item["path"] for item in receipt["members"]},expected)
            for item in receipt["members"]:
                content=(target/item["path"]).read_bytes()
                self.assertEqual(item["sha256"],sha256(content).hexdigest())
                self.assertEqual(item["bytes"],len(content))
                self.assertNotIn(canary.encode(),content)
            self.assertEqual(result["files"],9)
            before=(target/"context-receipt.json").read_bytes()
            with self.assertRaises(FileExistsError):
                context.prepare(source,target,patches=self.patch_directory,architecture="arm64")
            self.assertEqual(before,(target/"context-receipt.json").read_bytes())

    def test_source_and_failure_boundaries(self):
        for kind in ("symlink","directory","hardlink","failure"):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                source=self.fixture(root)
                item=source/"LICENSE"
                if kind != "failure":
                    item.unlink()
                    if kind=="symlink": item.symlink_to(source/"AUTHORS")
                    elif kind=="directory": item.mkdir()
                    else: os.link(source/"AUTHORS",item)
                with patch.object(context,"MAX_TOTAL_BYTES",1 if kind=="failure" else context.MAX_TOTAL_BYTES):
                    with self.assertRaises((context.ContextError,OSError)):
                        context.prepare(source,root/"context",patches=self.patch_directory,architecture="arm64")
                self.assertFalse((root/"context").exists())

    def test_patch_inputs_use_existing_file_boundary_before_acquisition(self):
        for kind in ("missing", "changed", "symlink", "hardlink", "directory"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary, patch_inputs() as patches:
                root = Path(temporary)
                source = self.fixture(root)
                selected = patches / "liblzma5_5.8.1-1+deb13u2_arm64.deb"
                original = selected.read_bytes()
                selected.unlink()
                if kind == "changed":
                    selected.write_bytes(b"x" * len(original))
                elif kind in ("symlink", "hardlink"):
                    other = patches / "other"
                    other.write_bytes(original)
                    if kind == "symlink":
                        selected.symlink_to(other)
                    else:
                        os.link(other, selected)
                elif kind == "directory":
                    selected.mkdir()
                target = root / "context"
                with self.assertRaises((context.ContextError, OSError)):
                    context.prepare(source, target, patches=patches, architecture="arm64")
                self.assertFalse(target.exists())

    def test_base_and_verified_installer_precede_application_installation(self):
        source = context.dockerfile("arm64").decode("ascii")
        self.assertTrue(source.startswith("FROM --platform=linux/arm64 python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS runtime_base\n"))
        self.assertLess(source.index('test "$VERSION_ID" = 13'), source.index("FROM runtime_base AS installer"))
        self.assertLess(source.index("sha256sum --check"), source.index("runpy.run_module"))
        self.assertIn("dpkg --install /opt/security-patches/liblzma5_5.8.1-1+deb13u2_arm64.deb", source)
        self.assertLess(source.index("dpkg --install"), source.index("FROM runtime_base AS installer"))
        self.assertLess(source.index("native package state"), source.index("FROM runtime_base AS installer"))
        self.assertLess(source.index("runpy.run_module"), source.index("python -m pip install"))
        self.assertLess(source.index("metadata.version"), source.index("python -m pip install"))
        self.assertEqual(source.count("FROM "), 3)
        self.assertIn("FROM runtime_base AS installer", source)
        self.assertIn("FROM runtime_base AS runtime", source)
        self.assertIn("--ignore-installed --no-compile --prefix=/opt/job/runtime-prefix", source)
        final = source.split("FROM runtime_base AS runtime\n", 1)[1]
        self.assertIn("COPY --from=installer /opt/job/runtime-prefix/ /usr/local/", final)
        self.assertIn("runtime installer modules", final)
        self.assertIn("native package state", final)
        self.assertIn("native decode", final)
        self.assertNotIn("runpy.run_module", final)
        self.assertNotIn("COPY wheels", final)

    def test_patch_directory_and_destination_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.fixture(root)
            alias = root / "patch-alias"
            alias.symlink_to(self.patch_directory, target_is_directory=True)
            with self.assertRaisesRegex(context.ContextError, "patch-directory"):
                context.prepare(source, root / "context", patches=alias, architecture="arm64")
            with self.assertRaisesRegex(context.ContextError, "external-context"):
                context.prepare(source, self.patch_directory / "context", patches=self.patch_directory, architecture="arm64")

    def test_requirements_require_hashes_and_registry_coordinates(self):
        digest="a"*64
        valid=f"package==1.0.0 \\\n --hash=sha256:{digest}\n".encode()
        self.assertTrue(context.requirements_admitted(valid))
        for data in (b"package==1.0\n",b"",b"--extra-index-url https://example.invalid\n",b"package @ file:private\n",valid+b"other==2.0\n"):
            with self.subTest(data=data):
                self.assertFalse(context.requirements_admitted(data))

    def test_publication_retains_prior_runs_and_cleans_failed_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def produce(output): (output/"value.json").write_text('{"value":3}\n')
            with patch.object(runtime.os,"getuid",return_value=root.stat().st_uid):
                first=runtime.publish(produce,root)
                second=runtime.publish(produce,root)
                self.assertNotEqual(first["directory"],second["directory"])
                self.assertEqual((root/first["directory"]/"payload"/"value.json").read_bytes(),(root/second["directory"]/"payload"/"value.json").read_bytes())
                def failed(output):
                    produce(output)
                    raise ValueError("fixture")
                with self.assertRaises(ValueError): runtime.publish(failed,root)
            self.assertEqual(len(list(root.glob("run-*"))),2)
            self.assertEqual(list(root.glob(".pending-*")),[])

    def test_output_rejects_symlinks_and_empty_results(self):
        for kind in ("symlink","empty"):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary)
                def produce(output):
                    if kind=="symlink": (output/"outside").symlink_to(root)
                with self.assertRaises(ValueError): runtime.publish(produce,root)
                self.assertEqual(list(root.iterdir()),[])

    def test_image_and_compose_confinement(self):
        self.assertIn(b"RUN --network=none",context.dockerfile("arm64"))
        self.assertIn(b"--require-hashes",context.dockerfile("arm64"))
        self.assertIn(b"USER 10001:10001",context.dockerfile("arm64"))
        source=(ROOT/"infra/container-compose.yml").read_text()
        for expected in ("read_only: true","network_mode: none","cap_drop: [ALL]","no-new-privileges:true","pids_limit: 128","mem_limit: 512m","init: true","create_host_path: false"):
            with self.subTest(expected=expected): self.assertIn(expected,source)

if __name__=="__main__": unittest.main()
