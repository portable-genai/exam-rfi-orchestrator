"""Tool functions an agent runtime calls: thin, side-effect-honest wrappers on the services.

Design rules, in the order they matter:

* **No business logic here.** The domain service decides HOW; the model only decides WHICH tool
  to call. A rule that lives in a tool wrapper is a rule the CLI and the API do not have.
* **Rule R8 applies on this path too.** An escalated result is ROUTED from inside the tool, in
  the same call that produced it. An agent surface that only returned the flag would be a third
  place an escalation can quietly stop, after the API and the CLI.
* **Import-safe without a runtime.** ``google.adk`` is imported lazily inside
  :func:`build_function_tools`, so these callables are importable, testable and runnable with
  no ADK and no cloud SDK installed.
* **Typed and documented.** A runtime derives each tool's name, description and JSON parameter
  schema from the signature and the docstring, so both are part of the contract.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from hex_service_kit.serialization import to_jsonable
from pii_kit import redact

from ..config import Container, Settings, build_container
from ..domain.kernel import utcnow
from ..domain.models import (
    Instrument,
    RegulatorRequest,
    RequestItem,
    RequestTopic,
)
from ..domain.pii import PII_PATTERNS
from ..services import build_service

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from google.adk.tools import FunctionTool

#: The identity a tool call is attributed to when the runtime propagates none. It names the
#: SERVICE, not a person, so an unattributed action is never mistaken for a human's.
DEFAULT_ACTOR = "exam-rfi-orchestrator-agent"


def _container(settings: Settings | None) -> Container:
    return build_container(settings)


def _redacted(node: Any) -> Any:
    """Mask personal data in every string of a tool result, however deeply it is nested.

    A tool result is not an API response. The API returns to the authenticated caller the text
    that caller just submitted; a TOOL result goes into a model's context, and P-04 says
    minimise the data that reaches a model. The evidence snippet a caller may legitimately read
    back is therefore masked here, on the way to the agent, using the same pattern pack the
    audit write masks with. Walking the whole structure rather than three named fields means a
    future field cannot arrive unredacted just because nobody remembered to add it.
    """
    if isinstance(node, str):
        return redact(node, PII_PATTERNS)
    if isinstance(node, dict):
        return {key: _redacted(value) for key, value in node.items()}
    if isinstance(node, list):
        return [_redacted(value) for value in node]
    return node


def assess_request_item(
    request_id: str,
    reference: str,
    regulator: str,
    instrument: str,
    regime: str,
    jurisdiction: str,
    received_on: str,
    period_start: str,
    period_end: str,
    item_ref: str,
    question: str,
    topic: str,
    owner: str = "",
    regulator_due_on: str = "",
    item_due_on: str = "",
    as_of: str = "",
    actor: str = DEFAULT_ACTOR,
    tenant: str = "",
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Assess one numbered question from a supervisory request, and route it if it escalates.

    Decomposes the question into the artefacts it demands, retrieves the entitled evidence, runs
    the admissibility ladder, computes the deadline on the configured business calendar, and
    returns the coverage, the withholding records, the numbered exhibits and the named blockers.
    An escalated assessment is submitted to the human-review console in this same call (rule R8).

    Nothing here decides release. Every outcome is held for a checker.

    Args:
      request_id: The firm's own case id for the supervisory request.
      reference: The supervisor's own reference on the letter.
      regulator: The requesting supervisor.
      instrument: The supervisory instrument, for example ``rfi``.
      regime: The named public regime the letter cites.
      jurisdiction: Selects the business calendar and the permitted transfer scope.
      received_on: ISO date the request arrived.
      period_start: ISO date the review period starts.
      period_end: ISO date the review period ends.
      item_ref: The number the supervisor gave this question.
      question: The question as written.
      topic: The subject-matter topic of the question.
      owner: Who answers for it; empty is a blocker rather than a default.
      regulator_due_on: ISO date the notice stated, or empty when it stated none.
      item_due_on: ISO date for this item alone, or empty.
      as_of: ISO evaluation date, or empty to use today.
      actor: The verified identity this call is attributed to.
      tenant: Tenant partition asserted on an outbound review.

    Returns:
      A JSON-safe result dict with every string masked for personal data (P-04: a tool result
      goes into a model's context), plus ``review_ref``: where the escalation WENT. It is empty
      only when the item did not escalate, so a caller can tell a routed escalation from a flag
      nobody read.
    """
    container = _container(settings)
    service = build_service(container)
    policy = container.settings.policy
    resolved_tenant = tenant or container.settings.tenant
    supervisory_request = RegulatorRequest(
        request_id=request_id,
        regulator=regulator,
        reference=reference,
        instrument=Instrument(instrument),
        regime=regime,
        jurisdiction=jurisdiction,
        received_on=date.fromisoformat(received_on),
        period_start=date.fromisoformat(period_start),
        period_end=date.fromisoformat(period_end),
        regulator_due_on=date.fromisoformat(regulator_due_on) if regulator_due_on else None,
        # Derived, never accepted from the caller: an agent tool must not be able to widen what
        # may be retrieved or where evidence may lawfully come from.
        entitlements=frozenset(),
        permitted_transfer_jurisdictions=policy.permitted_transfers(jurisdiction),
    )
    item = RequestItem(
        item_ref=item_ref,
        question=question,
        topic=RequestTopic(topic),
        requested_artefacts=(),
        owner=owner,
        item_due_on=date.fromisoformat(item_due_on) if item_due_on else None,
    )
    assessment = service.assess_item(
        supervisory_request,
        item,
        actor=actor,
        tenant=resolved_tenant,
        as_of=date.fromisoformat(as_of) if as_of else utcnow().date(),
    )
    review_ref = ""
    if assessment.requires_human_review:
        review_ref = container.review_router.route(assessment, maker=actor, tenant=resolved_tenant)
        service.record_case(
            supervisory_request, assessment, tenant=resolved_tenant, review_ref=review_ref
        )
    payload = _redacted(to_jsonable(assessment))
    if not isinstance(payload, dict):  # pragma: no cover - dataclasses serialise to objects
        raise TypeError("an item assessment must serialise to a JSON object")
    # Attached after the redaction pass: it is a routing reference, not narrative text, and
    # masking an identifier would break the caller's ability to look the review up.
    payload["review_ref"] = review_ref
    return payload


def verify_audit_trail(settings: Settings | None = None) -> dict[str, Any]:
    """Verify the audit trail's hash chain and its external head anchor.

    Returns:
      A dict with ``ok``, the record counts and a ``detail`` string. ``ok`` is false for an
      edited, deleted or reordered record, and, when an external anchor is configured, for a
      truncated tail as well. Without an anchor a truncation cannot be detected, and the detail
      says so rather than implying a stronger guarantee than the store provides.
    """
    resolved = settings or Settings.load()
    audit = _container(resolved).audit
    verify = getattr(audit, "verify", None)
    if verify is None:
        raise NotImplementedError(
            f"the {resolved.profile} audit adapter does not expose chain verification; a "
            "managed WORM sink is verified by its own retention policy, not from here"
        )
    report = verify()
    return {
        "ok": report.ok,
        "entries": report.entries,
        "chained": report.chained,
        "legacy": report.legacy,
        "first_bad_seq": report.first_bad_seq,
        "detail": report.detail,
        "anchored": bool(resolved.audit_anchor_path),
    }


#: The tool table. The agent card advertises exactly these, by function name.
TOOL_FUNCTIONS = (assess_request_item, verify_audit_trail)


def build_function_tools() -> list[FunctionTool]:
    """Wrap each callable as a runtime FunctionTool (the only ADK-dependent code path).

    The import is deliberately here rather than at module scope: without it this module, the
    card and every tool would need an agent runtime installed to be imported at all, and the
    offline gate installs none.
    """
    # No ignore comment: the missing-import error for this module is already reported (and
    # ignored) at the TYPE_CHECKING import above, and a second one would be flagged as unused.
    from google.adk.tools import FunctionTool

    return [FunctionTool(func=function) for function in TOOL_FUNCTIONS]
