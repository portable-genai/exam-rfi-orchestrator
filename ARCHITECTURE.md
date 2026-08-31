# ARCHITECTURE: Regulatory Exam and RFI Orchestrator (Cop2)

Hexagonal ports-and-adapters. A pure-stdlib domain core speaks only to ports (`typing.Protocol`s);
adapter families implement them; one env var (`EXAMRFI_PROFILE`) swaps the
whole stack with no domain edits.

Profile selection is an exact lookup. Every declared profile has an entry for every port; when
two profiles intentionally reuse one adapter, both entries name it. A missing local or exit
binding never inherits `gcp`, so it cannot import a managed SDK or change data custody silently.

`local` runs the real API, orchestration and deterministic domain with local or synthetic edges.
It may reduce OCR/narration quality, throughput, durability, enterprise identity, managed safety
and telemetry, but it does not change figures, evidence links, escalation rules or schemas.
`make portability` executes this boundary. If a primary managed operation is ever added as a
construction-only seam, the same change must name it in `managed_readiness.py` and refuse both API
startup and Terraform serving authorization until its live integration test exists.

## Layout (`src/exam_rfi_orchestrator/`)
- `domain/` : pure stdlib, no cloud/framework imports. `kernel.py` (vertical-neutral types,
  `StrEnum` taxonomies from the commons), `models.py` (this vertical's frozen artifacts and the
  reviewable-outcome Protocol), `policy.py` (the adopter-owned policy block and its parser),
  `artefact_taxonomy.py` (decomposition, rules D1 to D4), `coverage_engine.py` (the admissibility
  ladder and the coverage rules, A1 to A7 and C1 to C4), `sla_clock.py` (business-day arithmetic
  and the deadline, K1 to K5), `consistency.py` (the closed assertion vocabulary and the
  prior-answer conflict check, X1 and X2), `exhibit_index.py` (deterministic numbering, E1),
  `release_engine.py` (disposition, severity, the release gate, dual control and the pack roll-up,
  S, R and P), `narration.py` (the grounding contract, G1 to G3), `pii.py` (the jurisdiction
  pattern selection and order) and `response_pack_service.py` (the orchestration).
  `domain/triage_service.py` is DELETED rather than deprecated: a surviving keyword-band service
  would be a second, unbanded decision path that still reaches an audit write.
- `ports/` : `@runtime_checkable` Protocols (`AuditSinkPort`, `ReviewRouterPort`,
  `KnowledgeBaseReadPort`, `ObligationsReadPort`, `EvidencePackReadPort`, `GenerationPort`,
  `CaseStorePort`; identity, tracing and evaluation use the commons'), re-exported once with the
  `PORT_PROTOCOLS` map. `identity.py` adds
  this service's own identity vocabulary: what an adapter DECLARES about the end-user
  authentication it provides (`VERIFIED` / `CLIENT_ASSERTED` / `UNIMPLEMENTED`), which is what the
  loopback exposure guard reads, plus the refusal type that carries a status and a reason when no
  end user can be authenticated at all.
- `adapters/{local,gcp,onprem}/` : one adapter per port per profile. GCP imports are lazy.
  `adapters/_review_payload.py` is the shared, redacted conversion to the review kit's wire shape.
- `config.py` : `Settings` + `Container` (lazy DI, dotted `module:Class` bindings loaded from
  `config/settings.yaml`).
- `api/` : FastAPI app wired with the commons identity / S2S / fail-closed helpers.
- `cli/` : a stdlib argparse CLI.
- `agent/` : the optional-but-scaffolded agent surface. `tools.py` holds plain Python callables
  that delegate to the domain services (no business logic of their own) and route escalations
  like every other surface; `agent_card.py` builds the A2A discovery card served at
  `/.well-known/agent-card.json`. Nothing here needs ADK or a cloud SDK to import or test:
  `build_function_tools()` is the single lazily-imported runtime seam.

## Surfaces outside `src/`
- `scripts/` : the demo surface. `demo.py` holds the scripted arc and drives the REAL services;
  `render_ui.py` paints its panels as dependency-free static HTML; `demo_server.py` serves the
  same panels live, one real step per click; `walkthrough.py` drives that server over loopback
  HTTP and asserts every step, which is what lets the presenter tool double as the unattended
  self-test. `portability_demo.py` and `check_docs_links.py` are standalone checks. Nothing here
  is imported by `src/`, and `.dockerignore` keeps all of it out of the serving image.
- `ui/` : the embeddable Next.js micro-frontend. Its security boundary is one policy module
  (`lib/embed-policy.mjs`) shared by the document-layer `proxy.ts` and the same-origin API route,
  plus one server-side identity module (`lib/server/identity.ts`). The browser never asserts an
  actor and never holds the service credential. Delete it with `make drop-ui` if this repo has no
  user-facing surface; the gate checks that decision for consistency in both directions.

## Test layout (`tests/`)
`unit/` (one module or service, driven by the REAL local adapters), `contract/` (the boundary
claims: conformance, the five-way port drift guard, behavioural parity), `integration/` (needs a
live service; marked so the offline gate deselects the whole directory) and `fixtures/` (shared
data only). `contract/canonical.py` holds ONE canonical request per port, so the structural and
behavioural suites cannot quietly assert different things.

## Request pipeline (`ResponsePackService`, then the caller)

Per item, in this order:

1. resolve the principal at the surface, and DERIVE from it the entitlements and (from the policy
   transfer matrix) the permitted evidence jurisdictions. Neither is ever read from a body.
2. mask the question, and build the item's own citation from the masked text.
3. read the obligations for the topic and jurisdiction, masking every row on the way in, and
   recording the explicit "no obligation text available" string with a citation naming the
   register when there are none.
4. decompose into required artefacts (D1 to D4), unioning what the regulator named, the topic
   playbook and the register's floor. Those three DECLARED sources are the whole union: no model
   output is an input here, because a requirement moves the completeness denominator and
   everything downstream of it.
5. retrieve the entitled candidates and fetch any reused evidence packs; mask every title and
   snippet on the way in.
6. resolve any waiver and any extension FROM THE CASE STORE by reference.
7. run the admissibility ladder and compute coverage and completeness (A and C).
8. compute the clock on the jurisdiction's versioned calendar (K).
9. run the prior-answer consistency check over the facts normalised from the produced exhibits (X).
10. number the exhibits by a deterministic sort (E).
11. draft and validate the narrative, discarding it whole on any grounding failure (G).
12. compute the blockers, the disposition, the severity, the release gate and the approval count
    (S and R).
13. write the open-item board row.
14. redact, then write the WORM audit event.
15. the CALLER routes the escalation (R8).

Then, once, for the request: roll the items up into the pack (P), write its audit event, and route
it unconditionally. The audit actor and the review maker are both the verified `Principal`, never
the request body. Routing happens in the same request that produced the result, on the API, CLI and
agent surfaces alike, so an escalation never depends on a later job that may not exist.

## What is deterministic, and what the model does

| Deterministic, pure stdlib, replayable | The model, behind `GenerationPort` |
|---|---|
| decomposition, the admissibility ladder, every withhold decision and its basis | SUGGEST a topic and candidate artefacts for a free-text question, for a person to accept |
| the business-day deadline, the due basis, the band, the internal date and the extension-by date | normalise a produced exhibit into asserted facts from a CLOSED key vocabulary |
| the coverage states, the integer completeness, the exhibit numbering | draft the per-item narrative and the pack cover note from INDEXED exhibits only |
| the prior-answer conflict check, the disposition, the severity, the release gate, the approval count | propose additional artefact classes, advisory, entering no count and no gate |

Every model output has a deterministic validator that DISCARDS it rather than repairing it, and a
hard-withheld document is removed from the prompt inputs before the port is called.

"Advisory" is enforced rather than intended: no suggestion is an argument to any engine function.
A proposed artefact class is shown on the draft and unioned into no requirement, and a suggested
topic is named in the 422 that refuses an item declaring none. Both were once fed back in on the
argument that a union only ever widens, which is true of the artefact set and false of the
completeness denominator, the disposition, the severity, the review flag and the release blockers
that hang off it, and false of the topic in the other direction: the topic is the retrieval and
responsiveness key, so a wrong one drops every document the firm holds for that question.

## Spans
Two, one per unit of work: `exam.assess_item` and `exam.assemble_pack`. Both carry STRUCTURAL
attributes only, the action and the actor, and never an item reference, a question or a document
title. A span is not a redacted sink, and in this vertical a document title is the fact a
withholding rule exists to keep off surfaces. `tests/unit/test_span_content.py` holds the
attribute keys to a fixed allowlist.

## The port table
| Port | local | gcp | onprem |
|---|---|---|---|
| `AuditSinkPort` | hash-chained SQLite WORM (commons) | Cloud Logging WORM (lazy) | placeholder |
| `IdentityPort` | seeded personas (commons) | IAP assertion (lazy) | placeholder |
| `ReviewRouterPort` | review-kit outbox (offline, inspectable) | review console intake over S2S | placeholder |
| `KnowledgeBaseReadPort` | deterministic fixture corpus with ACL labels, handling tags and effective dates | the governed store over HTTPS, refusing when unconfigured | placeholder |
| `ObligationsReadPort` | deterministic fixture register, one pair deliberately unseeded | the obligation register's read surface | placeholder |
| `EvidencePackReadPort` | fixture packs, three deliberately non-responsive documents | the assembled-pack read surface | placeholder |
| `GenerationPort` | deterministic SDK-free narrator, plus a seeded UNGROUNDED response | the configured managed model, refusing when none is named | placeholder |
| `CaseStorePort` | SQLite board with the ACL filter in the query, one seeded waiver and one extension | Firestore in the residency region | placeholder |
| `ObservabilityTracerPort` | no-op | Cloud Trace or OTLP | ABSENT by design |
| `EvaluationGatePort` | offline scoring, refuses to promote | the promotion authority | placeholder |

The on-prem placeholders RAISE. A review router that silently returned would convert every
consequential result into an unreviewed one; a RETRIEVAL seam that returned an empty tuple would
not look broken at all, it would look like a firm that holds no responsive evidence, and that is
what would go to the supervisor over somebody's signature. The case store's `waiver()` and
`extension()` raise rather than returning `None` for the same reason: `None` means "no such record
exists", which would silently withhold a waived document and silently refuse to move a granted
deadline.

One deliberate deviation from the fleet's retrieval shape: `KnowledgeBaseReadPort.search` returns
a `RetrievalResult` rather than a bare tuple, because `suppressed_by_entitlement` is what turns
"nothing came back" into "responsive documents exist that you may not read", and
`suppressed_by_artefact` is what keeps that sentence attached to the class it is true of rather
than to every class the item asked for. The port's docstring carries that reason, so the
deviation is a decision somebody owns.

A port is registered in FIVE places: `ports/__init__.py` (`PORT_PROTOCOLS`), `config.py`
(`DEFAULT_BINDINGS` and a `Container` accessor), `config/settings.yaml` and
`tests/contract/canonical.py`. `tests/contract/test_port_parity.py` asserts set equality across
all five, so a port that is bound but unregistered (or registered but unbound) fails the build
instead of running with no enforcement. The full touch list is in `CONTRIBUTING.md`.

## Audit integrity
The local WORM log is hash-chained AND anchored: `audit_anchor_path` points at an external file,
on a different volume, that every append writes the chain head to. The chain alone catches an
edit, a deletion or a reorder; only the anchor catches a truncated tail, because a truncated
chain still verifies. `tests/unit/test_audit_anchor.py` proves both halves, including the
control case where the same truncation goes undetected without an anchor.
