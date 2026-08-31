"""Canonical synthetic cases, shared by the unit and contract suites.

Every party is obviously fictional, the supervisor is an invented authority that carries
FICTIONAL in the value itself, and every address is an ``.example`` domain. One canonical
request with a routine item, an escalating item and a personal-data item is enough for the
contract suite: parity means the SAME request through every implementation, so the request has
to have one home rather than being retyped per test.

The dates are fixed rather than relative to today, and that is load-bearing. Every clock
assertion in the suite would otherwise drift with the calendar and would be green for the wrong
reason on some days and red on others.
"""

from __future__ import annotations

from datetime import date

from exam_rfi_orchestrator.domain.models import (
    ArtefactClass,
    Instrument,
    PriorAnswer,
    RegulatorRequest,
    RequestItem,
    RequestTopic,
)
from exam_rfi_orchestrator.domain.policy import DEFAULT_POLICY

#: The verified principal the tests attribute work to (never a client-asserted actor).
ACTOR = "analyst@bank.example"

#: A tenant partition, so the outbound-review assertions are not all on the empty string.
TENANT = "demo-bank"

#: The entitlements a fully entitled exam-team caller carries, matching the seeded personas.
ENTITLEMENTS = frozenset({"group:analyst", "group:risk", "group:approver"})

#: A caller narrowed to one group, so the entitlement-suppression path has a fixture.
NARROW_ENTITLEMENTS = frozenset({"group:analyst"})

#: The evaluation date. Fixed, so every clock assertion is stable forever.
AS_OF = date(2027, 3, 15)

#: A planted identifier, so a redaction assertion has an independent literal to look for rather
#: than trusting the pattern pack to agree with itself. Checksum-valid, which the SG row needs.
PLANTED_NRIC = "S1234567D"


def request(**overrides: object) -> RegulatorRequest:
    """The canonical request header, with any field overridden for one test."""
    base: dict[str, object] = {
        "request_id": "EXAM-2027-0014",
        "regulator": "Meridian Prudential Authority (FICTIONAL)",
        "reference": "MPA-FICTIONAL/EX/2027/0014",
        "instrument": Instrument.RFI,
        "regime": "supervisory-information-request",
        "jurisdiction": "SG",
        "received_on": date(2027, 3, 1),
        "period_start": date(2026, 4, 1),
        "period_end": date(2027, 2, 28),
        "regulator_due_on": date(2027, 4, 30),
        "entitlements": ENTITLEMENTS,
        "permitted_transfer_jurisdictions": DEFAULT_POLICY.permitted_transfers("SG"),
    }
    base.update(overrides)
    return RegulatorRequest(**base)  # type: ignore[arg-type]


REQUEST = request()

#: An item that must NOT escalate: a router that manufactured a review here would be lying.
ROUTINE_ITEM = RequestItem(
    item_ref="1.a",
    question=(
        "Provide the financial-crime policy in force during the review period and the "
        "transaction-monitoring management information reported to the board for the two "
        "quarters ending in the period. Direct any queries to rfi.desk@meridian-bank.example."
    ),
    topic=RequestTopic.AML_FINANCIAL_CRIME,
    requested_artefacts=(ArtefactClass.POLICY, ArtefactClass.MANAGEMENT_INFORMATION),
    owner="Head of Financial Crime (FICTIONAL)",
)

#: An item that MUST escalate: a missing artefact, no owner, a red clock and a contradiction.
ESCALATING_ITEM = RequestItem(
    item_ref="2.c",
    question=(
        "Provide the results of independent testing of sanctions screening for the review "
        "period and the remediation status of every exception raised. Case officer contact "
        "casework@meridian-bank.example."
    ),
    topic=RequestTopic.TECHNOLOGY_AND_CYBER,
    requested_artefacts=(ArtefactClass.CONTROL_TEST_RESULT,),
    owner="",
    item_due_on=date(2027, 3, 19),
)

#: The prior submission the escalating item contradicts.
PRIOR_ANSWERS: tuple[PriorAnswer, ...] = (
    PriorAnswer(
        answer_id="PRIOR-FICTIONAL-2026-08",
        submitted_on=date(2026, 8, 14),
        item_ref="2.c",
        topic=RequestTopic.TECHNOLOGY_AND_CYBER,
        assertion_key="sanctions_screening_vendor",
        assertion_value="Northwind Screening (FICTIONAL)",
    ),
)

#: An escalating item whose evidence and question both carry personal data, for the
#: redact-before-anything proofs, and whose corpus spans all three withhold rules.
PII_ITEM = RequestItem(
    item_ref="3.a",
    question=(
        "Provide all internal correspondence and legal analysis concerning the payments outage "
        "in the review period, together with the customer files of every affected client. "
        f"Complainant NRIC {PLANTED_NRIC}."
    ),
    topic=RequestTopic.DATA_PRIVACY,
    requested_artefacts=(ArtefactClass.ISSUE_LOG, ArtefactClass.CUSTOMER_FILE),
    owner="Data Protection Officer (FICTIONAL)",
)

#: A skilled-person item that demands dual control and never escalates, which is the case a
#: severity-keyed approvals table in the review payload builder gets wrong.
SKILLED_PERSON_REQUEST = request(
    request_id="EXAM-2027-0041",
    reference="MPA-FICTIONAL/EX/2027/0041",
    instrument=Instrument.S166_SKILLED_PERSON,
    regime="skilled-person-review",
)

SKILLED_PERSON_ITEM = RequestItem(
    item_ref="2",
    question=(
        "Provide the terms of reference and the governance arrangements for the skilled person "
        "review, together with the board minute approving them. Programme mailbox "
        "s166.programme@meridian-bank.example."
    ),
    topic=RequestTopic.GOVERNANCE,
    owner="Skilled Person Programme Office (FICTIONAL)",
)


def _wire_item(item: RequestItem) -> dict[str, object]:
    body: dict[str, object] = {
        "item_ref": item.item_ref,
        "question": item.question,
        "topic": item.topic.value,
        "requested_artefacts": [artefact.value for artefact in item.requested_artefacts],
        "owner": item.owner,
        "evidence_pack_ref": item.evidence_pack_ref,
    }
    if item.item_due_on is not None:
        body["item_due_on"] = item.item_due_on.isoformat()
    return body


def wire_body(*items: RequestItem, prior_answers: bool = False) -> dict[str, object]:
    """The POST body for ``/v1/response-pack``, built from the same fixtures the domain uses.

    One home for the wire shape, so an API test and a domain test can never quietly disagree
    about what the same case is. ``as_of`` is pinned, so the API answers are byte-stable.
    """
    chosen = items or (ROUTINE_ITEM,)
    body: dict[str, object] = {
        "request_id": REQUEST.request_id,
        "regulator": REQUEST.regulator,
        "reference": REQUEST.reference,
        "instrument": REQUEST.instrument.value,
        "regime": REQUEST.regime,
        "jurisdiction": REQUEST.jurisdiction,
        "received_on": REQUEST.received_on.isoformat(),
        "period_start": REQUEST.period_start.isoformat(),
        "period_end": REQUEST.period_end.isoformat(),
        "regulator_due_on": (
            REQUEST.regulator_due_on.isoformat() if REQUEST.regulator_due_on else None
        ),
        "as_of": AS_OF.isoformat(),
        "items": [_wire_item(item) for item in chosen],
    }
    if prior_answers:
        body["prior_answers"] = [
            {
                "answer_id": prior.answer_id,
                "submitted_on": prior.submitted_on.isoformat(),
                "item_ref": prior.item_ref,
                "topic": prior.topic.value,
                "assertion_key": prior.assertion_key,
                "assertion_value": prior.assertion_value,
            }
            for prior in PRIOR_ANSWERS
        ]
    return body
