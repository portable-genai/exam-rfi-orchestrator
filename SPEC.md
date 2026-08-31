# SPEC: Regulatory Exam and RFI Orchestrator (Cop2)

Locked decisions, pinned stack, contracts. This document is the deepest authority on intent.

## Pinned stack
- Python `>=3.12`; ruff pinned exactly (`0.16.4`); mypy strict; deploy region `asia-southeast1`.
- Commons declared by tag in `pyproject.toml` (`pii-kit@v0.0.1`, `hex-service-kit@v0.0.6`, `agent-eval-kit@v0.0.1`, `review-kit@v0.0.1`) and pinned in the lockfiles to the 40-character COMMIT each tag resolved to. A tag can be moved; a commit cannot, so a lockfile that pinned the tag would let what installs change with no diff. `tests/unit/test_repo_artifacts.py` asserts the three-way agreement offline.
- The `hex-service-kit` pin is a security floor, not a preference: releases from v0.4.0 onward
  check the service-identity policy before the token, gate the zero-secret local opening on an
  exact profile match, and bind the loopback exposure guard over both HTTP and WebSocket scopes;
  v0.5.1 resolves every environment read in three states, so a variable set to empty fails closed
  instead of inheriting the unset default. Never move this pin backwards.
- Installs are LOCKED: `requirements-dev.lock` and `requirements-gcp.lock` are committed and are
  what `make install`, CI and the container image install. Nothing ships from an uncommitted
  resolve.

## Contracts
- **Identity**: a request's actor is a server-verified `Principal`; the client-supplied actor is
  discarded. Local profile resolves a seeded dev persona from `X-Dev-Persona`.
- **Redaction before anything**: every retrieved title and snippet, every obligation-register row
  (its title, its rule reference and its citation) and the question itself is masked (via
  `pii-kit`) the moment it enters the service: before the engine, before the model and before the
  audit write. Every inbound port that returns TEXT is masked, and the register is one of them: it
  is an external system of record, and a row naming the officer responsible for a control is an
  ordinary row. No raw identifier reaches the WORM store, a citation, a draft, a span or the
  review console. Masking after an immutable write is too late. The audit write masks AGAIN and
  that repetition is deliberate: it is the last line of defence on the immutable record, so it is
  falsified on its own rather than by the upstream masks happening to have run first.
- **Determinism, named**: PURE STDLIB and replayable are the decomposition of a question into
  required artefacts, the admissibility ladder over ACL labels, handling tags and effective dates,
  the business-day deadline on a named and versioned calendar, the coverage states, the integer
  completeness, the prior-answer consistency check, the exhibit numbering, the disposition, the
  severity, the release gate and the approval count. The MODEL may SUGGEST a topic and artefact
  classes for a free-text question, normalise a produced exhibit into asserted facts, and draft
  the narrative and cover note. It sets no requirement, no coverage state, no withhold, no date,
  no band, no count, no exhibit number, no disposition, no release blocker and no approval count,
  in any profile, and nothing it returns is an input to any of them.
- **The topic is DECLARED by the caller, never chosen by the model.** It is not a label: it is the
  retrieval key, the obligation-register key and rule A2's responsiveness filter, so a wrong topic
  drops every document the firm holds for that question and the pack then states that no
  admissible document of that class was produced. A classification can therefore NARROW an answer,
  which is why an item carrying no topic is REFUSED with a 422 that names what the classifier
  would have suggested, rather than assessed on the suggestion. The same rule is why a proposed
  artefact class enters no requirement: a requirement moves the completeness denominator, a
  coverage state, the disposition, the severity, the review flag and the release blockers. The
  BOUND of this claim, stated rather than left implied: this service never asks a model what the
  topic is and never acts on the answer when it does ask. On the agent surface the topic is a
  required tool argument, and an agent runtime calling that tool is supplying it like any other
  caller; what protects that path is rule R8, not this rule.
- **Entitlement is fail-closed and decided in the pure domain.** A document is readable only when
  its ACL labels are a subset of the caller's server-verified entitlements, so an empty principal
  reads untagged documents and never everything. The retrieval port additionally reports
  `suppressed_by_entitlement`, the COUNT of responsive documents the store refused this principal,
  and `suppressed_by_artefact`, that count split by artefact class: counts and nothing else, no
  title and no id. The count is what turns an empty answer into "responsive documents exist that
  you may not read" rather than "the firm holds nothing responsive", and a regulator told the
  second when the first is true has been given a materially false statement. The SPLIT is what
  keeps that sentence attached to the class it is true of: an item-level total alone made it true
  of every class the item asked for, including the ones the firm genuinely holds nothing of, which
  is the same false statement pointed the other way. A store that reports a total it cannot
  attribute keeps the over-broad reading, because understating a denial is the worse error. A
  document that
  nevertheless arrives exceeding the entitlements is DROPPED and raises at CRITICAL, because there
  the retrieval boundary failed rather than the caller.
- **DENIED never collapses into MISSING, and never spreads into it either.** "You are not entitled
  to see this" and "the firm holds no such document" are materially different statements to a
  regulator and only one of them is true. They are separate coverage states, separate blocker
  kinds and separate rows on every surface, including the console's. The separation is enforced in
  both directions: a class reads DENIED only where a document OF THAT CLASS was suppressed.
- **A hard withhold is never indexed, never quoted, never shown to the model and always recorded.**
  A withheld document gets a row on the withholding schedule with a stated basis and the id of the
  rule that decided it; it reaches no exhibit, no citation snippet, no narrative and no generation
  prompt. The SILENT-WITHHOLD asymmetry is configuration, not code: a tag in
  `policy.silent_withhold_tags` produces a row carrying an identifier and a basis and NO title,
  because in several regimes the existence of that filing is itself restricted. The adopter's
  counsel owns that list. The engine FLAGS privilege and never adjudicates it.
- **A waiver and an extension are STORED RECORDS resolved by reference.** The request carries
  `waiver_ref` and `extension_ref`, and both are lookup keys into the case store. A client-asserted
  waiver unlocks no privileged document and a client-asserted extension moves no regulatory
  deadline. A key that resolves to nothing, an expired record and a record filed under another
  tenant are all the same answer.
- **Prior-answer consistency**: facts normalised out of the produced exhibits are compared against
  the answers the firm already gave this regulator. A contradiction raises a blocker naming BOTH
  values with both citations. The assertion vocabulary is CLOSED (`KNOWN_ASSERTION_KEYS`) and an
  unrecognised key raises rather than being ignored, because a model that renamed a key would
  otherwise switch the whole check off in silence. The check has good PRECISION and unmeasured
  RECALL, and nothing here catches a contradiction the model failed to extract.
- **Grounding**: with zero admissible evidence the generation port is NOT CALLED at all and the
  item carries a blocker; empty retrieval is never an ungrounded answer. A draft that cites an
  exhibit outside this item's index, cites nothing at all, carries an integer the engine did not
  produce, or fails the response schema is DISCARDED WHOLE and replaced by a deterministic
  paragraph assembled from the accepted links. Nothing is ever repaired. The request builder, the
  parser and both grounding predicates are module-level pure functions, so the evaluation scores
  RAW model output through the same contract the service enforces.
- **Release**: every outcome carries `release_state = held_for_checker`. `released` exists in the
  vocabulary and NO code path in this service produces it: release happens in the human-review
  console, by a person, and an operator sends the production. The guard is proved against a
  planted mutant that returns `released`, and `docs/practices-audit.md` records that it was
  observed failing first.
- **Release is a separate question from disposition.** The disposition answers "can this be
  produced in time"; the release gate answers "may it leave the firm". An on-track item below the
  completeness floor is still blocked from release, and the checker is handed NAMED blocker kinds
  rather than a score.
- **Maker-checker (P-06) and routing (R8)**: an item whose severity is HIGH or CRITICAL sets
  `requires_human_review=True` AND is routed through `ReviewRouterPort` in the same request. The
  PACK routes unconditionally, including when every item in it is clean, because the contract is
  that a regulator response is approved before it leaves the firm: a clean pack routes for
  APPROVAL rather than for rescue. The flag alone is not the escalation. The response carries
  `review_ref`. The managed adapter refuses to run with no console configured rather than
  swallowing the escalation.
- **The approval count has exactly one owner.** Rule R3 in the engine decides it (two for a pack,
  two for an instrument in `policy.dual_control_instruments`, two at CRITICAL severity, otherwise
  one) and `adapters/_review_payload.py` READS it. A severity-keyed table in the adapter and this
  rule disagree the first time an instrument-driven case appears at low severity, which is exactly
  a skilled-person review: dual control, no escalation. A contract test asserts the adapter has no
  approvals rule of its own.
- **Policy is configuration.** The `policy:` block in `config/settings.yaml` carries every response
  window, the review buffer, the extension-notice period, the staleness limit, the band ceilings,
  the completeness floor, the evidence cap, the withhold tag lists, the transfer matrix, the
  dual-control rules, the named-regime register and the per-jurisdiction calendars with their
  VERSIONS. No number an exam response turns on is a module constant. Every one of them is
  reference policy, is not legal advice, and is owned by the adopter's counsel.
- **Profile**: resolved ONCE, at import, into a `ProfileChoice` and never a bare string. Three
  states of `EXAMRFI_PROFILE`: UNSET is NO CHOICE (the SDK-free adapters
  still bind, but the seeded personas are refused, no service-to-service scheme is selected, every
  relaxation sees `unconfigured` and the exposure guard refuses every route to a non-loopback
  peer); SET AND EMPTY raises, so it can never inherit the unset behaviour; SET AND UNKNOWN,
  including a mis-capitalised value, raises. Only a deliberately named profile is honoured, and
  both raises happen before the process can serve anything.
- **Two derived postures, opposite directions**: `exposure_profile` drives every RELAXATION (CORS
  allowlist, the `X-Dev-Persona` allowed header, the HSTS baseline, the S2S scheme) and reads
  `unconfigured` when nobody chose; `bind_profile` drives the RESTRICTION (the loopback bound) and
  reads `local` when nobody chose. One string cannot do both without weakening one of them.
  Only `config.py` reads the variable.
- **End-user authentication is a property of the identity BINDING**, declared by the adapter
  (`VERIFIED` / `CLIENT_ASSERTED` / `UNIMPLEMENTED`) and read by the loopback exposure guard. The
  service-to-service secret authenticates a calling SERVICE and no end user, so it takes no part
  in that decision: setting it closes the S2S routes and relaxes nothing.
- **Audit integrity**: the trail is hash-chained AND externally anchored. `audit_anchor_path`
  points at a file on a different volume that every append writes the chain head to; without it
  a truncated tail is undetectable, because the shorter chain still verifies. Once store and
  anchor disagree the service refuses to append rather than re-anchoring, so an ordinary write
  cannot launder a divergence. Re-anchoring is a deliberate operator action. Every record carries
  the due basis, the calendar version and every withhold basis, so a supervisor's four questions
  (when was it due, what did you produce, what did you withhold and why, who signed it) are
  answerable from the exported trail with no running system.
- **Agent surface**: optional but scaffolded. The A2A card at `/.well-known/agent-card.json` is
  built from the same tool table the runtime binds, so advertised skills and implemented tools
  are the same set. Tool results are masked for personal data before they return, because a tool
  result becomes model context (P-04); an API response to the caller who supplied the text is
  not. The agent tool asserts NO entitlements of its own, so it reads untagged documents only.
  Nothing in `agent/` needs a runtime to import; `build_function_tools()` is the only seam.
- **Ports**: a port is registered in five places (`PORT_PROTOCOLS`, `DEFAULT_BINDINGS`, the
  `Container` accessor, `config/settings.yaml`, and the canonical-call table) and the contract
  suite asserts set equality across all five, in both directions.
- **Demo**: the demo is code and it is asserted. `scripts/walkthrough.py` narrates eight steps
  and, at each one, checks that the service actually reached the state the narration claimed;
  `--auto --headless` runs the same steps unattended in CI. A step exists in exactly two places
  (`demo.STEPS` and `walkthrough.CHECKS`) and the two are held equal, so a narrated claim nobody
  verifies cannot exist. The demo needs no browser engine, no network and no cloud.
- **UI identity**: the browser never asserts who it is. Every client-supplied actor, tenant,
  role, ACL and authorization header is discarded before a request is forwarded; identity is
  resolved server-side and the resolved headers are attached afterwards. The service credential
  is read from the server environment only. Framing and CORS are allowlists that refuse a
  wildcard however it is written, and an empty allowlist denies rather than opening up. The
  console renders WITHHELD, DENIED and MISSING distinctly, which is a test rather than a
  convention, and it states that it cannot release anything.
- **Eval**: `--mode smoke` is the offline pre-merge check; `--mode gate` is the Hrz4 promotion
  authority. The gate fails closed.
- **Tests**: split into `unit`, `contract` and `integration`. The offline gate runs the first
  two; every integration module is marked, and that marking is itself enforced.

## Metrics and thresholds (smoke)

Every oracle is INDEPENDENT of the engine's own labels. A metric scored from the thing it is
checking is a green tick over an empty set.

- `disposition_accuracy >= 1.00` (disposition, severity, decision, review flag, approval count,
  release state and the named release blockers, all against the golden expectation)
- `clock_accuracy >= 1.00` (due date, due basis, band, breached, buffer consumed, and the
  pre-extension date where one applies)
- `completeness_accuracy >= 1.00` (the integer percentage, every coverage state, the out-of-scope
  count and the entitlement-suppression count)
- `withhold_precision >= 1.00` (no document carrying a hard-withhold tag IN THE CORPUS appears in
  any index, citation, narrative or payload)
- `blocker_recall >= 1.00` (MICRO-averaged over the expected blockers themselves, so a case that
  expects none contributes to neither side of the fraction instead of scoring a free 1.0 for
  producing nothing, and a dataset expecting no blocker at all refuses to score rather than
  reporting a green tick over an empty set)
- `citation_grounding >= 0.99` (RAW model output scored through the same narration predicates the
  service enforces, so it can actually go red)
- `entitlement_safety >= 1.00` (every emitted document id re-checked against the CORPUS's ACL
  labels, not against the engine's verdicts)
- `pii_safety >= 0.99` (pack scan plus a pack-independent planted-literal check, over the audit
  records AND the serialised outcomes)
