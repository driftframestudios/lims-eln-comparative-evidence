"""Independent score populations and adversarial saved-report receiving cases."""

from copy import deepcopy
from html import unescape
from importlib.util import find_spec
import json
import unittest
from unittest.mock import patch

HAS_PROFILE = (
    find_spec("lims_eln_contracts") is not None
    and find_spec("lims_eln_sim") is not None
    and find_spec("lims_eln_contracts.study_interpretation") is not None
    and find_spec("lims_eln_sim.administrative_pack") is not None
)
if HAS_PROFILE:
    from lims_eln_contracts.administrative_study import admit_administrative_study
    from lims_eln_contracts.canonical import canonical_json_bytes, canonical_sha256
    from lims_eln_contracts.study_interpretation import StudyInterpretation
    from lims_eln_sim.administrative_pack import admit_pack, build_pack
    from comparative_evidence.administrative_evaluation import demonstration_study, evaluate, render_html
    from comparative_evidence.administrative_report import (
        MAX_REPORT_BYTES, MAX_REPORT_VALUES, PROFILE, REPORT_SCHEMA_ID, ReportAdmissionError,
        admit_evaluation_report, verify_evaluation_report,
    )


def fraction(numerator, denominator, value):
    return {"numerator": numerator, "denominator": denominator, "value": value}


def independent_document():
    """Four literal observations: {A}/{A}, {A}/{B}, empty/empty, {A,B}/{A,B}."""
    digest = "sha256:" + "1" * 64
    rows = []
    for index, (exact, science, required, found, unsupported, supplied, minutes) in enumerate((
        (True, True, 1, 1, 0, 1, 10), (False, False, 1, 0, 1, 1, 20),
        (True, True, 0, 0, 0, 0, 5), (True, True, 2, 2, 0, 2, 25),
    )):
        pair = "SYN-PAIR-" + str(index // 2)
        rows.append({
            "run_id": "SYN-RUN-" + str(index), "pair_id": pair,
            "subject_id": "SYN-SUBJECT-" + str(index // 2), "cohort": "SYN-COHORT",
            "arm": "a" if index % 2 == 0 else "b", "repeat_index": 0,
            "status": "completed", "standing": "scored", "exact_labels": exact,
            "jaccard": 1.0 if exact else 0.0, "classification_matches": exact,
            "policy_matches": True, "raw_preserved": True, "required_facts": required,
            "found_required_facts": found, "unsupported_facts": unsupported,
            "supplied_facts": supplied, "scientific_matches": science, "workflow_minutes": minutes,
        })
    comparison = {
        "$schema": "urn:driftframe:lims-eln:administrative-study-comparison:1.0.0",
        "study_digest": digest, "planned": 4, "attempted": 4, "completed": 4,
        "pending": 0, "abstained": 0, "failed": 0, "cancelled": 0, "excluded": 0,
        "comparisons": [{
            "pair_id": "SYN-PAIR-" + str(index), "standing": "comparable", "reason_fields": [],
            "scientific_changed": True, "administrative_changed": True,
            "expected_invariant_violations": ["scientific"], "oracle_agrees": False,
        } for index in range(2)],
    }
    eligibility = {
        "$schema": "urn:driftframe:lims-eln:study-interpretation:1.0.0", "study_digest": digest,
        "profile": {"profile_id": "declared-input-comparison", "version": "1.0.0",
                    "required_specified_controls": [], "require_expected_pair": False},
        "comparison": deepcopy(comparison),
        "pairs": [{
            "pair_id": "SYN-PAIR-" + str(index), "controls": [], "declared_input_equal": True,
            "execution": "matched", "usable_arms": 2, "expected_pair_available": True,
            "reasons": [], "eligible": True,
        } for index in range(2)],
        "planned_pairs": 2, "eligible_pairs": 2, "excluded_pairs": 0,
        "expected_pairs_available": 2, "usable_runs": 4,
    }
    return {
        "$schema": REPORT_SCHEMA_ID, "pack_digest": "sha256:" + "2" * 64, "study_digest": digest,
        "scoring_digest": canonical_sha256(PROFILE), "evidence_mode": "caller_supplied_synthetic",
        "planned_runs": 4, "attempted_runs": 4, "completed_runs": 4, "attempt_records": 4,
        "status_counts": {"completed": 4}, "scored_coverage": fraction(4, 4, 1.0),
        "exact_label_agreement": fraction(3, 4, 0.75), "mean_jaccard": 0.75,
        "micro_precision": fraction(3, 4, 0.75), "micro_recall": fraction(3, 4, 0.75),
        "micro_f1": fraction(6, 8, 0.75), "macro_f1": 11 / 15,
        "required_fact_recall": fraction(3, 4, 0.75), "unsupported_fact_rate": fraction(1, 4, 0.25),
        "classification_agreement": fraction(3, 4, 0.75), "policy_agreement": fraction(4, 4, 1.0),
        "raw_preservation": fraction(4, 4, 1.0), "scientific_oracle_disagreements": 1,
        "labels": [
            {"label": "SYN-A", "support": 3, "true_positive": 2, "false_positive": 0, "false_negative": 1,
             "precision": fraction(2, 2, 1.0), "recall": fraction(2, 3, 2 / 3), "f1": fraction(4, 5, 0.8)},
            {"label": "SYN-B", "support": 1, "true_positive": 1, "false_positive": 1, "false_negative": 0,
             "precision": fraction(1, 2, 0.5), "recall": fraction(1, 1, 1.0), "f1": fraction(2, 3, 2 / 3)},
        ],
        "groups": [
            {"cohort": "SYN-COHORT", "planned_runs": 4, "attempted_runs": 4, "completed_runs": 4,
             "scored_runs": 4, "complete_pairs": 2, "independent_subjects": 2,
             "standing": "descriptive", "workflow_difference_minutes": 15.0},
            {"cohort": "SYN-EMPTY", "planned_runs": 0, "attempted_runs": 0, "completed_runs": 0,
             "scored_runs": 0, "complete_pairs": 0, "independent_subjects": 0,
             "standing": "empty", "workflow_difference_minutes": None},
        ],
        "runs": rows, "identity_comparison": comparison, "eligibility": eligibility,
    }


def with_label_sets(populations):
    """Independent set oracle for the four-run identity fixture."""
    document = independent_document()
    populations = [(set(expected), set(observed)) for expected, observed in populations]
    assert len(populations) == len(document["runs"])
    counts = {}
    for run, (expected, observed) in zip(document["runs"], populations, strict=True):
        run.update(exact_labels=expected == observed,
                   jaccard=len(expected & observed) / len(expected | observed) if expected | observed else 1.0)
        for label in expected | observed:
            tp, fp, fn = counts.setdefault(label, [0, 0, 0])
            counts[label] = [tp + int(label in expected & observed),
                             fp + int(label in observed - expected),
                             fn + int(label in expected - observed)]
    def divided(n, d):
        return fraction(n, d, n / d if d else None)
    document["labels"] = [
        {"label": label, "support": tp + fn, "true_positive": tp,
         "false_positive": fp, "false_negative": fn,
         "precision": divided(tp, tp + fp), "recall": divided(tp, tp + fn),
         "f1": divided(2 * tp, 2 * tp + fp + fn)}
        for label, (tp, fp, fn) in sorted(counts.items())
    ]
    tp, fp, fn = (sum(values[index] for values in counts.values()) for index in range(3))
    document.update(
        exact_label_agreement=divided(sum(run["exact_labels"] for run in document["runs"]), 4),
        mean_jaccard=sum(run["jaccard"] for run in document["runs"]) / 4,
        micro_precision=divided(tp, tp + fp), micro_recall=divided(tp, tp + fn),
        micro_f1=divided(2 * tp, 2 * tp + fp + fn),
        macro_f1=sum(row["f1"]["value"] for row in document["labels"]) / len(counts) if counts else None,
    )
    return document


@unittest.skipUnless(HAS_PROFILE, "administrative-study profile supplies the source-owned contracts")
class AdministrativeReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = build_pack(repeats=1)
        cls.study = demonstration_study(cls.pack)
        cls.report = evaluate(cls.pack, cls.study)

    def admit(self, document):
        return admit_evaluation_report(canonical_json_bytes(document))

    def rejected(self, document, code):
        with self.assertRaises(ReportAdmissionError) as held:
            self.admit(document)
        self.assertEqual(code, held.exception.code)
        self.assertIsNone(held.exception.__cause__)

    def test_independent_counts_scores_and_empty_cohort(self):
        report = self.admit(independent_document())
        self.assertEqual((4, 4, 4, 4), (report.planned_runs, report.attempted_runs, report.completed_runs,
                                      report.scored_coverage.numerator))
        self.assertEqual((3, 4, 0.75), (report.micro_precision.numerator, report.micro_precision.denominator,
                                      report.micro_precision.value))
        self.assertAlmostEqual(11 / 15, report.macro_f1)
        self.assertEqual((2, 2, 15.0), (report.groups[0].complete_pairs, report.groups[0].independent_subjects,
                                       report.groups[0].workflow_difference_minutes))
        self.assertEqual(0, report.groups[1].scored_runs)
        self.assertIsNone(report.groups[1].workflow_difference_minutes)
        self.assertEqual((0, 0, 1.0), (report.runs[2].required_facts, report.runs[2].supplied_facts,
                                       report.runs[2].jaccard))

    def test_joint_bounds_preserve_independent_set_populations_and_html(self):
        full = tuple(f"SYN-{index}" for index in range(16))
        populations = (
            [((), ())] * 4,
            [(("SYN-A",), ("SYN-B",))] * 4,
            [(full, full)] * 4,
            [(("SYN-A", "SYN-B"), ("SYN-B", "SYN-C")),
             (("SYN-A",), ("SYN-A", "SYN-B")),
             ((), ("SYN-A",)), (("SYN-A",), ())],
            [(full, ("SYN-EXTRA",)), (("SYN-A",), full), ((), ()), (full, full)],
        )
        for population in populations:
            with self.subTest(population=population):
                document = with_label_sets(population)
                report = self.admit(document)
                embedded = render_html(report).split('<pre id="report-json">', 1)[1].split("</pre>", 1)[0]
                self.assertEqual(report.model_dump(mode="json", by_alias=True), json.loads(unescape(embedded)))
                self.assertEqual(document["micro_f1"], report.micro_f1.model_dump())

    def test_joint_totals_reject_uniform_and_mixed_score_contradictions(self):
        for scores in ((0.5,) * 4, (0.5, 0.5, 0.25, 0.25)):
            with self.subTest(scores=scores):
                document = with_label_sets([(("SYN-A", "SYN-B"), ("SYN-A", "SYN-B", "SYN-C"))] * 4)
                self.assertEqual(fraction(8, 12, 2 / 3), document["micro_precision"])
                self.assertEqual(fraction(16, 20, 0.8), document["micro_f1"])
                for run, score in zip(document["runs"], scores, strict=True):
                    run["jaccard"] = score
                document["mean_jaccard"] = sum(scores) / 4
                self.rejected(document, "report_label_joint_counts")
                unchecked = type(self.report).model_construct(**document)
                with self.assertRaises(ReportAdmissionError):
                    render_html(unchecked)

    def test_joint_cardinality_admission_retains_float_tolerance(self):
        document = with_label_sets([(("SYN-A",), ("SYN-A", "SYN-B"))] * 4)
        for run in document["runs"]:
            run["jaccard"] += 5e-13
        document["mean_jaccard"] = document["runs"][0]["jaccard"]
        self.admit(document)
        for run in document["runs"]:
            run["jaccard"] += 1e-6
        document["mean_jaccard"] = document["runs"][0]["jaccard"]
        self.rejected(document, "report_run_score")

    def test_generated_roundtrip_typed_records_and_recomputation(self):
        payload = canonical_json_bytes(self.report)
        admitted = admit_evaluation_report(payload)
        self.assertIsInstance(admitted.eligibility, StudyInterpretation)
        self.assertEqual(payload, canonical_json_bytes(admitted))
        self.assertEqual(admitted, verify_evaluation_report(payload, pack=self.pack, study=self.study))
        schema = type(admitted).model_json_schema()
        self.assertIn("$ref", schema["properties"]["eligibility"])
        self.assertEqual(512, schema["properties"]["runs"]["maxItems"])

    def test_matching_empty_missing_and_duplicate_nested_records(self):
        for target in ("identity_comparison", "eligibility"):
            for kind in ("empty", "missing", "duplicate"):
                document = independent_document()
                key = "comparisons" if target == "identity_comparison" else "pairs"
                records = document[target][key]
                if kind == "empty":
                    records.clear()
                elif kind == "missing":
                    records.pop()
                else:
                    records.append(deepcopy(records[0]))
                self.rejected(document, "report_" + target)
        document = independent_document()
        document["identity_comparison"]["comparisons"] = []
        document["eligibility"]["comparison"]["comparisons"] = []
        document["eligibility"]["pairs"] = []
        self.rejected(document, "report_identity_comparison")

    def test_ratio_conventions_ranges_and_exact_integer_counts(self):
        for value in (None, 0.1):
            document = independent_document()
            document["micro_f1"]["value"] = value
            self.rejected(document, "report_ratio")
        for value in (-1, 1.1, True):
            document = independent_document()
            document["micro_f1"]["value"] = value
            self.rejected(document, "report_shape")
        for value in (-1, 6.0, True, 100001):
            document = independent_document()
            document["micro_f1"]["numerator"] = value
            self.rejected(document, "report_shape")
        for numerator, denominator, value in ((1, 0, None), (0, 0, 0.0), (2, 1, 1.0)):
            document = independent_document()
            document["micro_f1"] = fraction(numerator, denominator, value)
            self.rejected(document, "report_ratio")
        document = independent_document()
        document["micro_f1"] = fraction(3, 4, 0.75)
        self.rejected(document, "report_label_counts")

    def test_explicit_float_tolerance(self):
        document = independent_document()
        document["micro_f1"]["value"] += 5e-13
        self.admit(document)
        document["micro_f1"]["value"] += 1e-6
        self.rejected(document, "report_ratio")

    def test_run_partitions_missing_duplicate_and_field_coherence(self):
        changes = (
            (lambda d: d["runs"].pop(), "report_run_coverage"),
            (lambda d: d["runs"].append(deepcopy(d["runs"][0])), "report_run_coverage"),
            (lambda d: d["runs"][1].update(arm="a"), "report_pair_coverage"),
            (lambda d: d["runs"][1].update(cohort="SYN-OTHER"), "report_pair_coverage"),
            (lambda d: d["runs"][1].update(subject_id="SYN-OTHER"), "report_pair_coverage"),
            (lambda d: d["runs"][1].update(repeat_index=1), "report_pair_coverage"),
            (lambda d: d["status_counts"].update(completed=3, failed=1), "report_status_counts"),
            (lambda d: d.update(attempt_records=3), "report_attempt_counts"),
            (lambda d: d["runs"][0].update(jaccard=0.5), "report_run_score"),
            (lambda d: d["runs"][0].update(found_required_facts=2), "report_run_score"),
            (lambda d: d["runs"][0].update(workflow_minutes=1441), "report_shape"),
            (lambda d: d["runs"][0].update(scientific_matches=False), "report_run_score"),
            (lambda d: d.update(scientific_oracle_disagreements=0), "report_score_counts"),
        )
        for change, code in changes:
            with self.subTest(code=code, change=change):
                document = independent_document()
                change(document)
                self.rejected(document, code)

    def test_group_counts_membership_subjects_and_withholding(self):
        changes = (
            (lambda d: d["groups"].pop(0), "report_group_coverage"),
            (lambda d: d["groups"].append(deepcopy(d["groups"][0])), "report_group_coverage"),
            (lambda d: d["groups"][0].update(complete_pairs=1), "report_group_counts"),
            (lambda d: d["groups"][0].update(independent_subjects=1), "report_group_counts"),
            (lambda d: d["groups"][0].update(scored_runs=3), "report_group_counts"),
            (lambda d: d["groups"][0].update(workflow_difference_minutes=10.0), "report_group_estimate"),
            (lambda d: d["groups"][1].update(workflow_difference_minutes=0.0), "report_group_estimate"),
            (lambda d: d["groups"][0].update(standing="small_cell"), "report_group_estimate"),
        )
        for change, code in changes:
            with self.subTest(code=code):
                document = independent_document()
                change(document)
                self.rejected(document, code)
        document = independent_document()
        document["groups"][0].update(standing="small_cell", workflow_difference_minutes=None)
        self.admit(document)  # A supported threshold of three can explain withholding.

    def test_labels_aggregate_union_and_unsupported_values(self):
        for change, code in (
            (lambda d: d["labels"].append(deepcopy(d["labels"][0])), "report_label_counts"),
            (lambda d: d["labels"][0].update(support=2), "report_label_score"),
            (lambda d: d.update(macro_f1=None), "report_label_counts"),
            (lambda d: d["runs"][0].update(extra_score=0), "report_shape"),
        ):
            document = independent_document()
            change(document)
            self.rejected(document, code)

    def test_absent_sparse_all_failed_and_mismatched_outputs(self):
        for mode in ("absent", "sparse", "failed", "mismatch"):
            document = self.study.model_dump(mode="json", by_alias=True)
            if mode == "absent":
                document["observations"] = []
                expected = (0, 0, 0, 72)
            elif mode == "sparse":
                document["observations"] = [next(row for row in document["observations"] if row["status"] == "completed")]
                expected = (1, 1, 1, 71)
            elif mode == "failed":
                document["observations"] = [row for row in document["observations"] if row["status"] == "completed"]
                for row in document["observations"]:
                    row.update(status="failed", reason_code="SYN-FAILED")
                    row.pop("administrative_output")
                    row.pop("scientific_output")
                expected = (64, 0, 0, 8)
            else:
                for row in document["observations"]:
                    if row.get("execution"):
                        row["execution"]["model_id"] = "SYN-OTHER"
                expected = (68, 64, 0, 2)
            with self.subTest(mode=mode):
                study = admit_administrative_study(canonical_json_bytes(document))
                report = self.admit(evaluate(self.pack, study))
                self.assertEqual(expected, (report.attempted_runs, report.completed_runs,
                                             report.scored_coverage.numerator, report.status_counts["pending"]))
                self.assertTrue(all(group.workflow_difference_minutes is None for group in report.groups))
                if mode != "sparse":
                    self.assertIsNone(report.micro_f1.value)
                    self.assertIsNone(report.macro_f1)
                self.assertEqual(report, verify_evaluation_report(canonical_json_bytes(report), pack=self.pack, study=study))

    def test_prediction_only_label_is_in_macro_denominator(self):
        document = self.study.model_dump(mode="json", by_alias=True)
        row = next(row for row in document["observations"] if row["status"] == "completed")
        actual = json.loads(row["administrative_output"]["text"])
        actual["labels"].append("SYN-PREDICTION-ONLY")
        text = canonical_json_bytes(actual).decode()
        row["administrative_output"].update(text=text, digest=canonical_sha256(text))
        study = admit_administrative_study(canonical_json_bytes(document))
        report = self.admit(evaluate(self.pack, study))
        extra = next(label for label in report.labels if label.label == "SYN-PREDICTION-ONLY")
        self.assertEqual((0, 1, None, 0.0), (extra.support, extra.false_positive, extra.recall.value, extra.f1.value))
        self.assertEqual(4, len(report.labels))
        self.assertAlmostEqual(0.75, report.macro_f1)
        self.assertIn("including prediction-only labels", render_html(report))

    def test_one_differing_run_cannot_supply_two_errors_for_one_label(self):
        document = independent_document()
        document["labels"][0].update(
            false_positive=1, precision=fraction(2, 3, 2 / 3), f1=fraction(4, 6, 2 / 3),
        )
        document.update(
            micro_precision=fraction(3, 5, 3 / 5), micro_f1=fraction(6, 9, 2 / 3),
            macro_f1=2 / 3,
        )
        self.assertEqual(1, sum(not row["exact_labels"] for row in document["runs"]))
        self.rejected(document, "report_label_counts")

    def test_positive_nonexact_jaccards_require_true_positives(self):
        document = independent_document()
        for row in document["labels"]:
            row.update(
                true_positive=0, false_positive=1, false_negative=1, support=1,
                precision=fraction(0, 1, 0.0), recall=fraction(0, 1, 0.0),
                f1=fraction(0, 2, 0.0),
            )
        for row in document["runs"]:
            row.update(exact_labels=False, jaccard=0.5)
        document.update(
            exact_label_agreement=fraction(0, 4, 0.0), mean_jaccard=0.5,
            micro_precision=fraction(0, 2, 0.0), micro_recall=fraction(0, 2, 0.0),
            micro_f1=fraction(0, 4, 0.0), macro_f1=0.0,
        )
        self.assertEqual(0, sum(row["true_positive"] for row in document["labels"]))
        self.rejected(document, "report_label_counts")

    def test_zero_overlap_and_partial_overlap_bound_label_true_positives(self):
        for jaccards in ((0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.5)):
            document = independent_document()
            for row, jaccard in zip(document["runs"], jaccards):
                row.update(exact_labels=False, jaccard=jaccard)
            document.update(exact_label_agreement=fraction(0, 4, 0.0),
                            mean_jaccard=sum(jaccards) / 4,
                            micro_precision=fraction(3, 6, 0.5),
                            micro_f1=fraction(6, 10, 0.6), macro_f1=0.6)
            document["labels"][1].update(false_positive=3,
                                        precision=fraction(1, 4, 0.25), f1=fraction(2, 5, 0.4))
            # Retain the independently declared three true positives. Even the
            # partial-overlap case permits only one occurrence of SYN-A, not two.
            with self.subTest(jaccards=jaccards):
                self.rejected(document, "report_label_counts")

    def test_total_true_positives_fit_the_positive_overlap_run_capacity(self):
        document = independent_document()
        for index, row in enumerate(document["runs"]):
            row.update(exact_labels=index == 0, jaccard=1.0 if index == 0 else 0.0)
        document["labels"] = [
            {"label": f"SYN-COMMON-{index}", "support": 1, "true_positive": 1,
             "false_positive": 0, "false_negative": 0,
             "precision": fraction(1, 1, 1.0), "recall": fraction(1, 1, 1.0),
             "f1": fraction(2, 2, 1.0)}
            for index in range(17)
        ] + [
            {"label": "SYN-EXTRA", "support": 0, "true_positive": 0,
             "false_positive": 3, "false_negative": 0,
             "precision": fraction(0, 3, 0.0), "recall": fraction(0, 0, None),
             "f1": fraction(0, 3, 0.0)},
        ]
        document.update(
            exact_label_agreement=fraction(1, 4, 0.25), mean_jaccard=0.25,
            micro_precision=fraction(17, 20, 17 / 20), micro_recall=fraction(17, 17, 1.0),
            micro_f1=fraction(34, 37, 34 / 37), macro_f1=17 / 18,
        )
        # Every individual label fits one overlapping run; their total exceeds
        # that run's sixteen-label bound while fitting the four-run population.
        self.rejected(document, "report_label_counts")

    def test_nonexact_jaccard_bounds_intersection_below_sixteen(self):
        document = independent_document()
        for index, row in enumerate(document["runs"]):
            row.update(exact_labels=False, jaccard=0.5 if index == 0 else 0.0)
        # Sixteen intersections plus sixteen extra labels yield aggregate
        # precision 1/2, but the single overlapping run permits at most ten
        # intersections at Jaccard 1/2 with sixteen labels per side.
        document["labels"] = [
            {"label": f"SYN-COMMON-{index}", "support": 1, "true_positive": 1,
             "false_positive": 0, "false_negative": 0,
             "precision": fraction(1, 1, 1.0), "recall": fraction(1, 1, 1.0),
             "f1": fraction(2, 2, 1.0)}
            for index in range(16)
        ] + [
            {"label": f"SYN-EXTRA-{index}", "support": 0, "true_positive": 0,
             "false_positive": 1, "false_negative": 0,
             "precision": fraction(0, 1, 0.0), "recall": fraction(0, 0, None),
             "f1": fraction(0, 1, 0.0)}
            for index in range(16)
        ]
        document.update(
            exact_label_agreement=fraction(0, 4, 0.0), mean_jaccard=0.125,
            micro_precision=fraction(16, 32, 0.5), micro_recall=fraction(16, 16, 1.0),
            micro_f1=fraction(32, 48, 2 / 3), macro_f1=0.5,
        )
        self.rejected(document, "report_label_counts")

    def test_valid_empty_disjoint_and_positive_intersection_populations(self):
        # Each case declares its complete label universe and four set comparisons.
        cases = (
            {
                "name": "four matching empty sets", "jaccards": (1.0, 1.0, 1.0, 1.0),
                "labels": [], "exact": fraction(4, 4, 1.0), "mean": 1.0,
                "precision": fraction(0, 0, None), "recall": fraction(0, 0, None),
                "f1": fraction(0, 0, None), "macro": None, "true_positives": 0,
            },
            {
                "name": "A to empty, empty to A, two matching empty sets",
                "jaccards": (0.0, 0.0, 1.0, 1.0),
                "labels": [
                    {"label": "SYN-A", "support": 1, "true_positive": 0,
                     "false_positive": 1, "false_negative": 1,
                     "precision": fraction(0, 1, 0.0), "recall": fraction(0, 1, 0.0),
                     "f1": fraction(0, 2, 0.0)},
                ],
                "exact": fraction(2, 4, 0.5), "mean": 0.5,
                "precision": fraction(0, 1, 0.0), "recall": fraction(0, 1, 0.0),
                "f1": fraction(0, 2, 0.0), "macro": 0.0, "true_positives": 0,
            },
            {
                "name": "A to A-and-B, three matching empty sets",
                "jaccards": (0.5, 1.0, 1.0, 1.0),
                "labels": [
                    {"label": "SYN-A", "support": 1, "true_positive": 1,
                     "false_positive": 0, "false_negative": 0,
                     "precision": fraction(1, 1, 1.0), "recall": fraction(1, 1, 1.0),
                     "f1": fraction(2, 2, 1.0)},
                    {"label": "SYN-B", "support": 0, "true_positive": 0,
                     "false_positive": 1, "false_negative": 0,
                     "precision": fraction(0, 1, 0.0), "recall": fraction(0, 0, None),
                     "f1": fraction(0, 1, 0.0)},
                ],
                "exact": fraction(3, 4, 0.75), "mean": 0.875,
                "precision": fraction(1, 2, 0.5), "recall": fraction(1, 1, 1.0),
                "f1": fraction(2, 3, 2 / 3), "macro": 0.5, "true_positives": 1,
            },
        )
        for case in cases:
            with self.subTest(population=case["name"]):
                document = independent_document()
                for row, jaccard in zip(document["runs"], case["jaccards"]):
                    row.update(exact_labels=jaccard == 1.0, jaccard=jaccard)
                document.update(
                    labels=case["labels"], exact_label_agreement=case["exact"],
                    mean_jaccard=case["mean"], micro_precision=case["precision"],
                    micro_recall=case["recall"], micro_f1=case["f1"], macro_f1=case["macro"],
                )
                report = self.admit(document)
                self.assertEqual(case["true_positives"], sum(row.true_positive for row in report.labels))
                self.assertEqual(case["macro"], report.macro_f1)

    def test_source_mismatches_precede_missing_source(self):
        payload = canonical_json_bytes(self.report)
        for sources, code in (
            ({}, "report_sources_required"),
            ({"pack": self.pack}, "report_sources_required"),
            ({"study": self.study}, "report_sources_required"),
            ({"pack": build_pack(repeats=2)}, "report_pack_binding"),
            ({"study": self.pack.study}, "report_study_binding"),
        ):
            with self.subTest(code=code), self.assertRaises(ReportAdmissionError) as held:
                verify_evaluation_report(payload, **sources)
            self.assertEqual(code, held.exception.code)
        document = independent_document()
        document["scoring_digest"] = "sha256:" + "9" * 64
        self.rejected(document, "report_scoring_binding")
        document = independent_document()
        document["study_digest"] = "sha256:" + "9" * 64
        self.rejected(document, "report_study_binding")

    def test_coherent_altered_score_requires_source_recomputation(self):
        document = self.report.model_dump(mode="json", by_alias=True)
        row = next(row for row in document["runs"] if row["standing"] == "scored")
        row["classification_matches"] = False
        score = document["classification_agreement"]
        score.update(numerator=63, value=63 / 64)
        payload = canonical_json_bytes(document)
        self.assertEqual(63, admit_evaluation_report(payload).classification_agreement.numerator)
        with self.assertRaises(ReportAdmissionError) as held:
            verify_evaluation_report(payload, pack=self.pack, study=self.study)
        self.assertEqual("report_recomputation", held.exception.code)

    def test_pack_threshold_requires_source_recomputation(self):
        document = self.report.model_dump(mode="json", by_alias=True)
        for group in document["groups"]:
            if group["standing"] == "descriptive":
                group.update(standing="small_cell", workflow_difference_minutes=None)
        payload = canonical_json_bytes(document)
        admit_evaluation_report(payload)
        with self.assertRaises(ReportAdmissionError) as held:
            verify_evaluation_report(payload, pack=self.pack, study=self.study)
        self.assertEqual("report_recomputation", held.exception.code)

    def test_fixture_label_receives_its_source_check(self):
        report = evaluate(self.pack, self.pack.study, evidence_mode="fixture_demonstration")
        with self.assertRaises(ReportAdmissionError) as held:
            verify_evaluation_report(canonical_json_bytes(report), pack=self.pack, study=self.pack.study)
        self.assertEqual("report_fixture_identity", held.exception.code)

    def test_strict_parser_budgets_and_safe_errors(self):
        cases = (
            (b"\xff", "report_utf8"), (b"\xef\xbb\xbf{}", "report_json_syntax"),
            (b'{"private-canary":0,"private-canary":1}', "report_json_duplicate_key"),
            (b'{"private-canary":NaN}', "report_json_number"),
            (b'{"private-canary":1e9999}', "report_json_number"),
            (b"[" * 33 + b"0" + b"]" * 33, "report_json_depth"),
            (b"[" + b"0," * MAX_REPORT_VALUES + b"0]", "report_decoded_values"),
            (b" " * (MAX_REPORT_BYTES + 1), "report_input_bytes"),
            (b'{"unfinished":', "report_json_syntax"), (b"[]", "report_shape"),
            (b"{}", "report_schema"), ("{}", "report_payload"),
        )
        for payload, code in cases:
            with self.subTest(code=code), self.assertRaises(ReportAdmissionError) as held:
                admit_evaluation_report(payload)
            self.assertEqual(code, held.exception.code)
            self.assertNotIn("private-canary", str(held.exception))
            self.assertIsNone(held.exception.__cause__)
        with patch("comparative_evidence.administrative_report.strict_json_loads") as decode:
            with self.assertRaises(ReportAdmissionError):
                admit_evaluation_report(b"[" * 33 + b"]" * 33)
            decode.assert_not_called()

    def test_collection_and_nested_metadata_bounds(self):
        document = independent_document()
        document["runs"] *= 129
        self.rejected(document, "report_shape")
        document = independent_document()
        document["eligibility"]["pairs"][0]["metadata"] = {"unbounded": "private-canary"}
        self.rejected(document, "report_eligibility")
        document = independent_document()
        document["eligibility"]["pairs"][0]["eligible"] = False
        self.rejected(document, "report_eligibility")

    def test_decoded_budget_covers_each_generated_record_owner(self):
        # Expand the structural envelope independently. Repeated identities and
        # reasons here count capacity; semantic report admission has its own tests.
        document = self.report.model_dump(mode="json", by_alias=True)
        document["status_counts"] = {status: 0 for status in (
            "completed", "pending", "abstained", "failed", "timeout",
            "invalid_response", "cancelled", "excluded",
        )}
        document["runs"] = [document["runs"][0]] * 512
        document["labels"] = [document["labels"][0]] * 16384
        document["groups"] = [document["groups"][0]] * 8
        for comparison in (document["identity_comparison"], document["eligibility"]["comparison"]):
            row = deepcopy(comparison["comparisons"][0])
            row["reason_fields"] = ["source control"] * 35
            row["expected_invariant_violations"] = ["scientific", "administrative"]
            comparison["comparisons"] = [row] * 256
        pair = deepcopy(document["eligibility"]["pairs"][0])
        pair["controls"] = [{
            "a": {"name": "source_control", "standing": "specified", "value": "a"},
            "b": {"name": "source_control", "standing": "specified", "value": "b"},
        }] * 32
        pair["reasons"] = ["source control"] * 36
        document["eligibility"]["pairs"] = [pair] * 256
        pending, values = [document], 0
        while pending:
            item = pending.pop()
            values += 1
            if isinstance(item, dict):
                values += len(item)
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
        self.assertEqual(773229, values)
        self.assertEqual(values, MAX_REPORT_VALUES)

    def test_html_uses_admitted_values_and_rejects_unchecked_copy(self):
        report = self.admit(independent_document())
        html = render_html(report)
        embedded = html.split('<pre id="report-json">', 1)[1].split("</pre>", 1)[0]
        self.assertEqual(report.model_dump(mode="json", by_alias=True), json.loads(unescape(embedded)))
        with self.assertRaises(ReportAdmissionError) as held:
            render_html(report.model_copy(update={"planned_runs": 5}))
        self.assertEqual("report_run_coverage", held.exception.code)


if __name__ == "__main__":
    unittest.main()
