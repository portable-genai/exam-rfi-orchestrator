"""ONE canonical request per port, shared by the structural and behavioural contract suites.

Parity means the same request through every implementation, so the request needs a single home.
Retyping it per suite is how two "parity" tests end up asserting different things.

Each :class:`PortCase` answers three questions about one port:

* ``invoke``   : what a single canonical call to this port looks like;
* ``answered`` : what it means for the OFFLINE family to have actually answered (a port that
  returns ``None`` and records nothing has not answered, it has merely not raised);
* ``managed_refusal`` : what the MANAGED family must do when called with no cloud reachable.
  Never a silent success: either it refuses because it is unconfigured, or its lazy SDK import
  fails. Both are honest; returning as if the work happened is not.

Adding a port means adding a case here. ``test_port_parity.py`` fails the build if this table
and the port map ever disagree, so the touch list in ``CONTRIBUTING.md`` is enforced rather than
merely written down.

``CANONICAL_RESULT`` is an :class:`~exam_rfi_orchestrator.domain.models.ItemAssessment` rather
than a second, simpler shape. The review router is typed on the reviewable-outcome Protocol that
both an item assessment and a whole pack satisfy, so routing the real artifact is what the
parity suite has to exercise.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from agent_eval_kit import EvalReport
from hex_service_kit.identity import IdentityError, Principal, RequestContext
from hex_service_kit.observability import TokenUsage

from exam_rfi_orchestrator.domain.kernel import (
    AuditEvent,
    Citation,
    Decision,
    Severity,
)
from exam_rfi_orchestrator.domain.models import (
    ArtefactClass,
    BlockerKind,
    CaseRecord,
    Disposition,
    ItemAssessment,
    NarrativeDraft,
    ReleaseState,
    RequestTopic,
    RetrievalQuery,
    RetrievalResult,
    SlaClock,
)
from exam_rfi_orchestrator.ports.generation import GenerationRequest

from tests.fixtures import sample_cases

#: The audit record every audit-port implementation is handed. Already redacted, as the port
#: requires: a raw identifier must never reach a WORM record.
CANONICAL_EVENT = AuditEvent(
    action="assess_item",
    actor=sample_cases.ACTOR,
    decision=Decision.ESCALATED,
    severity=Severity.HIGH,
    redacted_summary="MPA-FICTIONAL/EX/2027/0014 item 2.c: blocked completeness=75%",
    citations=(
        Citation(source_id="item:EXAM-2027-0014:2.c", title="Request item 2.c", snippet="testing"),
    ),
)

_CANONICAL_SLA = SlaClock(
    due_on=date(2027, 3, 19),
    internal_due_on=date(2027, 3, 12),
    due_basis="regulator_stated",
    extension_request_by=date(2027, 3, 5),
    business_days_remaining=-1,
    band=Severity.CRITICAL,
    breached=False,
    buffer_consumed=True,
    calendar_id="SG",
    calendar_version="2027.1",
)

#: The escalated outcome every review-router implementation is handed (rule R8's payload).
CANONICAL_RESULT = ItemAssessment(
    item_ref="2.c",
    subject=f"{sample_cases.REQUEST.reference} item 2.c",
    case_ref=f"{sample_cases.REQUEST.request_id}:2.c",
    topic=RequestTopic.TECHNOLOGY_AND_CYBER,
    owner="",
    sla=_CANONICAL_SLA,
    narrative=NarrativeDraft(text="", drafted=False),
    disposition=Disposition.BLOCKED,
    severity=Severity.HIGH,
    decision=Decision.ESCALATED,
    summary="MPA-FICTIONAL/EX/2027/0014 item 2.c: blocked completeness=75%",
    requires_human_review=True,
    completeness_pct=75,
    satisfied_mandatory=3,
    total_mandatory=4,
    release_state=ReleaseState.HELD_FOR_CHECKER,
    release_blockers=(BlockerKind.MISSING_ARTEFACT, BlockerKind.BELOW_MIN_COMPLETENESS),
    required_approvals=2,
    citations=(
        Citation(source_id="item:EXAM-2027-0014:2.c", title="Request item 2.c", snippet="testing"),
    ),
)

#: The inbound transport context every identity implementation is handed.
CANONICAL_CONTEXT = RequestContext(headers={"x-dev-persona": "auditor"})

#: The retrieval query every knowledge-base implementation is handed.
CANONICAL_QUERY = RetrievalQuery(
    item_ref="1.a",
    topic=RequestTopic.AML_FINANCIAL_CRIME,
    artefacts=(ArtefactClass.POLICY, ArtefactClass.MANAGEMENT_INFORMATION),
    period_start=sample_cases.REQUEST.period_start,
    period_end=sample_cases.REQUEST.period_end,
    entitlements=sample_cases.ENTITLEMENTS,
)

#: The generation request every generation implementation is handed.
CANONICAL_GENERATION = GenerationRequest(
    system="You restate engine facts.",
    prompt="Facts (use ONLY these numbers):\ncompleteness_pct=100\nEX-1.a-01=EX-1.a-01 Policy",
    facts=(("completeness_pct", "100"), ("EX-1.a-01", "EX-1.a-01 Policy")),
    response_keys=("narrative", "proposed_artefacts"),
)

#: The case row every case-store implementation is handed.
CANONICAL_CASE = CaseRecord(
    request_id=sample_cases.REQUEST.request_id,
    item_ref="2.c",
    tenant=sample_cases.TENANT,
    owner="",
    disposition=Disposition.BLOCKED,
    band=Severity.CRITICAL,
    due_on=date(2027, 3, 19),
    internal_due_on=date(2027, 3, 12),
    business_days_remaining=-1,
    completeness_pct=75,
    acl_labels=sample_cases.ENTITLEMENTS,
)


@dataclass(frozen=True, slots=True)
class PortCase:
    """One port's canonical call plus the two verdicts the parity suites need."""

    invoke: Callable[[Any], Any]
    answered: Callable[[Any, Any], bool]
    managed_refusal: tuple[type[BaseException], ...]
    detail: str


def _audit_invoke(adapter: Any) -> Any:
    return adapter.record(CANONICAL_EVENT)


def _audit_answered(adapter: Any, _result: Any) -> bool:
    stored = adapter.log.read_all()
    return bool(stored) and stored[-1]["actor"] == sample_cases.ACTOR and adapter.verify().ok


def _identity_invoke(adapter: Any) -> Any:
    return adapter.resolve(CANONICAL_CONTEXT)


def _identity_answered(_adapter: Any, result: Any) -> bool:
    return isinstance(result, Principal) and bool(result.actor)


def _review_invoke(adapter: Any) -> Any:
    return adapter.route(CANONICAL_RESULT, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)


def _review_answered(adapter: Any, result: Any) -> bool:
    return bool(result) and len(adapter.outbox.pending()) == 1


def _tracer_invoke(adapter: Any) -> Any:
    with adapter.span("canonical.unit", action="canonical"):
        adapter.record_token_usage(TokenUsage(input_tokens=7, output_tokens=2), "canonical-model")
    return True


def _tracer_answered(adapter: Any, result: Any) -> bool:
    return bool(result)


def _evaluation_invoke(adapter: Any) -> Any:
    return adapter.evaluate("eval/datasets/canonical.jsonl")


def _evaluation_answered(adapter: Any, result: Any) -> bool:
    return isinstance(result, EvalReport) and result.dataset.endswith("canonical.jsonl")


def _knowledge_base_invoke(adapter: Any) -> Any:
    return adapter.search(CANONICAL_QUERY)


def _knowledge_base_answered(_adapter: Any, result: Any) -> bool:
    # A tuple that merely exists is not an answer: the offline corpus must return real,
    # inspectable documents carrying the ACL labels and tags the ladder actually reads.
    return (
        isinstance(result, RetrievalResult)
        and bool(result.items)
        and all(document.acl_labels for document in result.items)
    )


def _obligations_invoke(adapter: Any) -> Any:
    return adapter.obligations_for(RequestTopic.AML_FINANCIAL_CRIME, "SG")


def _obligations_answered(_adapter: Any, result: Any) -> bool:
    return bool(result) and all(row.required_artefacts for row in result)


def _evidence_packs_invoke(adapter: Any) -> Any:
    return adapter.packs_for("OBL-OUT-001")


def _evidence_packs_answered(_adapter: Any, result: Any) -> bool:
    return bool(result) and all(pack.items for pack in result)


def _generation_invoke(adapter: Any) -> Any:
    return adapter.generate(CANONICAL_GENERATION)


def _generation_answered(_adapter: Any, result: Any) -> bool:
    return bool(getattr(result, "text", "").strip())


def _case_store_invoke(adapter: Any) -> Any:
    adapter.record(CANONICAL_CASE)
    return adapter.open_items(sample_cases.TENANT, sample_cases.ENTITLEMENTS)


def _case_store_answered(_adapter: Any, result: Any) -> bool:
    return bool(result) and result[0].item_ref == "2.c"


CANONICAL_CALLS: dict[str, PortCase] = {
    "audit": PortCase(
        invoke=_audit_invoke,
        answered=_audit_answered,
        # The lazy `google.cloud` import is the first thing the managed sink does.
        managed_refusal=(ImportError,),
        detail="write one already-redacted WORM record",
    ),
    "identity": PortCase(
        invoke=_identity_invoke,
        answered=_identity_answered,
        # No IAP assertion header offline, so the managed adapter refuses before importing.
        managed_refusal=(IdentityError,),
        detail="resolve a verified principal from transport context",
    ),
    "review_router": PortCase(
        invoke=_review_invoke,
        answered=_review_answered,
        # Rule R8: with no console configured the managed router must refuse, not swallow.
        managed_refusal=(RuntimeError,),
        detail="route one escalated outcome to human review",
    ),
    "tracer": PortCase(
        invoke=_tracer_invoke,
        answered=_tracer_answered,
        # NOTHING. Tracing is not essential to correctness, so the managed adapter must not
        # refuse offline either: with no SDK installed it degrades to a no-op and the traced
        # body still runs. An adapter that raised here would take a request down over a
        # diagnostic, which is the opposite of what every other port on this table wants.
        managed_refusal=(),
        detail="open one span and report the cost of a model call",
    ),
    "evaluation": PortCase(
        invoke=_evaluation_invoke,
        answered=_evaluation_answered,
        # The managed gate reaches the promotion authority over HTTP, unreachable offline.
        managed_refusal=(Exception,),
        detail="score one golden dataset through the promotion authority",
    ),
    "knowledge_base": PortCase(
        invoke=_knowledge_base_invoke,
        answered=_knowledge_base_answered,
        # No endpoint configured offline, so the managed adapter refuses rather than reaching a
        # default host. An empty success here would be a false statement about what the firm holds.
        managed_refusal=(RuntimeError,),
        detail="retrieve entitled candidate documents with their handling tags",
    ),
    "obligations": PortCase(
        invoke=_obligations_invoke,
        answered=_obligations_answered,
        managed_refusal=(RuntimeError,),
        detail="read the obligations that bear on a topic in a jurisdiction",
    ),
    "evidence_packs": PortCase(
        invoke=_evidence_packs_invoke,
        answered=_evidence_packs_answered,
        managed_refusal=(RuntimeError,),
        detail="read an assembled control-evidence pack for reuse",
    ),
    "generation": PortCase(
        invoke=_generation_invoke,
        answered=_generation_answered,
        # No model configured offline, so the managed adapter refuses rather than defaulting.
        managed_refusal=(RuntimeError,),
        detail="return raw model text for one narration request",
    ),
    "case_store": PortCase(
        invoke=_case_store_invoke,
        answered=_case_store_answered,
        # No collection configured offline, so the managed adapter refuses rather than writing
        # the open-item board to a default place.
        managed_refusal=(RuntimeError,),
        detail="record one case row and read the open-item board back",
    ),
}
