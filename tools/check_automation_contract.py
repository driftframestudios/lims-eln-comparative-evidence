#!/usr/bin/env python3
"""Validate the hosted-automation YAML through a dependency-free semantic subset."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
PULL_REQUEST_WORKFLOW = Path(".github/workflows/pull-request.yml")
MANUAL_FULL_PROOF_WORKFLOW = Path(".github/workflows/verify.yml")
DEPENDABOT_CONFIGURATION = Path(".github/dependabot.yml")

EXPECTED_DEPENDABOT_DIRECTORIES = {"github-actions": "/"}

CHECKOUT_ACTION = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON_ACTION = (
    "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
)
RELEASE_COORDINATE_COMMAND = (
    "python tools/verify_release_coordinate.py --require-observed"
)
MANUAL_VALIDATION_JOB = "comparative-validation"


class AutomationContractError(ValueError):
    """The automation source exceeds or differs from the admitted contract."""


@dataclass(frozen=True)
class _YamlLine:
    indent: int
    content: str
    number: int


def _error(source: str, message: str, line: _YamlLine | None = None) -> None:
    coordinate = f"{source}:{line.number}" if line is not None else source
    raise AutomationContractError(f"{coordinate}: {message}")


def _tokenize_yaml(text: str, source: str) -> list[_YamlLine]:
    lines: list[_YamlLine] = []
    for number, raw_line in enumerate(text.splitlines(), start=1):
        if "\t" in raw_line:
            _error(source, "restricted YAML rejects tab characters", _YamlLine(0, raw_line, number))
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = _YamlLine(indent, raw_line[indent:], number)
        if indent % 2:
            _error(source, "indentation must use two-space levels", line)
        if line.content in {"---", "..."}:
            _error(source, "document markers are outside the restricted subset", line)
        if " #" in line.content:
            _error(source, "inline comments are outside the restricted subset", line)
        lines.append(line)
    if not lines:
        _error(source, "document must contain one mapping")
    if lines[0].indent != 0:
        _error(source, "document must begin at indentation zero", lines[0])
    return lines


def _split_mapping_entry(content: str, source: str, line: _YamlLine) -> tuple[str, str]:
    match = re.fullmatch(r"([A-Za-z0-9_-]+):(.*)", content)
    if match is None:
        _error(source, "restricted YAML requires a plain mapping key", line)
    assert match is not None
    return match.group(1), match.group(2).strip()


def _parse_scalar(raw: str, source: str, line: _YamlLine) -> object:
    if raw.startswith(("|", ">", "&", "*", "!", "[", "{")):
        _error(source, "scalar form is outside the restricted subset", line)
    if "#" in raw:
        _error(source, "unquoted comment markers are outside the restricted subset", line)
    if raw.startswith('"'):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            _error(source, f"invalid double-quoted scalar: {error.msg}", line)
        if not isinstance(value, str):
            _error(source, "double-quoted scalars must contain strings", line)
        return value
    if raw.startswith("'"):
        if len(raw) < 2 or not raw.endswith("'"):
            _error(source, "invalid single-quoted scalar", line)
        return raw[1:-1].replace("''", "'")
    if raw in {"true", "false"}:
        return raw == "true"
    if raw == "null":
        return None
    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)", raw):
        return int(raw)
    if not raw or ": " in raw:
        _error(source, "plain scalar is outside the restricted subset", line)
    return raw


def _parse_mapping_entry(
    lines: list[_YamlLine],
    index: int,
    indent: int,
    target: dict[str, object],
    source: str,
    *,
    content: str | None = None,
) -> int:
    line = lines[index]
    key, raw_value = _split_mapping_entry(
        line.content if content is None else content,
        source,
        line,
    )
    if key in target:
        _error(source, f"duplicate mapping key {key!r}", line)
    index += 1
    if raw_value:
        target[key] = _parse_scalar(raw_value, source, line)
        return index
    if index >= len(lines) or lines[index].indent <= indent:
        _error(source, f"mapping key {key!r} requires a nested value", line)
    if lines[index].indent != indent + 2:
        _error(source, f"mapping key {key!r} requires one nested indentation level", lines[index])
    target[key], index = _parse_block(lines, index, indent + 2, source)
    return index


def _parse_mapping(
    lines: list[_YamlLine], index: int, indent: int, source: str
) -> tuple[dict[str, object], int]:
    result: dict[str, object] = {}
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            _error(source, "unexpected nested mapping content", line)
        if line.content.startswith("- "):
            _error(source, "mapping and sequence entries cannot share one level", line)
        index = _parse_mapping_entry(lines, index, indent, result, source)
    return result, index


def _parse_sequence(
    lines: list[_YamlLine], index: int, indent: int, source: str
) -> tuple[list[object], int]:
    result: list[object] = []
    while index < len(lines):
        line = lines[index]
        if line.indent < indent:
            break
        if line.indent > indent:
            _error(source, "unexpected nested sequence content", line)
        if not line.content.startswith("- "):
            _error(source, "mapping and sequence entries cannot share one level", line)
        item_text = line.content[2:].strip()
        if not item_text:
            _error(source, "empty sequence items are outside the restricted subset", line)
        if re.fullmatch(r"[A-Za-z0-9_-]+:.*", item_text):
            item: dict[str, object] = {}
            map_indent = indent + 2
            index = _parse_mapping_entry(
                lines,
                index,
                map_indent,
                item,
                source,
                content=item_text,
            )
            while index < len(lines) and lines[index].indent == map_indent:
                if lines[index].content.startswith("- "):
                    _error(source, "nested list requires a mapping key", lines[index])
                index = _parse_mapping_entry(
                    lines,
                    index,
                    map_indent,
                    item,
                    source,
                )
            result.append(item)
        else:
            result.append(_parse_scalar(item_text, source, line))
            index += 1
            if index < len(lines) and lines[index].indent > indent:
                _error(source, "scalar sequence item cannot own nested content", lines[index])
    return result, index


def _parse_block(
    lines: list[_YamlLine], index: int, indent: int, source: str
) -> tuple[object, int]:
    if index >= len(lines) or lines[index].indent != indent:
        _error(source, "nested block begins at the wrong indentation")
    if lines[index].content.startswith("- "):
        return _parse_sequence(lines, index, indent, source)
    return _parse_mapping(lines, index, indent, source)


def parse_restricted_yaml(text: str, *, source: str = "<memory>") -> dict[str, object]:
    """Parse the mappings, sequences, and scalar forms used by admitted automation."""

    lines = _tokenize_yaml(text, source)
    document, index = _parse_block(lines, 0, 0, source)
    if index != len(lines):
        _error(source, "document has unconsumed content", lines[index])
    if not isinstance(document, dict):
        _error(source, "document root must be a mapping")
    return document


def _require_mapping(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AutomationContractError(f"{label} must be a mapping")
    return value


def _require_list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise AutomationContractError(f"{label} must be a sequence")
    return value


def _require_exact_keys(mapping: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(mapping) != expected:
        raise AutomationContractError(
            f"{label} keys differ: expected {sorted(expected)}, observed {sorted(mapping)}"
        )


def _require_equal(actual: object, expected: object, label: str) -> None:
    if actual != expected:
        raise AutomationContractError(
            f"{label} differs: expected {expected!r}, observed {actual!r}"
        )


def _extract_manual_validation_job(workflow_text: str) -> dict[str, object]:
    """Parse the release-coordinate job without widening the YAML subset.

    The manual workflow includes a folded command and a flow-style matrix in its
    report-producing job. Those forms remain outside this dependency-free parser's
    deliberately small grammar. The release-coordinate job uses the restricted
    grammar, so extract that owned mapping and parse it through the same semantic
    path as the pull-request workflow.
    """

    source = MANUAL_FULL_PROOF_WORKFLOW.as_posix()
    raw_lines = workflow_text.splitlines()
    jobs_lines = [index for index, line in enumerate(raw_lines) if line == "jobs:"]
    if len(jobs_lines) != 1:
        raise AutomationContractError(
            f"{source}: expected exactly one top-level jobs mapping"
        )

    jobs_start = jobs_lines[0]
    jobs_end = len(raw_lines)
    for index in range(jobs_start + 1, len(raw_lines)):
        line = raw_lines[index]
        if line and not line.startswith((" ", "#")):
            jobs_end = index
            break

    job_header = f"  {MANUAL_VALIDATION_JOB}:"
    job_lines = [
        index
        for index in range(jobs_start + 1, jobs_end)
        if raw_lines[index] == job_header
    ]
    if len(job_lines) != 1:
        raise AutomationContractError(
            f"{source}: expected exactly one {MANUAL_VALIDATION_JOB!r} job"
        )

    job_start = job_lines[0]
    job_end = jobs_end
    for index in range(job_start + 1, jobs_end):
        line = raw_lines[index]
        if line and not line.startswith(("    ", "#")):
            job_end = index
            break

    fragment = "jobs:\n" + "\n".join(raw_lines[job_start:job_end]) + "\n"
    document = parse_restricted_yaml(fragment, source=source)
    jobs = _require_mapping(document.get("jobs"), "manual workflow jobs")
    _require_exact_keys(jobs, {MANUAL_VALIDATION_JOB}, "manual workflow job fragment")
    return _require_mapping(
        jobs[MANUAL_VALIDATION_JOB],
        f"{MANUAL_VALIDATION_JOB} job",
    )


def _validate_manual_full_proof_workflow(workflow_text: str) -> None:
    job = _extract_manual_validation_job(workflow_text)
    _require_exact_keys(
        job,
        {"if", "needs", "runs-on", "timeout-minutes", "steps"},
        f"{MANUAL_VALIDATION_JOB} job",
    )
    _require_equal(
        job["if"],
        "${{ always() && vars.ENABLE_GITHUB_ACTIONS == 'true' "
        "&& inputs.confirm_run }}",
        "manual validation activation boundary",
    )
    _require_equal(job["needs"], "test-and-report", "manual validation dependency")
    _require_equal(job["runs-on"], "ubuntu-24.04", "manual validation runner")
    _require_equal(job["timeout-minutes"], 5, "manual validation timeout")

    steps = _require_list(job["steps"], "manual validation steps")
    if len(steps) != 6 or any(not isinstance(step, dict) for step in steps):
        raise AutomationContractError(
            "manual comparative-validation requires exactly six mapping steps"
        )
    require_matrix, checkout, setup, install, validate, verify_release = steps
    assert isinstance(require_matrix, dict)
    assert isinstance(checkout, dict)
    assert isinstance(setup, dict)
    assert isinstance(install, dict)
    assert isinstance(validate, dict)
    assert isinstance(verify_release, dict)

    _require_equal(
        require_matrix,
        {
            "name": "Require the complete comparative proof matrix",
            "env": {
                "TEST_AND_REPORT_RESULT": "${{ needs.test-and-report.result }}",
            },
            "run": 'test "$TEST_AND_REPORT_RESULT" = "success"',
        },
        "manual matrix-result gate",
    )
    _require_equal(
        checkout,
        {
            "uses": CHECKOUT_ACTION,
            "with": {"persist-credentials": False, "fetch-depth": 0},
        },
        "manual validation checkout",
    )
    _require_equal(
        setup,
        {
            "uses": SETUP_PYTHON_ACTION,
            "with": {"python-version": "3.13"},
        },
        "manual validation Python setup",
    )
    _require_equal(
        install,
        {
            "name": "Install released schema validation support",
            "run": 'python -m pip install --disable-pip-version-check --editable ".[validation]"',
        },
        "manual validation-support installation step",
    )
    _require_equal(
        validate,
        {
            "name": "Validate released evidence, calibration posture, and repository safety",
            "run": "python tools/validate_repository.py",
        },
        "manual aggregate validation step",
    )
    _require_equal(
        verify_release,
        {
            "name": "Verify signed release coordinate",
            "run": RELEASE_COORDINATE_COMMAND,
        },
        "manual signed-release verification step",
    )


def _validate_pull_request_workflow(document: Mapping[str, object]) -> dict[str, object]:
    _require_exact_keys(
        document,
        {"name", "on", "permissions", "concurrency", "jobs"},
        "pull-request workflow",
    )
    _require_equal(document["name"], "pull-request-proof", "workflow name")
    _require_equal(
        document["on"],
        {"pull_request": {"branches": ["develop", "main"]}},
        "workflow trigger",
    )
    _require_equal(document["permissions"], {"contents": "read"}, "workflow permissions")
    _require_equal(
        document["concurrency"],
        {
            "group": "pull-request-proof-${{ github.event.pull_request.number }}",
            "cancel-in-progress": True,
        },
        "workflow concurrency",
    )

    jobs = _require_mapping(document["jobs"], "workflow jobs")
    _require_exact_keys(jobs, {"repository-validation"}, "workflow jobs")
    job = _require_mapping(jobs["repository-validation"], "repository-validation job")
    _require_exact_keys(
        job,
        {"name", "runs-on", "timeout-minutes", "steps"},
        "repository-validation job",
    )
    _require_equal(job["name"], "Repository validation", "job name")
    _require_equal(job["runs-on"], "ubuntu-24.04", "job runner")
    _require_equal(job["timeout-minutes"], 10, "job timeout")

    steps = _require_list(job["steps"], "repository-validation steps")
    if len(steps) != 6 or any(not isinstance(step, dict) for step in steps):
        raise AutomationContractError("repository-validation requires exactly six mapping steps")
    checkout, setup, install, test, validate, verify_release = steps
    assert isinstance(checkout, dict)
    assert isinstance(setup, dict)
    assert isinstance(install, dict)
    assert isinstance(test, dict)
    assert isinstance(validate, dict)
    assert isinstance(verify_release, dict)

    _require_exact_keys(checkout, {"name", "uses", "with"}, "checkout step")
    _require_equal(checkout["name"], "Check out source", "checkout step name")
    _require_equal(checkout["uses"], CHECKOUT_ACTION, "checkout action")
    _require_equal(
        checkout["with"],
        {"persist-credentials": False, "fetch-depth": 0},
        "checkout credential persistence and history depth",
    )

    _require_exact_keys(setup, {"name", "uses", "with"}, "setup-python step")
    _require_equal(setup["name"], "Select Python", "setup-python step name")
    _require_equal(setup["uses"], SETUP_PYTHON_ACTION, "setup-python action")
    _require_equal(
        setup["with"],
        {"python-version": "3.12", "cache": ""},
        "Python setup inputs",
    )

    _require_equal(
        install,
        {
            "name": "Install validation support",
            "run": 'python -m pip install --disable-pip-version-check --editable ".[validation]"',
        },
        "validation-support installation step",
    )
    _require_equal(
        test,
        {
            "name": "Exercise comparison and admission behavior",
            "run": "python -m unittest discover -s tests -v",
        },
        "comparison behavior step",
    )
    _require_equal(
        validate,
        {
            "name": "Validate repository evidence contracts",
            "run": "python tools/validate_repository.py",
        },
        "aggregate validation step",
    )
    _require_equal(
        verify_release,
        {
            "name": "Verify signed release coordinate",
            "run": RELEASE_COORDINATE_COMMAND,
        },
        "signed-release verification step",
    )

    return {
        "pull_request_workflow": PULL_REQUEST_WORKFLOW.as_posix(),
        "pull_request_targets": ["develop", "main"],
        "pull_request_runner": "ubuntu-24.04",
        "pull_request_python": "3.12",
        "pull_request_timeout_minutes": 10,
        "pull_request_permissions": {"contents": "read"},
        "pull_request_concurrency_cancellation": True,
    }


def _validate_dependabot(document: Mapping[str, object]) -> dict[str, object]:
    _require_exact_keys(document, {"version", "updates"}, "Dependabot document")
    _require_equal(document["version"], 2, "Dependabot version")
    updates = _require_list(document["updates"], "Dependabot updates")
    if len(updates) != len(EXPECTED_DEPENDABOT_DIRECTORIES):
        raise AutomationContractError("Dependabot requires one update entry per admitted ecosystem")

    observed: set[str] = set()
    for position, value in enumerate(updates):
        update = _require_mapping(value, f"Dependabot update {position}")
        _require_exact_keys(
            update,
            {
                "package-ecosystem",
                "directory",
                "target-branch",
                "schedule",
                "open-pull-requests-limit",
                "groups",
            },
            f"Dependabot update {position}",
        )
        ecosystem = update["package-ecosystem"]
        if not isinstance(ecosystem, str) or ecosystem not in EXPECTED_DEPENDABOT_DIRECTORIES:
            raise AutomationContractError(f"Dependabot ecosystem is not admitted: {ecosystem!r}")
        if ecosystem in observed:
            raise AutomationContractError(
                f"Dependabot ecosystem appears more than once: {ecosystem}"
            )
        observed.add(ecosystem)
        _require_equal(
            update["directory"],
            EXPECTED_DEPENDABOT_DIRECTORIES[ecosystem],
            f"{ecosystem} directory",
        )
        _require_equal(update["target-branch"], "develop", f"{ecosystem} target")
        _require_equal(update["schedule"], {"interval": "monthly"}, f"{ecosystem} schedule")
        _require_equal(update["open-pull-requests-limit"], 2, f"{ecosystem} update limit")
        _require_equal(
            update["groups"],
            {
                f"{ecosystem}-minor-patch": {
                    "patterns": ["*"],
                    "update-types": ["minor", "patch"],
                }
            },
            f"{ecosystem} grouping",
        )
    if observed != set(EXPECTED_DEPENDABOT_DIRECTORIES):
        raise AutomationContractError("Dependabot ecosystem set differs from the admitted set")
    return {
        "dependabot_configuration": DEPENDABOT_CONFIGURATION.as_posix(),
        "dependabot_target": "develop",
        "dependabot_interval": "monthly",
        "dependabot_open_pull_requests_per_ecosystem": 2,
        "dependabot_grouped_update_types": ["minor", "patch"],
    }


def validate_automation_documents(
    workflow_text: str,
    dependabot_text: str,
    *,
    manual_workflow_text: str,
    declared_controls: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate source text and return the controls derived from its semantics."""

    workflow = parse_restricted_yaml(
        workflow_text,
        source=PULL_REQUEST_WORKFLOW.as_posix(),
    )
    dependabot = parse_restricted_yaml(
        dependabot_text,
        source=DEPENDABOT_CONFIGURATION.as_posix(),
    )
    _validate_manual_full_proof_workflow(manual_workflow_text)
    controls = {
        **_validate_pull_request_workflow(workflow),
        "manual_full_proof_workflow": MANUAL_FULL_PROOF_WORKFLOW.as_posix(),
        **_validate_dependabot(dependabot),
    }
    if declared_controls is not None:
        for key, actual in controls.items():
            if declared_controls.get(key) != actual:
                raise AutomationContractError(
                    f"declared automation control {key!r} differs from source: "
                    f"expected {actual!r}, observed {declared_controls.get(key)!r}"
                )
    return controls


def validate_automation_contract(
    root: Path = ROOT,
    *,
    declared_controls: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Validate the repository-owned workflow and Dependabot source files."""

    paths = (
        root / PULL_REQUEST_WORKFLOW,
        root / MANUAL_FULL_PROOF_WORKFLOW,
        root / DEPENDABOT_CONFIGURATION,
    )
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise AutomationContractError(
                f"automation contract requires a regular repository-owned file: "
                f"{path.relative_to(root)}"
            )
    return validate_automation_documents(
        (root / PULL_REQUEST_WORKFLOW).read_text(encoding="utf-8"),
        (root / DEPENDABOT_CONFIGURATION).read_text(encoding="utf-8"),
        manual_workflow_text=(root / MANUAL_FULL_PROOF_WORKFLOW).read_text(
            encoding="utf-8"
        ),
        declared_controls=declared_controls,
    )


def main() -> int:
    release = json.loads(
        (ROOT / "release" / "repository-role.json").read_text(encoding="utf-8")
    )
    controls = validate_automation_contract(
        ROOT,
        declared_controls=release["automation_controls"],
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "pull_request_jobs": 1,
                "dependabot_ecosystems": sorted(EXPECTED_DEPENDABOT_DIRECTORIES),
                "source_controls": controls,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
