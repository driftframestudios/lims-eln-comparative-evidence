"""Material behavior checks for the source-owned Pages projection."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from build_pages import (
    BIG_BENCH_CANARY,
    DEFAULT_CANONICAL_ORIGIN,
    MANIFEST_PATH,
    MAPS_CANARY,
    MANIFEST_FILE_SCOPE,
    MANIFEST_VERSION,
    PagesBuildError,
    PROJECTION_OWNER,
    PUBLIC_ATTRIBUTION,
    SOURCE_LINK_PATHS,
    ValidationFixtureSourceProof,
    build_projection,
    clean_source_revision,
    projection_byte_inventory,
    validate_projection,
    verify_reproducible_projections,
)
from comparative_evidence.compare import compare_synthetic_contract
from comparative_evidence.model import ObservationEnvelope, strict_json_loads
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


def initialize_git_repository(parent: Path, name: str) -> Path:
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
    (repository / "source.txt").write_text("settled\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.txt"], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "settle source"],
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
            self.assertNotIn("CNAME", inventory)
            self.assertEqual(
                set(inventory),
                {
                    ".nojekyll",
                    "assets/site.css",
                    "data-use.html",
                    "index.html",
                    "projection-manifest.json",
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
            with self.assertRaisesRegex(PagesBuildError, "validated runtime report"):
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
            with self.assertRaisesRegex(PagesBuildError, "clean worktree"):
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
                        message = "clean worktree"
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
