from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import tracemalloc
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from comparative_evidence import contract_v1
from comparative_evidence.artifact_boundary import ReportArtifactError, report_artifact_inventory
from comparative_evidence.cli import _load
from comparative_evidence.compare import compare_synthetic_contract
from comparative_evidence.legacy_json import (
    ContractBoundaryError, INPUT_BUDGET, REPORT_BUDGET, HTML_BYTES,
    RepresentationCapacityError, validate_representation,
)
from comparative_evidence.model import ObservationEnvelope
from comparative_evidence.report import write_reports


def load(relative):
    return json.loads((ROOT / relative).read_text())


class LegacyJsonBoundaryTests(unittest.TestCase):
    def assert_capacity(self, code, operation):
        with self.assertRaises(RepresentationCapacityError) as caught:
            operation()
        self.assertEqual(caught.exception.code, 'legacy_' + code)
        self.assertNotIn('sensitive-value', str(caught.exception))

    def test_retained_input_fixtures_fit(self):
        for path in sorted((ROOT / 'fixtures').rglob('*.json')):
            with self.subTest(path=path.relative_to(ROOT)):
                document = _load(path)
                validate_representation(document)

    def test_bytes_are_bounded_before_decode(self):
        with patch.object(contract_v1.json, 'loads') as decode:
            self.assert_capacity('bytes', lambda: contract_v1.strict_json_loads(b' ' * (INPUT_BUDGET.bytes + 1)))
            decode.assert_not_called()
        self.assertEqual(contract_v1.strict_json_loads('0' + ' ' * (INPUT_BUDGET.bytes - 1)), 0)

    def test_file_reader_requests_at_most_budget_plus_one(self):
        from comparative_evidence import artifact_boundary
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'
            path.write_bytes(b'{}')
            requested = []
            real_reader = artifact_boundary.io.BufferedReader
            class Reader:
                def __init__(self, stream): self.stream = stream
                def fileno(self): return self.stream.fileno()
                def close(self): self.stream.close()
                def read(self, size):
                    requested.append(size)
                    return b' ' * size
            with patch.object(artifact_boundary.io, 'BufferedReader', side_effect=lambda raw: Reader(real_reader(raw))), patch('comparative_evidence.cli.strict_json_loads') as decode:
                with self.assertRaises(ReportArtifactError):
                    _load(path)
                decode.assert_not_called()
            self.assertEqual(requested, [INPUT_BUDGET.bytes + 1])

    def test_depth_preflight_counts_containers_outside_strings(self):
        maximum = '[' * INPUT_BUDGET.depth + '0' + ']' * INPUT_BUDGET.depth
        contract_v1.strict_json_loads(maximum)
        with patch.object(contract_v1.json, 'loads') as decode:
            self.assert_capacity('depth', lambda: contract_v1.strict_json_loads('[' + maximum + ']'))
            decode.assert_not_called()
        self.assertEqual(contract_v1.strict_json_loads('"[\\\"{"'), '["{')

    def test_decoded_depth_and_cycles_precede_copy(self):
        for kind in ('depth', 'cycle'):
            value = load('fixtures/contracts/planned-observation.json')
            nested = []
            if kind == 'cycle':
                nested.append(nested)
            else:
                for _ in range(INPUT_BUDGET.depth): nested = [nested]
            value['result']['extension'] = nested
            with patch.object(contract_v1, 'deepcopy') as copy:
                with self.assertRaises(ContractBoundaryError):
                    ObservationEnvelope.from_dict(value)
                copy.assert_not_called()

    def test_envelope_capacity_precedes_shape_sorting_and_projection(self):
        for location in ('root', 'source'):
            for category in ('values', 'string'):
                document = load('fixtures/contracts/planned-observation.json')
                target = document if location == 'root' else document['source']
                if category == 'values':
                    target.update({f'extra_{index}': 0 for index in range(INPUT_BUDGET.values)})
                else:
                    target['x' * (INPUT_BUDGET.key_bytes + 1)] = 0
                with self.subTest(location=location, category=category), patch('builtins.sorted', wraps=sorted) as sort, patch('comparative_evidence.model.validate_observation_compatibility') as projection:
                    self.assert_capacity(category, lambda: ObservationEnvelope.from_dict(document))
                    sort.assert_not_called()
                    projection.assert_not_called()

    def test_values_names_and_repeated_reference_expansion(self):
        validate_representation([None] * (INPUT_BUDGET.values - 1))
        self.assert_capacity('values', lambda: validate_representation([None] * INPUT_BUDGET.values))
        small = replace(INPUT_BUDGET, values=5)
        validate_representation({'a': 1, 'b': 2}, small)
        self.assert_capacity('values', lambda: validate_representation({'a': 1, 'b': 2, 'c': 3}, small))
        shared = [0] * 100
        self.assert_capacity('values', lambda: validate_representation([shared] * 200))
        for key in (None, 1):
            with self.assertRaises(ContractBoundaryError): validate_representation({key: 1})

    def test_text_key_and_integer_boundaries(self):
        validate_representation('x' * INPUT_BUDGET.string_bytes)
        self.assert_capacity('string', lambda: validate_representation('x' * (INPUT_BUDGET.string_bytes + 1)))
        validate_representation({'x' * INPUT_BUDGET.key_bytes: 0})
        self.assert_capacity('string', lambda: validate_representation({'x' * (INPUT_BUDGET.key_bytes + 1): 0}))
        validate_representation(['x' * INPUT_BUDGET.string_bytes] * 4)
        self.assert_capacity('text', lambda: validate_representation(['x' * INPUT_BUDGET.string_bytes] * 4 + ['x']))
        largest = 2**INPUT_BUDGET.integer_bits - 1
        self.assertEqual(contract_v1.strict_json_loads(str(largest)), largest)
        for value in (largest + 1, -(largest + 1)):
            self.assert_capacity('integer', lambda: validate_representation(value))
            self.assert_capacity('integer', lambda: contract_v1.strict_json_loads(str(value)))
        self.assert_capacity('integer', lambda: contract_v1.strict_json_loads('1' * 5000))

    def test_decoded_byte_budget_charges_numbers_and_json_escapes(self):
        self.assert_capacity('bytes', lambda: validate_representation([2**INPUT_BUDGET.integer_bits - 1] * 2000))
        for value in ('a', '\n', '\x01', 'é', {'x': [1, False, None]}):
            exact = len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode())
            budget = replace(INPUT_BUDGET, bytes=exact)
            validate_representation(value, budget)
            self.assert_capacity('bytes', lambda: validate_representation(value, replace(budget, bytes=exact-1)))

    def test_direct_envelope_constructor_rejects_cycles_before_freezing(self):
        document = load('fixtures/contracts/planned-observation.json')
        document['result']['extension'] = document['result']
        with patch('comparative_evidence.model._deep_freeze') as freeze:
            self.assert_capacity('cycle', lambda: ObservationEnvelope(**document))
            freeze.assert_not_called()

    def test_output_capacity_rejection_precedes_publication(self):
        from comparative_evidence import report as report_owner
        simulation = ObservationEnvelope.from_dict(load('fixtures/pairs/simulation-observation.json'))
        candidate = ObservationEnvelope.from_dict(load('fixtures/contracts/planned-observation.json'))
        report = compare_synthetic_contract(simulation, candidate, load('specification/comparison-profile.json'))
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'accepted'
            write_reports(report, target)
            retained = {p.name: p.read_bytes() for p in target.iterdir()}
            with patch.object(report_owner, 'REPORT_BUDGET', replace(REPORT_BUDGET, bytes=1)), patch('comparative_evidence.filesystem_publication.publish_report') as publish:
                self.assert_capacity('bytes', lambda: write_reports(report, target))
                publish.assert_not_called()
            self.assertEqual(retained, {p.name: p.read_bytes() for p in target.iterdir()})

    def test_maximum_integer_fits_minimum_supported_interpreter_digit_limit(self):
        source = """from comparative_evidence.contract_v1 import canonical_json_bytes, strict_json_loads
from comparative_evidence.legacy_json import INPUT_BUDGET, RepresentationCapacityError
maximum = 2**INPUT_BUDGET.integer_bits - 1
encoded = canonical_json_bytes(maximum)
assert len(encoded) == 617
assert strict_json_loads(encoded) == maximum
try:
    strict_json_loads(str(maximum + 1))
except RepresentationCapacityError as error:
    assert error.code == 'legacy_integer'
else:
    raise AssertionError('one-over integer admitted')
"""
        result = subprocess.run([sys.executable, '-c', source], cwd=ROOT,
            env={**os.environ, 'PYTHONINTMAXSTRDIGITS': '640', 'PYTHONPATH': str(ROOT / 'src')},
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_strict_and_unicode_meaning_remains(self):
        for text in ('{"x":1,"x":2}', 'NaN', '1e309', b'\xff', '"\\ud800"'):
            with self.subTest(text_type=type(text)), self.assertRaises(ValueError):
                contract_v1.strict_json_loads(text)
        self.assertEqual(contract_v1.strict_json_loads('{"測定":"é"}'.encode()), {'測定': 'é'})
        self.assert_capacity('string', lambda: validate_representation('é' * (INPUT_BUDGET.string_bytes // 2 + 1)))

    def test_compatibility_owns_one_snapshot_and_retains_original_values(self):
        value = load('fixtures/contracts/planned-observation.json')
        value['provenance']['governed_locator'] = ' ' + value['provenance']['governed_locator'] + ' '
        before = deepcopy(value)
        with patch.object(contract_v1, 'deepcopy', wraps=deepcopy) as copy:
            owned = contract_v1.validate_observation_compatibility(value)
        self.assertEqual(copy.call_count, 1)
        self.assertEqual(owned, before)
        owned['result']['extension'] = {'changed': True}
        self.assertEqual(value, before)

    def test_near_string_capacity_roundtrip_and_rejection_preserves_accepted_pair(self):
        simulation = load('fixtures/pairs/simulation-observation.json')
        candidate = load('fixtures/contracts/planned-observation.json')
        profile = load('specification/comparison-profile.json')
        simulation['result']['extension'] = 'a' * INPUT_BUDGET.string_bytes
        candidate['result']['extension'] = 'b' * INPUT_BUDGET.string_bytes
        profile['reportable_paths'].append('$.extension')
        profile['required_paths'].append('$.extension')
        before = deepcopy(candidate)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'candidate.json'
            source.write_text(json.dumps(candidate))
            received = ObservationEnvelope.from_dict(_load(source))
            report = compare_synthetic_contract(ObservationEnvelope.from_dict(simulation), received, profile)
            target = root / 'accepted'
            write_reports(report, target)
            inventory = report_artifact_inventory(target)
            retained = {p.name: p.read_bytes() for p in target.iterdir()}
            self.assertEqual(candidate, before)
            candidate['result']['extension'] += 'x'
            with self.assertRaises(ContractBoundaryError):
                ObservationEnvelope.from_dict(candidate)
            self.assertEqual(retained, {p.name: p.read_bytes() for p in target.iterdir()})
            self.assertEqual(inventory, report_artifact_inventory(target))
            candidate['result']['extension'] = 'mutated'
            self.assertEqual(received.result['extension'], before['result']['extension'])

    def test_standalone_artifact_membership_stops_before_read(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'comparison.json').write_text('{}')
            (root / 'comparison.html').write_text('placeholder')
            (root / 'nested').mkdir()
            with patch('comparative_evidence.artifact_boundary._read_regular_file') as read:
                with self.assertRaises(ReportArtifactError): report_artifact_inventory(root)
                read.assert_not_called()

    def test_standalone_artifact_caps_keep_exact_prepared_limits_separate(self):
        from comparative_evidence import artifact_boundary
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('comparison.json', 'comparison.html'): (root / name).write_bytes(b'')
            with patch.object(artifact_boundary, '_read_regular_file', return_value=b'') as read, patch.object(artifact_boundary, '_report_content_inventory', side_effect=lambda contents: list(contents)):
                report_artifact_inventory(root)
                actual = {call.args[1]: call.kwargs['max_bytes'] for call in read.call_args_list}
            self.assertEqual(actual, {'comparison.json': REPORT_BUDGET.bytes, 'comparison.html': HTML_BYTES})
            with patch.object(artifact_boundary, '_read_regular_file', return_value=b'') as read, patch.object(artifact_boundary, '_report_content_inventory', side_effect=lambda contents: list(contents)):
                fd = os.open(root, os.O_RDONLY)
                try: artifact_boundary._report_inventory_at(fd, {'comparison.json': 7, 'comparison.html': 11})
                finally: os.close(fd)
                self.assertEqual({c.args[1]: c.kwargs['max_bytes'] for c in read.call_args_list}, {'comparison.json': 7, 'comparison.html': 11})

    def test_native_container_uses_the_same_capacity_receiver(self):
        sys.path.insert(0, str(ROOT / 'infra'))
        try:
            spec = importlib.util.spec_from_file_location('capacity_container_entry', ROOT / 'infra/container_entry.py')
            entry = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(entry)
        finally: sys.path.remove(str(ROOT / 'infra'))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'
            path.write_bytes(b' ' * (INPUT_BUDGET.bytes + 1))
            for receiver in (_load, entry.load):
                with self.assertRaises(ReportArtifactError): receiver(path)

    def test_repeated_reference_rejection_has_bounded_working_allocation(self):
        shared = [0] * 100
        expanded = [shared] * 10000
        tracemalloc.start()
        try:
            self.assert_capacity('values', lambda: validate_representation(expanded))
            _, peak = tracemalloc.get_traced_memory()
        finally: tracemalloc.stop()
        # Input allocation is outside this observation; the walk retains ancestors,
        # not a queue or detached copy of the million-value serialized expansion.
        self.assertLess(peak, 128 * 1024)


if __name__ == '__main__': unittest.main()
