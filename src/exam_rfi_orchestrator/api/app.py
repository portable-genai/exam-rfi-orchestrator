"""FastAPI application for Regulatory Exam and RFI Orchestrator (Cop2).

Import-safe (the Container is built at request time, never at import; only ``Settings`` is read
at import, to learn which identity adapter is bound, and no adapter is constructed), identity is
a server-verified Principal (the client-asserted actor is discarded), S2S callers are
authenticated fail-closed, and the fail-closed network defaults come from the commons: a profile
that cannot authenticate an end user binds loopback unless explicitly opted out, and CORS never
falls back to ``*``.

The profile is resolved ONCE, by ``config.resolve_profile``, and an absent
``EXAMRFI_PROFILE`` is NO CHOICE rather than a silent ``local``. Every
posture decision here keys off that one resolution, through the derived member that fails closed
in the right direction:

* the RELAXATIONS (CORS allowlist, the ``X-Dev-Persona`` allowed header, the HSTS baseline, the
  S2S scheme) key off ``exposure_profile``, where an unconsented run is ``unconfigured`` and
  therefore gets none of them;
* the RESTRICTION (the loopback bound) keys off ``bind_profile``, where an unconsented run is
  ``local`` and therefore stays on loopback.

One string could not do both: handing the relaxations ``local`` would grant a dev CORS
allowlist and the persona header to a deploy whose profile variable went missing, and handing
the restriction ``unconfigured`` would let that same deploy bind every interface.

The loopback bound lives on the APP OBJECT, not in ``main()``. The Dockerfile ``CMD`` and the
Makefile ``run-api`` target serve ``app`` directly, so a guard reachable only from ``main()``
never runs in a shipped process. ``add_loopback_exposure_guard`` is therefore registered at
module scope below, and ``resolve_bind_host`` in ``main()`` is the second layer rather than the
only one.

WHAT SWITCHES THE EXPOSURE GUARD OFF is one thing and one thing only: the identity adapter
bound to the identity port declaring that it VERIFIES the end user (see ``ports/identity.py``).
The guard exists to bound routes that answer an end user with no credential, so the question it
has to settle is whether an end user CAN be authenticated here, and only the bound adapter
knows. Deriving it from the profile string plus the presence of
``EXAMRFI_S2S_TOKEN`` is wrong in the most dangerous direction:
that secret authenticates a calling SERVICE and no end user at all, so SETTING it disabled the
guard for exactly the end-user routes it was protecting. A LAN peer with no Authorization
header and no ``X-Dev-Persona`` then got the seeded persona list and a real, routed pack.

THE INTERACTIVE DOCS ARE PART OF THAT EXPOSURE, and they are switched off with it. Under the one
profile whose guard deliberately stands down, an uncredentialed LAN peer would receive ``/docs``
and ``/openapi.json`` as 200: the complete route inventory, every request and response schema and
every field name, handed to a caller who cannot reach a single one of those routes. That is
reconnaissance with no counterpart benefit. Swagger UI and the raw OpenAPI document are a
development affordance, so they are served under the DELIBERATE offline ``local`` profile and
nowhere else (see ``_DOCS_URL`` below). There is deliberately no opt-in variable to re-enable
them: another three-state posture switch is another thing to get wrong, the schema is generated
from this file and available to anyone with the repo, and a deployment that wants to publish it
can serve the artifact from somewhere that is not the authenticated service.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from hex_service_kit.identity import IdentityError, IdentityPort, Principal, RequestContext
from hex_service_kit.logging import configure_logging
from hex_service_kit.netdefaults import cors_allowlist, resolve_bind_host
from hex_service_kit.web import (
    add_loopback_exposure_guard,
    add_security_headers,
    make_require_service_caller,
)

from ..config import (
    LOCAL_PROFILE,
    Container,
    ProfileChoice,
    Settings,
    build_container,
    end_user_auth_kind,
    resolve_profile,
)
from ..domain.kernel import utcnow
from ..domain.models import (
    ArtefactClass,
    Instrument,
    PriorAnswer,
    RegulatorRequest,
    RequestItem,
    RequestTopic,
)
from ..domain.response_pack_service import ResponsePackService
from ..managed_readiness import assert_managed_profile_ready
from ..ports.identity import VERIFIED, EndUserAuthUnavailableError
from ..services import build_service
from .schemas import HealthResponse, ResponsePackRequest, ResponsePackResponse

# Resolved at import, so an unknown, mis-capitalised or deliberately emptied profile is a BOOT
# failure rather than a first-request failure (a serving process must not come up on a profile
# nobody defined).
_CHOICE = resolve_profile()

# Every environment NAME this module hands to the commons, hoisted to constants. They are
# constants rather than literals at the call sites so that `ruff format` produces the same
# result whatever `env_prefix` a repo is rendered with: a long prefix inlined into a call
# argument pushes the line past the limit and would need a DIFFERENT formatting, which is a
# rendered repo failing its own format check on nothing but the length of its name.
_TOKEN_ENV = "EXAMRFI_S2S_TOKEN"
_INSECURE_DEMO_ENV = "EXAMRFI_ALLOW_INSECURE_DEMO"
_CORS_ORIGINS_ENV = "EXAMRFI_CORS_ORIGINS"
_ALLOWED_CALLERS_ENV = "EXAMRFI_S2S_ALLOWED_CALLERS"
_AUDIENCE_ENV = "EXAMRFI_S2S_AUDIENCE"
_API_HOST_ENV = "EXAMRFI_API_HOST"


@lru_cache(maxsize=1)
def _container() -> Container:
    return build_container(Settings.load())


def _identity() -> IdentityPort:
    return _container().identity


def _request_choice(request: Request) -> ProfileChoice:
    """The app's own resolution, so a test app carrying a different one is honoured."""
    choice = getattr(request.app.state, "profile_choice", None)
    return choice if isinstance(choice, ProfileChoice) else _CHOICE


def get_principal(request: Request) -> Principal:
    """Resolve the VERIFIED end-user principal, or refuse with a status AND a reason.

    The client-asserted actor in the request body is never read; identity flows from here.

    ``hex_service_kit.web.make_get_principal`` is not used, deliberately. It collapses every
    :class:`~hex_service_kit.identity.IdentityError` into a bare 401 carrying "authentication
    required", which is the right answer for a caller who could have authenticated and did not,
    and the wrong one for a deployment that can authenticate NOBODY. An operator reading that
    401 goes looking for a missing credential when the truth is that the bound adapter is an
    unimplemented placeholder or refused to construct at all, and no credential would have
    helped. Those cases raise ``ports/identity.py``'s
    :class:`EndUserAuthUnavailableError`, which carries its own status and its own message, and
    this is where the two are told apart.
    """
    try:
        identity = _identity()
        ctx = RequestContext(headers={k.lower(): v for k, v in request.headers.items()})
        return identity.resolve(ctx)
    except EndUserAuthUnavailableError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except IdentityError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        ) from exc


_authenticate_service_caller = make_require_service_caller(
    lambda request: _request_choice(request).exposure_profile,
    token_env=_TOKEN_ENV,
    allowed_callers_env=_ALLOWED_CALLERS_ENV,
    audience_env=_AUDIENCE_ENV,
)


def require_service_caller(request: Request) -> None:
    """Authenticate the calling SERVICE, refusing to decide at all without a chosen profile.

    The commons dependency picks its scheme from the profile string: a Google-signed OIDC ID
    token under a secure profile, the shared-secret bearer otherwise. The shared-secret path
    stays OPEN when ``EXAMRFI_S2S_TOKEN`` is unset (loopback dev with zero
    secrets), so an UNSET ``EXAMRFI_PROFILE`` must never be allowed to
    select it: that combination is an unauthenticated write path on a deploy nobody configured.
    When no profile was chosen, no scheme was chosen either, and the answer is 401.

    Known limit, stated rather than papered over: with the profile set to ``local``
    DELIBERATELY and no S2S secret, these endpoints remain unauthenticated. That is the offline
    demo posture, and it is bounded by EXPOSURE rather than by this dependency (the guard on the
    app object below), not left open.

    SETTING the secret closes this dependency and nothing else. It does not make the end-user
    routes authenticated and it does not relax the exposure guard, which reads the identity
    binding and never this variable. Under the ``local`` profile the guard therefore keeps the
    whole app, S2S routes included, on loopback: this token is a shared secret in a
    seeded-persona demo posture, not a reason to accept LAN callers. Choose a profile whose
    identity adapter verifies an assertion for that, or opt in with
    ``EXAMRFI_ALLOW_INSECURE_DEMO=1``.
    """
    if not _request_choice(request).service_auth_configured:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "service-to-service authentication is unconfigured: "
                "EXAMRFI_PROFILE is not set, so no authentication scheme "
                "has been chosen"
            ),
        )
    _authenticate_service_caller(request)


# Every relaxation below keys off ``exposure_profile``, never the raw profile: an unset profile
# variable is not consent, so it gets no CORS allowlist, no dev-persona header and HSTS on.
_EXPOSURE = _CHOICE.exposure_profile

#: Service name on every log line and every span. The project slug rather than the friendly
#: name: it is stable, greppable and matches what the tracer reports as `service.name`. A
#: module constant because it holds a rendered value.
_SERVICE_NAME = "exam-rfi-orchestrator"

# Configured at MODULE scope for the same reason the exposure guard is bound at module
# scope: the Dockerfile CMD and `make run-api` serve the app OBJECT, so anything living only
# inside main() never runs in a shipped process. A deployed profile gets JSON that Cloud
# Logging parses and links to the active trace; local and onprem keep plain text. The project
# for the trace resource name is resolved by the commons from GOOGLE_CLOUD_PROJECT.
configure_logging(_EXPOSURE, service=_SERVICE_NAME)

# The interactive docs are a RELAXATION, so they key off the same string as every other one and
# an unconsented run gets none of them either. `openapi_url=None` removes the schema route, and
# Swagger UI and ReDoc both fetch that schema, so this is ONE decision rather than three that
# could disagree. See the module docstring for why there is no opt-in variable to re-enable it.
_DOCS_SERVED = _EXPOSURE == LOCAL_PROFILE
_OPENAPI_URL = "/openapi.json" if _DOCS_SERVED else None
_DOCS_URL = "/docs" if _DOCS_SERVED else None
_REDOC_URL = "/redoc" if _DOCS_SERVED else None

#: The OpenAPI title and description. Each rendered value sits alone on its own line and the
#: sentence is assembled from them, rather than being written out inline: a long friendly_name
#: and a long region on ONE line push it past the 100 column limit `make lint` enforces, and a
#: literal is not something `ruff format` can wrap for us.
_APP_TITLE = "Regulatory Exam and RFI Orchestrator"
_APP_REGION = "asia-southeast1"
_APP_DESCRIPTION = _APP_TITLE + ". Region " + _APP_REGION + "."

app = FastAPI(
    title=_APP_TITLE,
    version="0.1.0",
    description=_APP_DESCRIPTION,
    openapi_url=_OPENAPI_URL,
    docs_url=_DOCS_URL,
    redoc_url=_REDOC_URL,
)
app.state.profile_choice = _CHOICE
app.state.profile = _CHOICE.profile

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowlist(_EXPOSURE, origins_env=_CORS_ORIGINS_ENV),
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"]
    + (["X-Dev-Persona"] if _EXPOSURE == LOCAL_PROFILE else []),
)

add_security_headers(app, profile=_EXPOSURE)

# A request arrives with nothing authenticating the END USER unless BOTH of these hold, and the
# guard bounds every case where either fails:
#
#   1. a profile was chosen. Absent that, nobody selected an identity scheme OR an S2S scheme;
#      the seeded-persona adapter refuses to construct and every S2S route answers 401, but
#      /healthz and the agent card would still answer a stranger, and a deployment in that state
#      has no business being reachable at all. It is also the one case where a settings file
#      that bound a verifying adapter under `local` must NOT buy the relaxation: unset is not
#      consent, whatever the binding says;
#   2. the identity adapter the active binding names DECLARES that it verifies the end user.
#      Seeded personas arrive on a header the caller wrote (client-asserted) and the on-premises
#      placeholder resolves nobody at all (unimplemented); neither authenticates anyone, so
#      neither may switch this off.
#
# Note what is NOT in this expression: EXAMRFI_S2S_TOKEN. A service
# credential is evidence about a calling SERVICE and says nothing about the end-user routes, so
# setting one must not, and now cannot, disable their bound. The S2S routes are bounded by
# `require_service_caller` above, which is where a service credential belongs.
_END_USER_AUTH = end_user_auth_kind()
_END_USER_AUTHENTICATED = _CHOICE.explicit and _END_USER_AUTH == VERIFIED

# The RESTRICTION's profile string. `bind_profile` already reads an unconsented run as `local`
# (the confined case); this widens the same rule to every posture that cannot authenticate an
# end user, so the start-up bound in `main()` and the request-time guard below agree instead of
# one binding every interface while the other refuses every caller on it.
_BIND_PROFILE = _CHOICE.bind_profile if _END_USER_AUTHENTICATED else LOCAL_PROFILE

# Registered LAST, so it is the OUTERMOST middleware: an off-loopback caller is refused before
# CORS, before the header baseline and before any route or dependency runs. Bound to the app
# object so it holds under `uvicorn ...:app --host 0.0.0.0` as well as under `main()`.
add_loopback_exposure_guard(
    app,
    unauthenticated=not _END_USER_AUTHENTICATED,
    insecure_demo_env=_INSECURE_DEMO_ENV,
    posture=_EXPOSURE,
)


def _enum(
    value: str, kind: type[Instrument] | type[RequestTopic] | type[ArtefactClass], field: str
) -> object:
    """Resolve a wire value into its taxonomy member, or refuse with a 422 naming the field.

    An unknown instrument, regime or jurisdiction is never a silent default: a guessed instrument
    picks a response window, and a guessed jurisdiction picks a calendar and a transfer scope.

    EVERY caller-supplied taxonomy value goes through here, including the ones inside the item
    and prior-answer lists. A member constructed directly raises ``ValueError``, which is an
    unhandled 500 and a stack trace in the log: a caller's typo is a validation error naming the
    field, not a server fault.
    """
    try:
        return kind(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"{field}: {value!r} is not a known value",
        ) from exc


def _topic(value: str, field: str) -> RequestTopic:
    resolved = _enum(value, RequestTopic, field)
    assert isinstance(resolved, RequestTopic)
    return resolved


def _artefact(value: str, field: str) -> ArtefactClass:
    resolved = _enum(value, ArtefactClass, field)
    assert isinstance(resolved, ArtefactClass)
    return resolved


@app.post("/v1/response-pack", response_model=ResponsePackResponse, tags=["artifacts"])
def response_pack(
    request: ResponsePackRequest,
    principal: Annotated[Principal, Depends(get_principal)],
) -> ResponsePackResponse:
    """Assemble one supervisory response pack; identity comes from the verified principal.

    Every field that could widen what may be retrieved, unlock a privileged document, move a
    regulatory deadline or lower the approval bar is DERIVED here rather than accepted:
    entitlements from ``principal.entitlement_principals()``, the tenant from the principal, the
    permitted transfer scope from the configured policy matrix, and both waivers and extensions
    from the case store by reference.

    Rule R8: every escalated item and the pack itself are ROUTED to the review console in the
    same request that produced them. Setting the flag is not the escalation; routing is. The pack
    routes unconditionally, because the contract is that a regulator response is maker-checker
    approved before it leaves the firm.
    """
    container = _container()
    service = build_service(container)
    policy = container.settings.policy
    entitlements = frozenset(principal.entitlement_principals())
    tenant = principal.tenant or container.settings.tenant

    instrument = _enum(request.instrument, Instrument, "instrument")
    assert isinstance(instrument, Instrument)
    if request.regime not in policy.regime_register:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"regime: {request.regime!r} is not in the configured regime register",
        )
    if request.jurisdiction not in policy.calendars:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"jurisdiction: {request.jurisdiction!r} has no configured business calendar",
        )
    if not request.items:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="items: a response pack needs at least one numbered question",
        )

    # Resolved server-side and ECHOED, so a replay of this request is exact.
    as_of = request.as_of or utcnow().date()
    regulator_request = RegulatorRequest(
        request_id=request.request_id,
        regulator=request.regulator,
        reference=request.reference,
        instrument=instrument,
        regime=request.regime,
        jurisdiction=request.jurisdiction,
        received_on=request.received_on,
        period_start=request.period_start,
        period_end=request.period_end,
        regulator_due_on=request.regulator_due_on,
        extension_ref=request.extension_ref,
        waiver_ref=request.waiver_ref,
        entitlements=entitlements,
        permitted_transfer_jurisdictions=policy.permitted_transfers(request.jurisdiction),
    )
    prior_answers = tuple(
        PriorAnswer(
            answer_id=prior.answer_id,
            submitted_on=prior.submitted_on,
            item_ref=prior.item_ref,
            topic=_topic(prior.topic, "prior_answers[].topic"),
            assertion_key=prior.assertion_key,
            assertion_value=prior.assertion_value,
        )
        for prior in request.prior_answers
    )

    assessments = []
    item_reviews: dict[str, str] = {}
    for wire_item in request.items:
        topic = _resolve_topic(service, wire_item.item_ref, wire_item.topic, wire_item.question)
        item = RequestItem(
            item_ref=wire_item.item_ref,
            question=wire_item.question,
            topic=topic,
            requested_artefacts=tuple(
                _artefact(value, "items[].requested_artefacts")
                for value in wire_item.requested_artefacts
            ),
            owner=wire_item.owner,
            item_due_on=wire_item.item_due_on,
            evidence_pack_ref=wire_item.evidence_pack_ref,
        )
        try:
            assessment = service.assess_item(
                regulator_request,
                item,
                actor=principal.actor,
                tenant=tenant,
                as_of=as_of,
                prior_answers=[p for p in prior_answers if p.item_ref == item.item_ref],
            )
        except LookupError as exc:
            # A named pack that does not exist is a caller error, and it is deliberately NOT the
            # same answer as a pack that is empty: only one of those is a coverage result.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"items[].evidence_pack_ref: {exc}",
            ) from exc
        if assessment.requires_human_review:
            reference = container.review_router.route(
                assessment, maker=principal.actor, tenant=tenant
            )
            item_reviews[assessment.item_ref] = reference
            service.record_case(regulator_request, assessment, tenant=tenant, review_ref=reference)
        assessments.append(assessment)

    pack = service.assemble_pack(
        regulator_request, assessments, actor=principal.actor, tenant=tenant, as_of=as_of
    )
    # P2: the pack always routes, including when every item in it is clean.
    review_ref = container.review_router.route(pack, maker=principal.actor, tenant=tenant)
    return ResponsePackResponse.from_domain(
        pack, regime=request.regime, review_ref=review_ref, item_reviews=item_reviews
    )


def _resolve_topic(
    service: ResponsePackService, item_ref: str, declared: str, question: str
) -> RequestTopic:
    """Take the DECLARED topic, and refuse an item that names none, suggestion in hand.

    The model is asked, and its answer goes into the refusal rather than into the assessment.
    The topic is not a label: it is the retrieval key, the obligation-register key and rule A2's
    responsiveness filter, so a wrong one drops every document the firm actually holds and the
    pack then states that no admissible document of that class was produced. That is the same
    materially false statement to a supervisor that the DENIED/MISSING rule exists to prevent,
    and it is not a statement a classifier gets to make. So the caller names the topic, or gets
    a 422 that names what the model would have suggested and stops.
    """
    if declared:
        return _topic(declared, "items[].topic")
    suggested_topic, suggested_artefacts = service.propose_topic(item_ref, question)
    suggestion = "none could be proposed either"
    if suggested_topic is not None:
        artefacts = ", ".join(artefact.value for artefact in suggested_artefacts)
        suggestion = f"the classifier suggests {suggested_topic.value!r}"
        if artefacts:
            suggestion = f"{suggestion} and the artefact class(es) {artefacts}"
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=(
            f"items[].topic: {item_ref} names no topic and one cannot be guessed for it; "
            f"{suggestion}. Declare the topic: it decides which documents are responsive, so a "
            "guessed one silently changes what the pack says the firm holds"
        ),
    )


@app.post("/v1/audit/ping", dependencies=[Depends(require_service_caller)], tags=["ops"])
def audit_ping() -> dict[str, bool]:
    """A stand-in S2S endpoint, guarded by fail-closed calling-service authentication."""
    return {"ok": True}


@app.get("/healthz", response_model=HealthResponse, tags=["ops"])
def healthz() -> HealthResponse:
    settings = _container().settings
    return HealthResponse(
        status="ok",
        profile=settings.profile,
        region=settings.region,
        runtime=settings.runtime,
        generator_model=settings.generator_model,
    )


@app.get("/.well-known/agent-card.json", tags=["ops"])
def agent_card() -> dict[str, object]:
    """Serve the A2A discovery card (rule R4: a deployed agent is discoverable and registered).

    Built from the same tool table the agent runtime binds, so the card cannot advertise a skill
    the service does not implement. It carries no secret and no per-caller data.
    """
    from ..agent.agent_card import agent_card_document

    return agent_card_document(_container().settings)


@app.get("/v1/personas", tags=["ops"])
def personas() -> list[dict[str, str]]:
    """List seeded dev personas for the local persona picker (empty outside local).

    The seeded-persona adapter REFUSES to construct when the local profile was inherited rather
    than chosen, so this reports that refusal as a 503 with its reason instead of a bare 500: a
    picker that silently shows nothing looks like a UI bug, not the configuration error it is.
    """
    try:
        identity = _container().identity
    except IdentityError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    lister = getattr(identity, "personas", None)
    if lister is None:
        return []
    return [dict(p) for p in lister()]


def main() -> None:
    """Run the API locally with uvicorn; fail-closed loopback bind whenever no end user can auth."""
    assert_managed_profile_ready(_CHOICE.profile, Settings.load().adapters)

    import uvicorn

    # ``_BIND_PROFILE``, not ``exposure_profile``: this guard treats ``local`` as the RESTRICTIVE
    # case (loopback only), so an unconsented run, and any other posture with no verified
    # end-user identity, must look like ``local`` here even though an unconsented one looks like
    # ``unconfigured`` to every relaxation above.
    host = resolve_bind_host(
        _BIND_PROFILE,
        host_env=_API_HOST_ENV,
        insecure_demo_env=_INSECURE_DEMO_ENV,
    )
    uvicorn.run(app, host=host, port=int(os.environ.get("PORT", "8080")))


if __name__ == "__main__":
    main()
