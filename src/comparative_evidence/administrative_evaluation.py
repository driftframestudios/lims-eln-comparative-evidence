"""Independent field scoring over Program-admitted synthetic observations.

Indexes retain O(R + A + L) space for runs, attempts and label vocabulary.
Scoring is O(R + A + B + L), plus O(R log R) stable output ordering; B is
bounded output text. Subject means give each independent subject equal weight.
Byte-identity comparison and substantive scores retain distinct meanings.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError
from lims_eln_contracts.administrative_study import AdministrativeStudy, admit_administrative_study
from lims_eln_contracts.canonical import canonical_json_bytes, canonical_sha256, strict_json_loads
from lims_eln_contracts.primitives import ContractModel, Sha256Digest
from lims_eln_contracts.study_interpretation import interpret_administrative_study
from lims_eln_sim.administrative_pack import Classification, MAX_BYTES, PolicyState, ScenarioPack, Token, Tokens, admit_pack

from .publication import render_public_boundary

PROFILE = {"id":"administrative-fields", "version":"1.0.0", "primary":"exact label-set match", "averaging":"micro over label decisions; macro over labels with expected or observed support", "zero_denominator":"null", "empty_set_jaccard":1, "paired_estimator":"equal subject weight after within-subject repeat means", "uncertainty":"descriptive fixture observations; inferential intervals require an independently reviewed sampling design"}
Count = Annotated[int, Field(ge=0, le=100000)]


class EvaluationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code + ": reconcile the pack, observation identity, and scoring contract")


class AdministrativeOutput(ContractModel):
    labels: Tokens
    classification: Classification
    policy_state: PolicyState
    raw_label: Annotated[str, Field(max_length=1024)]
    workflow_minutes: Annotated[int, Field(ge=0, le=1440)]


class ScientificOutput(ContractModel):
    facts: Tokens


class Ratio(ContractModel):
    numerator: Count
    denominator: Count
    value: float | None


def ratio(numerator: int, denominator: int) -> Ratio:
    return Ratio(numerator=numerator, denominator=denominator, value=numerator / denominator if denominator else None)


class RunScore(ContractModel):
    run_id: Token
    pair_id: Token
    subject_id: Token
    cohort: Token
    arm: Literal["a", "b"]
    repeat_index: Count
    status: Literal["pending", "completed", "abstained", "timeout", "cancelled", "invalid_response", "failed", "excluded"]
    standing: Literal["scored", "output_unavailable", "execution_mismatch", "output_shape"]
    exact_labels: bool | None = None
    jaccard: float | None = None
    classification_matches: bool | None = None
    policy_matches: bool | None = None
    raw_preserved: bool | None = None
    required_facts: Count = 0
    found_required_facts: Count = 0
    unsupported_facts: Count = 0
    supplied_facts: Count = 0
    scientific_matches: bool | None = None
    workflow_minutes: int | None = None


class LabelScore(ContractModel):
    label: Token
    support: Count
    true_positive: Count
    false_positive: Count
    false_negative: Count
    precision: Ratio
    recall: Ratio
    f1: Ratio


class GroupScore(ContractModel):
    cohort: Token
    planned_runs: Count
    attempted_runs: Count
    completed_runs: Count
    scored_runs: Count
    complete_pairs: Count
    independent_subjects: Count
    standing: Literal["descriptive", "small_cell", "empty"]
    workflow_difference_minutes: float | None


class EvaluationReport(ContractModel):
    schema_id: Literal["urn:driftframe:comparison:administrative-evaluation:1.0.0"] = Field(alias="$schema")
    pack_digest: Sha256Digest
    study_digest: Sha256Digest
    scoring_digest: Sha256Digest
    evidence_mode: Literal["fixture_demonstration", "caller_supplied_synthetic"]
    evidence_scope: Literal["authored_synthetic_task_and_declared_outputs"] = "authored_synthetic_task_and_declared_outputs"
    planned_runs: Count
    attempted_runs: Count
    completed_runs: Count
    attempt_records: Count
    status_counts: dict[str, Count]
    scored_coverage: Ratio
    exact_label_agreement: Ratio
    mean_jaccard: float | None
    micro_precision: Ratio
    micro_recall: Ratio
    micro_f1: Ratio
    macro_f1: float | None
    required_fact_recall: Ratio
    unsupported_fact_rate: Ratio
    classification_agreement: Ratio
    policy_agreement: Ratio
    raw_preservation: Ratio
    scientific_oracle_disagreements: Count
    labels: tuple[LabelScore, ...]
    groups: tuple[GroupScore, ...]
    runs: tuple[RunScore, ...]
    identity_comparison: dict
    eligibility: dict


def _parsed(model: type[ContractModel], text: str) -> ContractModel:
    strict_json_loads(text)
    return model.model_validate_json(text, strict=True)


def evaluate(pack: ScenarioPack, study: AdministrativeStudy, *, evidence_mode: Literal["fixture_demonstration", "caller_supplied_synthetic"] = "caller_supplied_synthetic") -> EvaluationReport:
    """Score actual outputs against a separately received immutable oracle."""
    plan = pack.study
    runs = {run.run_id: run for run in study.runs}
    if study.specification != plan.specification or runs != {run.run_id:run for run in plan.runs} or {e.pair_id:e for e in study.expected_pairs} != {e.pair_id:e for e in plan.expected_pairs}:
        raise EvaluationError("study_pack_binding")
    expected = {item.run_id:item for item in pack.expected}
    interpretation = interpret_administrative_study(study)
    eligible_pairs = {pair.pair_id for pair in interpretation.pairs if pair.eligible}
    latest = {}
    attempted = set()
    for observation in study.observations:
        prior = latest.get(observation.run_id)
        if prior is None or observation.attempt > prior.attempt:
            latest[observation.run_id] = observation
        if observation.started_at is not None:
            attempted.add(observation.run_id)
    scores = []
    tp, fp, fn, support = Counter(), Counter(), Counter(), Counter()
    for run_id in sorted(runs):
        run, oracle, observation = runs[run_id], expected[run_id], latest.get(run_id)
        row = {"run_id":run_id,"pair_id":run.pair_id,"subject_id":run.subject_id,"cohort":oracle.cohort,"arm":run.arm,"repeat_index":run.repeat_index,"status":observation.status if observation else "pending","standing":"output_unavailable"}
        if observation is None or observation.status != "completed":
            scores.append(RunScore(**row))
            continue
        if observation.execution != study.specification.expected_execution:
            row["standing"] = "execution_mismatch"
            scores.append(RunScore(**row))
            continue
        try:
            actual = _parsed(AdministrativeOutput, observation.administrative_output.text)
            science = _parsed(ScientificOutput, observation.scientific_output.text)
            if len(set(actual.labels)) != len(actual.labels) or len(set(science.facts)) != len(science.facts):
                raise ValueError("set members are unique")
        except (ValueError, TypeError, RecursionError):
            row["standing"] = "output_shape"
            scores.append(RunScore(**row))
            continue
        wanted, observed = set(oracle.labels), set(actual.labels)
        union = wanted | observed
        tp.update(wanted & observed); fp.update(observed - wanted); fn.update(wanted - observed); support.update(wanted)
        facts, required, permitted = set(science.facts), set(oracle.required_facts), set(oracle.allowed_facts)
        raw = strict_json_loads(run.administrative_input)["raw_label"]
        row.update(standing="scored", exact_labels=wanted == observed, jaccard=len(wanted & observed) / len(union) if union else 1.0, classification_matches=actual.classification == oracle.classification, policy_matches=actual.policy_state == oracle.policy_state, raw_preserved=actual.raw_label == raw, required_facts=len(required), found_required_facts=len(required & facts), unsupported_facts=len(facts - permitted), supplied_facts=len(facts), scientific_matches=required <= facts <= permitted, workflow_minutes=actual.workflow_minutes)
        scores.append(RunScore(**row))
    label_rows = tuple(LabelScore(label=label,support=support[label],true_positive=tp[label],false_positive=fp[label],false_negative=fn[label],precision=ratio(tp[label],tp[label]+fp[label]),recall=ratio(tp[label],tp[label]+fn[label]),f1=ratio(2*tp[label],2*tp[label]+fp[label]+fn[label])) for label in sorted(set(tp)|set(fp)|set(fn)))
    scored = tuple(row for row in scores if row.standing == "scored")
    pair_rows = defaultdict(dict)
    cohort_rows = defaultdict(list)
    for row in scores:
        pair_rows[row.pair_id][row.arm] = row
        cohort_rows[row.cohort].append(row)
    subject_deltas = defaultdict(lambda: defaultdict(list))
    pair_counts = Counter()
    for pair_id, pair in pair_rows.items():
        a, b = pair["a"], pair["b"]
        if pair_id in eligible_pairs and a.standing == b.standing == "scored":
            subject_deltas[a.cohort][a.subject_id].append(b.workflow_minutes - a.workflow_minutes)
            pair_counts[a.cohort] += 1
    groups = []
    for cohort in sorted(pack.design.planned_cohorts):
        rows = cohort_rows[cohort]
        subjects = subject_deltas[cohort]
        standing = "empty" if not rows else "small_cell" if len(subjects) < pack.design.minimum_subjects else "descriptive"
        mean = sum(sum(values)/len(values) for values in subjects.values())/len(subjects) if subjects and standing == "descriptive" else None
        groups.append(GroupScore(cohort=cohort,planned_runs=len(rows),attempted_runs=sum(row.run_id in attempted for row in rows),completed_runs=sum(row.status=="completed" for row in rows),scored_runs=sum(row.standing=="scored" for row in rows),complete_pairs=pair_counts[cohort],independent_subjects=len(subjects),standing=standing,workflow_difference_minutes=mean))
    comparison = interpretation.comparison
    count = len(scored)
    exact = sum(row.exact_labels for row in scored)
    all_tp, all_fp, all_fn = sum(tp.values()), sum(fp.values()), sum(fn.values())
    return EvaluationReport(schema_id="urn:driftframe:comparison:administrative-evaluation:1.0.0",pack_digest=canonical_sha256(pack),study_digest=canonical_sha256(study),scoring_digest=canonical_sha256(PROFILE),evidence_mode=evidence_mode,planned_runs=len(runs),attempted_runs=len(attempted),completed_runs=comparison.completed,attempt_records=len(study.observations),status_counts=dict(Counter(row.status for row in scores)),scored_coverage=ratio(count,len(runs)),exact_label_agreement=ratio(exact,count),mean_jaccard=sum(row.jaccard for row in scored)/count if count else None,micro_precision=ratio(all_tp,all_tp+all_fp),micro_recall=ratio(all_tp,all_tp+all_fn),micro_f1=ratio(2*all_tp,2*all_tp+all_fp+all_fn),macro_f1=sum(row.f1.value for row in label_rows)/len(label_rows) if label_rows else None,required_fact_recall=ratio(sum(row.found_required_facts for row in scored),sum(row.required_facts for row in scored)),unsupported_fact_rate=ratio(sum(row.unsupported_facts for row in scored),sum(row.supplied_facts for row in scored)),classification_agreement=ratio(sum(row.classification_matches for row in scored),count),policy_agreement=ratio(sum(row.policy_matches for row in scored),count),raw_preservation=ratio(sum(row.raw_preserved for row in scored),count),scientific_oracle_disagreements=sum(row.scientific_matches is False for row in scored),labels=label_rows,groups=tuple(groups),runs=tuple(scores),identity_comparison=comparison.model_dump(mode="json",by_alias=True),eligibility=interpretation.model_dump(mode="json",by_alias=True))


def _fixture_response(run) -> tuple[str, dict, dict]:
    """A small observation producer, independent of Simulation's oracle values."""
    values = strict_json_loads(run.administrative_input)
    raw = values["raw_label"]
    normalized = raw.strip().casefold()
    routes = {"commercial":(["SYN-EMPLOYER"],"matched"),"public and employer":(["SYN-EMPLOYER","SYN-PUBLIC"],"multiple"),"private":(["SYN-EMPLOYER","SYN-INDIVIDUAL"],"ambiguous"),"":([],"absent"),"conflicting rules":(["SYN-EMPLOYER"],"matched")}
    statuses = {"review requested":"abstained","adapter failure":"failed","awaiting observation":"pending","unsupported combination":"excluded"}
    status = statuses.get(normalized,"completed")
    labels, classification = routes.get(normalized,([],"unknown"))
    policy, minutes = "review", 10
    if values["review"] == "retracted":
        policy = "retracted"
    elif values["review"] == "accepted-employer":
        labels, classification, policy, minutes = ["SYN-EMPLOYER"], "matched", "overridden", 5
    elif values["service_day"] >= "2027-01-01":
        policy = "expired"
    elif values["enrollment"] == "pending":
        policy = "pending"
    elif normalized == "conflicting rules":
        policy = "conflict"
    elif values["reportability"] == "reportable":
        policy, minutes = "submit", 5
    facts = ["SYN-MARKER-PRESENT","SYN-VALUE-4"]
    if run.scenario_id == "SYN-CASE-INJECTED" and run.arm == "b":
        facts = ["SYN-MARKER-PRESENT","SYN-VALUE-9"]
    return status, {"labels":labels,"classification":classification,"policy_state":policy,"raw_label":raw,"workflow_minutes":minutes}, {"facts":facts}


def _demonstration_execution(repeats: int) -> dict[str, str]:
    """Describe this versioned local producer and its actual execution settings."""
    return {
        "provider_id": "SYN-OFFLINE",
        "model_id": "SYN-RESPONSE-FIXTURE",
        "adapter_version": "1.0.0",
        "prompt_digest": canonical_sha256("Preserve the supplied facts and return the declared administrative fields."),
        "configuration_digest": canonical_sha256({"order": "counterbalanced", "repeats": repeats}),
    }


def demonstration_study(pack: ScenarioPack) -> AdministrativeStudy:
    """Counterbalance fixture execution, preserving observations as their own artifact."""
    document = pack.study.model_dump(mode="json",by_alias=True)
    execution = _demonstration_execution(pack.design.repeats)
    ordered = sorted(pack.study.runs, key=lambda run:(run.pair_id, run.arm if run.repeat_index % 2 == 0 else ("a" if run.arm == "b" else "b")))
    observations = []
    for order, run in enumerate(ordered):
        status, administrative, science = _fixture_response(run)
        item = {"observation_id":"SYN-OBS-"+run.run_id,"run_id":run.run_id,"attempt":1,"specification_digest":canonical_sha256(pack.study.specification),"input_digest":canonical_sha256(run),"status":status}
        if status != "pending":
            if status != "completed":
                item["reason_code"] = "SYN-FIXTURE-" + status.upper()
            if status != "excluded":
                started = datetime(2026,10,14,tzinfo=timezone.utc)+timedelta(seconds=order*2)
                item.update(execution=dict(execution),execution_order=order,started_at=started.isoformat().replace("+00:00","Z"),finished_at=(started+timedelta(seconds=1)).isoformat().replace("+00:00","Z"))
            if status == "completed":
                for key, output in (("scientific_output",science),("administrative_output",administrative)):
                    text = canonical_json_bytes(output).decode()
                    item[key] = {"text":text,"digest":canonical_sha256(text),"completeness":"complete"}
        observations.append(item)
    document["observations"] = observations
    return admit_administrative_study(canonical_json_bytes(document))


def render_html(report: EvaluationReport) -> str:
    """Render declared report fields and the complete escaped semantic companion."""
    rows = "".join(f'<tr><th scope="row">{escape(group.cohort)}</th><td>{group.planned_runs}</td><td>{group.scored_runs}</td><td>{group.independent_subjects}</td><td>{escape(group.standing)}</td><td>{group.workflow_difference_minutes if group.workflow_difference_minutes is not None else "Requires sufficient paired subjects"}</td></tr>' for group in report.groups)
    embedded = escape(json.dumps(report.model_dump(mode="json",by_alias=True),indent=2,sort_keys=True))
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Administrative comparison</title>
<style>:root{{color-scheme:light;--ink:#152433;--paper:#f4f0e8;--line:#b8c2cc}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 ui-sans-serif,system-ui,sans-serif}}main{{max-width:1000px;margin:auto;padding:2rem}}table{{min-width:55rem;width:100%;border-collapse:collapse}}th,td{{border:1px solid var(--line);padding:.7rem;text-align:left}}.table-scroll{{overflow-x:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.skip-link{{position:absolute;transform:translateY(-200%)}}.skip-link:focus{{transform:none}}@media(max-width:600px){{main{{padding:1rem}}}}</style></head><body><a class="skip-link" href="#content">Skip to comparison</a><main id="content">
<h1>Administrative comparison</h1><p>{escape(report.evidence_mode)}: {report.scored_coverage.numerator} scored runs of {report.planned_runs} planned. Exact label agreement: {report.exact_label_agreement.numerator} of {report.exact_label_agreement.denominator} scored runs.</p>
<p>Scientific oracle disagreements: {report.scientific_oracle_disagreements}. Authored fixture results support harness review; population and causal conclusions receive a separately reviewed study design.</p>
<h2 id="groups">Cohort coverage and paired workflow</h2><p>Scroll within the table to inspect every column. Workflow differences use equal subject weights after averaging repeats; small and empty cells retain coverage while their score stays withheld.</p>
<div class="table-scroll" role="region" aria-labelledby="groups" tabindex="0"><table><caption>Designed cohorts and complete-pair evidence</caption><thead><tr><th scope="col">Cohort</th><th scope="col">Planned runs</th><th scope="col">Scored runs</th><th scope="col">Paired subjects</th><th scope="col">Standing</th><th scope="col">Workflow difference, minutes</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>Scoring and evidence</h2><p>Micro scores aggregate label decisions. Macro F1 gives equal weight to supported labels. Empty-set Jaccard is one; undefined ratios remain null. Omitted required facts and unsupported facts remain separate counts. Probability calibration and inferential uncertainty require fitting probability outputs and a sampling design.</p>
<details><summary>Complete machine-readable report</summary><pre id="report-json">{embedded}</pre></details><footer>{render_public_boundary()}</footer></main></body></html>'''


def _read(path: Path) -> bytes:
    with path.open("rb") as stream:
        payload = stream.read(MAX_BYTES+1)
    if len(payload) > MAX_BYTES:
        raise EvaluationError("input_bytes")
    return payload


def main() -> None:
    from .administrative_artifacts import publish_administrative_bundle

    parser = argparse.ArgumentParser(description="Score a bounded synthetic administrative study.")
    parser.add_argument("--pack",type=Path,required=True)
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--study",type=Path)
    sources.add_argument("--fixture-demo",action="store_true")
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    try:
        pack = admit_pack(_read(args.pack))
        study = demonstration_study(pack) if args.fixture_demo else admit_administrative_study(_read(args.study))
        report = evaluate(pack,study,evidence_mode="fixture_demonstration" if args.fixture_demo else "caller_supplied_synthetic")
        publish_administrative_bundle(pack, study, report, args.output)
        print(f"{report.planned_runs} planned; {report.scored_coverage.numerator} scored; {report.scientific_oracle_disagreements} scientific oracle disagreements")
    except (ValueError, OSError) as error:
        parser.exit(2, str(error)+"\n")


if __name__ == "__main__":
    main()
