# Model card: Regulatory Exam and RFI Orchestrator (`exam-rfi-orchestrator`)

This is a STARTER model card. It records the model boundary as built and the controls that must be
completed before a managed deployment.

**The deterministic engine is the system of record; the model is a bounded, replaceable
component.** Every consequential step is pure stdlib: the decomposition requirement, the
admissibility ladder, the deadline, the coverage states, the completeness number, the consistency
check, the exhibit numbering, the disposition, the severity, the release blockers and the approval
count. Binding a generative port added obligations, and this card is where they are listed rather
than discovered.

## What the model does, and does not do

Four narrow jobs behind `ports/generation.py`, each with a deterministic validator in
`domain/narration.py` that **discards** bad output rather than repairing it:

| # | Job | What bounds it |
|---|---|---|
| 1 | **SUGGEST** a topic and candidate artefact set for a free-text question | The suggestion goes to a PERSON. The surface refuses an item that declares no topic and names the suggestion in the refusal. It is never unioned into anything, because the topic is rule A2's responsiveness key and a wrong one would drop every document the firm holds for that question. |
| 2 | **NORMALISE** a produced exhibit into asserted facts | Only the closed assertion vocabulary is accepted. An unrecognised assertion becomes an `UNRECOGNISED_ASSERTION` release blocker, not a silent pass. |
| 3 | **DRAFT** the per-item narrative and pack cover note | From INDEXED exhibits only, checked against a citation-grounding contract. |
| 4 | **PROPOSE** artefact classes the playbook may have missed | Advisory in the literal sense: displayed on the draft, an argument to no engine function. It enters no requirement, no count and no gate. |

**Does NOT**: set an artefact requirement, a coverage state, a withhold, a deadline, a band, a
completeness number, an exhibit number, a disposition, a release blocker or an approval count.

It is also **never shown a hard-withheld document at all**. Withheld candidates are removed from
the prompt inputs by the engine before the port is called, so privilege containment does not
depend on the model behaving.

Every request builder, parser and predicate in `narration.py` is a module-level pure function, so
the evaluation scores RAW model output through the same contract the service enforces and
`citation_grounding` can actually go red. Repairing a draft would move that contract outside the
pure domain where the eval cannot reach it.

## Adapters and profiles

| Profile | Generation adapter | Behaviour |
|---|---|---|
| `local` | `adapters/local/generation.py` | Deterministic stub. SDK-free, no model, no network. |
| `gcp` | `adapters/gcp/generation.py` | Reaches a managed model. The model id is per-deployment configuration read three-state through `Settings`: unset and emptied both arrive as `""` and the adapter **refuses** rather than picking a default, because a banner naming a model the deployment never calls is worse than a refusal. `temperature=0.2`, `response_mime_type="application/json"`, a per-request `max_output_tokens`. The adapter returns the response RAW and never parses, repairs or validates. |
| `onprem` | `adapters/onprem/generation.py` | Fail-fast placeholder naming the client-hosted gateway to bind. |

## Boundary as built

- A model is reachable through exactly one port with one method. There is no second model seam in
  the request path.
- Personal data is masked before anything is audited, and the audit stores the redacted text.
- Nothing is released. There is no code path in this service that returns `released`; every
  outcome comes back held for a checker (rule R8).
- The service does not decide privilege. It NAMES the basis on a withholding schedule and holds
  the document; a lawyer decides.

## Remaining controls (TODO, repo owner)

- **Model id, version and region** (P-07, P-11). The adapter correctly refuses without
  `EXAMRFI_GENERATION_MODEL`, but nothing pins WHICH model a deployment should set, confirms it is
  served in the deployment region, or records the served version at promotion. Pin it and record
  it here.
- **Per-request token budget and rate limit** (P-10). `max_output_tokens` is carried per request;
  there is no per-tenant aggregate budget and no rate limit.
- **A documented kill switch** (P-11). Unsetting the model id makes the managed adapter refuse,
  which is a deterministic-only mode by accident rather than a designed operator action. Make it
  one and document it in the runbook.
- **No retrieval cache**. Each run re-reaches the knowledge base.
- **Prompt-injection screening** (rule R1). `agent-guardrail-gateway` is not bound. The inputs here are documents and
  question text supplied by parties outside this service.
- **Reasoning trace** (P-07). The audit carries the redacted outcome and its citations, not a
  prompt and reply pair.
- **Managed-profile evaluation** (P-08, rule R5). The offline eval scores the deterministic
  pipeline with the stub bound. Add a managed-profile run registered with the `model-quality-gate`.

## What the eval does and does not prove

`disposition_accuracy`, `clock_accuracy`, `completeness_accuracy`, `withhold_precision`,
`blocker_recall`, `entitlement_safety` and `pii_safety` are scored against golden cases built from
the SHIPPED fixture corpus. That proves the engine is consistent with its own corpus. It does not
prove a real submission would be defensible, and two limits are worth stating explicitly:

- **Decomposition recall is unmeasured and unmeasurable offline.** Turning a question into the
  artefacts it demands is a draft a checker corrects, not a completeness guarantee.
- **Prior-answer consistency has good precision and unmeasured recall.**

## The classification inputs are the corpus's, not this service's

Privilege, restricted-filing status and cross-border restriction are decided by the CORPUS's
handling tags. A mislabelled document is produced; a document wrongly tagged privileged is
withheld from a regulator entitled to it. That is a data-governance dependency, not a model risk,
and it is the single most consequential input this service does not control.

One configuration note that belongs here because it looks like a model-risk control and is not:
`min_completeness_pct_for_release` ships at 100, which is correct for a regulator submission and
also exactly how an exam lead learns to ignore the release state. It is a default to argue with.

## Reference data

The corpus, obligation register, evidence packs, prior answers and regulator are all FIXTURES with
fictional names and `.example` domains. A green self-test proves the engine is consistent with its
own corpus, and nothing more.
