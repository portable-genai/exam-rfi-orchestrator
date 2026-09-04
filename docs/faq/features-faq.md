# Features FAQ

For product, compliance and delivery. What the engine does, what is deterministic, and where this
repo stops.

### What does it actually do?

It turns an incoming exam request list or supervisory inquiry into a managed, citation-backed
response pack.

1. **Decomposes** each question into the artefacts it demands, against the artefact taxonomy.
2. **Retrieves** candidate evidence entitlement-aware, through the knowledge base port.
3. **Applies the admissibility ladder** to each candidate: responsive, in period, privileged,
   restricted, silently withheld or stale.
4. **Tracks the clocks**: signed business-day arithmetic on a named, versioned calendar, with the
   regulator's date, the internal buffer and the regime cap.
5. **Computes coverage and completeness** per item and for the pack.
6. **Checks consistency** against prior answers.
7. **Numbers the exhibits** and builds the document index.
8. **Drafts the narrative**, then holds everything for a checker.

### What is deterministic, and what does the model write?

The consequential path is pure stdlib and replayable: the decomposition requirement, the
admissibility ladder, the deadline, the coverage states, the completeness number, the consistency
check, the exhibit numbering, the disposition, the severity, the release blockers and the approval
count.

The model has four narrow jobs, each with a validator that discards bad output rather than
repairing it: SUGGEST a topic and candidate artefacts (to a person, never unioned into anything),
NORMALISE an exhibit into a closed assertion vocabulary, DRAFT the narrative from indexed exhibits
only, and PROPOSE artefact classes the playbook may have missed (advisory, an argument to no
engine function).

It is never shown a hard-withheld document: withheld candidates are removed from the prompt inputs
by the engine before the port is called. See [`../model-card.md`](../model-card.md).

### What will it refuse to do?

These are worth reading before the feature list, because an exam team will assume otherwise.

- **File anything with a regulator.**
- **Grant, request or infer an extension.** A reference on the wire is a lookup key into the case
  store; a client assertion moves no date.
- **Decide privilege.** It NAMES the basis on a withholding schedule and holds the document. A
  lawyer decides.
- **Release a pack.** Every outcome comes back held for a checker. There is no code path in this
  service that returns `released`.
- **Assert that any shipped policy number is currently correct in law.**

### Which surfaces expose it?

| Route | What it drives |
|---|---|
| `POST /v1/response-pack` | The whole assembly for one request list: decomposition, retrieval, ladder, clocks, coverage, consistency, exhibit index, draft narrative, blockers, and the held disposition. |
| `GET /v1/personas` | The read-only persona listing the console uses. |

### Why does the withhold ladder run in that order?

`coverage_engine.py` evaluates A1, A2, A4, A5, A6, A3. The withhold rules run before the staleness
rule A3 deliberately: A3 first would give a stale-but-privileged document the status A3 treats as
still usable, and the document would be produced. The ordering is a disclosure control, not a
style choice.

### What does this repo own, and what does it integrate?

**Owns:** the artefact taxonomy, the admissibility ladder, the SLA clocks and calendars, the
coverage and completeness engines, the prior-answer consistency check, the exhibit index, the
release gate and the approval rules.

**Integrates, and must not rebuild:**

| Sibling | Boundary |
|---|---|
| `enterprise-knowledge-base` | Owns ACL-aware retrieval and the index. This service reaches it as a PORT and builds no second index. |
| `human-review-console` | Owns maker-checker. Every outcome is routed to it (rule R8). |
| `agent-registry` | Discovery, via the A2A card. |
| `model-quality-gate` eval / quality gate | Owns promotion verdicts. |
| `agent-observability` and WORM audit | Owns the immutable audit sink and traces. |
| `agent-guardrail-gateway` | **Not bound.** Rule R1 applies here: untrusted document and question text reaches a live model. |

### Can I demo it without a cloud project?

Yes. `make demo` runs the whole arc on loopback with the `local` profile: fixture corpus,
obligation register, evidence packs, prior answers and regulator, and a deterministic narration
stub. No credentials, no network, no SDK. `make demo-selftest` runs the same arc headless and
exits non-zero when a step stops being true.

### What is not built yet?

The catalog row for `exam-rfi-orchestrator` carries the honest list. The headline items: the managed knowledge-base,
obligations, evidence-pack and case-store adapters refuse correctly when unconfigured but their
live payload parsing is unwired and no live upstream has been exercised; the case store's
Firestore resources are absent from `infra/terraform/`; `agent-guardrail-gateway`, `agent-observability` and `agent-registry` are unwired;
decomposition recall is unmeasured and unmeasurable offline; and the regime cap rule K3 is
exercised by unit tests alone because every shipped register row fixes no response window.
