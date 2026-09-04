# Runbook: Regulatory Exam and RFI Orchestrator (`exam-rfi-orchestrator`)

## Deploy (gcp)
1. `EXAMRFI_PROFILE=gcp`, install `.[gcp]`, region `asia-southeast1`.
2. **Check the posture offline first.** `make tf-check` runs `terraform init -backend=false`,
   `validate`, `fmt -check -recursive` and `test` against `infra/terraform/`. It needs the
   terraform binary and nothing else: no project, no credentials, no state. The `terraform` job
   in CI runs the same four commands, so a drifted format or a broken residency validation fails
   the pull request rather than the apply.
3. **Choose a posture in `terraform.tfvars`** (copy `terraform.tfvars.example`). Two are
   supported and the file spells out both:
   - QUICK EVALUATION: `enable_org_policies = false`, `enable_vpc_sc = false`,
     `worm_locked = false`. Everything stays deletable. NOT a compliant production posture.
   - SOVEREIGN (the defaults): Org Policy guardrails on, the WORM audit bucket LOCKED, and a
     VPC-SC perimeter in DRY RUN. Locking is irreversible; confirm `retention_days` first.
4. **Initialise the state backend and apply.** The backend is partial, so
   `terraform init -backend-config="bucket=YOUR_STATE_BUCKET" -backend-config="prefix=exam-rfi-orchestrator/ENVIRONMENT"`.
   The serving edge is off by default, so the residency, encryption and audit stack can be
   applied and reviewed before anything serves traffic.
5. **Enable the edge, then apply TWICE.** `iap_audience` names the backend service this stack
   creates, so it cannot be a reference without forming a cycle. First apply with it empty: the
   service starts, stays health-checkable and refuses every end-user request with a 503 naming
   the variable, which is the documented fail-closed behaviour. Read the `iap_audience` output,
   set the variable to it, apply again.
6. **Read the outputs.** `region` and `residency_allowlist` (what the plan validated),
   `kms_key`, `log_bucket`, `worm_locked` and `audit_log_name` (the log the WORM sink routes and
   the managed audit adapter writes, derived from the same rendered package name so they agree
   by construction), `app_service_account`, `service_origin`, `edge_ip_address` and
   `iap_audience_configured`.
7. **Run the perimeter in dry run for a full business cycle** before setting
   `vpc_sc_enforce = true`. The `vpc_sc_denials` alert is the evidence; add the operator and CI
   identities to `operator_members` first. Never enforce blind on a path nobody has watched.
8. Ingress is fronted by IAP/Apigee; the app authenticates the S2S caller fail-closed
   (`EXAMRFI_S2S_TOKEN` local, Google OIDC + allowlist secure). Credentials
   reach the service as pinned Secret Manager versions through `additional_secret_env`; no secret
   value is ever written into the Terraform configuration.
9. **Set `EXAMRFI_IAP_AUDIENCE`.** With the edge enabled Terraform sets it
   on the service for you at step 5. Without it the service starts, stays health-checkable and
   refuses every end-user request with 503 naming this variable. See below.

## The IAP audience (required for the gcp profile)
`EXAMRFI_IAP_AUDIENCE` is the IAP-protected resource the assertion must be
addressed to: `/projects/<PROJECT_NUMBER>/global/backendServices/<BACKEND_SERVICE_ID>` behind an
HTTPS load balancer. Read through `iap_audience` in `config/settings.yaml`, so it resolves in the
usual three states and UNSET and SET-AND-EMPTY both land on empty.

It is not optional and there is no unverified fallback, because the fallback is the vulnerability.
`google.oauth2.id_token.verify_token` documents `audience=None` as "the audience is not verified",
so an adapter that omitted it would accept ANY Google-signed OIDC ID token, from any project and
any application, and turn its `email` claim into a verified principal on this service. The adapter
therefore refuses before it reads the assertion header at all, which also means the refusal does
not depend on the SDK being importable or on the network being up.

Two operator-facing refusals, both 503 rather than 401 because no credential the caller could
present would have helped, and both naming what to fix:

| Symptom | Cause | Fix |
|---|---|---|
| 503, detail names `EXAMRFI_IAP_AUDIENCE` | no audience configured | set it to the protected resource above |
| 503, detail says the verifier is not installed | `google-auth` missing from the image | install `requirements-gcp.lock` (the shipped `Dockerfile` does) |

A caller-facing failure is different: a malformed, expired, wrong-audience, wrong-issuer or
wrong-key assertion answers **401 `authentication required`**, with the specific reason recorded in
the log and the exception chain rather than returned. That asymmetry is deliberate: telling an
unauthenticated caller which check failed tells them what to change next. Nothing in this path may
answer 500; `scripts/prove-exposure-matrix.sh` in the template drives each of those cases over a
real socket from a real LAN address and fails on a bare 500, and
`tests/unit/test_iap_crypto_matrix.py` runs the real verifier over locally minted assertions with
no project, no credential and no network.

## Interactive API docs
Swagger UI (`/docs`), ReDoc (`/redoc`) and the raw OpenAPI document (`/openapi.json`) are served
under the DELIBERATE offline `local` profile and nowhere else; every other posture answers 404
because the routes are not registered at all. They are a development affordance, and on a fronted
deployment they hand an uncredentialed caller the complete route inventory and every request and
response schema, for routes that same caller cannot reach. There is no variable to switch them back
on: the schema is generated from the source and available to anyone with the repository, and a
deployment that wants to publish it should serve the artifact from somewhere that is not the
authenticated service. Removing the routes rather than guarding them is what holds under `gcp`,
where the loopback guard has deliberately stood down and the process binds every interface.

## Rate limits / body caps
Enforced at the edge (IAP/Apigee/LB).

## Exposure of an unauthenticated posture
An END-USER route is authenticated here when, and only when, the identity adapter the active
binding names can produce a verified principal WITHOUT trusting a header the client wrote. That is
the single question the guard below asks, and the answer comes from the adapter itself, which
declares it (`ports/identity.py`, `config.end_user_auth_kind`). The shipped answers:

| Identity binding | Declares | End-user routes |
|---|---|---|
| `local` seeded dev personas | `client-asserted` | NOT authenticated: the caller names a persona in `X-Dev-Persona` and receives its groups and tenant |
| `gcp` IAP assertion | `verified` | authenticated: the signature (against IAP's own key set), the audience (against `EXAMRFI_IAP_AUDIENCE`), the expiry and the issuer are all checked before any claim is read |
| `onprem` placeholder | `unimplemented` | nobody can be authenticated until the client's own IdP adapter is bound |

So a request arrives with nothing authenticating the end user in exactly three situations, and ALL
THREE are bounded by the guard below:

1. **Nobody chose a profile.** `EXAMRFI_PROFILE` is absent, so no end-user
   identity scheme and no service-to-service scheme has been selected. This is what a production
   deployment looks like when the variable drops out of its environment, and it is refused rather
   than relaxed: the seeded-persona adapter will not construct (401), every S2S route answers 401,
   the dev CORS allowlist and the `X-Dev-Persona` header are withdrawn, HSTS is on, and every
   route, `/healthz` included, is refused to any non-loopback peer.
2. **The `local` profile, chosen deliberately.** The seeded personas are a client-asserted
   identity, so this is bounded whatever else is configured, INCLUDING when
   `EXAMRFI_S2S_TOKEN` is set. Setting that secret closes the S2S
   dependency and nothing else: it authenticates a calling SERVICE and authenticates no end user,
   so it cannot make `/v1/response-pack` or `/v1/personas` authenticated and it does NOT switch the
   guard off. Were it to, a LAN peer with no credential at all would receive the full seeded
   persona list, approver included, and a real, routed response pack.
3. **The `onprem` profile with the placeholder still bound.** No identity provider is wired, so
   no end user can be authenticated. `/v1/response-pack` answers 501 with the reason and the name of the
   file to read; binding a verifying adapter (below) is what lifts both the 501 and the bound.

Symmetrically, the guard STANDS DOWN when the binding declares `verified`: `gcp` serves
`/healthz` and the discovery card to any peer (a fronted deployment must stay health-checkable
and neither carries per-caller data) while `/v1/response-pack` answers 401 without an IAP assertion. The
route does the authenticating, which is the whole reason the guard may stand down.

That is also why the declaration has to be EARNED rather than asserted. It was not: the verifier
was called with no audience and no key-set URL, so any Google-signed token from any project was
accepted, and the call was unwrapped, so a caller-supplied header that was not a JWT crashed out
of the route as a bare 500. Both are closed, and the interactive docs went with them (below):
under this profile the process really does bind every interface, so anything the guard is not
covering has to be safe on its own.

To lift the bound on an on-premises deployment, bind an identity adapter that verifies your IdP's
assertion under `adapters.identity.onprem` in `config/settings.yaml` and declare
`end_user_auth = VERIFIED` on it. See [onprem-migration.md](onprem-migration.md). Nothing else
lifts it except the explicit opt-out below.

The bound is applied twice, and the outer one is on the app object rather than on one entry point:

- `add_loopback_exposure_guard` is registered at module scope in `api/app.py`, so it holds under
  `uvicorn exam_rfi_orchestrator.api.app:app --host 0.0.0.0` (what the Dockerfile `CMD`
  and `make run-api` do) as well as under `main()`. A non-loopback peer gets 503; a WebSocket is
  closed with 1008. A request carrying `x-forwarded-for` or `forwarded` is refused whatever it
  claims, because a proxy has already overwritten the ASGI peer address.
- `resolve_bind_host` still binds loopback in `main()`, for the same three situations: the
  start-up bound and the request-time guard read one derived posture, so a process can never bind
  every interface while refusing every caller on it.

Set `EXAMRFI_ALLOW_INSECURE_DEMO=1` to accept the exposure deliberately.
That is the only opt-out, and it is read per request rather than baked in at import.

`scripts/prove-exposure-matrix.sh` in the template repo drives the whole matrix (profile x S2S
token x persona header) against a real socket from a real LAN address;
`tests/unit/test_serving_path_exposure.py` and `tests/unit/test_end_user_auth_posture.py` are the
in-gate halves, the second of which fails the build if the guard's posture ever reaches a service
credential again.

## Profile misconfiguration
`EXAMRFI_PROFILE` is read once, in `config.py`, and it has three states:

| State | What happens |
|---|---|
| unset | No choice was recorded. The SDK-free adapters bind (the alternative is importing cloud SDKs that are not installed), but every relaxation is withdrawn and the exposure guard refuses every route to any non-loopback peer. Symptom: 401 on `/v1/response-pack` naming the variable, and 503 naming the `unconfigured` posture from off-box. Fix: set the variable. |
| set to an empty value | Refused AT IMPORT (`ConfiguredEmptyError`). The process does not start. An emptied variable is an expressed intent that names no profile, so it never inherits the unset behaviour. Common cause: a config map or deployment template that renders an empty string. |
| set but unknown, including `Local`, `LOCAL`, `GCP` | Refused AT IMPORT. A typo is not a synonym, and coercing the case would turn it into a silent choice. |

In every refusing case the process fails to boot or answers 4xx/5xx, rather than serving a first
request on a posture nobody chose. The relaxations key off a derived `exposure_profile` and the
loopback bound off a derived `bind_profile`, because those two fail closed in opposite directions:
see `config.ProfileChoice`.

## Human review routing (rule R8)
Set `HUMAN_REVIEW_URL` to the `human-review-console` (HTTPS is required off loopback) and provide
`HUMAN_REVIEW_S2S_TOKEN`; `HUMAN_REVIEW_S2S_SIGNING_KEY` optionally signs the propagated actor. These are the
OUTBOUND credentials and are deliberately distinct from this service's own inbound
`EXAMRFI_S2S_TOKEN`. With the URL unset, the managed router REFUSES rather
than swallowing the escalation, so a misconfiguration is a loud failure and never a silent
auto-execution. Under the local profile the escalation goes to the review-kit outbox, which is
inspectable and flushes to the console when one becomes reachable.

## This vertical's deployment inputs

Five reads, all three-state, none with a default. Unset or emptied means the managed adapter
REFUSES, which is the intended behaviour: an empty answer from the wrong host is a false
statement about what the firm holds.

| Variable | What it names | If it is missing |
|---|---|---|
| `EXAMRFI_KNOWLEDGE_BASE_URL` | the governed enterprise corpus, ACL-aware | every retrieval refuses; nothing is silently empty |
| `EXAMRFI_OBLIGATIONS_URL` | the obligation register's read surface | every obligation lookup refuses |
| `EXAMRFI_EVIDENCE_PACKS_URL` | the assembled control-evidence pack surface | every pack read refuses |
| `EXAMRFI_CASE_COLLECTION` | the Firestore collection holding the open-item board, the waivers and the extensions | every case write and every waiver or extension lookup refuses |
| `EXAMRFI_GENERATION_MODEL` | the managed model the generation port calls | generation refuses, the draft falls back to the deterministic paragraph, and the item carries an `ungrounded_draft` blocker. No number changes. |

Plus the whole `policy:` block in `config/settings.yaml`: the response windows per instrument,
the review buffer, the extension-notice period, the staleness window, the SLA band ceilings, the
completeness floor for release, the evidence cap, the hard-withhold and silent-withhold tag lists,
the cross-border transfer matrix, the dual-control rules, the named-regime register, and the
per-jurisdiction business calendars each with its `calendar_version`. Every one of those is the
adopter's number and the adopter's counsel owns it. Changing one is a configuration review with
an audit trail, not a release.

## Standing operational items

Two things degrade silently and neither can be detected from inside this codebase. Both need a
named cadence and an owner.

**Review the holiday calendars and the regime register, at least annually and whenever a
jurisdiction publishes its next year's holidays.** A missing public holiday shifts every internal
due date by a day, in the UNSAFE direction, and nothing in the code can tell that a calendar is
merely out of date. What the code does instead is PIN `calendar_version` on every clock and in
every audit record, so a deadline recomputed years later either matches or the record shows which
input moved. Bump the version string whenever the holiday list changes, or the pin means nothing.
The regime register needs the same treatment for the opposite reason: every shipped row says the
regime fixes NO response window, and if counsel ever identifies one that does, it is configured
here rather than patched into code.

**Verify entitlement provisioning after any identity-provider change.** The entitlements that
decide what may be retrieved come from the verified principal's principals claim. An identity
provider that stops populating it does not fail: it presents as "you are entitled to nothing" on
every item, so every pack comes back with `denied_no_entitlement` blockers and near-zero
completeness, and an operator will otherwise spend a day looking for the fault in the knowledge
base. Check the claim reaches the service before concluding the corpus is empty.

## Supply chain
Installs come from the committed lockfiles. After changing a dependency run `make lock` and commit
both files, then `make audit` (`pip-audit` over both locks). CI runs the same audit as a hard
failure, so a known-vulnerable dependency blocks the merge.

## Audit operations
The local WORM log supports `verify_chain()` and JSONL export/restore.

**Configure the external head anchor for any durable audit path.** Set
`EXAMRFI_AUDIT_ANCHOR` (read by `audit_anchor_path` in
`config/settings.yaml`) to a file on a DIFFERENT volume from
`EXAMRFI_AUDIT_PATH`, ideally writable by a different principal. This is
not decoration:

- the hash chain detects an edited, deleted or reordered record, because each of those breaks a
  link;
- it CANNOT detect a truncated tail, because dropping the newest rows leaves a shorter chain
  that verifies perfectly. Only the anchored head exposes that.

Leave it unset only for the ephemeral `:memory:` store the gate uses.

Operating rules:

- **The anchor is not last-write-wins.** Once the store and the anchor disagree, the service
  REFUSES to append rather than re-anchoring the store as it now stands, because one ordinary
  append would otherwise launder the divergence. Expect a hard failure on the write path, not a
  warning in a log nobody reads.
- **Re-establishing an anchor is a deliberate act.** Verify the store out of band first (against
  an exported trail held elsewhere), then call `reanchor()`. Never as a reflex to clear an alert.
- **Verify on a schedule**, not only after an incident: `verify_audit_trail` (the agent tool) and
  `HashChainedAuditLog.verify_chain()` both return the anchor cross-check, and the tool's
  `anchored` field says whether the stronger guarantee was even available.
- A managed WORM sink does not need the anchor: it provides non-rewritability itself.

## Agent surface
The A2A discovery card is served at `/.well-known/agent-card.json` and is built from the same
tool table the runtime binds, so it cannot advertise a skill the service does not implement.
Register it with the `agent-registry` (rule R4). The tools themselves need no agent runtime to run;
only `build_function_tools()` imports one.

## Running the integration tests
`make test-integration` runs `tests/integration/`, which the offline gate deselects. Each test
SKIPS rather than fails when its configuration is absent, so an unconfigured run reports nothing
rather than a false pass. It writes an obviously fictional audit record to the configured project
and, when `HUMAN_REVIEW_URL` is set, submits one fictional review to the live console.

## Alerts
`infra/terraform/monitoring.tf` creates five log-based metrics and an alert policy for each:
critical escalations in the app audit log, service-account key creation, VPC-SC denials, CMEK
destroy or update operations, and Cloud Armor denials at the edge. Set
`alert_notification_channels` or they fire into nowhere; the serving edge REFUSES to plan without
at least one, because an alert nobody receives is not an alert. There is deliberately no
guardrail-block metric until a guardrail port is bound (rule R1): a filter that can never match
is a green light nobody earned. Add it, and this vertical's own signals, in the same commit that
binds the guardrail.
