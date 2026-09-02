"""Material behavior checks for the source-owned Pages projection."""

from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import build_pages as pages_builder
from build_pages import (
    DEFAULT_CANONICAL_ORIGIN,
    DEFAULT_REPOSITORY_URL,
    MANIFEST_PATH,
    MANIFEST_FILE_SCOPE,
    MANIFEST_VERSION,
    PagesBuildError,
    PROJECTION_OWNER,
    SOURCE_LINK_PATHS,
    ValidationFixtureSourceProof,
    build_projection,
    clean_source_revision,
    projection_byte_inventory,
    validate_projection,
    verify_reproducible_projections,
)
from comparative_evidence.compare import compare_synthetic_contract
from comparative_evidence.golden_verification import compare_golden_specimen
from comparative_evidence.model import ObservationEnvelope, strict_json_loads
from comparative_evidence.publication import (
    BIG_BENCH_CANARY,
    MAPS_CANARY,
    PUBLIC_ATTRIBUTION,
)
from comparative_evidence.report import write_reports


REVISION = "a" * 40


def load(relative: str) -> dict:
    value = strict_json_loads((ROOT / relative).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def update_manifest_identity(projection: Path, relative: str) -> None:
    manifest_path = projection / MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    content = (projection / relative).read_bytes()
    entry = next(item for item in manifest["files"] if item["path"] == relative)
    entry["bytes"] = len(content)
    entry["sha256"] = sha256(content).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def update_manifest_field(projection: Path, field: str, value: object) -> None:
    manifest_path = projection / MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[field] = value
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def initialize_git_repository(
    parent: Path,
    name: str,
    *,
    origin: str = DEFAULT_REPOSITORY_URL + ".git",
) -> Path:
    repository = parent / name
    repository.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "collaborator@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Repository Collaborator"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", origin],
        cwd=repository,
        check=True,
    )
    (repository / "source.txt").write_text("settled\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.txt"], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "settle source"],
        cwd=repository,
        check=True,
    )
    return repository


def initialize_publication_repository(
    parent: Path,
    name: str,
    *,
    origin: str = DEFAULT_REPOSITORY_URL + ".git",
) -> Path:
    repository = parent / name
    shutil.copytree(
        ROOT,
        repository,
        ignore=shutil.ignore_patterns(
            ".git",
            ".artifacts",
            ".venv",
            "__pycache__",
            "*.pyc",
        ),
    )
    subprocess.run(["git", "init", "--quiet"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "collaborator@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Repository Collaborator"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", origin],
        cwd=repository,
        check=True,
    )
    subprocess.run(["git", "add", "--all"], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "settle publication source"],
        cwd=repository,
        check=True,
    )
    return repository


class PagesProjectionTests(unittest.TestCase):
    def build(self, parent: Path, name: str, **kwargs: str) -> Path:
        output = parent / name
        build_projection(
            ROOT,
            output,
            source_proof=ValidationFixtureSourceProof(REVISION),
            **kwargs,
        )
        return output

    def test_isolated_builds_are_byte_identical_and_source_bound(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-") as directory:
            parent = Path(directory)
            first = self.build(parent, "first")
            replay = self.build(parent, "replay")
            inventory = verify_reproducible_projections(first, replay)
            manifest = validate_projection(first)

            self.assertEqual(manifest["sourceRevision"], REVISION)
            self.assertEqual(manifest["sourceStanding"], "validation_fixture")
            self.assertEqual(manifest["manifestVersion"], MANIFEST_VERSION)
            self.assertEqual(manifest["projectionOwner"], PROJECTION_OWNER)
            self.assertEqual(manifest["fileScope"], MANIFEST_FILE_SCOPE)
            self.assertEqual(manifest["canonicalOrigin"], DEFAULT_CANONICAL_ORIGIN)
            self.assertIsNone(manifest["cname"])
            self.assertTrue(
                manifest["goldenSpecimenReportDigest"].startswith("sha256:")
            )
            self.assertNotIn("CNAME", inventory)
            self.assertEqual(
                set(inventory),
                {
                    ".nojekyll",
                    "assets/site.css",
                    "data-use.html",
                    "index.html",
                    "projection-manifest.json",
                    "reports/golden-specimen/comparison.html",
                    "reports/golden-specimen/comparison.json",
                    "reports/reference/comparison.html",
                    "reports/reference/comparison.json",
                },
            )
            for entry in manifest["files"]:
                self.assertEqual(entry["sourceRevision"], REVISION)

    def test_report_projection_preserves_comparator_runtime_bytes(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="comparative-pages-") as directory,
            tempfile.TemporaryDirectory(prefix="comparative-report-") as report_directory,
        ):
            projection = self.build(Path(directory), "site")
            report = compare_synthetic_contract(
                ObservationEnvelope.from_dict(
                    load("fixtures/pairs/simulation-observation.json")
                ),
                ObservationEnvelope.from_dict(
                    load("fixtures/contracts/planned-observation.json")
                ),
                load("specification/comparison-profile.json"),
            )
            runtime = Path(report_directory)
            write_reports(
                report,
                runtime,
                canonical_url=(
                    DEFAULT_CANONICAL_ORIGIN
                    + "reports/reference/comparison.html"
                ),
            )
            for filename in ("comparison.html", "comparison.json"):
                self.assertEqual(
                    (projection / "reports/reference" / filename).read_bytes(),
                    (runtime / filename).read_bytes(),
                )

    def test_golden_projection_preserves_comparator_runtime_bytes(self) -> None:
        with (
            tempfile.TemporaryDirectory(prefix="comparative-pages-") as directory,
            tempfile.TemporaryDirectory(prefix="golden-report-") as report_directory,
        ):
            projection = self.build(Path(directory), "site")
            report = compare_golden_specimen(
                load("fixtures/pairs/enterprise-postgresql-observation.json"),
                load("fixtures/pairs/simulation-golden-specimen-observation.json"),
                load("specification/golden-specimen-verification-profile.json"),
                load("constellation.lock.json"),
            )
            runtime = Path(report_directory)
            write_reports(
                report,
                runtime,
                canonical_url=(
                    DEFAULT_CANONICAL_ORIGIN
                    + "reports/golden-specimen/comparison.html"
                ),
            )
            for filename in ("comparison.html", "comparison.json"):
                self.assertEqual(
                    (
                        projection
                        / "reports/golden-specimen"
                        / filename
                    ).read_bytes(),
                    (runtime / filename).read_bytes(),
                )

    def test_golden_report_keeps_public_and_horizontal_boundaries(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-") as directory:
            projection = self.build(Path(directory), "site")
            document = (
                projection / "reports/golden-specimen/comparison.html"
            ).read_text(encoding="utf-8")

            self.assertIn(
                "Scroll horizontally inside the comparison table",
                document,
            )
            self.assertIn('class="table-scroll" role="region"', document)
            self.assertIn('aria-describedby="adjudication-instructions"', document)
            self.assertIn('tabindex="0"', document)
            self.assertIn("overflow-x:auto", document)
            self.assertLess(
                document.index(MAPS_CANARY),
                document.index(BIG_BENCH_CANARY),
            )
            self.assertIn(PUBLIC_ATTRIBUTION, document)

    def test_all_html_carries_accessible_orientation_and_marker_order(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-") as directory:
            projection = self.build(Path(directory), "site")
            for path in sorted(projection.rglob("*.html")):
                with self.subTest(path=path.relative_to(projection)):
                    document = path.read_text(encoding="utf-8")
                    self.assertIn('<html lang="en">', document)
                    self.assertIn('name="viewport"', document)
                    self.assertLess(
                        document.index(MAPS_CANARY),
                        document.index(BIG_BENCH_CANARY),
                    )
                    self.assertIn(PUBLIC_ATTRIBUTION, document)
            index = (projection / "index.html").read_text(encoding="utf-8")
            self.assertIn('class="skip-link"', index)
            self.assertIn('<main id="content"', index)

    def test_source_links_use_the_complete_revision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-") as directory:
            projection = self.build(Path(directory), "site")
            index = (projection / "index.html").read_text(encoding="utf-8")
            self.assertIn(
                'href="reports/golden-specimen/comparison.html"',
                index,
            )
            self.assertIn(
                'href="reports/golden-specimen/comparison.json"',
                index,
            )
            prefix = (
                "https://github.com/driftframestudios/"
                f"lims-eln-comparative-evidence/blob/{REVISION}/"
            )
            for source_path in SOURCE_LINK_PATHS:
                self.assertIn(prefix + source_path, index)
            self.assertNotIn("/blob/main/", index)
            self.assertNotIn("/blob/develop/", index)

    def test_custom_domain_is_explicit_and_matches_the_canonical_origin(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-") as directory:
            projection = self.build(
                Path(directory),
                "site",
                canonical_origin="https://comparison.example.test/",
                cname="comparison.example.test",
            )
            manifest = validate_projection(projection)
            self.assertEqual(manifest["cname"], "comparison.example.test")
            self.assertEqual(
                (projection / "CNAME").read_text(encoding="utf-8"),
                "comparison.example.test\n",
            )
            with self.assertRaisesRegex(PagesBuildError, "same root-level hostname"):
                self.build(
                    Path(directory),
                    "mismatch",
                    canonical_origin="https://different.example.test/",
                    cname="comparison.example.test",
                )

    def test_manifest_identity_fields_fail_closed_under_mutation(self) -> None:
        mutations = (
            ("manifestVersion", "2.0.0", "requires version"),
            ("projectionOwner", "adjacent-builder", "released builder owner"),
            ("fileScope", "selected files", "released file-scope statement"),
            ("sourceStanding", "accepted_enough", "declared source standing"),
        )
        with tempfile.TemporaryDirectory(prefix="comparative-pages-") as directory:
            parent = Path(directory)
            for field, value, message in mutations:
                with self.subTest(field=field):
                    projection = self.build(parent, field)
                    update_manifest_field(projection, field, value)
                    with self.assertRaisesRegex(PagesBuildError, message):
                        validate_projection(projection)

    def test_every_html_canonical_is_owned_by_the_manifest_origin(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-") as directory:
            parent = Path(directory)
            for relative in (
                "index.html",
                "data-use.html",
                "reports/golden-specimen/comparison.html",
                "reports/reference/comparison.html",
            ):
                with self.subTest(relative=relative):
                    projection = self.build(
                        parent,
                        relative.replace("/", "-"),
                    )
                    document_path = projection / relative
                    document = document_path.read_text(encoding="utf-8")
                    canonical = (
                        DEFAULT_CANONICAL_ORIGIN
                        if relative == "index.html"
                        else DEFAULT_CANONICAL_ORIGIN + relative
                    )
                    self.assertIn(f'href="{canonical}"', document)
                    document_path.write_text(
                        document.replace(
                            f'href="{canonical}"',
                            'href="https://mismatch.example.test/"',
                            1,
                        ),
                        encoding="utf-8",
                    )
                    update_manifest_identity(projection, relative)
                    with self.assertRaisesRegex(
                        PagesBuildError,
                        "manifest-owned canonical URL",
                    ):
                        validate_projection(projection)

    def test_manifest_origin_cname_and_report_digest_agree_with_outputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-") as directory:
            parent = Path(directory)
            projection = self.build(parent, "origin")
            update_manifest_field(
                projection,
                "canonicalOrigin",
                "https://different.example.test/",
            )
            with self.assertRaisesRegex(
                PagesBuildError,
                "manifest-owned canonical URL",
            ):
                validate_projection(projection)

            projection = self.build(
                parent,
                "cname",
                canonical_origin="https://comparison.example.test/",
                cname="comparison.example.test",
            )
            update_manifest_field(
                projection,
                "canonicalOrigin",
                "https://different.example.test/",
            )
            with self.assertRaisesRegex(PagesBuildError, "same root-level hostname"):
                validate_projection(projection)

            projection = self.build(parent, "digest")
            update_manifest_field(projection, "reportDigest", "sha256:" + "0" * 64)
            with self.assertRaisesRegex(
                PagesBuildError,
                "reference comparison digest requires the validated runtime report",
            ):
                validate_projection(projection)

            projection = self.build(parent, "golden-digest")
            update_manifest_field(
                projection,
                "goldenSpecimenReportDigest",
                "sha256:" + "0" * 64,
            )
            with self.assertRaisesRegex(
                PagesBuildError,
                "Golden Specimen comparison digest requires the validated runtime report",
            ):
                validate_projection(projection)

    def test_relative_link_and_responsive_contracts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-") as directory:
            parent = Path(directory)
            projection = self.build(parent, "broken-link")
            index_path = projection / "index.html"
            index_path.write_text(
                index_path.read_text(encoding="utf-8").replace(
                    "data-use.html", "missing.html", 1
                ),
                encoding="utf-8",
            )
            update_manifest_identity(projection, "index.html")
            with self.assertRaisesRegex(PagesBuildError, "unresolved projection link"):
                validate_projection(projection)

            projection = self.build(parent, "broken-layout")
            css_path = projection / "assets/site.css"
            css_path.write_text(
                css_path.read_text(encoding="utf-8").replace(
                    "@media (max-width: 52rem)", "@media (max-width: 1rem)", 1
                ),
                encoding="utf-8",
            )
            update_manifest_identity(projection, "assets/site.css")
            with self.assertRaisesRegex(PagesBuildError, "narrow and bounded"):
                validate_projection(projection)

    def test_builder_preserves_existing_output_and_rejects_partial_revisions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-") as directory:
            parent = Path(directory)
            self.build(parent, "site")
            with self.assertRaisesRegex(PagesBuildError, "fresh destination"):
                self.build(parent, "site")
            with self.assertRaisesRegex(PagesBuildError, "40-character Git SHA"):
                ValidationFixtureSourceProof("abc123")
            with self.assertRaisesRegex(PagesBuildError, "structured .*source proof"):
                build_projection(
                    ROOT,
                    parent / "unproved",
                    source_proof=REVISION,  # type: ignore[arg-type]
                )

    def test_command_source_boundary_requires_clean_exact_head(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-git-") as directory:
            repository = initialize_git_repository(Path(directory), "repository")
            revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            proof = clean_source_revision(
                repository,
                expected_revision=revision,
            )
            self.assertEqual(proof.revision, revision)
            with self.assertRaisesRegex(PagesBuildError, "differs"):
                clean_source_revision(
                    repository,
                    expected_revision="b" * 40,
                )
            (repository / "source.txt").write_text("active\n", encoding="utf-8")
            with self.assertRaisesRegex(PagesBuildError, "differs from exact HEAD"):
                clean_source_revision(repository)

    def test_verified_clean_proof_reobserves_worktree_state_at_build_entry(self) -> None:
        cases = ("untracked", "tracked", "head")
        with tempfile.TemporaryDirectory(prefix="comparative-pages-proof-") as directory:
            parent = Path(directory)
            for case in cases:
                with self.subTest(case=case):
                    repository = initialize_git_repository(parent, f"repository-{case}")
                    proof = clean_source_revision(repository)
                    if case == "untracked":
                        (repository / "new.txt").write_text("new\n", encoding="utf-8")
                        message = "clean worktree"
                    elif case == "tracked":
                        (repository / "source.txt").write_text(
                            "changed\n",
                            encoding="utf-8",
                        )
                        message = "differs from exact HEAD"
                    else:
                        (repository / "source.txt").write_text(
                            "next revision\n",
                            encoding="utf-8",
                        )
                        subprocess.run(
                            ["git", "add", "source.txt"],
                            cwd=repository,
                            check=True,
                        )
                        subprocess.run(
                            ["git", "commit", "--quiet", "-m", "advance source"],
                            cwd=repository,
                            check=True,
                        )
                        message = "HEAD differs"
                    with self.assertRaisesRegex(PagesBuildError, message):
                        build_projection(
                            repository,
                            parent / f"output-{case}",
                            source_proof=proof,
                        )

    def test_verified_clean_proof_is_bound_to_one_resolved_worktree(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-proof-") as directory:
            parent = Path(directory)
            source = initialize_git_repository(parent, "source")
            proof = clean_source_revision(source)
            receiver = parent / "receiver"
            subprocess.run(
                ["git", "clone", "--quiet", str(source), str(receiver)],
                check=True,
            )
            with self.assertRaisesRegex(PagesBuildError, "different Git worktree"):
                build_projection(
                    receiver,
                    parent / "output-cross-root",
                    source_proof=proof,
                )

    def test_source_root_and_origin_match_the_claimed_repository(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-identity-") as directory:
            parent = Path(directory)
            repository = initialize_git_repository(parent, "repository")
            nested = repository / "nested"
            nested.mkdir()
            with self.assertRaisesRegex(PagesBuildError, "Git worktree root"):
                clean_source_revision(nested)

            adjacent = initialize_git_repository(
                parent,
                "adjacent",
                origin="https://github.com/driftframestudios/adjacent-evidence.git",
            )
            with self.assertRaisesRegex(PagesBuildError, "origin differs"):
                clean_source_revision(adjacent)

    def test_caller_git_redirection_and_config_are_sanitized(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-git-env-") as directory:
            parent = Path(directory)
            repository = initialize_git_repository(parent, "repository")
            decoy = initialize_git_repository(
                parent,
                "decoy",
                origin="https://github.com/driftframestudios/decoy.git",
            )
            caller_config = parent / "caller.gitconfig"
            caller_config.write_text(
                "[remote \"origin\"]\n"
                "\turl = https://github.com/driftframestudios/redirected.git\n",
                encoding="utf-8",
            )
            expected_revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            with patch.dict(
                os.environ,
                {
                    "GIT_DIR": str(decoy / ".git"),
                    "GIT_WORK_TREE": str(decoy),
                    "GIT_CONFIG": str(caller_config),
                },
                clear=False,
            ):
                proof = clean_source_revision(repository)
            self.assertEqual(proof.revision, expected_revision)
            self.assertEqual(proof.repository_url, DEFAULT_REPOSITORY_URL)

    def test_masked_and_divergent_index_state_returns_to_reconciliation(self) -> None:
        cases = (
            ("assume-unchanged", "--assume-unchanged"),
            ("skip-worktree", "--skip-worktree"),
        )
        with tempfile.TemporaryDirectory(prefix="comparative-pages-index-") as directory:
            parent = Path(directory)
            for name, flag in cases:
                with self.subTest(name=name):
                    repository = initialize_git_repository(parent, name)
                    subprocess.run(
                        ["git", "update-index", flag, "source.txt"],
                        cwd=repository,
                        check=True,
                    )
                    with self.assertRaisesRegex(PagesBuildError, "masked index flags"):
                        clean_source_revision(repository)

            repository = initialize_git_repository(parent, "staged")
            (repository / "source.txt").write_text("staged\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "source.txt"],
                cwd=repository,
                check=True,
            )
            with self.assertRaisesRegex(PagesBuildError, "index differs"):
                clean_source_revision(repository)

    def test_worktree_executable_mode_matches_the_head_blob(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-mode-") as directory:
            parent = Path(directory)
            repository = initialize_git_repository(parent, "repository")
            os.chmod(repository / "source.txt", 0o755)
            with self.assertRaisesRegex(PagesBuildError, "executable mode"):
                clean_source_revision(repository)

            executable = initialize_git_repository(parent, "executable")
            os.chmod(executable / "source.txt", 0o755)
            subprocess.run(
                ["git", "add", "source.txt"],
                cwd=executable,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "--quiet", "-m", "make source executable"],
                cwd=executable,
                check=True,
            )
            subprocess.run(
                ["git", "config", "core.fileMode", "false"],
                cwd=executable,
                check=True,
            )
            os.chmod(executable / "source.txt", 0o650)
            with self.assertRaisesRegex(PagesBuildError, "executable mode"):
                clean_source_revision(executable)

    def test_source_read_rejects_a_fifo_without_waiting_for_a_writer(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("FIFO creation is unavailable")
        with tempfile.TemporaryDirectory(prefix="comparative-pages-source-kind-") as directory:
            repository = initialize_git_repository(Path(directory), "repository")
            (repository / "source.txt").unlink()
            os.mkfifo(repository / "source.txt")
            with self.assertRaisesRegex(PagesBuildError, "regular file bytes"):
                clean_source_revision(repository)

    def test_source_tree_requires_regular_head_blobs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-source-kind-") as directory:
            repository = initialize_git_repository(Path(directory), "repository")
            (repository / "linked-source.txt").symlink_to("source.txt")
            subprocess.run(
                ["git", "add", "linked-source.txt"],
                cwd=repository,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "--quiet", "-m", "add linked source"],
                cwd=repository,
                check=True,
            )
            with self.assertRaisesRegex(PagesBuildError, "regular HEAD blobs"):
                clean_source_revision(repository)

    def test_pages_output_stays_outside_source_and_matches_proof_origin(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-separation-") as directory:
            parent = Path(directory)
            repository = initialize_git_repository(parent, "repository")
            proof = clean_source_revision(repository)
            with self.assertRaisesRegex(PagesBuildError, "separate directory trees"):
                build_projection(
                    repository,
                    repository / ".artifacts/pages",
                    source_proof=proof,
                )
            with self.assertRaisesRegex(PagesBuildError, "same repository identity"):
                build_projection(
                    repository,
                    parent / "wrong-links",
                    source_proof=proof,
                    repository_url="https://github.com/driftframestudios/adjacent-evidence",
                )

            linked = parent / "linked"
            subprocess.run(
                ["git", "worktree", "add", "--quiet", "--detach", str(linked), "HEAD"],
                cwd=repository,
                check=True,
            )
            linked_proof = clean_source_revision(linked)
            for name, protected in (
                ("private", linked_proof.repository_identity.git_directory),
                ("common", linked_proof.repository_identity.common_directory),
            ):
                with self.subTest(name=name):
                    with self.assertRaisesRegex(
                        PagesBuildError,
                        "Git administration.*separate directory trees",
                    ):
                        build_projection(
                            linked,
                            protected / "pages-output",
                            source_proof=linked_proof,
                        )

    def test_projection_validation_rejects_symlinks_and_special_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-artifact-") as directory:
            parent = Path(directory)
            projection = self.build(parent, "linked")
            outside = parent / "outside.css"
            outside.write_text("body {}\n", encoding="utf-8")
            stylesheet = projection / "assets/site.css"
            stylesheet.unlink()
            stylesheet.symlink_to(outside)
            with self.assertRaisesRegex(PagesBuildError, "regular files and directories"):
                validate_projection(projection)

            if hasattr(os, "mkfifo"):
                projection = self.build(parent, "special")
                os.mkfifo(projection / "pending.pipe")
                with self.assertRaisesRegex(
                    PagesBuildError,
                    "regular files and directories",
                ):
                    validate_projection(projection)

    def test_verified_build_uses_commit_bytes_and_rechecks_before_acceptance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-commit-") as directory:
            parent = Path(directory)
            repository = initialize_publication_repository(parent, "repository")
            proof = clean_source_revision(repository)
            output = parent / "accepted"
            manifest = build_projection(repository, output, source_proof=proof)
            self.assertEqual(manifest["sourceStanding"], "clean_exact_revision")
            self.assertEqual(manifest["sourceRevision"], proof.revision)
            validate_projection(output)

            repository = initialize_publication_repository(parent, "artifact-mutating")
            proof = clean_source_revision(repository)
            output = parent / "artifact-held"
            outside = parent / "outside.css"
            outside.write_text("body {}\n", encoding="utf-8")
            original_worker = pages_builder._run_materialized_worker

            def replace_artifact(*args: object, **kwargs: object) -> dict[str, object]:
                result = original_worker(*args, **kwargs)
                output_root = args[1]
                self.assertIsInstance(output_root, Path)
                stylesheet = output_root / "assets/site.css"
                stylesheet.unlink()
                stylesheet.symlink_to(outside)
                return result

            with patch.object(
                pages_builder,
                "_run_materialized_worker",
                replace_artifact,
            ):
                with self.assertRaisesRegex(
                    PagesBuildError,
                    "regular files and directories",
                ):
                    build_projection(repository, output, source_proof=proof)
            self.assertFalse(output.exists())

            repository = initialize_publication_repository(parent, "mutating")
            proof = clean_source_revision(repository)
            output = parent / "held"
            source_input = repository / "specification/comparison-profile.json"
            original_worker = pages_builder._run_materialized_worker

            def mutate_source(*args: object, **kwargs: object) -> dict[str, object]:
                result = original_worker(*args, **kwargs)
                source_input.write_text("{}\n", encoding="utf-8")
                return result

            with patch.object(
                pages_builder,
                "_run_materialized_worker",
                mutate_source,
            ):
                with self.assertRaisesRegex(PagesBuildError, "differs from exact HEAD"):
                    build_projection(repository, output, source_proof=proof)
            self.assertFalse(output.exists())
            self.assertFalse(
                any(path.name.startswith(".held-build-") for path in parent.iterdir())
            )
            self.assertFalse(
                any(
                    path.name.startswith(".comparative-source-")
                    for path in parent.iterdir()
                )
            )

    def test_verified_build_ignores_untracked_timestamp_valid_bytecode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-bytecode-") as directory:
            parent = Path(directory)
            repository = initialize_publication_repository(parent, "repository")
            publication = repository / "src/comparative_evidence/publication.py"
            authentic = publication.read_text(encoding="utf-8")
            altered = authentic.replace("MAPS EVALS", "FAKE EVALS", 1)
            self.assertEqual(len(authentic), len(altered))
            staged_source = parent / "publication.py"
            staged_source.write_text(altered, encoding="utf-8")
            source_status = publication.stat()
            os.utime(
                staged_source,
                ns=(source_status.st_atime_ns, source_status.st_mtime_ns),
            )
            bytecode = (
                publication.parent
                / "__pycache__"
                / f"publication.{sys.implementation.cache_tag}.pyc"
            )
            bytecode.parent.mkdir()
            py_compile.compile(
                str(staged_source),
                cfile=str(bytecode),
                dfile=str(publication),
                doraise=True,
                invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP,
            )
            status = subprocess.run(
                ["git", "status", "--porcelain=v1", "--untracked-files=all"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertEqual(status, "")
            revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            output = parent / "output"
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    str(repository / "tools/build_pages.py"),
                    "--source-revision",
                    revision,
                    "--output",
                    str(output),
                ],
                cwd=repository,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn(MAPS_CANARY, index)
            self.assertNotIn("FAKE EVALS", index)

    def test_command_repository_url_binds_origin_and_generated_links(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-pages-cli-origin-") as directory:
            parent = Path(directory)
            repository_url = (
                "https://github.com/driftframestudios/comparative-receiver"
            )
            repository = initialize_publication_repository(
                parent,
                "repository",
                origin=repository_url + ".git",
            )
            revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            output = parent / "output"
            result = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    str(repository / "tools/build_pages.py"),
                    "--source-revision",
                    revision,
                    "--repository-url",
                    repository_url,
                    "--output",
                    str(output),
                ],
                cwd=repository,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads(
                (output / MANIFEST_PATH).read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["repositoryUrl"], repository_url)
            index = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn(f"{repository_url}/blob/{revision}/", index)

    def test_personal_attribution_uses_only_approved_carriers(self) -> None:
        authors = (ROOT / "AUTHORS").read_text(encoding="utf-8")
        marker = "authored by "
        self.assertIn(marker, authors)
        personal_name = authors.split(marker, 1)[1].split(" and\n", 1)[0]
        self.assertTrue(personal_name.strip())
        self.assertIn(personal_name, PUBLIC_ATTRIBUTION)
        approved_carriers = {
            ROOT / "AUTHORS",
            ROOT / "src/comparative_evidence/publication.py",
        }
        for path in sorted(ROOT.rglob("*")):
            if (
                not path.is_file()
                or path in approved_carriers
                or any(part in {".git", "__pycache__", ".artifacts"} for part in path.parts)
                or path.suffix in {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".pdf"}
            ):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            self.assertNotIn(personal_name, content, str(path.relative_to(ROOT)))


if __name__ == "__main__":
    unittest.main()
