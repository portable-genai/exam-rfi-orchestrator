"""The admissibility ladder and the coverage rules, with the ladder's ORDER held to the wall.

Every rule here decides what a regulator is told, so each one is exercised against a document
built to trip exactly it. Three of these tests exist because the obvious implementation is wrong
in a way that is invisible in a green demo:

* **A stale privileged document must be WITHHELD, not produced because it is old.** Evaluating
  the period rule before the withhold rules gives it the status ``stale``, which rule A3
  documents as still usable, and the memo goes to the supervisor. The evaluation order is
  therefore A1, A2, A4, A5, A6, A3 and this file is what holds it there.
* **DENIED must never collapse into MISSING.** "You are not entitled to see this" and "the firm
  holds no such document" are different statements and only one of them is true.
* **A document that arrives exceeding the caller's entitlements is a BOUNDARY FAILURE**, not a
  caller error, so it is dropped and raises at CRITICAL rather than at HIGH.
"""

from __future__ import annotations

from datetime import date

from exam_rfi_orchestrator.domain.artefact_taxonomy import decompose
from exam_rfi_orchestrator.domain.coverage_engine import assess_evidence
from exam_rfi_orchestrator.domain.kernel import Severity
from exam_rfi_orchestrator.domain.models import (
    ArtefactClass,
    BlockerKind,
    EvidenceItem,
    EvidenceStatus,
    RequestItem,
    RequestTopic,
    SensitivityTag,
    WaiverRecord,
)
from exam_rfi_orchestrator.domain.policy import DEFAULT_POLICY

from tests.fixtures import sample_cases

_ENTITLED = frozenset({"group:risk"})
_AS_OF = sample_cases.AS_OF


def _item(**overrides: object) -> RequestItem:
    base: dict[str, object] = {
        "item_ref": "1.a",
        "question": "Provide the policy.",
        "topic": RequestTopic.DATA_PRIVACY,
        "requested_artefacts": (ArtefactClass.POLICY,),
        "owner": "Data Protection Officer (FICTIONAL)",
    }
    base.update(overrides)
    return RequestItem(**base)  # type: ignore[arg-type]


def _document(**overrides: object) -> EvidenceItem:
    base: dict[str, object] = {
        "doc_id": "doc-1",
        "title": "Personal data handling policy (FICTIONAL)",
        "artefact": ArtefactClass.POLICY,
        "topic": RequestTopic.DATA_PRIVACY,
        "as_of": date(2026, 9, 1),
        "owning_jurisdiction": "SG",
        "acl_labels": _ENTITLED,
        "snippet": "Handling rules (FICTIONAL).",
    }
    base.update(overrides)
    return EvidenceItem(**base)  # type: ignore[arg-type]


def _assess(
    documents: list[EvidenceItem],
    *,
    item: RequestItem | None = None,
    entitlements: frozenset[str] = _ENTITLED,
    suppressed: int = 0,
    suppressed_by_artefact: dict[ArtefactClass, int] | None = None,
    waiver: WaiverRecord | None = None,
) -> object:
    resolved = item or _item()
    request = sample_cases.request(entitlements=entitlements)
    return assess_evidence(
        request,
        resolved,
        decompose(resolved),
        documents,
        as_of=_AS_OF,
        policy=DEFAULT_POLICY,
        waiver=waiver,
        tenant=sample_cases.TENANT,
        suppressed_by_entitlement=suppressed,
        suppressed_by_artefact=suppressed_by_artefact,
    )


def _states(assessment: object) -> dict[str, str]:
    return {row.artefact.value: row.state.value for row in assessment.coverage}  # type: ignore[attr-defined]


def _kinds(assessment: object) -> list[str]:
    return [blocker.kind.value for blocker in assessment.blockers]  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------- #
# The ladder's order
# --------------------------------------------------------------------------------------- #
def test_a_privileged_document_that_is_merely_stale_is_still_withheld() -> None:
    """The order test. A3 before A4 would call this ``stale``, which rule A3 calls usable."""
    stale_and_privileged = _document(
        doc_id="doc-privileged-stale",
        as_of=date(2025, 6, 1),
        sensitivity=(SensitivityTag.LEGALLY_PRIVILEGED,),
    )
    assessment = _assess([stale_and_privileged])
    statuses = [link.status for link in assessment.links]  # type: ignore[attr-defined]
    assert statuses == [EvidenceStatus.WITHHELD_PRIVILEGED]
    assert _states(assessment)["policy"] == "withheld"
    assert "privilege_hold" in _kinds(assessment)


def test_a_privileged_document_is_produced_only_when_a_STORED_waiver_resolves() -> None:
    """A client-asserted waiver unlocks nothing; a record for THIS tenant does."""
    privileged = _document(
        doc_id="doc-privileged", sensitivity=(SensitivityTag.LEGALLY_PRIVILEGED,)
    )
    assert _states(_assess([privileged]))["policy"] == "withheld"

    waiver = WaiverRecord(
        ref="WVR-FICTIONAL-TEST",
        tenant=sample_cases.TENANT,
        scope="data_privacy",
        granted_by="General Counsel (FICTIONAL)",
        expires_on=date(2027, 12, 31),
    )
    assert _states(_assess([privileged], waiver=waiver))["policy"] == "covered"


def test_an_expired_or_wrong_tenant_waiver_is_the_same_as_no_waiver() -> None:
    privileged = _document(
        doc_id="doc-privileged", sensitivity=(SensitivityTag.LEGALLY_PRIVILEGED,)
    )
    expired = WaiverRecord(
        ref="WVR-FICTIONAL-TEST",
        tenant=sample_cases.TENANT,
        scope="data_privacy",
        granted_by="General Counsel (FICTIONAL)",
        expires_on=date(2027, 1, 1),
    )
    other_tenant = WaiverRecord(
        ref="WVR-FICTIONAL-TEST",
        tenant="other-bank",
        scope="data_privacy",
        granted_by="General Counsel (FICTIONAL)",
        expires_on=date(2027, 12, 31),
    )
    assert _states(_assess([privileged], waiver=expired))["policy"] == "withheld"
    assert _states(_assess([privileged], waiver=other_tenant))["policy"] == "withheld"


def test_a_silent_withhold_row_carries_an_identifier_and_a_basis_and_no_title() -> None:
    filing = _document(doc_id="doc-filing", sensitivity=(SensitivityTag.SAR_CONFIDENTIAL,))
    assessment = _assess([filing])
    record = assessment.withheld[0]  # type: ignore[attr-defined]
    assert record.doc_id == "doc-filing"
    assert record.basis_rule == "A5"
    assert record.title == ""
    assert record.citation is None
    # And no blocker names it: a blocker would put the fact of the filing back on the surfaces
    # the rule just removed it from.
    assert "privilege_hold" not in _kinds(assessment)


def test_a_document_outside_the_permitted_transfer_scope_is_withheld() -> None:
    offshore = _document(doc_id="doc-offshore", owning_jurisdiction="JP")
    assessment = _assess([offshore])
    assert assessment.withheld[0].basis_rule == "A6"  # type: ignore[attr-defined]
    assert "restricted_transfer" in _kinds(assessment)


# --------------------------------------------------------------------------------------- #
# Denied is not missing (rule C4)
# --------------------------------------------------------------------------------------- #
def test_a_suppressed_requirement_reads_denied_and_not_missing() -> None:
    assessment = _assess([], suppressed=2)
    assert _states(assessment)["policy"] == "denied"
    assert "missing_artefact" not in _kinds(assessment)
    detail = next(b.detail for b in assessment.blockers)  # type: ignore[attr-defined]
    assert "2" in detail
    # The detail names a COUNT and nothing else: no title, no id.
    assert "doc-" not in detail


def test_with_nothing_suppressed_the_same_requirement_reads_missing() -> None:
    """The control. Without it, "denied is not missing" would be true for the boring reason."""
    assessment = _assess([])
    assert _states(assessment)["policy"] == "missing"
    assert "missing_artefact" in _kinds(assessment)


def test_a_suppression_denies_only_the_class_it_actually_happened_to() -> None:
    """The other direction of rule C4, and the one an item-level count gets wrong.

    A store that refused two policies says nothing about the transaction sample. Reading the
    item-level total for every requirement puts "you are not entitled to read this" on a class
    the firm genuinely holds nothing of, which is a false statement to a supervisor made by the
    rule that exists to prevent the mirror image of it.
    """
    item = _item(requested_artefacts=(ArtefactClass.POLICY, ArtefactClass.TRANSACTION_SAMPLE))
    attributed = _assess(
        [],
        item=item,
        suppressed=2,
        suppressed_by_artefact={ArtefactClass.POLICY: 2},
    )
    states = _states(attributed)
    assert states["policy"] == "denied"
    assert states["transaction_sample"] == "missing", (
        "a suppression of one class denied a class nothing was suppressed for"
    )
    # The item-level blocker still names the total, because a caller is owed the fact that
    # something was refused somewhere in this item.
    assert "denied_no_entitlement" in _kinds(attributed)


def test_a_store_that_cannot_attribute_keeps_the_over_broad_reading() -> None:
    """The fallback, stated as a test so it is a decision rather than an accident.

    An empty split with a non-zero total is a store that counted and could not say of what.
    Reading zero there would turn "you may not read this" into "the firm holds nothing", which
    is the error rule C4 exists to prevent, so the over-broad reading stands instead.
    """
    item = _item(requested_artefacts=(ArtefactClass.POLICY, ArtefactClass.TRANSACTION_SAMPLE))
    unattributed = _assess([], item=item, suppressed=2)
    assert _states(unattributed)["transaction_sample"] == "denied"


def test_a_document_that_arrives_exceeding_the_entitlements_is_a_boundary_failure() -> None:
    """Dropped AND raised at CRITICAL: there the retrieval boundary failed, not the caller."""
    leaked = _document(doc_id="doc-leaked", acl_labels=frozenset({"group:board-only"}))
    assessment = _assess([leaked])
    blockers = [b for b in assessment.blockers if b.kind is BlockerKind.DENIED_NO_ENTITLEMENT]  # type: ignore[attr-defined]
    assert blockers and blockers[0].severity is Severity.CRITICAL
    assert _states(assessment)["policy"] == "denied"
    assert not [link for link in assessment.links if link.status is EvidenceStatus.ACCEPTED]  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------- #
# Responsiveness, staleness and the completeness arithmetic
# --------------------------------------------------------------------------------------- #
def test_a_non_responsive_document_is_dropped_and_counted_but_never_listed() -> None:
    """Listing a document nobody asked for tells a supervisor about material outside the request."""
    wrong_class = _document(doc_id="doc-wrong-class", artefact=ArtefactClass.TRANSACTION_SAMPLE)
    wrong_topic = _document(doc_id="doc-wrong-topic", topic=RequestTopic.CREDIT_RISK)
    item = _item(requested_artefacts=(ArtefactClass.POLICY,), topic=RequestTopic.DATA_PRIVACY)
    assessment = _assess([_document(), wrong_class, wrong_topic], item=item)
    assert assessment.out_of_scope_dropped == 2  # type: ignore[attr-defined]
    listed = {link.doc_id for link in assessment.links}  # type: ignore[attr-defined]
    assert listed == {"doc-1"}


def test_an_accepted_document_with_a_stale_sibling_reads_partial_and_still_counts() -> None:
    fresh = _document(doc_id="doc-fresh", as_of=date(2026, 12, 1))
    stale = _document(doc_id="doc-stale", as_of=date(2025, 6, 1))
    assessment = _assess([fresh, stale])
    assert _states(assessment)["policy"] == "partial"
    assert "stale_evidence" in _kinds(assessment)
    # PARTIAL still COUNTS towards completeness: the artefact was produced, with a caveat the
    # supervisor can see, which is a different thing from not producing it.
    satisfied = [row for row in assessment.coverage if row.artefact.value == "policy"]  # type: ignore[attr-defined]
    assert satisfied and satisfied[0].accepted


def test_a_requirement_supported_only_by_stale_evidence_is_stale_and_satisfies_nothing() -> None:
    """The state nothing else in the suite reaches, and the one the completeness number turns on.

    Out-of-period-but-within-the-staleness-window evidence is USABLE, which is why rule A3 keeps
    it, and it is not the same as evidence from the review period the supervisor asked about. So
    the row reads STALE and the requirement stays unsatisfied: widening the completeness
    numerator to include it would report an item supported entirely by evidence from outside the
    review period as fully complete and clear of the release floor.
    """
    only_stale = _document(doc_id="doc-stale-only", as_of=date(2025, 6, 1))
    assessment = _assess([only_stale])
    assert _states(assessment)["policy"] == "stale"
    assert "stale_evidence" in _kinds(assessment)
    assert assessment.satisfied_mandatory == 0, "stale evidence satisfied a requirement"  # type: ignore[attr-defined]
    assert assessment.completeness_pct == 0  # type: ignore[attr-defined]
    # And the link survives with its status named, so the checker can see WHAT was relied on.
    assert [link.status for link in assessment.links] == [EvidenceStatus.STALE]  # type: ignore[attr-defined]


def test_a_document_beyond_the_staleness_window_supports_nothing() -> None:
    ancient = _document(doc_id="doc-ancient", as_of=date(2020, 1, 1))
    assessment = _assess([ancient])
    assert assessment.links[0].status is EvidenceStatus.OUT_OF_PERIOD  # type: ignore[attr-defined]
    assert _states(assessment)["policy"] == "missing"


def test_accepted_evidence_is_capped_in_the_order_the_store_returned_it() -> None:
    """Rule A7: the engine never re-ranks, so nothing downstream of the corpus chooses."""
    documents = [_document(doc_id=f"doc-{index}", as_of=date(2026, 9, 1)) for index in range(1, 9)]
    assessment = _assess(documents)
    accepted = assessment.coverage[0].accepted  # type: ignore[attr-defined]
    assert len(accepted) == DEFAULT_POLICY.max_evidence_per_requirement
    assert [link.doc_id for link in accepted] == [f"doc-{index}" for index in range(1, 6)]


def test_completeness_is_integer_arithmetic_over_the_mandatory_requirements() -> None:
    """Three mandatory artefacts, two satisfied: 66, not 66.67 and not 67."""
    item = _item(topic=RequestTopic.GOVERNANCE, requested_artefacts=())
    documents = [
        _document(doc_id="doc-pol", artefact=ArtefactClass.POLICY, topic=RequestTopic.GOVERNANCE),
        _document(
            doc_id="doc-org",
            artefact=ArtefactClass.ORG_AND_ROLES,
            topic=RequestTopic.GOVERNANCE,
        ),
    ]
    assessment = _assess(documents, item=item)
    assert assessment.total_mandatory == 3  # type: ignore[attr-defined]
    assert assessment.satisfied_mandatory == 2  # type: ignore[attr-defined]
    assert assessment.completeness_pct == 66  # type: ignore[attr-defined]


def test_an_item_can_never_decompose_to_zero_requirements() -> None:
    """Rule D4: zero requirements would read as trivially one hundred per cent complete."""
    prose = RequestItem(
        item_ref="9.z",
        question="Set out the firm's approach, in narrative form.",
        topic=RequestTopic.CAPITAL_AND_LIQUIDITY,
        requested_artefacts=(),
        owner="Regulatory Affairs (FICTIONAL)",
    )
    bare = RequestItem(
        item_ref="9.z",
        question=prose.question,
        # A topic with no playbook row is impossible while the table is complete, so the D4 path
        # is reached by decomposing with no topic artefacts AND no obligations at all.
        topic=prose.topic,
        owner=prose.owner,
    )
    requirements = decompose(bare)
    assert requirements, "decomposition produced nothing at all"
    assert all(requirement.mandatory for requirement in requirements)
