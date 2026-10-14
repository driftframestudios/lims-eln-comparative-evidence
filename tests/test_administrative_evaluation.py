"""Independent scoring expectations and source-bound failure counterexamples."""
from importlib.util import find_spec
from html import unescape
import json
from pathlib import Path
import unittest

HAS_CONTRACTS = (
    find_spec("lims_eln_contracts") is not None
    and find_spec("lims_eln_sim") is not None
    and find_spec("lims_eln_contracts.administrative_study") is not None
    and find_spec("lims_eln_contracts.study_interpretation") is not None
    and find_spec("lims_eln_sim.administrative_pack") is not None
)
if HAS_CONTRACTS:
    from lims_eln_contracts.administrative_study import admit_administrative_study
    from lims_eln_contracts.canonical import canonical_json_bytes,canonical_sha256
    from lims_eln_sim.administrative_pack import PackBoundaryError,admit_pack,build_pack
    from comparative_evidence.administrative_evaluation import EvaluationError,demonstration_study,evaluate,render_html


@unittest.skipUnless(HAS_CONTRACTS,"administrative-study extra supplies exact Program and Simulation sources")
class AdministrativeEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack=build_pack(repeats=1)
        cls.study=demonstration_study(cls.pack)

    def changed(self,change):
        document=self.study.model_dump(mode="json",by_alias=True)
        change(document)
        return admit_administrative_study(canonical_json_bytes(document))

    def test_complete_denominators_and_injected_scientific_difference(self):
        report=evaluate(self.pack,self.study,evidence_mode="fixture_demonstration")
        self.assertEqual(72,report.planned_runs)
        self.assertEqual(68,report.attempted_runs)
        self.assertEqual(64,report.completed_runs)
        self.assertEqual(64,report.scored_coverage.numerator)
        self.assertEqual({"completed":64,"failed":2,"abstained":2,"pending":2,"excluded":2},report.status_counts)
        self.assertEqual(2,report.scientific_oracle_disagreements)
        self.assertEqual(126,report.required_fact_recall.numerator)
        self.assertEqual(128,report.required_fact_recall.denominator)
        self.assertEqual(2,report.unsupported_fact_rate.numerator)
        self.assertEqual(1.0,report.exact_label_agreement.value)
        self.assertEqual(1.0,report.policy_agreement.value)
        self.assertEqual(1.0,report.raw_preservation.value)

    def test_missing_all_observations_preserves_planned_denominator(self):
        report=evaluate(self.pack,self.pack.study)
        self.assertEqual(72,report.status_counts["pending"])
        self.assertEqual(0,report.scored_coverage.numerator)
        self.assertIsNone(report.micro_f1.value)
        self.assertIsNone(report.exact_label_agreement.value)

    def test_metrics_detect_incorrect_multilabel_output(self):
        def change(document):
            item=next(o for o in document["observations"] if "MULTIPLE" in o["run_id"] and o["run_id"].endswith("-b"))
            output=json.loads(item["administrative_output"]["text"])
            output["labels"]=["SYN-EMPLOYER","SYN-EXTRA"]
            text=canonical_json_bytes(output).decode()
            item["administrative_output"].update(text=text,digest=canonical_sha256(text))
        report=evaluate(self.pack,self.changed(change))
        extra=next(row for row in report.labels if row.label=="SYN-EXTRA")
        public=next(row for row in report.labels if row.label=="SYN-PUBLIC")
        self.assertEqual(1,extra.false_positive)
        self.assertEqual(1,public.false_negative)
        self.assertEqual(63,report.exact_label_agreement.numerator)
        changed=next(row for row in report.runs if "MULTIPLE" in row.run_id and row.exact_labels is False)
        self.assertAlmostEqual(1/3,changed.jaccard)

    def test_actual_provider_change_remains_visible_and_unscored(self):
        def change(doc): doc["observations"][0]["execution"]["model_id"]="SYN-OTHER"
        report=evaluate(self.pack,self.changed(change))
        self.assertEqual(63,report.scored_coverage.numerator)
        self.assertEqual(1,sum(row.standing=="execution_mismatch" for row in report.runs))
        self.assertTrue(any(pair["execution"]=="mismatched" for pair in report.eligibility["pairs"]))

    def test_reordered_input_preserves_scoring(self):
        def change(doc):
            doc["runs"].reverse();doc["observations"].reverse();doc["expected_pairs"].reverse()
        first=evaluate(self.pack,self.study)
        second=evaluate(self.pack,self.changed(change))
        self.assertEqual(first.runs,second.runs)
        self.assertEqual(first.groups,second.groups)
        self.assertEqual(first.micro_f1,second.micro_f1)

    def test_observer_is_independent_of_expected_values(self):
        # A deliberately unadmitted in-memory double proves producer independence.
        altered = self.pack.expected[0].model_copy(update={"labels": ("SYN-DIFFERENT",)})
        changed = self.pack.model_copy(update={"expected": (altered,) + self.pack.expected[1:]})
        self.assertEqual(self.study,demonstration_study(changed))
        with self.assertRaises(PackBoundaryError):
            admit_pack(canonical_json_bytes(changed))

    def test_requested_identity_cannot_rename_the_actual_producer(self):
        document = self.pack.model_dump(mode="json", by_alias=True)
        document["study"]["specification"]["expected_execution"]["model_id"] = "SYN-OTHER-PRODUCER"
        pack = admit_pack(canonical_json_bytes(document))
        observed = demonstration_study(pack)
        self.assertEqual({"SYN-RESPONSE-FIXTURE"}, {row.execution.model_id for row in observed.observations if row.execution is not None})
        report = evaluate(pack, observed)
        self.assertEqual(0, report.scored_coverage.numerator)
        self.assertEqual(64, sum(row.standing == "execution_mismatch" for row in report.runs))
        self.assertEqual(72, len(report.runs))

    def test_program_eligibility_gates_the_paired_estimator(self):
        # Exercise defense for trusted in-memory callers; byte admission rejects this source edit.
        document = self.pack.study.model_dump(mode="json", by_alias=True)
        changed = next(row for row in document["runs"] if "REPORTABILITY-ADULT-EN" in row["run_id"] and row["arm"] == "b")
        changed["scientific_evidence"] = "Different controlled evidence"
        study = admit_administrative_study(canonical_json_bytes(document))
        pack = self.pack.model_copy(update={"study": study})
        with self.assertRaises(PackBoundaryError):
            admit_pack(canonical_json_bytes(pack))
        report = evaluate(pack, demonstration_study(pack))
        baseline = evaluate(self.pack, self.study)
        eligibility = next(row for row in report.eligibility["pairs"] if row["pair_id"] == changed["pair_id"])
        self.assertFalse(eligibility["eligible"])
        self.assertIn("controlled_input_mismatch", eligibility["reasons"])
        self.assertEqual(baseline.groups[0].complete_pairs - 1, report.groups[0].complete_pairs)
        self.assertEqual(baseline.groups[1].complete_pairs, report.groups[1].complete_pairs)
        self.assertEqual(baseline.scored_coverage, report.scored_coverage)
        self.assertEqual(72, len(report.runs))

    def test_empty_and_small_group_scores_are_withheld(self):
        doc=self.pack.model_dump(mode="json",by_alias=True)
        doc["design"]["minimum_subjects"]=32
        report=evaluate(admit_pack(canonical_json_bytes(doc)),self.study)
        self.assertEqual(["small_cell","small_cell","empty"],[group.standing for group in report.groups])
        self.assertTrue(all(group.workflow_difference_minutes is None for group in report.groups))
        self.assertEqual(72,sum(group.planned_runs for group in report.groups))

    def test_shape_errors_preserve_run_and_execution_counts(self):
        for text in ('{"labels":[]}', '{"facts":[],"facts":[]}', '{"x":NaN}'):
            def change(doc): doc["observations"][0]["administrative_output"].update(text=text,digest=canonical_sha256(text))
            with self.subTest(text=text):
                report=evaluate(self.pack,self.changed(change))
                self.assertEqual(64,report.completed_runs)
                self.assertEqual(63,report.scored_coverage.numerator)

    def test_input_binding_rejects_changed_scientific_source(self):
        document=self.pack.study.model_dump(mode="json",by_alias=True)
        document["runs"][0]["scientific_evidence"]="Another authored source"
        with self.assertRaises(EvaluationError): evaluate(self.pack,admit_administrative_study(canonical_json_bytes(document)))

    def test_rendered_and_machine_report_agree_and_keep_raw_text_local(self):
        report=evaluate(self.pack,self.study)
        html=render_html(report)
        embedded=html.split('<pre id="report-json">',1)[1].split("</pre>",1)[0]
        self.assertEqual(report.model_dump(mode="json",by_alias=True),json.loads(unescape(embedded)))
        self.assertIn('role="region"',html)
        self.assertIn('data-canary="maps"',html)
        self.assertIn('data-canary="big-bench"',html)
        self.assertNotIn("  Commercial  ",html)

    def test_unequal_complete_repeats_keep_equal_subject_weights(self):
        pack = build_pack(repeats=2)
        study = demonstration_study(pack)
        # Five paired differences produce subject means 0, 10, 20.
        # Their equal-subject mean is 10; a pair-weighted mean would be 12.
        differences = {
            ('SYN-CASE-REPEAT', 0): 0,
            ('SYN-CASE-MULTIPLE', 0): 4,
            ('SYN-CASE-MULTIPLE', 1): 16,
            ('SYN-CASE-REPORTABILITY', 0): 14,
            ('SYN-CASE-REPORTABILITY', 1): 26,
        }
        cohorts = {row.run_id: row.cohort for row in pack.expected}
        selected = {
            run.run_id: run for run in study.runs
            if cohorts[run.run_id] == 'SYN-COHORT-ADULT-EN'
            and (run.scenario_id, run.repeat_index) in differences
        }
        self.assertEqual(10, len(selected))
        document = study.model_dump(mode='json', by_alias=True)
        observations = []
        for observation in document['observations']:
            run = selected.get(observation['run_id'])
            if run is None:
                continue
            self.assertEqual('completed', observation['status'])
            output = json.loads(observation['administrative_output']['text'])
            delta = differences[(run.scenario_id, run.repeat_index)]
            output['workflow_minutes'] = 100 + (delta if run.arm == 'b' else 0)
            text = canonical_json_bytes(output).decode()
            observation['administrative_output'].update(text=text, digest=canonical_sha256(text))
            observations.append(observation)
        for reverse in (False, True):
            with self.subTest(reversed_observations=reverse):
                document['observations'] = list(reversed(observations)) if reverse else observations
                observed = admit_administrative_study(canonical_json_bytes(document))
                report = evaluate(pack, observed)
                group = next(row for row in report.groups if row.cohort == 'SYN-COHORT-ADULT-EN')
                self.assertEqual(144, report.planned_runs)
                self.assertEqual(10, report.attempted_runs)
                self.assertEqual(10, report.completed_runs)
                self.assertEqual(10, report.scored_coverage.numerator)
                self.assertEqual(134, report.status_counts['pending'])
                self.assertEqual(5, group.complete_pairs)
                self.assertEqual(3, group.independent_subjects)
                self.assertEqual('descriptive', group.standing)
                self.assertAlmostEqual(10.0, group.workflow_difference_minutes)

    def test_repeated_subjects_are_counted_once_and_pair_order_is_balanced(self):
        pack=build_pack(repeats=2)
        study=demonstration_study(pack)
        report=evaluate(pack,study)
        self.assertEqual(14,report.groups[0].independent_subjects)
        self.assertEqual(28,report.groups[0].complete_pairs)
        plans={run.run_id:run for run in study.runs}
        for repeat in (0,1):
            observations=[o for o in study.observations if plans[o.run_id].scenario_id=="SYN-CASE-REPEAT" and plans[o.run_id].repeat_index==repeat and "ADULT-EN" in o.run_id]
            self.assertEqual("a" if repeat==0 else "b",plans[observations[0].run_id].arm)


class AdministrativeOrientationTests(unittest.TestCase):
    def test_quick_start_and_receiving_routes(self):
        root=Path(__file__).resolve().parents[1]
        text=(root/"README.md").read_text()
        self.assertLess(text.index("--output build/first-comparison"),text.index("## Choose your route"))
        for target in ("lims-eln-comparative-evidence/issues/44","lims-eln-program-specification/issues/54","lims-eln-comparative-evidence/issues/40","docs/administrative-evaluation.md"):
            self.assertIn(target,text)
        self.assertTrue((root/"docs/administrative-evaluation.md").is_file())


if __name__ == "__main__": unittest.main()
