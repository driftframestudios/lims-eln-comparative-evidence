"""Material contracts for the copy-local collaboration workbench."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "comparative_validate_repository",
    ROOT / "tools" / "validate_repository.py",
)
assert SPEC and SPEC.loader
validation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validation
SPEC.loader.exec_module(validation)


class CollaborationWorkbenchTests(unittest.TestCase):
    def copy_workbench(self, destination: Path) -> None:
        shutil.copytree(ROOT / ".agents", destination / ".agents")
        shutil.copy2(ROOT / "README.md", destination / "README.md")
        shutil.copy2(ROOT / "AGENTS.md", destination / "AGENTS.md")

    def copy_living_carriers(self, destination: Path) -> None:
        shutil.copy2(
            ROOT / "COORDINATION-HORIZON.json",
            destination / "COORDINATION-HORIZON.json",
        )
        shutil.copy2(ROOT / "first-receipt.json", destination / "first-receipt.json")
        shutil.copy2(ROOT / "machine-node.json", destination / "machine-node.json")
        (destination / "release").mkdir()
        shutil.copy2(
            ROOT / "release/repository-role.json",
            destination / "release/repository-role.json",
        )

    def test_copy_local_workbench_has_exact_lineage_and_routes(self) -> None:
        self.assertEqual([], validation.validate_collaboration_workbench())
        self.assertEqual(
            {
                "contextual-jargon-scan",
                "deterministic-comparison-report-projection",
                "repository-reentry",
                "source-authority-mapping",
            },
            {
                validation.parse_skill_source(ROOT / relative)[0]["name"]
                for relative in validation.PUBLIC_POSSIBLE_SKILL_METADATA
            },
        )
        self.assertTrue(
            all(
                validation.parse_skill_source(ROOT / relative)[0]["source_band"]
                == "public_possible"
                for relative in validation.PUBLIC_POSSIBLE_SKILL_METADATA
            )
        )

    def test_orientation_readme_graph_is_complete_and_linked(self) -> None:
        self.assertEqual([], validation.validate_orientation_readmes())
        self.assertEqual(
            {
                "README.md",
                "accepted/README.md",
                "receipts/redacted/README.md",
                "simulated-closures/README.md",
            },
            set(validation.ORIENTATION_README_CONTRACTS),
        )

    def test_orientation_heading_parser_ignores_fenced_examples(self) -> None:
        source = """# Visible\n\n```markdown\n## Example only\n```\n\n## Route\n"""
        self.assertEqual(
            ["# Visible", "## Route"],
            validation._markdown_headings(source),
        )

    def test_same_document_readme_fragment_must_resolve(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-readme-") as temporary:
            copy_root = Path(temporary)
            readme = copy_root / "README.md"
            readme.write_text(
                "# Orientation\n\n[Missing route](#missing-self-fragment)\n",
                encoding="utf-8",
            )
            self.assertEqual(
                [
                    "README.md link fragment is absent: "
                    "#missing-self-fragment"
                ],
                validation._markdown_link_findings(readme, copy_root),
            )

    def test_upstream_lineage_drift_is_visible(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-workbench-") as temporary:
            copy_root = Path(temporary)
            self.copy_workbench(copy_root)
            target = copy_root / ".agents/skills/repository-reentry/SKILL.md"
            source = target.read_text(encoding="utf-8")
            target.write_text(
                source.replace(
                    "0c023343e46cd9b1333a63c2d509787352fbad14",
                    "f" * 40,
                    1,
                ),
                encoding="utf-8",
            )
            findings = validation.validate_collaboration_workbench(copy_root)
            self.assertTrue(any("metadata differs" in item for item in findings))

    def test_native_projection_skill_carries_report_and_publication_boundaries(self) -> None:
        skill = (
            ROOT
            / ".agents/skills/deterministic-comparison-report-projection/SKILL.md"
        ).read_text(encoding="utf-8")
        for material_rule in (
            "JSON and HTML are semantic twins",
            "Pages preserves runtime bytes",
            "Presentation changes preserve semantic facts",
            "Evidence posture survives publication",
            "Promotion stays with its receiver",
        ):
            self.assertIn(material_rule, skill)

    def test_living_carriers_record_current_publication_and_prior_history(self) -> None:
        self.assertEqual([], validation.validate_living_publication_state())
        role = json.loads(
            (ROOT / "release/repository-role.json").read_text(encoding="utf-8")
        )
        publication = role["publication_coordinates"]
        self.assertEqual("release_observed", role["release_state"])
        self.assertEqual(
            "release_observed",
            role["promotion_coordinates"]["status"],
        )
        self.assertEqual(
            "comparison-v0.3.1",
            role["promotion_coordinates"]["prior_release"]["tag"],
        )
        self.assertEqual("published", publication["status"])
        self.assertEqual(
            role["promotion_coordinates"]["release_subject"]["commit_oid"],
            publication["release_subject_commit_oid"],
        )
        self.assertEqual(
            validation.ACCEPTED_MAIN_SOURCE_REVISION,
            publication["source_revision"],
        )
        self.assertEqual(
            validation.ACCEPTED_DOCS_REVISION,
            publication["docs_revision"],
        )
        self.assertEqual(
            validation.ACCEPTED_PROJECTION_MANIFEST_SHA256,
            publication["projection_manifest_sha256"],
        )
        self.assertEqual(
            validation.ACCEPTED_PAGES_RUN_ID,
            publication["hosted_observation"]["pages_run_id"],
        )
        prior_publication = next(
            item["publication_coordinates"]
            for item in role["historical_external_releases"]
            if item["external_release"] == "comparison-v0.3.1"
        )
        self.assertEqual(
            validation.PRIOR_PUBLICATION_COORDINATES,
            prior_publication,
        )

    def test_source_revision_divergence_is_visible(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-publication-") as temporary:
            copy_root = Path(temporary)
            self.copy_living_carriers(copy_root)
            role_path = copy_root / "release/repository-role.json"
            role = json.loads(role_path.read_text(encoding="utf-8"))
            role["publication_coordinates"]["source_revision"] = "f" * 40
            role_path.write_text(
                json.dumps(role, indent=2) + "\n",
                encoding="utf-8",
            )
            findings = validation.validate_living_publication_state(copy_root)
            self.assertIn(
                "release role differs from the accepted public coordinates",
                findings,
            )

    def test_prior_publication_divergence_is_visible(self) -> None:
        with tempfile.TemporaryDirectory(prefix="comparative-publication-") as temporary:
            copy_root = Path(temporary)
            self.copy_living_carriers(copy_root)
            role_path = copy_root / "release/repository-role.json"
            role = json.loads(role_path.read_text(encoding="utf-8"))
            role["historical_external_releases"][0]["publication_coordinates"][
                "docs_revision"
            ] = "f" * 40
            role_path.write_text(
                json.dumps(role, indent=2) + "\n",
                encoding="utf-8",
            )
            findings = validation.validate_living_publication_state(copy_root)
            self.assertIn(
                "release role must retain the complete 0.3.1 publication",
                findings,
            )


if __name__ == "__main__":
    unittest.main()
