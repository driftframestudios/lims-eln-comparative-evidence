"""Preserve existing evidence admission and deterministic report rendering."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from container_runtime import run
from comparative_evidence.compare import compare_synthetic_contract
from comparative_evidence.model import ObservationEnvelope
from comparative_evidence.report import write_reports


def load(path): return json.loads(Path(path).read_bytes())

def produce(output):
    report=compare_synthetic_contract(ObservationEnvelope.from_dict(load("fixtures/pairs/simulation-observation.json")),ObservationEnvelope.from_dict(load("fixtures/contracts/planned-observation.json")),load("specification/comparison-profile.json"))
    write_reports(report,output)

if __name__=="__main__": run(produce)
