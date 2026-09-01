"""Regression tests for comparator branch coordinates."""

from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
import json
from pathlib import Path
import re
import sys
import unittest

from tools.check_automation_contract import (
    AutomationContractError,
    EXPECTED_DEPENDABOT_DIRECTORIES,
    validate_automation_documents,
)


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
    def automation_documents(self) -> tuple[str, str, dict[str, object]]:
        workflow = (
            ROOT / ".github" / "workflows" / "pull-request.yml"
        ).read_text(encoding="utf-8")
        dependabot = (ROOT / ".github" / "dependabot.yml").read_text(
            encoding="utf-8"
        )
        release = json.loads(
            (ROOT / "release" / "repository-role.json").read_text(encoding="utf-8")
        )
        return workflow, dependabot, release["automation_controls"]

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
        self.assertEqual(0, self.invoke("develop", head, "dependabot[bot]")[0])
        self.assertEqual(1, self.invoke("develop", head, "contributor")[0])
        self.assertEqual(0, self.invoke("main", head, "dependabot[bot]")[0])
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

    def test_dependency_schedule_matches_branch_grammar(self) -> None:
        self.assertFalse((ROOT / ".github" / "dependabot.manual.yml").exists())
        workflow, config, declared = self.automation_documents()
        controls = validate_automation_documents(
            workflow,
            config,
            declared_controls=declared,
        )
        configured = {
            ecosystem.replace("-", "_")
            for ecosystem in EXPECTED_DEPENDABOT_DIRECTORIES
        }
        self.assertEqual(check_branch_flow.DEPENDABOT_BRANCH_ECOSYSTEMS, configured)
        self.assertEqual("develop", controls["dependabot_target"])
        self.assertEqual("monthly", controls["dependabot_interval"])
        self.assertEqual(2, controls["dependabot_open_pull_requests_per_ecosystem"])
        self.assertEqual(
            ["minor", "patch"],
            controls["dependabot_grouped_update_types"],
        )
        self.assertEqual(
            1,
            self.invoke(
                "develop",
                "dependabot/pip/urllib3-3.0.0",
                "dependabot[bot]",
            )[0],
        )

    def test_feature_branch_routes_through_develop(self) -> None:
        head = "feature/comparison-profile"
        self.assertEqual(0, self.invoke("develop", head, "contributor")[0])
        self.assertEqual(1, self.invoke("main", head, "contributor")[0])

    def test_full_proof_uses_human_cued_activation_boundary(self) -> None:
        workflow_directory = ROOT / ".github" / "workflows"
        workflow_paths = sorted(
            [*workflow_directory.glob("*.yml"), *workflow_directory.glob("*.yaml")]
        )
        self.assertEqual(
            ["pull-request.yml", "verify.yml"],
            [path.name for path in workflow_paths],
        )
        workflow = (workflow_directory / "verify.yml").read_text(encoding="utf-8")
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

    def test_pull_request_workflow_is_bounded_and_read_only(self) -> None:
        workflow, dependabot, declared = self.automation_documents()
        controls = validate_automation_documents(
            workflow,
            dependabot,
            declared_controls=declared,
        )
        self.assertEqual(["develop", "main"], controls["pull_request_targets"])
        self.assertEqual({"contents": "read"}, controls["pull_request_permissions"])
        self.assertTrue(controls["pull_request_concurrency_cancellation"])
        self.assertEqual(10, controls["pull_request_timeout_minutes"])

    def test_pull_request_contract_rejects_material_mutations(self) -> None:
        workflow, dependabot, declared = self.automation_documents()
        checkout_sha = "3d3c42e5aac5ba805825da76410c181273ba90b1"
        setup_sha = "5fda3b95a4ea91299a34e894583c3862153e4b97"
        mutations = {
            "unknown top-level key": workflow + "\nunexpected: true\n",
            "quoted permission key": workflow.replace(
                "permissions:\n",
                '"permissions":\n',
                1,
            ),
            "flow permission mapping": workflow.replace(
                "permissions:\n  contents: read",
                "permissions: {contents: read}",
            ),
            "top-level permission broadening": workflow.replace(
                "permissions:\n  contents: read",
                "permissions:\n  contents: read\n  issues: write",
            ),
            "job-level permission broadening": workflow.replace(
                "    steps:\n",
                "    permissions:\n      contents: write\n    steps:\n",
                1,
            ),
            "validation can fail open": workflow.replace(
                "      - name: Validate repository evidence contracts\n        run:",
                "      - name: Validate repository evidence contracts\n"
                "        continue-on-error: true\n        run:",
            ),
            "cancellation comment decoy": workflow.replace(
                "  cancel-in-progress: true",
                "  cancel-in-progress: false\n  # cancel-in-progress: true",
            ),
            "timeout comment decoy": workflow.replace(
                "    timeout-minutes: 10",
                "    timeout-minutes: 11\n    # timeout-minutes: 10",
            ),
            "extra runner job": workflow
            + "\n  extra-validation:\n"
            "    runs-on: ubuntu-24.04\n"
            "    timeout-minutes: 10\n"
            "    steps:\n"
            "      - name: Extra proof\n"
            "        run: python tools/validate_repository.py\n",
            "extra reusable job": workflow
            + "\n  delegated-proof:\n"
            "    uses: outside/example/.github/workflows/proof.yml@main\n",
            "anonymous action step": workflow.replace(
                "      - name: Select Python",
                "      - uses: outside/example@main\n\n      - name: Select Python",
            ),
            "unpinned action": workflow.replace(
                f"actions/checkout@{checkout_sha}",
                "actions/checkout@main",
            ),
            "unapproved action": workflow.replace(
                f"actions/setup-python@{setup_sha}",
                f"outside/setup-python@{setup_sha}",
            ),
            "wrong full action SHA with comment decoy": workflow.replace(
                f"        uses: actions/checkout@{checkout_sha}",
                "        uses: actions/checkout@0000000000000000000000000000000000000000\n"
                f"        # uses: actions/checkout@{checkout_sha}",
            ),
            "trigger drift": workflow.replace(
                "  pull_request:",
                "  pull_request_target:",
            ),
            "branch drift": workflow.replace(
                "      - develop",
                "      - release",
                1,
            ),
            "secret injection": workflow.replace(
                "    steps:\n",
                "    env:\n      CREDENTIAL: ${{ secrets.CREDENTIAL }}\n    steps:\n",
                1,
            ),
            "bracket-form secret command": workflow.replace(
                "        run: python tools/validate_repository.py",
                "        run: echo \"${{ secrets['AUTOMATION_TOKEN'] }}\"",
            ),
            "checkout credential persistence": workflow.replace(
                "          persist-credentials: false",
                "          persist-credentials: true",
            ),
        }
        for name, mutated in mutations.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AutomationContractError):
                    validate_automation_documents(
                        mutated,
                        dependabot,
                        declared_controls=declared,
                    )

    def test_dependabot_contract_rejects_material_mutations(self) -> None:
        workflow, dependabot, declared = self.automation_documents()
        mutations = {
            "quoted ecosystem key": dependabot.replace(
                "  - package-ecosystem: github-actions",
                '  - "package-ecosystem": github-actions',
            ),
            "quoted directory key": dependabot.replace(
                "    directory: /",
                '    "directory": /wrong',
                1,
            ),
            "flow schedule": dependabot.replace(
                "    schedule:\n      interval: monthly",
                "    schedule: {interval: daily}",
            ),
            "ecosystem directory": dependabot.replace(
                "  - package-ecosystem: github-actions\n    directory: /",
                "  - package-ecosystem: github-actions\n    directory: /wrong",
            ),
            "target comment decoy": dependabot.replace(
                "    target-branch: develop",
                "    target-branch: main\n#    target-branch: develop",
            ),
            "cadence comment decoy": dependabot.replace(
                "      interval: monthly",
                "      interval: daily\n#      interval: monthly",
            ),
            "limit comment decoy": dependabot.replace(
                "    open-pull-requests-limit: 2",
                "    open-pull-requests-limit: 20\n#    open-pull-requests-limit: 2",
            ),
            "pattern comment decoy": dependabot.replace(
                '          - "*"',
                '          - "actions/checkout"\n#          - "*"',
            ),
            "update-type comment decoy": dependabot.replace(
                "          - patch",
                "          - major\n#          - patch",
            ),
            "group-name drift": dependabot.replace(
                "      github-actions-minor-patch:",
                "      dependency-updates:",
            ),
            "quoted group-name drift": dependabot.replace(
                "      github-actions-minor-patch:",
                '      "dependency-updates":',
            ),
            "extra ecosystem": dependabot
            + "\n  - package-ecosystem: pip\n"
            "    directory: /wrong\n"
            "    target-branch: main\n"
            "    schedule:\n"
            "      interval: daily\n"
            "    open-pull-requests-limit: 20\n"
            "    groups:\n"
            "      pip-minor-patch:\n"
            "        patterns:\n"
            "          - \"*\"\n"
            "        update-types:\n"
            "          - minor\n"
            "          - patch\n",
            "flow extra ecosystem": dependabot
            + "\n  - {package-ecosystem: pip, directory: /wrong, "
            "target-branch: main}\n",
        }
        for name, mutated in mutations.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AutomationContractError):
                    validate_automation_documents(
                        workflow,
                        mutated,
                        declared_controls=declared,
                    )

    def test_declared_automation_controls_are_derived_from_source(self) -> None:
        workflow, dependabot, declared = self.automation_documents()
        drifted = deepcopy(declared)
        drifted["pull_request_timeout_minutes"] = 9
        with self.assertRaisesRegex(
            AutomationContractError,
            "declared automation control 'pull_request_timeout_minutes' differs",
        ):
            validate_automation_documents(
                workflow,
                dependabot,
                declared_controls=drifted,
            )

    def test_release_manifest_records_bounded_automation_source(self) -> None:
        release = json.loads(
            (ROOT / "release" / "repository-role.json").read_text(encoding="utf-8")
        )
        automation = release["automation_controls"]
        self.assertEqual(["develop", "main"], automation["pull_request_targets"])
        self.assertEqual("ubuntu-24.04", automation["pull_request_runner"])
        self.assertEqual("3.12", automation["pull_request_python"])
        self.assertEqual(10, automation["pull_request_timeout_minutes"])
        self.assertEqual({"contents": "read"}, automation["pull_request_permissions"])
        self.assertTrue(automation["pull_request_concurrency_cancellation"])
        self.assertEqual("develop", automation["dependabot_target"])
        self.assertEqual(
            {"minimum": 100, "maximum": 300},
            automation["monthly_budget_minutes"],
        )

    def test_control_surfaces_have_explicit_review_ownership(self) -> None:
        owners = (ROOT / "CODEOWNERS").read_text(encoding="utf-8")
        for surface in (
            "/.github/workflows/",
            "/.github/dependabot.yml",
            "/tools/check_automation_contract.py",
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
