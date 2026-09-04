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

    def test_living_carriers_separate_release_from_prior_public_baseline(self) -> None:
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
            validation.ACCEPTED_MAIN_SOURCE_REVISION,
            publication["source_revision"],
        )
        self.assertEqual(
            validation.ACCEPTED_DOCS_REVISION,
            publication["docs_revision"],
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


if __name__ == "__main__":
    unittest.main()
