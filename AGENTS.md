# AGENTS.md

The working agreement for any coding agent in this repository, in the portable `AGENTS.md`
format that agent tools read. It is the only such file here, so there is no second copy to
keep in step.

## What this is

Regulatory Exam and RFI Orchestrator (Cop2): turns an incoming regulator exam request list or
supervisory inquiry into a managed, citation-backed response. It decomposes each numbered question
into requested artefacts, runs ACL-aware retrieval as a PORT, deterministically tracks deadlines,
owners, SLA clocks and completeness, records what it withholds and why, and drafts the response
narrative and document index. Every assertion is citation-backed and the response is maker-checker
approved before it leaves the firm.
Rendered from `hex-service-template`, so it starts at reference parity rather than converging
toward it. Package `exam_rfi_orchestrator`, environment prefix
`EXAMRFI`, region `asia-southeast1`.

## Documentation authority order

On any conflict, the earlier document wins: `SPEC.md` > `ARCHITECTURE.md` > `COMPLIANCE.md` >
`README.md`. `docs/runbook.md` and `docs/onprem-migration.md` are operational and never restate
product behaviour. `docs/practices-audit.md` records the per-check verdict against the common
base practices, and it is the file to update when a gap closes.

## The hard gate

```sh
make install   # locked install from requirements-dev.lock, then the project with --no-deps
make gate      # ruff check + ruff format --check + mypy src + pytest -m 'not integration' + eval
make audit     # pip-audit over both lockfiles (needs network; CI runs the same two commands)
```

`make gate` is deliberately OFFLINE and credential-free: no cloud SDK, no project, no network. If
a change makes the gate need any of those, the change is wrong, not the gate. `make audit` is the
one step that needs a vulnerability feed, which is why it is separate locally and a hard-failing
job in CI rather than an advisory one.

After any dependency change, run `make lock` and commit both lockfiles. An uncommitted resolution
is a version set nobody reviewed.

## Architecture

Hexagonal, ports and adapters:

- `src/exam_rfi_orchestrator/domain/` is PURE stdlib. No web framework, no cloud SDK,
  no HTTP. `kernel.py` holds the vertical-neutral machinery; everything else is this vertical:
  `models.py` (the frozen artifacts and the reviewable-outcome Protocol), `policy.py` (the
  adopter-owned policy block and its parser), `artefact_taxonomy.py` (decomposition),
  `coverage_engine.py` (the admissibility ladder and coverage), `sla_clock.py` (the deadline),
  `consistency.py` (prior-answer conflict), `exhibit_index.py` (numbering), `release_engine.py`
  (disposition, severity, the release gate, dual control, the pack roll-up), `narration.py` (the
  grounding contract) and `response_pack_service.py` (the orchestration). A fork building a
  different vertical rewrites all of those and leaves `kernel.py`.
- `ports/` holds `@runtime_checkable` Protocols, re-exported once from `ports/__init__.py` with
  the `PORT_PROTOCOLS` map, plus `ports/identity.py`: what an identity adapter declares about the
  end-user authentication it provides, and the refusal type that carries a status and a reason.
- `adapters/{local,gcp,onprem}/` are the three families. `local` is SDK-free and actually works;
  `gcp` imports its SDK LAZILY inside the method, so the other two profiles import it with no
  cloud SDK installed; `onprem` is a placeholder that RAISES rather than pretending.
- `config.py` resolves the profile and binds every port. `config/settings.yaml` carries the
  binding table, so switching a port is configuration, not a code edit.
- `agent/` is the optional-but-scaffolded agent surface: plain tool callables plus the A2A card.
  It imports with no ADK and no cloud SDK; `build_function_tools()` is the only runtime seam.
- `tests/` splits into `unit/`, `contract/`, `integration/` and `fixtures/`. Integration modules
  are marked so `pytest -m 'not integration'` deselects them, and a test dropped into `tests/`
  root fails `tests/unit/test_test_layout.py`.
- `scripts/` is the demo surface (see `scripts/README.md`): the scripted arc, a static renderer,
  a live click-through server, the presenter walkthrough that doubles as the self-test, the
  executable portability claim and the offline documentation checker. It is importable from the
  suite (`pythonpath = ["scripts"]`) and excluded from the serving image.
- `ui/` is the embeddable micro-frontend. One policy module and one server-side identity module
  are its whole security boundary. Run `make drop-ui` if this repo has no user-facing surface.
- `infra/terraform/` is the vertical-neutral deploy posture, not a skeleton: residency validated
  at plan time, Org Policy guardrails, a regional CMEK key ring, a least-privilege serving
  identity, a locked WORM log bucket and sink, the five security metrics and alerts, a
  dry-run-first VPC-SC perimeter, and the opt-in Cloud Run serving edge behind IAP and Cloud
  Armor. `render.tf.json` is the ONE file cookiecutter rendered; every `.tf` and `.tftest.hcl`
  beside it was copied verbatim, because Terraform interpolation and Jinja fight over braces.
  The render-time constants therefore arrive as JSON locals (`render_region`,
  `render_package_name`, `render_env_prefix`, `render_catalog_id`) and `naming.tf` derives
  everything else from them. `make tf-check` runs the whole offline check; the vertical's own
  resources (a store, a warehouse, a bucket) are yours to add, in four places at once.

## Invariants (a change that breaks one of these is a defect, not a trade-off)

- **Born fail-closed.** `add_loopback_exposure_guard` is bound at MODULE scope in `api/app.py`,
  because the Dockerfile `CMD` and `make run-api` serve the app OBJECT: a bound that lives only
  in `main()` never runs in a shipped process. `tests/unit/test_serving_path_exposure.py` is the
  standing gate.
- **The exposure guard is derived from the IDENTITY BINDING, and from nothing else.** An end-user
  route is authenticated when the bound identity adapter can produce a verified principal without
  trusting a header the client wrote, and the adapter DECLARES that (`ports/identity.py`:
  `VERIFIED` / `CLIENT_ASSERTED` / `UNIMPLEMENTED`, defaulting to client-asserted when silent).
  `EXAMRFI_S2S_TOKEN` may never enter that decision: it authenticates a
  calling SERVICE and no end user, and while it did, SETTING it switched the guard off for the
  end-user routes it was protecting and a LAN peer with no credential got the seeded approver
  persona and a real, routed response pack. `tests/unit/test_end_user_auth_posture.py` walks the
  guard's argument through the constants it names and fails the build if a credential reappears
  at any depth; `scripts/prove-exposure-matrix.sh` in the template drives the whole matrix over a
  real socket.
- **The one adapter that declares `VERIFIED` must EARN it, and it is the one adapter that may not
  go untested.** `adapters/gcp/identity.py` calls `id_token.verify_token` with `audience=` (the
  configured `EXAMRFI_IAP_AUDIENCE`, three-state: unset or emptied REFUSES,
  because `audience=None` means the audience is NOT verified and accepts any Google-signed token
  from any project) and `certs_url=` (IAP's own key set, not google-auth's OAuth2 default), checks
  the issuer itself (`verify_token` does not), and WRAPS both the verifier call and the lazy
  import so no caller-supplied header can become a 500. `MalformedError` is a `ValueError`, not an
  `IdentityError`. Caller faults are 401 with the reason kept in the log; deployment faults (no
  audience, no verifier installed) are 503 naming the fix. `tests/unit/test_iap_identity.py` runs
  in every `make gate`; `tests/unit/test_iap_crypto_matrix.py` runs the REAL verifier over
  locally minted assertions and is required by the `iap-verifier` CI job and by the template's
  render gate, which fail if it skips. There is no `# pragma: no cover` on this adapter.
- **Interactive docs are a relaxation, not a constant.** `/docs`, `/redoc` and `/openapi.json` are
  registered only when `exposure_profile` is the deliberate `local`. Under `gcp` the loopback
  guard has stood down and the process binds every interface, so an uncredentialed peer was
  receiving the whole route inventory and every schema; the routes are ABSENT there rather than
  guarded, because a guard the profile has switched off is no guard.
- **One profile read, three states, refused at import.** `config.PROFILE_CHOICE` resolves once at
  import into a `ProfileChoice`. UNSET is NO CHOICE, not a silent `local`; SET-AND-EMPTY raises so
  it cannot inherit the unset behaviour; SET-AND-UNKNOWN raises. Both raises kill the process
  before it can serve a request. Only `config.py` may read
  `EXAMRFI_PROFILE` (mentioning it in a refusal message is wanted, reading
  it is the defect); `tests/unit/test_profile_single_source.py` fails the build if any other
  module re-derives it, because a permissive default gets reintroduced one module at a time.
- **Two derived postures, never one string.** Relaxations (CORS, the `X-Dev-Persona` allowed
  header, HSTS, the S2S scheme) key off `ProfileChoice.exposure_profile`, which is `unconfigured`
  when nobody chose. The loopback bound keys off `ProfileChoice.bind_profile`, which is `local`
  when nobody chose. They fail closed in OPPOSITE directions, so a single effective-profile
  string would harden one and weaken the other. The seeded-persona adapter refuses to construct
  unless `local` was chosen deliberately.
- **The audit trail is anchored, not just chained.** `audit_anchor_path` writes the chain head to
  a file on another volume. The chain catches an edit, a deletion or a reorder; only the anchor
  catches a truncated tail. `tests/unit/test_audit_anchor.py` proves both, including the control
  case that fails without it.
- **Three-state environment reads, everywhere, enforced, in BOTH languages.** UNSET,
  SET-AND-EMPTY and SET-AND-VALID are three states, not two. A variable an operator deliberately
  emptied must never inherit the unset default. In Python use
  `hex_service_kit.netdefaults.read_env_setting`; `tests/unit/test_three_state_env_reads.py`
  walks the AST of `src/`, `scripts/` and `eval/` and fails the build on any two-state
  `os.environ.get` / `os.getenv` read that is neither an exact-match comparison against a literal
  nor listed with a written reason. In `ui/` use `readEnvSetting` from `ui/lib/env-setting.mjs`;
  `ui/tests/three-state-env-reads.test.mjs` scans every shipped `.mjs` / `.ts` / `.tsx` with the
  same rule and the same two escapes. Both halves are needed: a guard that only watched the
  PROFILE variable is how a two-state read of a different one stayed invisible, and a guard that
  only parsed Python is how `env.UI_TENANT_ORIGINS || "*"` survived the entire gate.
- **Every unit of work opens a span, and no span carries content.** `exam.assess_item` and
  `exam.assemble_pack` wrap their work in `self._tracer.span(...)` with STRUCTURAL attributes
  only: the action and the actor, never the question, an item reference or a document title. In
  this vertical the last one matters most: a document title is the fact a withholding rule exists
  to keep off surfaces. A span is not a redacted sink. Tracing is the one seam that is
  ABSENT rather than fatal on-prem, and the one managed adapter that must not refuse offline:
  it is a diagnostic, not a control, and an exporter fault must never become a request fault.
  `demo.EXIT_ABSENT` records that exemption and the portability tour asserts it in both
  directions, so a tracer that starts raising fails the tour. The no-content half is a TEST, not
  a convention: `tests/unit/test_span_content.py` holds the attribute keys to a fixed allowlist
  and asserts the planted identifier never appears in a value. Widening that set is a decision
  about what leaves the trust boundary, and it is made in that file rather than at a call site,
  because the pressure to add "just the case text" comes from someone debugging a real incident
  and sounds entirely reasonable at the time.
- **Logs are diagnosis; the audit trail is evidence. Do not confuse them.** `configure_logging`
  is called at MODULE scope in `api/app.py` (the Dockerfile CMD serves the app object) and at the
  top of the CLI. A deployed profile emits JSON with Cloud Logging's own field names and the
  active trace id; `local` and `onprem` stay plain text. The formatter emits an ALLOWLIST and
  never the record's `__dict__`: logs are not WORM and nothing redacts them downstream, so
  `logger.info("...", extra={"prompt": prompt})` must not be able to put a model prompt in a log
  sink. Add a key to the allowlist deliberately, in the commons, with a reviewer.
- **The core's purity is a test, not a convention, and it is proved twice.**
  `tests/unit/test_core_purity.py` walks the AST of `domain/` and `ports/` and fails the build on
  any import outside the standard library, this package and the workspace kits. It is an
  ALLOWLIST rather than a list of banned SDK names, because a blocklist rots the day a vendor
  renames a distribution. The dynamic half is
  `tests/contract/test_port_parity.py::test_every_profile_constructs_with_no_cloud_sdk_importable`,
  which constructs every profile in a fresh interpreter where the managed SDKs cannot be
  imported. Both are needed: the probe cannot see a lazy import inside a function body on a call
  path that construction never reaches, and the static scan cannot see an adapter that fails to
  build. An import that must stay gets a NAMED row in `EXEMPT_IMPORTS` with a written reason, so
  it is debt somebody owns rather than a silently widened rule, and a stale row fails rather than
  quietly covering the next violation.
- **Redact before anything leaves.** PII is masked before the audit write and before any outbound
  payload. The raw identifier never reaches a WORM record or the review console.
- **Rule R8: escalations are ROUTED, never merely flagged.** Setting `requires_human_review` and
  calling `ReviewRouterPort.route` is one act. `api/app.py`, `cli/main.py` and `agent/tools.py`
  all route in the same call that produced the result. `tests/unit/test_review_routing.py` is the
  standing gate; a local router that silently did nothing would let a producer ship R8 unwired
  and green.
- **The consequential decision is deterministic, and the list is long.** Decomposition, the
  admissibility ladder, every withhold decision and its basis, the business-day deadline on a
  named and versioned calendar, the coverage states, the integer completeness, the prior-answer
  conflict check, the exhibit numbering, the disposition, the severity, the release gate and the
  approval count are ALL pure stdlib and replayable. The model suggests, normalises and drafts;
  it sets none of them, in any profile, and none of its output is an argument to any of them.
  Two specific consequences, because both were once wired the other way: a proposed artefact
  class enters no requirement (a requirement moves the completeness denominator and everything
  hanging off it), and the topic is DECLARED by the caller (it is the retrieval and
  responsiveness key, so a suggested one would drop documents the firm holds and the pack would
  say they do not exist). `tests/unit/` holds each rule set separately.
- **Every result carries a citation.** A claim with no provenance is not shippable.
- **Entitlement is decided in the pure domain, fail-closed.** A document is readable only when its
  ACL labels are a subset of the server-verified entitlements, so an empty principal reads
  untagged documents and never everything. A document that ARRIVES exceeding them is dropped and
  raises at CRITICAL: there the retrieval boundary failed, not the caller.
  `tests/unit/test_coverage_engine.py` holds both directions.
- **DENIED is never collapsed into MISSING.** "You are not entitled to see this" and "the firm
  holds no such document" are different statements to a regulator and only one is true. Separate
  coverage states, separate blocker kinds, visually distinct rows in `ui/`.
  `tests/unit/test_coverage_engine.py` and `tests/unit/test_ui_surface.py`.
- **A hard-withheld document never reaches the index, the review payload, a span, the audit record
  or the generation port**, and it is always RECORDED on the withholding schedule with a stated
  basis. `tests/unit/test_response_pack_service.py`. The withhold rules are evaluated BEFORE the
  period rule, so a stale privileged memo is withheld rather than produced because it is old.
- **A client-asserted waiver or extension grants nothing.** Both are lookup keys the case store
  resolves for THIS tenant. `tests/unit/test_response_pack_service.py`,
  `tests/unit/test_sla_clock.py`.
- **Empty retrieval is a blocker and never an ungrounded answer**, and a draft that cites an
  exhibit outside its index or invents an integer is discarded WHOLE rather than repaired.
  `tests/unit/test_narration_and_consistency.py`.
- **`required_approvals` has exactly one owner.** The engine decides it under rule R3 and
  `adapters/_review_payload.py` reads it. `tests/contract/test_review_payload_owner.py` carries
  the mutant.
- **A pack always routes**, including a clean one, and every outcome comes back
  `held_for_checker`. `ReleaseState.RELEASED` has no producer;
  `tests/unit/test_release_engine.py` proves the guard against a planted mutant that returns it.
- **The demo is code, and every narrated claim is checked.** A step lives in `demo.STEPS` and in
  `walkthrough.CHECKS`, and `tests/unit/test_demo_surface.py` holds the two equal, so a claim the
  demo makes but nobody verifies cannot exist. `make demo-selftest` runs the whole arc headless
  in CI. Do NOT move the demo into `make gate`: the gate proves the service and must stay fast
  and offline, and the demo has its own required check.
- **The browser never asserts who it is.** In `ui/`, every client-supplied actor, tenant, role,
  ACL and authorization header is discarded before forwarding, identity is resolved server-side,
  and the service credential stays on the server. Framing and CORS are allowlists that refuse a
  wildcard, and every variable behind them is read in three states: unset takes the documented
  restrictive default, EMPTIED refuses. `UI_PROFILE` refuses rather than seeding a dev persona
  when nobody chose; `UI_FRAME_ANCESTORS` and `UI_TENANT_ORIGINS` refuse from `next.config.mjs`,
  so the refusal is a build/boot refusal rather than a surprise on a later request. The one
  deliberate exception is the OUTBOUND `AGENT_S2S_TOKEN`, exempted with a written reason because
  the receiver decides whether an uncredentialed call is acceptable.
- **The console must actually HYDRATE, and only one check can tell you.** The document CSP is
  nonce-based (`script-src 'self' 'nonce-<n>' 'strict-dynamic'`), `proxy.ts` puts that policy
  on the REQUEST `Content-Security-Policy` header because that is the only name Next reads a
  nonce from, and `app/layout.tsx` sets `force-dynamic` because Next can only stamp a nonce
  onto a dynamically rendered route. All three are required: a bare `script-src 'self'` blocks
  Next's inline hydration bootstrap so React never attaches, and a nonce on a prerendered
  route is worse still, since `'strict-dynamic'` then also blocks the chunk scripts. Correct
  headers, a clean `tsc`, green policy tests, a successful build and a good screenshot are all
  consistent with a page that never hydrates, so the gate is `npm run assert-hydratable`,
  which serves the built app and asserts every script tag carries the served nonce.
  `assertHydratableCsp` refuses the half-configured build outright.
- **`ui/`, its dependabot ecosystem and its CI job agree, in both directions.** Present together
  or absent together. `make drop-ui` is the one step that keeps them consistent, and
  `tests/unit/test_ui_surface.py` fails the gate until they do.
- **The deploy posture is CHECKED offline, and the refusals live in the tests, not in the
  comments.** `make tf-check` and the `terraform` CI job run `init -backend=false`, `validate`,
  `fmt -check -recursive` and `test`, with no backend, no project and no credentials;
  `infra/terraform/production_edge.tftest.hcl` uses `mock_provider` and plan-only runs. Fourteen
  runs carry the claims: residency defaults in country, the perimeter starting in dry run, the
  edge absent by default, the served edge's contract, and nine refusals (an out-of-allowlist
  region, retention below the six-month floor, a reduced locked retention, a perimeter with no
  access policy, a mutable image tag, an edge with no review console, an edge with no alert
  channel, an audience with no IAP, and a reserved or moving secret). A residency claim that
  lives only in a comment is a claim nobody checks.
- **The audit log name agrees BY CONSTRUCTION, and a test holds the derivation.**
  `adapters/gcp/audit.py` writes to the logger `exam_rfi_orchestrator-audit` and
  `naming.tf` derives `local.audit_log_name` from `local.render_package_name`, which is the same
  cookiecutter variable. A WORM sink filter naming a log nobody writes routes an EMPTY stream and
  looks exactly like a working sink, so the tftest asserts both the derivation and that the
  sink's filter contains it. Do not re-pin either half by hand.
- **The region is injected once, and only once.** `render.tf.json` carries it; `variables.tf`
  keeps `region` and `allowed_regions` nullable and `naming.tf` makes them effective, so an
  operator overrides in `terraform.tfvars` and the single cross-variable validation holds the
  pair consistent. That validation lives on `var.region` alone and reads
  `coalesce(var.region, local.render_region)` rather than `local.region`: two validations that
  read each other's variable is a dependency cycle Terraform refuses to build, and
  `terraform validate` then fails before it checks anything at all.
- **VPC-SC starts in DRY RUN.** `use_explicit_dry_run_spec = !var.vpc_sc_enforce`, so the first
  apply audits rather than enforces. Watch the `vpc_sc_denials` alert for a full business cycle,
  add the operator identities, and only then enforce. Never enforce blind on a path nobody has
  watched.

## Extending

`CONTRIBUTING.md` carries the file-by-file touch list for both walkthroughs, with the test that
enforces each row. The short version:

- **A new adapter:** the class under `adapters/<family>/` (one constructor shape,
  `Adapter(settings)`, cloud imports inside the method), the same `module:Class` target in
  `config.DEFAULT_BINDINGS` AND `config/settings.yaml` (`tests/unit/test_settings_file.py` fails
  if the two disagree), plus any new variable in `.env.example`.
- **A new port:** it must be registered in FIVE places, or it runs with no enforcement at all:
  `ports/__init__.py` (`PORT_PROTOCOLS`), `config.DEFAULT_BINDINGS`, a `Container` accessor,
  `config/settings.yaml`, and a `PortCase` in `tests/contract/canonical.py`. Then bind it in all
  three families. `tests/contract/test_port_parity.py` asserts set equality across the five.
- **A new surface:** whatever it is, it routes escalations (R8) and it minimises what it hands a
  model. An agent tool also needs its skill in `agent/agent_card.py`; the card and the tool table
  are compared for set equality.
- **A new demo step:** the `Step` and its `_step_<key>` method in `scripts/demo.py`, plus the
  matching entry in `walkthrough.CHECKS`. Put the numbers the check reads in the step's `facts`
  dict, never only in the rendered rows: a check that parses prose breaks on a wording change.
- **Synthetic data only.** Fixtures, demos and docs use obviously fictional parties and
  `.example` domains. No real customer, counterparty or identifier, ever.
