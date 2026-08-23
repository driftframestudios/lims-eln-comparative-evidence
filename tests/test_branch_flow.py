"""Regression tests for comparator branch coordinates."""

from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "comparator_check_branch_flow",
    ROOT / "tools" / "check_branch_flow.py",
)
assert SPEC and SPEC.loader
check_branch_flow = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = check_branch_flow
SPEC.loader.exec_module(check_branch_flow)


def workflow_trigger_keys(workflow: str) -> set[str]:
    """Read the exact top-level event keys from a conventionally formatted workflow."""
    lines = workflow.splitlines()
    start = lines.index("on:") + 1
    triggers: set[str] = set()
    for line in lines[start:]:
        if line and not line.startswith(" "):
            break
        match = re.fullmatch(r"""  ["']?([A-Za-z0-9_-]+)["']?:.*""", line)
        if match:
            triggers.add(match.group(1))
    return triggers


def runner_job_blocks(workflow: str) -> dict[str, str]:
    """Return each job block that allocates a runner."""
    lines = workflow.splitlines()
    start = lines.index("jobs:") + 1
    job_starts = [
        (index, match.group(1))
        for index in range(start, len(lines))
        if (match := re.fullmatch(r"  ([A-Za-z0-9_-]+):", lines[index]))
    ]
    blocks: dict[str, str] = {}
    for position, (index, name) in enumerate(job_starts):
        end = (
            job_starts[position + 1][0]
            if position + 1 < len(job_starts)
            else len(lines)
        )
        block = "\n".join(lines[index:end])
        if re.search(r"(?m)^    runs-on:", block):
            blocks[name] = block
    return blocks


class BranchFlowTests(unittest.TestCase):
    def invoke(self, base: str, head: str, author: str) -> tuple[int, str]:
        output = StringIO()
        with redirect_stdout(output):
            result = check_branch_flow.main(
                ["--base", base, "--head", head, "--author", author]
            )
        return result, output.getvalue()

    def test_non_pull_request_and_partial_coordinates(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(0, check_branch_flow.main([]))
        self.assertIn("non-pull-request", output.getvalue())
        self.assertEqual(
            2,
            self.invoke("", "release/0.3.0", "contributor")[0],
        )

    def test_dependabot_requires_identity_and_target(self) -> None:
        head = "dependabot/github_actions/actions/checkout-5.0.0"
        self.assertEqual(0, self.invoke("main", head, "dependabot[bot]")[0])
        self.assertEqual(1, self.invoke("main", head, "contributor")[0])
        self.assertEqual(1, self.invoke("release/0.3.0", head, "dependabot[bot]")[0])

    def test_renovate_identity_is_exact(self) -> None:
        result, output = self.invoke(
            "develop", "renovate/github-actions-minor", "renovate[bot]"
        )
        self.assertEqual(0, result)
        self.assertIn("Renovate branch", output)
        self.assertEqual(
            1,
            self.invoke(
                "develop",
                "renovate/github-actions-minor",
                "self-hosted-renovate[bot]",
            )[0],
        )

    def test_malformed_automation_path_is_rejected(self) -> None:
        result, output = self.invoke(
            "main",
            "dependabot/github_actions/actions/../release",
            "dependabot[bot]",
        )
        self.assertEqual(1, result)
        self.assertIn("outside the branch naming contract", output)

    def test_dependency_activation_template_matches_branch_grammar(self) -> None:
        config = (ROOT / ".github" / "dependabot.manual.yml").read_text(
            encoding="utf-8"
        )
        self.assertFalse((ROOT / ".github" / "dependabot.yml").exists())
        self.assertIn("Activation template:", config)
        configured = {
            item.replace("-", "_")
            for item in re.findall(
                r"^\s*-\s+package-ecosystem:\s*[\"']?([a-z0-9-]+)",
                config,
                flags=re.MULTILINE,
            )
        }
        self.assertEqual(check_branch_flow.DEPENDABOT_BRANCH_ECOSYSTEMS, configured)
        self.assertNotIn("pull-request-branch-name:", config)
        self.assertEqual(
            1,
            self.invoke(
                "main",
                "dependabot/pip/urllib3-3.0.0",
                "dependabot[bot]",
            )[0],
        )

    def test_feature_branch_routes_through_develop(self) -> None:
        head = "feature/comparison-profile"
        self.assertEqual(0, self.invoke("develop", head, "contributor")[0])
        self.assertEqual(1, self.invoke("main", head, "contributor")[0])

    def test_remote_proof_uses_human_cued_activation_boundary(self) -> None:
        workflow_directory = ROOT / ".github" / "workflows"
        workflow_paths = sorted(
            [*workflow_directory.glob("*.yml"), *workflow_directory.glob("*.yaml")]
        )
        self.assertEqual(["verify.yml"], [path.name for path in workflow_paths])
        workflow = workflow_paths[0].read_text(encoding="utf-8")
        self.assertFalse(
            (ROOT / ".github" / "workflows" / "branch-policy.yml").exists()
        )
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertEqual({"workflow_dispatch"}, workflow_trigger_keys(workflow))
        self.assertIn("confirm_run:", workflow)
        self.assertIn("vars.ENABLE_GITHUB_ACTIONS == 'true'", workflow)
        self.assertIn("inputs.confirm_run", workflow)
        self.assertIn("retain_comparison:", workflow)
        self.assertIn("retention-days: 1", workflow)
        self.assertIn("timeout-minutes: 10", workflow)
        self.assertIn("persist-credentials: false", workflow)
        jobs = runner_job_blocks(workflow)
        self.assertTrue(jobs)
        for name, block in jobs.items():
            with self.subTest(job=name):
                gate = re.search(r"(?m)^    if:\s*(.+)$", block)
                self.assertIsNotNone(gate)
                assert gate is not None
                self.assertIn("vars.ENABLE_GITHUB_ACTIONS == 'true'", gate.group(1))
                self.assertIn("inputs.confirm_run", gate.group(1))

    def test_control_surfaces_have_explicit_review_ownership(self) -> None:
        owners = (ROOT / "CODEOWNERS").read_text(encoding="utf-8")
        for surface in (
            "/.github/workflows/",
            "/.github/dependabot.manual.yml",
            "/tools/check_branch_flow.py",
            "/tools/check_artifacts.py",
            "/tests/test_branch_flow.py",
            "/machine-node.json",
            "/first-receipt.json",
            "/COORDINATION-HORIZON.json",
            "/src/comparative_evidence/simulated_closure.py",
            "/schemas/simulated-closure-bundle.schema.json",
            "/fixtures/simulated-closures/",
        ):
            with self.subTest(surface=surface):
                self.assertIn(surface, owners)


    def test_stable_comparative_context_fails_closed_on_matrix_result(self):
        workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("\n  comparative-validation:\n", workflow)
        self.assertIn(
            "if: ${{ always() && vars.ENABLE_GITHUB_ACTIONS == 'true' && inputs.confirm_run }}",
            workflow,
        )
        self.assertIn('test "$TEST_AND_REPORT_RESULT" = "success"', workflow)
        self.assertNotIn("ubuntu-latest", workflow)
        self.assertGreaterEqual(workflow.count("runs-on: ubuntu-24.04"), 2)
        self.assertIn("fail-fast: false", workflow)


if __name__ == "__main__":
    unittest.main()
