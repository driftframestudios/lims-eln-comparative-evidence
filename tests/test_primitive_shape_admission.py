"""Public correction routes establish primitive prerequisites before hashing."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from comparative_evidence.compare import compare_synthetic_contract
from comparative_evidence.contract_v1 import strict_json_loads
from comparative_evidence.model import EnvelopeError, ObservationEnvelope


INVALID_MEMBERS = (None, False, True, 0, 1.5, [], {}, "unrecognized-value")
PATH_FIELDS = ("required_paths", "critical_exact_paths", "declared_nondeterminism", "reportable_paths")
ENVELOPE_MESSAGES = {
    "evidence_mode": "evidence_mode requires planned, simulated, or observed",
    "assurance_stage": "assurance_stage requires a released assurance-stage value",
}
ADJUDICATION_PATH = "$.restore.observed_recovery_seconds"
ADJUDICATION_MESSAGES = {
    "direction": "requires lower_is_better or higher_is_better",
    "favorable_classification": "requires a released classification",
    "unfavorable_classification": "requires a released classification",
}


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text())


def compare_profile(profile: dict) -> dict:
    return compare_synthetic_contract(
        ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),
        ObservationEnvelope.from_dict(load("fixtures/contracts/planned-observation.json")),
        profile,
    )


def wire_copy(value: dict) -> dict:
    return strict_json_loads(json.dumps(value).encode("utf-8"))


class PrimitiveShapeAdmissionTests(unittest.TestCase):
    def assert_correction(self, document, operation, error_type, message):
        before = deepcopy(document)
        for route in (lambda value: value, wire_copy):
            with self.subTest(route=route.__name__), self.assertRaises(error_type) as caught:
                operation(route(document))
            self.assertEqual(str(caught.exception), message)
            self.assertEqual(document, before)

    def test_envelope_enum_shapes_use_the_declared_correction_family(self):
        for field, message in ENVELOPE_MESSAGES.items():
            for value in INVALID_MEMBERS:
                document = load("fixtures/contracts/planned-observation.json")
                document[field] = deepcopy(value)
                with self.subTest(field=field, value=value):
                    self.assert_correction(document, ObservationEnvelope.from_dict, EnvelopeError, message)

    def test_path_collections_admit_array_shape_before_members(self):
        for field in PATH_FIELDS:
            for value in (None, False, 0, 1.5, {}, "$.restore"):
                profile = load("specification/comparison-profile.json")
                profile[field] = deepcopy(value)
                with self.subTest(field=field, value=value):
                    self.assert_correction(profile, compare_profile, ValueError,
                                           f"{field} requires unique released result paths")

    def test_path_members_admit_text_before_uniqueness(self):
        for field in PATH_FIELDS:
            for value in INVALID_MEMBERS:
                profile = load("specification/comparison-profile.json")
                profile[field] = [deepcopy(value)]
                with self.subTest(field=field, value=value):
                    self.assert_correction(profile, compare_profile, ValueError,
                                           f"{field} requires unique released result paths")

    def test_adjudication_enum_shapes_use_field_specific_corrections(self):
        for field, suffix in ADJUDICATION_MESSAGES.items():
            for value in INVALID_MEMBERS:
                profile = load("specification/comparison-profile.json")
                profile["adjudications"][ADJUDICATION_PATH][field] = deepcopy(value)
                with self.subTest(field=field, value=value):
                    self.assert_correction(profile, compare_profile, ValueError,
                                           f"adjudication {ADJUDICATION_PATH}.{field} {suffix}")

    def test_existing_field_grammar_and_relation_precedence_is_preserved(self):
        envelope = load("fixtures/contracts/planned-observation.json")
        envelope.update(evidence_mode=[], assurance_stage={})
        self.assert_correction(envelope, ObservationEnvelope.from_dict, EnvelopeError,
                               ENVELOPE_MESSAGES["evidence_mode"])
        del envelope["observation_id"]
        self.assert_correction(envelope, ObservationEnvelope.from_dict, EnvelopeError,
                               "envelope requires fields: observation_id")
        for field in PATH_FIELDS:
            profile = load("specification/comparison-profile.json")
            profile[field] = ["$.restore", "$.restore"]
            self.assert_correction(profile, compare_profile, ValueError,
                                   f"{field} requires unique released result paths")
            profile[field] = ["$.restore..seconds"]
            self.assert_correction(profile, compare_profile, ValueError,
                                   f"{field} uses the released comparison path grammar: '$.restore..seconds'")
        profile = load("specification/comparison-profile.json")
        profile["required_paths"] = []
        profile["adjudications"][ADJUDICATION_PATH]["direction"] = []
        with self.assertRaisesRegex(ValueError, "required_paths requires every governed comparison path"):
            compare_profile(profile)
        profile = load("specification/comparison-profile.json")
        disposition = profile["adjudications"][ADJUDICATION_PATH]
        disposition.update(direction=[], favorable_classification={})
        self.assert_correction(profile, compare_profile, ValueError,
                               f"adjudication {ADJUDICATION_PATH}.direction {ADJUDICATION_MESSAGES['direction']}")
        del disposition["favorable_rationale"]
        self.assert_correction(profile, compare_profile, ValueError,
                               f"adjudication {ADJUDICATION_PATH} requires directional released fields")

    def test_retained_valid_report_identity_is_preserved(self):
        profile = load("specification/comparison-profile.json")
        baseline = compare_profile(profile)
        self.assertEqual(baseline["report_digest"],
                         "sha256:5f66ed1a3023b00bc7779f8810c0440f594dd5fe10e90a475b073eaa438f741b")
        for field in PATH_FIELDS:
            reordered = deepcopy(profile)
            reordered[field] = list(reversed(reordered[field]))
            report = compare_profile(reordered)
            self.assertEqual(report["summary"], baseline["summary"])
            self.assertEqual(report["differences"], baseline["differences"])

    def test_native_and_prepared_file_routes_preserve_accepted_bytes(self):
        native_code = """import runpy,sys
sys.path.insert(0, sys.argv.pop(1) + '/src')
sys.argv[0] = 'comparative_evidence.cli'
runpy.run_module('comparative_evidence.cli', run_name='__main__')
"""
        prepared_code = """from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1] + '/infra')
import container_entry
container_entry.produce(Path(sys.argv[2]))
"""
        cases = []
        for field, message in ENVELOPE_MESSAGES.items():
            cases.append(("fixtures/contracts/planned-observation.json", (field,), [], "EnvelopeError", message))
        for field in PATH_FIELDS:
            cases.append(("specification/comparison-profile.json", (field,), [{}], "ValueError",
                          f"{field} requires unique released result paths"))
        for field, suffix in ADJUDICATION_MESSAGES.items():
            cases.append(("specification/comparison-profile.json", ("adjudications", ADJUDICATION_PATH, field), {},
                          "ValueError", f"adjudication {ADJUDICATION_PATH}.{field} {suffix}"))
        with tempfile.TemporaryDirectory(prefix="comparative-shape-") as temporary:
            root = Path(temporary)
            prepared = root / "source"
            for relative in load("infra/container-profile.json")["files"]:
                target = prepared / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            native_output, prepared_output = root / "native", root / "prepared"
            native = [sys.executable, "-I", "-S", "-B", "-c", native_code, str(prepared),
                      "compare-synthetic-contract", "--profile", str(prepared / "specification/comparison-profile.json"),
                      "--simulation", str(prepared / "fixtures/pairs/simulation-observation.json"),
                      "--contract-candidate", str(prepared / "fixtures/contracts/planned-observation.json"),
                      "--output", str(native_output)]
            finite = [sys.executable, "-I", "-S", "-B", "-c", prepared_code, str(prepared), str(prepared_output)]
            environment = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
            for command in (native, finite):
                result = subprocess.run(command, capture_output=True, text=True, env=environment)
                self.assertEqual(result.returncode, 0, result.stderr)
            retained = {path.name: path.read_bytes() for path in native_output.iterdir()}
            self.assertEqual(retained, {path.name: path.read_bytes() for path in prepared_output.iterdir()})
            for relative, fields, value, error_type, message in cases:
                target = prepared / relative
                original = target.read_bytes()
                document = json.loads(original)
                owner = document
                for field in fields[:-1]:
                    owner = owner[field]
                owner[fields[-1]] = value
                target.write_text(json.dumps(document))
                try:
                    for route, command in (("native", native), ("prepared", finite)):
                        with self.subTest(fields=fields, route=route):
                            result = subprocess.run(command, capture_output=True, text=True, env=environment)
                            self.assertNotEqual(result.returncode, 0)
                            self.assertEqual(result.stderr.splitlines()[-1].split(": ", 1)[-1], message)
                            self.assertTrue(result.stderr.splitlines()[-1].split(": ", 1)[0].endswith(error_type))
                            self.assertEqual(retained, {path.name: path.read_bytes() for path in (root / route).iterdir()})
                finally:
                    target.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
