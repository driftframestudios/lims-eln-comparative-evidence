# Compare administrative observations

Inspect normalization quality, policy agreement, scientific-content findings,
and workflow differences in one bounded offline comparison. Each score retains
its denominator, source pack, recorded execution, and independent expectation.

## Quick start

Use Python 3.12 or newer from this checkout. The optional profile resolves exact
Program and Simulation commits through the collaborator's existing Git access.
The ordinary Golden Specimen and observed-evidence routes remain independently
available through the [root README](../README.md#start-with-a-comparison).

```bash
python3 -m venv .venv-admin
.venv-admin/bin/python -m pip install --editable ".[administrative-study]"
.venv-admin/bin/python -m lims_eln_sim.administrative_pack \
  --output build/administrative-pack.json
.venv-admin/bin/python -m comparative_evidence.administrative_evaluation \
  --pack build/administrative-pack.json --fixture-demo \
  --output build/administrative-comparison
```

Open `build/administrative-comparison/comparison.html`. The directory also holds
the exact `comparison.json` and Program-admitted `study.json`. The default pack
plans 144 runs. Its demonstration includes abstention, failure, exclusion,
pending observations, and an intentionally changed scientific fact. Those
findings exercise the observer; they are useful evidence about this harness.

Choose a fresh destination for a separate comparison. To score a receiving team's
synthetic observations, replace `--fixture-demo` with `--study STUDY_JSON`.
The study must bind the same plans, specification, and expected-pair identities.
Actual outputs can agree, differ, remain partial, or carry a failed attempt.

## Read the scores

| Question | Result | Denominator and meaning |
| --- | --- | --- |
| Did normalization return the expected set? | Exact set agreement and Jaccard | Scored runs; two empty sets have Jaccard one |
| Which labels need attention? | Per-label counts, micro precision/recall/F1, macro F1 | Micro pools label decisions; macro weights supported labels equally |
| Was uncertainty or policy interpreted as expected? | Classification and policy agreement | Scored runs, beside planned-run coverage |
| Was raw source retained? | Exact raw-label preservation | Scored runs; original text stays in the local study |
| Was required information carried forward? | Required-fact recall | Required facts in scored runs |
| Was unsupported information introduced? | Unsupported-fact rate | Supplied facts in scored runs |
| What happened to workflow effort? | Paired difference in minutes | Within-subject repeat mean, then equal weight per complete paired subject |

Undefined ratios are `null`. Empty and small groups retain counts while their
workflow score stays withheld. The group threshold counts independent subjects,
rather than runs. The full local diagnostic report retains run-level findings;
its small-cell display rule is an interpretive safeguard, rather than a privacy
release mechanism. Any public population extract receives its own disclosure review.

Program's byte-identity comparison and eligibility companion remain separate
report sections. Parsed field scoring can distinguish harmless text formatting
from changed content. Probability calibration needs probability outputs, and
inferential intervals need a reviewed sampling design. This deliberately authored
distribution supports fixture and observer correctness; broader population,
causal, fairness, and deployment conclusions retain their own evidence routes.

## Ownership, recovery, and extension

Simulation owns the input pack and expected results. Comparative's fixture
producer uses its own literal rules and creates a separate observation artifact.
The evaluator admits caller observations through Program and computes scores
from those observations. Altering an expectation changes the evaluation while
the demonstration's emitted observations stay stable.

Every planned run remains visible, including unattempted and incomplete work.
Retain `study.json` as the finite observation checkpoint. A renewed comparison
can read that artifact without executing a model. Changed plans or specification
receive a successor study; existing observations keep their original bindings.

[Enterprise #36](https://github.com/driftframestudios/lims-eln-enterprise-implementation/issues/36)
owns the broader adapter handoff. [#40](https://github.com/driftframestudios/lims-eln-comparative-evidence/issues/40)
owns additional source admission and exercised recovery procedures.
[#44](https://github.com/driftframestudios/lims-eln-comparative-evidence/issues/44)
retains the independent Golden Specimen measurement question. Publication,
release tags, and external model execution remain separately authorized.

Return to [first receipt](../README.md#first-receipt).

## Execution identity and paired evidence

The local demonstration records its own versioned producer identity and actual
repeat settings. A different requested identity appears as an execution mismatch
through the existing Program interpretation. Matching an authored fixture shows
that the evaluator can recognize the expected result; external model behavior
has its own authorized receiving study.

Paired workflow estimates require Program eligibility and two usable scored
outputs. Every planned run remains in coverage, including runs belonging to an
ineligible pair. The complete report retains Program's reasons alongside the
field-level scores, so a receiving reviewer can distinguish coverage, substantive
agreement, and comparison eligibility.
