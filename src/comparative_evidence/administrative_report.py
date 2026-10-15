"""Saved administrative-report coherence and separate source recomputation.

Program owns nested comparison/eligibility and JSON resource guards. Comparative
owns score coherence. Indexes take O(R + L + G) space; reconciliation is O(R + L
+ G), followed by bounded serialization. Decoder/model costs retain their own
byte, depth and collection envelopes. Admission establishes internal agreement;
source recomputation establishes agreement with a separately admitted oracle.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from math import gcd, isclose
from typing import Annotated, Literal, Self, cast

from pydantic import Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError

from lims_eln_contracts.administrative_admission import (
    AdministrativeAdmissionError, _canonical_output, _decoded_values, _json_depth,
)
from lims_eln_contracts.administrative_study import (
    AdministrativeStudy, RunStatus, StudyComparisonReport, admit_administrative_study,
)
from lims_eln_contracts.canonical import (
    DuplicateObjectKeyError, NonFiniteNumberError, canonical_sha256, strict_json_loads,
)
from lims_eln_contracts.primitives import ContractModel, Sha256Digest
from lims_eln_contracts.study_interpretation import StudyAnalysisProfile, StudyInterpretation
from lims_eln_sim.administrative_pack import MAX_BYTES, ScenarioPack, Token, admit_pack


REPORT_SCHEMA_ID = "urn:driftframe:comparison:administrative-evaluation:1.0.0"
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_REPORT_DEPTH = 32
MAX_REPORT_LABELS = 16384
MAX_REPORT_RUNS = 512
MAX_REPORT_GROUPS = 8
# Count containers, member names and scalar values in the generated wire shape.
# Fixed metadata includes ten ratios, eight status counts and nested metadata.
# Each Program comparison has up to 35 source-derived reasons and two output
# families; eligibility carries 32 controls (17 values each) and 36 reasons.
# Both copies of the comparison are budgeted. The independent byte cap also
# bounds inputs whose Program reason collections exceed the producer envelope.
MAX_REPORT_VALUES = (
    213 + 35 * MAX_REPORT_LABELS + 39 * MAX_REPORT_RUNS + 19 * MAX_REPORT_GROUPS
    + (MAX_REPORT_RUNS // 2) * (2 * (15 + 35 + 2) + 17 + 32 * 17 + 36)
)
FLOAT_REL_TOL = 1e-12
FLOAT_ABS_TOL = 1e-12
PROFILE = {"id":"administrative-fields", "version":"1.0.0", "primary":"exact label-set match", "averaging":"micro over label decisions; macro over labels with expected or observed support", "zero_denominator":"null", "empty_set_jaccard":1, "paired_estimator":"equal subject weight after within-subject repeat means", "uncertainty":"descriptive fixture observations; inferential intervals require an independently reviewed sampling design"}
Count = Annotated[int, Field(ge=0, le=100000)]
UnitScore = Annotated[float, Field(ge=0, le=1)]
Workflow = Annotated[int, Field(ge=0, le=1440)]

ReportCode = Literal[
    "report_payload", "report_input_bytes", "report_utf8", "report_json_depth",
    "report_json_syntax", "report_json_duplicate_key", "report_json_number",
    "report_decoded_values", "report_decoder_capacity", "report_output",
    "report_schema", "report_shape", "report_identity_comparison", "report_eligibility",
    "report_ratio", "report_run_score", "report_label_score", "report_run_coverage",
    "report_pair_coverage", "report_status_counts", "report_attempt_counts",
    "report_score_counts", "report_label_counts", "report_label_joint_counts", "report_group_coverage",
    "report_group_counts", "report_group_threshold", "report_group_estimate",
    "report_study_binding", "report_scoring_binding", "report_interpretation_profile",
    "report_pack_source", "report_study_source", "report_pack_binding",
    "report_sources_required", "report_source_binding", "report_fixture_identity",
    "report_recomputation",
]
_COHERENCE_CODES = frozenset({
    "report_ratio", "report_run_score", "report_label_score", "report_run_coverage",
    "report_pair_coverage", "report_status_counts", "report_attempt_counts",
    "report_score_counts", "report_label_counts", "report_label_joint_counts", "report_group_coverage",
    "report_group_counts", "report_group_threshold", "report_group_estimate",
    "report_study_binding", "report_scoring_binding", "report_interpretation_profile", "report_eligibility",
})


class ReportAdmissionError(ValueError):
    """A fixed category keeps rejected input and diagnostics with the caller."""

    def __init__(self, code: ReportCode):
        self.code = code
        super().__init__(code + ": reconcile the retained report and its separately admitted sources")


def _require(condition: bool, code: ReportCode) -> None:
    if not condition:
        raise PydanticCustomError(code, "report fields satisfy their declared relationship")


def _same_float(actual: float | None, expected: float | None) -> bool:
    if actual is None or expected is None:
        return actual is expected
    return isclose(actual, expected, rel_tol=FLOAT_REL_TOL, abs_tol=FLOAT_ABS_TOL)


OverlapSegment = tuple[tuple[int, int], tuple[int, int]]


def _overlap_segment(jaccard: float) -> OverlapSegment:
    """Endpoints of the feasible (intersection, symmetric difference) hull.

    A partial score admits multiples of one reduced integer ratio. With at
    most sixteen labels on each side, distinct ratios are farther apart than
    the declared float tolerance; their feasible points lie on one segment.
    """
    if jaccard == 0:
        return (0, 1), (0, 32)
    if jaccard == 1:
        # An exact match includes the declared empty/empty convention.
        return (0, 0), (16, 0)
    points = [
        (intersection, union - intersection) for intersection in range(1, 16)
        for union in range(intersection + 1, 33 - intersection)
        if _same_float(jaccard, intersection / union)
    ]
    _require(bool(points), "report_run_score")
    return points[0], points[-1]


def _reconcile_overlap_totals(
    segments: Counter[OverlapSegment], intersection: int, errors: int,
) -> None:
    """Check exact supporting bounds of the summed cardinality segments.

    A sum of segments has edge directions drawn from those same segments.
    Their perpendiculars plus the coordinate axes therefore bound the whole
    convex sum, including a single segment or point. Integer dot products keep
    this joint check exact. This is a necessary arithmetic condition, rather
    than an integer assignment of individual labels to runs.

    K distinct segments cost O(K**2) time and O(K) space. K is bounded by the
    finite sixteen-label ratio family, independently of report label count.
    """
    normals = {(1, 0), (0, 1)}
    for low, high in segments:
        dx, dy = high[0] - low[0], high[1] - low[1]
        divisor = gcd(dx, dy)
        if divisor:
            normals.add((dy // divisor, -dx // divisor))
    for x, y in normals:
        lower = upper = 0
        for (low, high), multiplicity in segments.items():
            endpoints = (x * low[0] + y * low[1], x * high[0] + y * high[1])
            lower += multiplicity * min(endpoints)
            upper += multiplicity * max(endpoints)
        _require(lower <= x * intersection + y * errors <= upper,
                 "report_label_joint_counts")


class Ratio(ContractModel):
    numerator: Count
    denominator: Count
    value: UnitScore | None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        _require(self.numerator <= self.denominator, "report_ratio")
        expected = self.numerator / self.denominator if self.denominator else None
        _require(_same_float(self.value, expected), "report_ratio")
        return self


def ratio(numerator: int, denominator: int) -> Ratio:
    return Ratio(numerator=numerator, denominator=denominator, value=numerator / denominator if denominator else None)


def _ratio_counts(value: Ratio, numerator: int, denominator: int, code: ReportCode) -> None:
    # Counts retain integer equality; tolerance applies only to divided values.
    _require((value.numerator, value.denominator) == (numerator, denominator), code)


class RunScore(ContractModel):
    run_id: Token
    pair_id: Token
    subject_id: Token
    cohort: Token
    arm: Literal["a", "b"]
    repeat_index: Count
    status: RunStatus
    standing: Literal["scored", "output_unavailable", "execution_mismatch", "output_shape"]
    exact_labels: bool | None = None
    jaccard: UnitScore | None = None
    classification_matches: bool | None = None
    policy_matches: bool | None = None
    raw_preserved: bool | None = None
    required_facts: Annotated[int, Field(ge=0, le=16)] = 0
    found_required_facts: Annotated[int, Field(ge=0, le=16)] = 0
    unsupported_facts: Annotated[int, Field(ge=0, le=16)] = 0
    supplied_facts: Annotated[int, Field(ge=0, le=16)] = 0
    scientific_matches: bool | None = None
    workflow_minutes: Workflow | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        values = (self.exact_labels, self.jaccard, self.classification_matches,
                  self.policy_matches, self.raw_preserved, self.scientific_matches,
                  self.workflow_minutes)
        facts = (self.required_facts, self.found_required_facts,
                 self.unsupported_facts, self.supplied_facts)
        _require((self.status == "completed") == (self.standing != "output_unavailable"), "report_run_score")
        if self.standing == "scored":
            _require(all(value is not None for value in values), "report_run_score")
            _require(self.exact_labels == (self.jaccard == 1.0), "report_run_score")
            _require(self.found_required_facts <= self.required_facts
                     and self.found_required_facts + self.unsupported_facts <= self.supplied_facts,
                     "report_run_score")
            _require(self.scientific_matches == (self.found_required_facts == self.required_facts
                                                  and self.unsupported_facts == 0), "report_run_score")
        else:
            _require(all(value is None for value in values) and all(value == 0 for value in facts),
                     "report_run_score")
        return self


class LabelScore(ContractModel):
    label: Token
    support: Count
    true_positive: Count
    false_positive: Count
    false_negative: Count
    precision: Ratio
    recall: Ratio
    f1: Ratio

    @model_validator(mode="after")
    def coherent(self) -> Self:
        tp, fp, fn = self.true_positive, self.false_positive, self.false_negative
        _require(self.support == tp + fn and tp + fp + fn > 0, "report_label_score")
        _ratio_counts(self.precision, tp, tp + fp, "report_label_score")
        _ratio_counts(self.recall, tp, tp + fn, "report_label_score")
        _ratio_counts(self.f1, 2 * tp, 2 * tp + fp + fn, "report_label_score")
        return self


class GroupScore(ContractModel):
    cohort: Token
    planned_runs: Count
    attempted_runs: Count
    completed_runs: Count
    scored_runs: Count
    complete_pairs: Count
    independent_subjects: Count
    standing: Literal["descriptive", "small_cell", "empty"]
    workflow_difference_minutes: Annotated[float, Field(ge=-1440, le=1440)] | None


class EvaluationReport(ContractModel):
    schema_id: Literal[REPORT_SCHEMA_ID] = Field(alias="$schema")
    pack_digest: Sha256Digest
    study_digest: Sha256Digest
    scoring_digest: Sha256Digest
    evidence_mode: Literal["fixture_demonstration", "caller_supplied_synthetic"]
    evidence_scope: Literal["authored_synthetic_task_and_declared_outputs"] = "authored_synthetic_task_and_declared_outputs"
    planned_runs: Count
    attempted_runs: Count
    completed_runs: Count
    attempt_records: Annotated[int, Field(ge=0, le=4096)]
    status_counts: Annotated[dict[RunStatus, Count], Field(max_length=8)]
    scored_coverage: Ratio
    exact_label_agreement: Ratio
    mean_jaccard: UnitScore | None
    micro_precision: Ratio
    micro_recall: Ratio
    micro_f1: Ratio
    macro_f1: UnitScore | None
    required_fact_recall: Ratio
    unsupported_fact_rate: Ratio
    classification_agreement: Ratio
    policy_agreement: Ratio
    raw_preservation: Ratio
    scientific_oracle_disagreements: Count
    labels: Annotated[tuple[LabelScore, ...], Field(max_length=MAX_REPORT_LABELS)]
    groups: Annotated[tuple[GroupScore, ...], Field(min_length=1, max_length=MAX_REPORT_GROUPS)]
    runs: Annotated[tuple[RunScore, ...], Field(min_length=2, max_length=MAX_REPORT_RUNS)]
    identity_comparison: StudyComparisonReport
    eligibility: StudyInterpretation

    @model_validator(mode="after")
    def coherent(self) -> Self:
        _reconcile_report(self)
        return self


def _reconcile_report(report: EvaluationReport) -> None:
    comparison, interpretation = report.identity_comparison, report.eligibility
    _require(report.study_digest == comparison.study_digest == interpretation.study_digest
             and comparison == interpretation.comparison, "report_study_binding")
    _require(report.scoring_digest == canonical_sha256(PROFILE), "report_scoring_binding")
    _require(interpretation.profile == StudyAnalysisProfile(), "report_interpretation_profile")
    _require(len({row.run_id for row in report.runs}) == len(report.runs)
             and report.planned_runs == len(report.runs) == comparison.planned, "report_run_coverage")
    counts = Counter(row.status for row in report.runs)
    _require(dict(counts) == report.status_counts and report.completed_runs == counts["completed"],
             "report_status_counts")
    for status in ("completed", "pending", "abstained", "cancelled", "excluded"):
        _require(counts[status] == getattr(comparison, status), "report_status_counts")
    _require(sum(counts[status] for status in ("failed", "timeout", "invalid_response")) == comparison.failed,
             "report_status_counts")
    _require(report.attempted_runs == comparison.attempted
             and max(report.attempted_runs, report.planned_runs - counts["pending"]) <= report.attempt_records
             <= 8 * report.planned_runs, "report_attempt_counts")

    pairs, cohorts = defaultdict(dict), defaultdict(list)
    for row in report.runs:
        _require(row.arm not in pairs[row.pair_id], "report_pair_coverage")
        pairs[row.pair_id][row.arm] = row
        cohorts[row.cohort].append(row)
    eligibility = {pair.pair_id: pair for pair in interpretation.pairs}
    _require(set(pairs) == set(eligibility), "report_pair_coverage")
    subject_deltas = defaultdict(lambda: defaultdict(list))
    complete_pairs, minimum_attempted = Counter(), Counter()
    for pair_id, pair in pairs.items():
        _require(set(pair) == {"a", "b"}, "report_pair_coverage")
        a, b = pair["a"], pair["b"]
        _require((a.cohort, a.subject_id, a.repeat_index) == (b.cohort, b.subject_id, b.repeat_index),
                 "report_pair_coverage")
        eligible = eligibility[pair_id]
        _require(eligible.usable_arms == sum(row.status == "completed" for row in pair.values()),
                 "report_eligibility")
        mismatch = any(row.standing == "execution_mismatch" for row in pair.values())
        _require(not mismatch or eligible.execution == "mismatched", "report_eligibility")
        _require(eligible.usable_arms != 2 or eligible.execution != "mismatched" or mismatch,
                 "report_eligibility")
        executed = sum(row.status in {"completed", "abstained", "failed", "timeout", "invalid_response"}
                       for row in pair.values())
        minimum_attempted[a.cohort] += max(
            executed, 2 if eligible.execution == "matched" else int(eligible.execution == "mismatched"),
        )
        if eligible.eligible and a.standing == b.standing == "scored":
            subject_deltas[a.cohort][a.subject_id].append(b.workflow_minutes - a.workflow_minutes)
            complete_pairs[a.cohort] += 1

    scored = tuple(row for row in report.runs if row.standing == "scored")
    count = len(scored)
    _ratio_counts(report.scored_coverage, count, report.planned_runs, "report_score_counts")
    for field, attribute in (("exact_label_agreement", "exact_labels"),
                             ("classification_agreement", "classification_matches"),
                             ("policy_agreement", "policy_matches"), ("raw_preservation", "raw_preserved")):
        _ratio_counts(getattr(report, field), sum(getattr(row, attribute) for row in scored), count,
                      "report_score_counts")
    _require(_same_float(report.mean_jaccard, sum(row.jaccard for row in scored) / count if count else None),
             "report_score_counts")
    _ratio_counts(report.required_fact_recall, sum(row.found_required_facts for row in scored),
                  sum(row.required_facts for row in scored), "report_score_counts")
    _ratio_counts(report.unsupported_fact_rate, sum(row.unsupported_facts for row in scored),
                  sum(row.supplied_facts for row in scored), "report_score_counts")
    _require(report.scientific_oracle_disagreements == sum(not row.scientific_matches for row in scored),
             "report_score_counts")

    _require(len({row.label for row in report.labels}) == len(report.labels), "report_label_counts")
    differing = sum(not row.exact_labels for row in scored)
    overlapping = sum(row.jaccard > 0 for row in scored)
    # Each union is at most 32 minus its intersection. The fixed label cap
    # bounds this search; repeated Jaccard values share one local calculation.
    bounds = {value: _overlap_segment(value) for value in {row.jaccard for row in scored}}
    tp = fp = fn = 0
    for row in report.labels:
        _require(max(row.support, row.true_positive + row.false_positive) <= count, "report_label_counts")
        # A label contributes a true positive only in a run with an intersection.
        _require(row.true_positive <= overlapping, "report_label_counts")
        # One label contributes at most one error per differing run.
        _require(row.false_positive + row.false_negative <= differing, "report_label_counts")
        tp += row.true_positive
        fp += row.false_positive
        fn += row.false_negative
    # Matching empty sets have Jaccard one and require no true positives.
    _require(sum(bounds[row.jaccard][0][0] for row in scored) <= tp
             <= sum(bounds[row.jaccard][1][0] for row in scored),
             "report_label_counts")
    _require(differing <= fp + fn <= 32 * differing
             and max(tp + fp, tp + fn) <= 16 * count, "report_label_counts")
    _reconcile_overlap_totals(Counter(bounds[row.jaccard] for row in scored), tp, fp + fn)
    _ratio_counts(report.micro_precision, tp, tp + fp, "report_label_counts")
    _ratio_counts(report.micro_recall, tp, tp + fn, "report_label_counts")
    _ratio_counts(report.micro_f1, 2 * tp, 2 * tp + fp + fn, "report_label_counts")
    _require(_same_float(report.macro_f1, sum(row.f1.value for row in report.labels) / len(report.labels)
                         if report.labels else None), "report_label_counts")

    _require(len({group.cohort for group in report.groups}) == len(report.groups)
             and set(cohorts) <= {group.cohort for group in report.groups}, "report_group_coverage")
    _require(sum(group.attempted_runs for group in report.groups) == report.attempted_runs,
             "report_attempt_counts")
    lower_threshold, upper_threshold = 2, 32
    for group in report.groups:
        rows, subjects = cohorts[group.cohort], subject_deltas[group.cohort]
        _require((group.planned_runs, group.completed_runs, group.scored_runs,
                  group.complete_pairs, group.independent_subjects) ==
                 (len(rows), sum(row.status == "completed" for row in rows),
                  sum(row.standing == "scored" for row in rows), complete_pairs[group.cohort], len(subjects)),
                 "report_group_counts")
        _require(minimum_attempted[group.cohort] <= group.attempted_runs <= len(rows),
                 "report_attempt_counts")
        _require((group.standing == "empty") == (not rows), "report_group_threshold")
        if group.standing == "descriptive":
            upper_threshold = min(upper_threshold, len(subjects))
            expected = sum(sum(values) / len(values) for values in subjects.values()) / len(subjects) if subjects else None
            _require(group.workflow_difference_minutes is not None
                     and _same_float(group.workflow_difference_minutes, expected), "report_group_estimate")
        else:
            _require(group.workflow_difference_minutes is None, "report_group_estimate")
            if group.standing == "small_cell":
                lower_threshold = max(lower_threshold, len(subjects) + 1)
    _require(lower_threshold <= upper_threshold, "report_group_threshold")


def admit_evaluation_report(payload: bytes) -> EvaluationReport:
    """Admit UTF-8 bytes and internal coherence, preserving the 1.0.0 wire shape."""
    if type(payload) is not bytes:
        raise ReportAdmissionError("report_payload")
    if len(payload) > MAX_REPORT_BYTES:
        raise ReportAdmissionError("report_input_bytes")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise ReportAdmissionError("report_utf8") from None
    try:
        _json_depth(text, MAX_REPORT_DEPTH)
        document = strict_json_loads(text)
        _decoded_values(document, MAX_REPORT_VALUES)
    except AdministrativeAdmissionError as error:
        code = {"json_depth": "report_json_depth", "decoded_values": "report_decoded_values"}
        raise ReportAdmissionError(cast(ReportCode, code.get(error.code, "report_json_syntax"))) from None
    except DuplicateObjectKeyError:
        raise ReportAdmissionError("report_json_duplicate_key") from None
    except NonFiniteNumberError:
        raise ReportAdmissionError("report_json_number") from None
    except RecursionError:
        raise ReportAdmissionError("report_decoder_capacity") from None
    except ValueError:
        raise ReportAdmissionError("report_json_syntax") from None
    if not isinstance(document, dict):
        raise ReportAdmissionError("report_shape")
    if document.get("$schema") != REPORT_SCHEMA_ID:
        raise ReportAdmissionError("report_schema")
    try:
        report = EvaluationReport.model_validate_json(text, strict=True)
    except ValidationError as error:
        errors = error.errors(include_url=False, include_context=False, include_input=False)
        first = errors[0]
        code = first["type"]
        if code not in _COHERENCE_CODES:
            head = first["loc"][0] if first["loc"] else None
            code = {"identity_comparison": "report_identity_comparison", "eligibility": "report_eligibility"}.get(head, "report_shape")
        raise ReportAdmissionError(cast(ReportCode, code)) from None
    try:
        _canonical_output(report, MAX_REPORT_BYTES)
    except (ValueError, TypeError, RecursionError):
        raise ReportAdmissionError("report_output") from None
    return report


def readmit_evaluation_report(report: EvaluationReport) -> EvaluationReport:
    """Detach and validate a model, including callers using unchecked model_copy."""
    if not isinstance(report, EvaluationReport):
        raise ReportAdmissionError("report_shape")
    try:
        payload = _canonical_output(report, MAX_REPORT_BYTES)
    except (ValueError, TypeError, RecursionError):
        raise ReportAdmissionError("report_output") from None
    return admit_evaluation_report(payload)


def _same_report_value(actual, expected) -> bool:
    """Compare exact counts/types and structure, with tolerance only for floats."""
    if type(expected) is float:
        return type(actual) in (int, float) and _same_float(actual, expected)
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_same_report_value(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same_report_value(a, b) for a, b in zip(actual, expected))
    return actual == expected


def verify_evaluation_report(
    payload: bytes, *, pack: ScenarioPack | None = None, study: AdministrativeStudy | None = None,
) -> EvaluationReport:
    """Re-admit supplied sources and reproduce the report; surface known bindings first."""
    from .administrative_evaluation import EvaluationError, demonstration_study, evaluate

    report = admit_evaluation_report(payload)
    if pack is not None:
        try:
            pack = admit_pack(_canonical_output(pack, MAX_BYTES))
        except (ValueError, TypeError, AttributeError, RecursionError):
            raise ReportAdmissionError("report_pack_source") from None
        if report.pack_digest != canonical_sha256(pack):
            raise ReportAdmissionError("report_pack_binding")
    if study is not None:
        try:
            study = admit_administrative_study(_canonical_output(study, MAX_BYTES))
        except (ValueError, TypeError, AttributeError, RecursionError):
            raise ReportAdmissionError("report_study_source") from None
        if report.study_digest != canonical_sha256(study):
            raise ReportAdmissionError("report_study_binding")
    if pack is None or study is None:
        raise ReportAdmissionError("report_sources_required")
    try:
        reproduced = evaluate(pack, study, evidence_mode=report.evidence_mode)
    except EvaluationError:
        raise ReportAdmissionError("report_source_binding") from None
    if report.evidence_mode == "fixture_demonstration" and study != demonstration_study(pack):
        raise ReportAdmissionError("report_fixture_identity")
    if not _same_report_value(report.model_dump(mode="json", by_alias=True),
                              reproduced.model_dump(mode="json", by_alias=True)):
        raise ReportAdmissionError("report_recomputation")
    return report
