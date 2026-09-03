# Regulatory Exam and RFI Orchestrator (Cop2)

Turns an incoming regulator exam request list or supervisory inquiry into a managed,
citation-backed response; handles RFIs and skilled-person-style reviews; decomposes each question
into requested artefacts, runs ACL-aware retrieval (the enterprise knowledge base, reached as a
PORT) to assemble the cited evidence pack, deterministically tracks deadlines, owners, SLA clocks
and completeness, and drafts the response narrative and document index. Every assertion is
citation-backed; the response is maker-checker approved before it leaves the firm.

A hexagonal ports-and-adapters build on the catalog commons. Every consequential step is pure,
deterministic stdlib: the decomposition, the admissibility ladder, the deadline, the coverage
states, the completeness number, the consistency check, the exhibit numbering, the disposition,
the severity, the release gate and the approval count. The model narrates, normalises and
suggests, and owns none of them: a suggested topic or artefact class reaches a person and never
an engine. Personal data is masked before anything is audited, every
result carries a citation, and every outcome is ROUTED to a human reviewer (rule R8) rather than
auto-executed or left in a flag nobody reads.

## What this does NOT do

Worth reading before the feature list, because these are the things an exam team will assume.

- It does not file anything with a regulator.
- It does not grant, request or infer an extension. A reference on the wire is a lookup key into
  the case store; a client assertion moves no date.
- It does not decide privilege. It NAMES the basis on a withholding schedule and holds the
  document; a lawyer decides.
- It does not release a pack. Every outcome comes back held for a checker, and there is no code
  path in this service that returns `released`.
- It does not assert that any shipped policy number is currently correct in law. Every window,
  buffer, band, staleness limit, withhold tag, holiday and approval rule is the adopter's,
  configured in `config/settings.yaml` and owned by the adopter's counsel.
- It does not let a model choose the topic of a question. The classifier SUGGESTS one and an item
  that declares none is refused with the suggestion named, because the topic decides which
  documents are responsive and a guessed one would drop evidence the firm holds.
- Decomposition RECALL is unmeasured and unmeasurable offline. Decomposing a question into the
  artefacts it demands is a DRAFT a checker corrects, not a guarantee of completeness.

## Commands

```bash
python3.12 -m venv .venv && source .venv/bin/activate
make install          # locked install from requirements-dev.lock, then the project --no-deps
make gate             # the full offline gate: lint + type + test + eval
make audit            # pip-audit over both lockfiles (needs network; a HARD gate in CI)
make lock             # recompile both lockfiles after a dependency change
make test-integration # tests/integration only; needs a live project (the gate deselects it)
make run-api          # uvicorn (loopback for the no-auth local profile)
exam_rfi_orchestrator respond request.json --persona approver
```

The offline gate is SDK-free and is what CI runs (via the shared reusable hard-gate workflow):

```bash
ruff check src tests && ruff format --check src tests && mypy src && \
  pytest -m 'not integration' && python eval/run_eval.py
```

The demo surface sits OUTSIDE that gate, because the gate proves the service and the demo proves
the story it is presented with. It is enforced inside the offline gate by
`tests/unit/test_demo_surface.py`, which the hosted GitHub Actions check runs, so it cannot rot
quietly:

```bash
make demo             # the presenter-paced walkthrough (see DEMO.md)
make demo-selftest    # the same walkthrough, headless and unattended, asserting every step
make demo-static      # static audit-first HTML for screenshots
make portability      # the executable portability claim, pass or fail per named check
make docs-check       # relative links resolve, fences close, no em-dash in shipped prose
make ui-install ui-check   # the micro-frontend: tsc, node tests, production build, npm audit
```

## Profiles

One env var, `EXAMRFI_PROFILE`, selects the adapter family:

- `local` (default) : SDK-free offline stack (seeded dev personas, hash-chained SQLite WORM audit
  from the commons). No cloud SDK. The default for dev/test/CI.
- `gcp` : managed cloud (Cloud Logging WORM, IAP identity). SDK imports are lazy.
- `onprem` : fail-fast `NotImplementedError` placeholders (the reversibility proof, P-12).

Unset means `local` adapters bind but nobody chose them. A value that is set but unknown, `Local`
and `GCP` included, raises at import: a typo must not silently pick a family. And because the
local profile's seeded personas authenticate nobody, the loopback exposure guard is registered on
the app object itself, so serving it off loopback returns 503 unless
`EXAMRFI_ALLOW_INSECURE_DEMO=1` says otherwise. The guard reads the identity
BINDING to decide that, never a service credential: setting
`EXAMRFI_S2S_TOKEN` closes the S2S routes and does not open anything else.
See `docs/runbook.md`.

## What comes from the commons

| Package | Used for |
|---|---|
| `hex-service-kit` | `Principal` / `IdentityPort` / seeded personas, fail-closed bind + CORS, `make_require_service_caller` / the app-object exposure guard / security headers (the end-user dependency is this repo's own, so a deployment that can authenticate nobody answers with a status and a reason rather than a blanket 401), the hash-chained WORM audit log, `StrEnum` taxonomies |
| `agent-eval-kit` | the `--mode smoke\|gate` scaffold, the Hrz4 gate client, the not-falsely-green harness |
| `pii-kit` | the jurisdiction PII pattern pack every retrieved title, snippet and question is masked with |
| `review-kit` | the rule R8 producer path: the review payload, the submission client and the outbox |

## Surfaces

`POST /v1/response-pack` is the one vertical route. It takes a request-list header plus its
numbered questions and returns the assembled pack: the per-item assessments, the contiguously
numbered document index, the consolidated withholding schedule, the ranked blockers, the clock
and the cover note. A per-item assessment is reached by submitting a ONE-ITEM list rather than by
a second route, so every surface routes rule R8 through the same path and the pack, which is the
artifact a supervisor actually receives, is what the API names.

The same capability is reachable four ways, and they behave the same because they share the
domain service rather than reimplementing it: the FastAPI app (`api/`), the argparse CLI
(`cli/`), the agent tools (`agent/`, advertised on the A2A card at
`/.well-known/agent-card.json`) and the embeddable micro-frontend (`ui/`), which calls the app.
Each of them routes every escalated item AND the pack itself to human review in the same call
that produced them, so rule R8 holds wherever a result is produced for a person rather than on
one surface with three that only set a flag.

`eval/run_eval.py` drives the same service and is deliberately NOT one of those surfaces: it
scores assessments against the golden set, assembles no pack and routes nothing, because a
scoring harness that filed reviews would fill a human queue with runs nobody asked for.

`ui/` is a Next.js micro-frontend that runs standalone or embeds in a client application. Its
security value is that the browser never asserts who the user is: every client-supplied actor,
tenant, role and authorization header is discarded, identity is resolved server-side, the
service credential never leaves the server, and framing and CORS are per-tenant allowlists that
refuse a wildcard. **If this repo has no user-facing surface, run `make drop-ui`** rather than
leaving it half-wired; `tests/unit/test_ui_surface.py` holds the repo consistent in both
directions. See `ui/README.md`.

The tool results are masked for personal data before they return, which the API response is not:
a tool result becomes a model's context, and P-04 is about what reaches the model.

## Configuration

`config/settings.yaml` holds the per-port adapter map, the adopter-owned `policy:` block and the
non-secret defaults, and it is the only place a binding lives. The policy block is where every
number an exam response turns on lives: the response windows per instrument, the maker-checker
review buffer, the extension-notice period, the SLA band ceilings, the staleness window, the
completeness floor for release, the evidence cap, the never-produced and silent-withhold tag
lists, the cross-border transfer matrix, the dual-control rules, the named-regime register and
the per-jurisdiction business calendars WITH their versions. Changing one is a configuration
review with an audit trail, not a release.

The upstream reads are three-state and have NO default host: `EXAMRFI_KNOWLEDGE_BASE_URL`,
`EXAMRFI_OBLIGATIONS_URL`, `EXAMRFI_EVIDENCE_PACKS_URL`, `EXAMRFI_CASE_COLLECTION` and
`EXAMRFI_GENERATION_MODEL` each cause the managed adapter to REFUSE when unset or emptied. That is
deliberate: for retrieval and for the obligation register an empty success is a false statement
about what the firm holds, and it would go to a supervisor over somebody's signature.

Upstream systems are named rather than counted: this repository reads the shared enterprise
knowledge base as its retrieval port, the obligations-and-control-mapping register as its single
system of record for obligations, and the risk function's assembled control-evidence packs for
reuse. `.env.example` documents every non-secret variable;
`.env.secrets.example` documents the secret NAMES with placeholder values. Every security-relevant
read resolves three states: unset, set-and-empty and set-and-valid are different, and a value an
operator deliberately emptied never inherits the more permissive unset default.
`tests/unit/test_three_state_env_reads.py` fails the build on any two-state read that ships, so
the rule is enforced rather than remembered.

**Name the profile.** `EXAMRFI_PROFILE` has no default. Leaving it unset is
its own state: the offline adapters still bind, but the seeded dev personas are refused, no
service-to-service scheme is selected, the dev CORS allowlist and the `X-Dev-Persona` header are
withdrawn, and the exposure guard refuses every route to any non-loopback peer. A deployment that
loses the variable fails visibly instead of serving a stranger.

Deepest authority on intent, in order: `SPEC.md` -> `ARCHITECTURE.md` -> `COMPLIANCE.md` -> this
file. `docs/practices-audit.md` records the per-check verdict. Region pinned to
`asia-southeast1`.

## License

Apache-2.0. Synthetic, obviously fictional data only.
