# How the exam and RFI orchestrator is evaluated

Read this page if you decide what this service is allowed to send a supervisor. The metrics, the
bars and the corpus below are generated from the artifacts that actually gate the build, so they
cannot drift from what runs: `make evals-doc-check` fails the build when this page and those
artifacts disagree.

## How to run it

```sh
make eval              # offline, no credentials
make evals-doc-check   # this page is still true
```

`make gate` runs both on every change.

## Almost every bar here is 1.0, and that is not ambition

Seven of the eight metrics gate at exactly 1.0. Each is a policy decision about what a regulator
is told, and none of them has a sampling process for a rate to describe: a disposition that is
right most of the time is a response pack with a wrong answer in it, and a statutory clock that is
right most of the time is a missed deadline waiting for the case it gets wrong.

`citation_grounding` moved from 0.99 to 1.0 for a narrower reason, and the reason is arithmetic:
the score is a per-case grounding verdict over eleven requests, so a 0.99 bar passed only at
eleven out of eleven. It was a 1.0 wearing a 0.99 label.

## Two design details worth copying

**`blocker_recall` is micro-averaged over blockers, not over cases.** A per-case mean gave the
cases that expect no blocker a free 1.0 each, which is a green tick over an empty set: a large
share of the score was awarded for checking nothing, and a real regression on the rest could still
clear the bar. Averaging over the blockers themselves makes every blocker count once.

**The corpus preconditions RAISE rather than score.** The runner refuses a golden set that plants
no identifier, because a leak metric over a corpus with nothing to leak is a vacuous 1.0; and it
refuses a fixture corpus with no hard-withhold tag, because withhold precision over a corpus with
nothing to withhold reports perfect judgement about a decision it never had to make.

## What is measured, and against what bar

Every bar below lives in `eval/rubrics/*.yaml` next to the argument for it, and the
runner reads it from there. There is no dict of thresholds in the runner any more: a
metric scored with no reviewed bar fails the build, and so does a bar that names no
metric, which is the direction that rots quietly because it rots toward looking well
governed.

The third column is the denominator rule, and it applies only where a score is a
FRACTION over scored positives: such a threshold `t` tolerates a single miss only over
at least `1/(1-t)` of them. `all or nothing` marks a bar that already asks for no
headroom, so a bigger corpus would not change what it means. Each rubric declares which
it is rather than the rule being guessed from the number.

| Metric | Bar | Denominator | What it measures |
|---|---|---|---|
| `blocker_recall` | 1 | all or nothing | Every blocker a reviewer recorded is surfaced, counted per blocker rather than per case. |
| `citation_grounding` | 1 | all or nothing | Every assertion in the response resolves to a document the orchestrator actually holds. |
| `clock_accuracy` | 1 | all or nothing | The response clock the orchestrator computes equals the deadline the golden case declares. |
| `completeness_accuracy` | 1 | all or nothing | The completeness verdict for a response pack equals the one a reviewer assigned. |
| `disposition_accuracy` | 1 | all or nothing | The disposition assigned to each request item equals the one a reviewer assigned by reading it. |
| `entitlement_safety` | 1 | all or nothing | No response pack contains a document the requesting examiner is not entitled to see. |
| `pii_safety` | 0.99 | all or nothing | No raw identifier survives into any emitted record, checked by the shared pack and by an independent planted literal. |
| `withhold_precision` | 1 | all or nothing | Every document the orchestrator withholds is one the corpus marks as legitimately withheld. |

Scored over 11 golden exam requests.

## What is exercised

- **11 golden exam requests** in `eval/datasets/golden_cases.jsonl`, each
  with the disposition, deadline, completeness verdict and blockers a reviewer assigned.
- **0 blockers across 0 of those cases.** That is what `blocker_recall`
  is micro-averaged over, and the distinction is the reason the metric means anything: a
  per-case mean gave the 11 cases with no blockers a free 1.0 each.
- **11 cases plant a raw identifier**, so the leak metric has a target it
  could miss. The runner REFUSES a golden set that plants none, and refuses a fixture
  corpus with no hard-withhold tag, because withhold precision over a corpus with nothing
  to withhold reports perfect judgement about a decision it never had to make.

## What is NOT measured here

Naming this is part of the page, because an unmeasured claim that goes unmentioned reads as a
measured one.

- **The response narrative's prose.** Whether the drafted response reads as a complete, defensible
  answer to the request is a judgement and nothing judges it. That is the largest remaining gap
  here.
- **A real model's words.** Every metric scores a deterministic core against a deterministic fake
  model adapter, so `citation_grounding` measures the VALIDATOR rather than a model's restraint.
- **Production traffic.** Everything here is a golden set. Nothing samples live requests.
