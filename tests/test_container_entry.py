"""The finite entry preserves native JSON admission and artifact inventories."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infra"))
spec = importlib.util.spec_from_file_location("finite_entry", ROOT / "infra/container_entry.py")
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
from container_runtime import publish
from comparative_evidence.artifact_boundary import report_artifact_inventory as inventory


class NativeEntryTests(unittest.TestCase):
    def test_native_ingress_retains_duplicate_and_object_rules(self):
        for value in ('{"field":1,"field":2}', '[]'):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "input.json"
                path.write_text(value, encoding="utf-8")
                with self.assertRaises(ValueError):
                    entry.load(path)

    def test_published_payload_passes_native_inventory_and_replays(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = publish(entry.produce, root, validate=inventory)
            second = publish(entry.produce, root, validate=inventory)
            self.assertNotEqual(first["directory"], second["directory"])
            first_inventory = inventory(root / first["directory"] / "payload")
            second_inventory = inventory(root / second["directory"] / "payload")
            self.assertEqual(len(first_inventory), 2)
            self.assertEqual(first_inventory, second_inventory)
            receipt = json.loads((root / first["directory"] / "job-receipt.json").read_bytes())
            self.assertEqual({item["path"] for item in receipt["files"]}, {"payload/" + name for name in first_inventory})


if __name__ == "__main__":
    unittest.main()
