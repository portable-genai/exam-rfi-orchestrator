"""Rule R8: a reviewable outcome is ROUTED to the console, not left in a per-repo boolean.

This is the standing gate for the failure the rule exists to prevent. A repo can set
``requires_human_review = True``, pass every other test, and still auto-execute in practice
because nothing ever reads the flag. So the assertions here are about the ROUTING, not the flag:
an escalation produces an outbound review, a non-escalation produces none, the payload leaves
redacted, and the on-prem placeholder refuses rather than swallowing the escalation.

Two things are specific to this vertical and neither is decoration:

* **The pack routes unconditionally**, including when every item in it is clean, because the
  contract is that a regulator response is maker-checker approved before it leaves the firm.
* **The approval count has exactly one owner.** The engine decides it under rule R3 and the
  payload builder reads it. The skilled-person case below is the one a severity-keyed table in
  the adapter gets wrong: it demands two approvals and never escalates.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from exam_rfi_orchestrator.adapters.gcp.review_router import (
    CloudReviewRouter,
)
from exam_rfi_orchestrator.adapters.local.review_router import (
    LocalReviewRouter,
)
from exam_rfi_orchestrator.adapters.onprem.review_router import (
    OnPremReviewRouter,
)
from exam_rfi_orchestrator.api.app import (
    app,
)
from exam_rfi_orchestrator.config import (
    Settings,
    build_container,
)
from exam_rfi_orchestrator.domain.kernel import (
    Severity,
)
from exam_rfi_orchestrator.domain.models import (
    ItemAssessment,
    RequestItem,
    ResponsePack,
)
from exam_rfi_orchestrator.services import (
    build_service,
)

from tests.fixtures import sample_cases


def _settings(profile: str = "local") -> Settings:
    return Settings(profile=profile, audit_path=":memory:", tenant=sample_cases.TENANT)


def _assess(item: RequestItem, **kwargs: object) -> ItemAssessment:
    service = build_service(build_container(_settings()))
    return service.assess_item(
        kwargs.pop("request", sample_cases.REQUEST),  # type: ignore[arg-type]
        item,
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        as_of=sample_cases.AS_OF,
        prior_answers=kwargs.pop("prior_answers", ()),  # type: ignore[arg-type]
    )


def _pack() -> ResponsePack:
    service = build_service(build_container(_settings()))
    item = service.assess_item(
        sample_cases.REQUEST,
        sample_cases.ROUTINE_ITEM,
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        as_of=sample_cases.AS_OF,
    )
    return service.assemble_pack(
        sample_cases.REQUEST,
        (item,),
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        as_of=sample_cases.AS_OF,
    )


def test_an_escalated_item_produces_an_outbound_review() -> None:
    router = LocalReviewRouter(_settings())
    outcome = _assess(sample_cases.ESCALATING_ITEM, prior_answers=sample_cases.PRIOR_ANSWERS)
    ref = router.route(outcome, maker=sample_cases.ACTOR)
    assert ref, "routing must return a reference, so the caller can record where it went"
    pending = router.outbox.pending()
    assert len(pending) == 1
    review = pending[0].review
    assert review.maker == sample_cases.ACTOR
    assert review.tenant == sample_cases.TENANT
    assert review.severity == Severity.CRITICAL.value
    assert review.source_key, "a durable outbox needs an idempotency key"


def test_the_engine_owns_the_approval_count_and_the_payload_reads_it() -> None:
    """The skilled-person item: dual control WITHOUT escalation.

    A severity-keyed table in the payload builder sends this for one approval while the engine
    says two, and the two disagree the first time an instrument-driven case appears at low
    severity. That is this case.
    """
    outcome = _assess(sample_cases.SKILLED_PERSON_ITEM, request=sample_cases.SKILLED_PERSON_REQUEST)
    assert outcome.requires_human_review is False
    assert outcome.severity is Severity.LOW
    assert outcome.required_approvals == 2

    router = LocalReviewRouter(_settings())
    router.route(outcome, maker=sample_cases.ACTOR)
    assert router.outbox.pending()[0].review.required_approvals == outcome.required_approvals


def test_a_clean_pack_still_routes_and_demands_two_approvals() -> None:
    """Rule P2. A good pack routes for APPROVAL rather than for rescue."""
    pack = _pack()
    assert pack.disposition.value == "on_track"
    assert pack.requires_human_review is True
    assert pack.required_approvals == 2
    router = LocalReviewRouter(_settings())
    assert router.route(pack, maker=sample_cases.ACTOR)
    review = router.outbox.pending()[0].review
    assert review.required_approvals == 2
    assert review.source_key.endswith(":pack"), (
        "an item exception and a pack approval must carry different source keys, or a console "
        "that merged them would collapse two different reviews with two different readers"
    )


def test_the_payload_is_redacted_before_it_leaves_the_process() -> None:
    """The console is a shared sink; a raw identifier must never reach the wire."""
    router = LocalReviewRouter(_settings())
    router.route(_assess(sample_cases.PII_ITEM), maker=sample_cases.ACTOR)
    review = router.outbox.pending()[0].review
    wire = repr(review.to_payload())
    assert sample_cases.PLANTED_NRIC not in wire
    assert "REDACTED" in wire


def test_the_managed_router_refuses_when_no_console_is_configured() -> None:
    """An escalation with nowhere to go must fail loudly, not return as if it were reviewed."""
    router = CloudReviewRouter(Settings(profile="gcp", audit_path=":memory:", review_url=""))
    with pytest.raises(RuntimeError, match="R8"):
        router.route(
            _assess(sample_cases.ESCALATING_ITEM, prior_answers=sample_cases.PRIOR_ANSWERS),
            maker=sample_cases.ACTOR,
        )


def test_the_onprem_placeholder_refuses_rather_than_dropping_the_escalation() -> None:
    router = OnPremReviewRouter(_settings("onprem"))
    with pytest.raises(NotImplementedError, match="R8"):
        router.route(_assess(sample_cases.ESCALATING_ITEM), maker=sample_cases.ACTOR)


def test_the_api_routes_every_escalation_and_the_pack_in_the_same_request() -> None:
    """The serving path, not just the adapter: an escalation must not depend on a later job."""
    client = TestClient(app, client=("127.0.0.1", 50000))
    body = client.post(
        "/v1/response-pack",
        json=_wire_request(),
        headers={"X-Dev-Persona": "approver"},
    ).json()
    assert body["requires_human_review"] is True
    assert body["review_ref"], "rule P2: a pack with no routing reference went nowhere"
    assert body["release_state"] == "held_for_checker"

    by_ref = {item["item_ref"]: item for item in body["items"]}
    assert by_ref["2.c"]["requires_human_review"] is True
    assert by_ref["2.c"]["review_ref"], "an escalated item with no routing reference went nowhere"
    assert by_ref["1.a"]["requires_human_review"] is False
    assert by_ref["1.a"]["review_ref"] == "", "a clean item must not manufacture a review"


def _wire_request() -> dict[str, object]:
    request = sample_cases.REQUEST
    return {
        "request_id": request.request_id,
        "regulator": request.regulator,
        "reference": request.reference,
        "instrument": request.instrument.value,
        "regime": request.regime,
        "jurisdiction": request.jurisdiction,
        "received_on": request.received_on.isoformat(),
        "period_start": request.period_start.isoformat(),
        "period_end": request.period_end.isoformat(),
        "regulator_due_on": request.regulator_due_on.isoformat()
        if request.regulator_due_on
        else None,
        "as_of": sample_cases.AS_OF.isoformat(),
        "items": [
            {
                "item_ref": sample_cases.ROUTINE_ITEM.item_ref,
                "question": sample_cases.ROUTINE_ITEM.question,
                "topic": sample_cases.ROUTINE_ITEM.topic.value,
                "requested_artefacts": [
                    a.value for a in sample_cases.ROUTINE_ITEM.requested_artefacts
                ],
                "owner": sample_cases.ROUTINE_ITEM.owner,
            },
            {
                "item_ref": sample_cases.ESCALATING_ITEM.item_ref,
                "question": sample_cases.ESCALATING_ITEM.question,
                "topic": sample_cases.ESCALATING_ITEM.topic.value,
                "requested_artefacts": [
                    a.value for a in sample_cases.ESCALATING_ITEM.requested_artefacts
                ],
                "owner": "",
                "item_due_on": "2027-03-19",
            },
        ],
        "prior_answers": [
            {
                "answer_id": prior.answer_id,
                "submitted_on": prior.submitted_on.isoformat(),
                "item_ref": prior.item_ref,
                "topic": prior.topic.value,
                "assertion_key": prior.assertion_key,
                "assertion_value": prior.assertion_value,
            }
            for prior in sample_cases.PRIOR_ANSWERS
        ],
    }
