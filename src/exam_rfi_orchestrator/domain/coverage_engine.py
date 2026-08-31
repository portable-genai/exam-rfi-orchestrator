"""Admissibility and completeness: which document supports which requirement, and why.

This is the module a supervisor's second and third question reduce to: what did you produce, and
what did you withhold and on what basis. Both are decided here, by a first-match ladder over
handling tags, ACL labels and effective dates, with the rule id that decided each document
recorded on the link. No model takes part, so a withhold decision replays byte for byte.

THE LADDER'S EVALUATION ORDER, and one deliberate deviation from the rule numbering. The rules
are numbered A1 to A6 and evaluated in the order A1, A2, A4, A5, A6, A3: the WITHHOLD rules run
before the period rule. Evaluating A3 first would give a stale-but-privileged document the status
``stale``, which rule A3 documents as still usable, and the document would be produced to a
regulator because it was old. The numbering is kept because the rule ids appear on every stored
link and in every audit record; the order is the safe one, and a unit test plants exactly that
document to hold it.

Two determinations that never collapse into one another:

* **DENIED is not MISSING.** "You are not entitled to see this" and "the firm holds no such
  document" are materially different statements to a regulator, and only one of them is true. A
  requirement with nothing surviving reads DENIED rather than MISSING whenever the store
  suppressed a document OF THAT CLASS, because a pack must never state that no such document
  exists when the truth is that the caller could not see it. The attribution matters in both
  directions: a suppression counted only at item level would make the denial sentence true of
  every class the item asked for, including the ones the firm really does hold nothing of, which
  is the same false statement pointed the other way. A store that reports a total it cannot
  attribute keeps the over-broad reading, because understating a denial is the worse error.
* **PARTIAL is not COVERED.** Produced with a withheld, denied or stale sibling is the state a
  supervisor most often challenges, so it is named.

Pure stdlib: no ports, no I/O, no model, no clock.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from .kernel import Citation, Severity
from .models import (
    WITHHELD_STATUSES,
    ArtefactClass,
    ArtefactCoverage,
    ArtefactRequirement,
    Blocker,
    BlockerKind,
    CoverageState,
    EvidenceItem,
    EvidenceLink,
    EvidenceStatus,
    ExamPolicy,
    RegulatorRequest,
    RequestItem,
    SensitivityTag,
    WaiverRecord,
    WithholdRecord,
)

__all__ = ["EvidenceAssessment", "assess_evidence"]

_BASIS_TEXT: dict[str, str] = {
    "A1": "the caller is not entitled to this document",
    "A3-stale": "outside the review period but within the staleness window",
    "A3-out": "outside the review period and beyond the staleness window",
    "A4": "legal professional privilege asserted and no waiver record resolves",
    "A5": "restricted filing: the existence of the filing is itself restricted",
    "A6": "cross-border transfer to the requesting jurisdiction is not permitted",
}


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    """Everything the admissibility ladder decided for one item."""

    links: tuple[EvidenceLink, ...] = ()
    coverage: tuple[ArtefactCoverage, ...] = ()
    withheld: tuple[WithholdRecord, ...] = ()
    blockers: tuple[Blocker, ...] = ()
    accepted_by_requirement: dict[str, tuple[EvidenceLink, ...]] = field(default_factory=dict)
    out_of_scope_dropped: int = 0
    satisfied_mandatory: int = 0
    total_mandatory: int = 0
    completeness_pct: int = 0


def _citation(doc: EvidenceItem) -> Citation:
    return Citation(source_id=f"doc:{doc.doc_id}", title=doc.title, snippet=doc.snippet[:160])


def _waiver_resolves(waiver: WaiverRecord | None, *, tenant: str, as_of: date) -> bool:
    """A stored waiver only counts for this tenant and only while it has not expired.

    The request's ``waiver_ref`` is a lookup key and grants nothing. A key that resolves to
    nothing, an expired record and a record filed under another tenant are all the same answer.
    """
    if waiver is None:
        return False
    if waiver.tenant != tenant:
        return False
    return waiver.expires_on > as_of


def _status_for(
    doc: EvidenceItem,
    *,
    request: RegulatorRequest,
    policy: ExamPolicy,
    as_of: date,
    waiver_ok: bool,
) -> tuple[EvidenceStatus, str]:
    """The first matching rule's verdict for one paired candidate, and the rule id."""
    tags = set(doc.sensitivity)

    # A4 PRIVILEGE, WAIVER BY RECORD ONLY. The engine names the basis and never adjudicates
    # privilege: a lawyer decides whether it is actually asserted.
    privileged = SensitivityTag.LEGALLY_PRIVILEGED
    if (
        privileged in tags
        and privileged in set(policy.hard_withhold_tags)
        and policy.privilege_requires_waiver
        and not waiver_ok
    ):
        return EvidenceStatus.WITHHELD_PRIVILEGED, "A4"

    # A5 SILENT WITHHOLD. The document is never quoted, never indexed and never handed to the
    # generation port; only its identifier, status and basis survive onto the schedule.
    for tag in policy.silent_withhold_tags:
        if tag in tags:
            return EvidenceStatus.WITHHELD_SAR, "A5"

    # A5 (continued) any other hard-withhold tag that is not the privilege row above.
    for tag in policy.hard_withhold_tags:
        if tag in tags and tag is not SensitivityTag.LEGALLY_PRIVILEGED:
            return EvidenceStatus.WITHHELD_SAR, "A5"

    # A6 CROSS-BORDER TRANSFER.
    if doc.owning_jurisdiction not in request.permitted_transfer_jurisdictions:
        return EvidenceStatus.WITHHELD_RESTRICTED_TRANSFER, "A6"

    # A3 PERIOD AND STALENESS.
    if request.period_start <= doc.as_of <= request.period_end:
        return EvidenceStatus.ACCEPTED, "A3"
    horizon = request.period_end + timedelta(days=policy.evidence_max_age_days)
    floor = request.period_start - timedelta(days=policy.evidence_max_age_days)
    if floor <= doc.as_of <= horizon:
        return EvidenceStatus.STALE, "A3-stale"
    return EvidenceStatus.OUT_OF_PERIOD, "A3-out"


def _withhold_record(
    doc: EvidenceItem, status: EvidenceStatus, basis_rule: str, policy: ExamPolicy
) -> WithholdRecord:
    """One row on the withholding schedule, silent where the policy says the row is silent.

    NO SNIPPET, ever, on either kind of row. Quoting a document is producing it, so a withhold
    citation carries the identifier and the title and nothing from inside the document. A silent
    row drops the title and the citation too, because in several regimes the existence of the
    filing is itself restricted.
    """
    silent = any(tag in set(doc.sensitivity) for tag in policy.silent_withhold_tags)
    if silent:
        return WithholdRecord(
            doc_id=doc.doc_id,
            title="",
            artefact=doc.artefact,
            status=status,
            basis_rule=basis_rule,
            stated_basis=_BASIS_TEXT.get(basis_rule, basis_rule),
            citation=None,
        )
    return WithholdRecord(
        doc_id=doc.doc_id,
        title=doc.title,
        artefact=doc.artefact,
        status=status,
        basis_rule=basis_rule,
        stated_basis=_BASIS_TEXT.get(basis_rule, basis_rule),
        citation=Citation(source_id=f"doc:{doc.doc_id}", title=doc.title, snippet=""),
    )


def assess_evidence(
    request: RegulatorRequest,
    item: RequestItem,
    requirements: Sequence[ArtefactRequirement],
    candidates: Sequence[EvidenceItem],
    *,
    as_of: date,
    policy: ExamPolicy,
    waiver: WaiverRecord | None = None,
    tenant: str = "",
    suppressed_by_entitlement: int = 0,
    suppressed_by_artefact: Mapping[ArtefactClass, int] | None = None,
) -> EvidenceAssessment:
    """Run the admissibility ladder and compute coverage for one item.

    ``candidates`` arrive in the order the ports returned them and the engine never re-ranks, so
    nothing downstream of the corpus can influence which evidence is produced (rule A7).

    ``suppressed_by_entitlement`` is the item-level total the store refused this caller and
    ``suppressed_by_artefact`` is that total attributed to the classes it happened to. Rule C4
    reads the attribution where there is one and the total where there is not.
    """
    by_artefact = {requirement.artefact: requirement for requirement in requirements}
    waiver_ok = _waiver_resolves(waiver, tenant=tenant, as_of=as_of)

    links: list[EvidenceLink] = []
    withheld: list[WithholdRecord] = []
    blockers: list[Blocker] = []
    dropped = 0
    seen: set[str] = set()

    # A1 ENTITLEMENT BOUNDARY, FAIL-CLOSED AND DOUBLE-CHECKED. The retrieval adapter must have
    # filtered already; this re-checks, which is defence in depth rather than duplication.
    leaked = [doc for doc in candidates if not doc.acl_labels <= request.entitlements]
    leaked_ids = {doc.doc_id for doc in leaked}
    if leaked:
        blockers.append(
            Blocker(
                kind=BlockerKind.DENIED_NO_ENTITLEMENT,
                severity=Severity.CRITICAL,
                detail=(
                    f"{len(leaked)} document(s) reached this service exceeding the caller's "
                    "entitlements and were dropped; the retrieval boundary failed"
                ),
                citation=item.citation,
            )
        )
    if suppressed_by_entitlement > 0:
        blockers.append(
            Blocker(
                kind=BlockerKind.DENIED_NO_ENTITLEMENT,
                severity=Severity.HIGH,
                detail=(
                    f"{suppressed_by_entitlement} responsive document(s) exist that this caller "
                    "is not entitled to read"
                ),
                citation=item.citation,
            )
        )

    for doc in candidates:
        if doc.doc_id in seen:
            continue
        seen.add(doc.doc_id)

        requirement = by_artefact.get(doc.artefact)
        # A2 RESPONSIVENESS, THE OVER-PRODUCTION CONTROL. A candidate matching no requirement, or
        # carrying a different topic, is DROPPED and counted. It reaches no index row, no
        # schedule row, no review payload and no prompt: listing a document nobody asked for
        # tells a supervisor about material outside the request.
        if requirement is None or doc.topic is not item.topic:
            dropped += 1
            continue

        if doc.doc_id in leaked_ids:
            links.append(
                EvidenceLink(
                    requirement_id=requirement.requirement_id,
                    doc_id=doc.doc_id,
                    title="",
                    locator="",
                    artefact=doc.artefact,
                    as_of=doc.as_of,
                    status=EvidenceStatus.DENIED_NO_ENTITLEMENT,
                    basis_rule="A1",
                    origin=doc.origin,
                    citation=Citation(source_id=f"doc:{doc.doc_id}", title=""),
                )
            )
            continue

        status, basis_rule = _status_for(
            doc, request=request, policy=policy, as_of=as_of, waiver_ok=waiver_ok
        )
        if status in WITHHELD_STATUSES:
            record = _withhold_record(doc, status, basis_rule, policy)
            withheld.append(record)
            links.append(
                EvidenceLink(
                    requirement_id=requirement.requirement_id,
                    doc_id=doc.doc_id,
                    title=record.title,
                    locator="",
                    artefact=doc.artefact,
                    as_of=doc.as_of,
                    status=status,
                    basis_rule=basis_rule,
                    origin=doc.origin,
                    citation=record.citation or Citation(source_id=f"doc:{doc.doc_id}", title=""),
                )
            )
            continue

        links.append(
            EvidenceLink(
                requirement_id=requirement.requirement_id,
                doc_id=doc.doc_id,
                title=doc.title,
                locator=doc.locator,
                artefact=doc.artefact,
                as_of=doc.as_of,
                status=status,
                basis_rule=basis_rule,
                origin=doc.origin,
                citation=_citation(doc),
            )
        )

    blockers.extend(_withhold_blockers(withheld, item.citation))
    coverage, accepted_by_requirement, coverage_blockers = _coverage(
        requirements,
        links,
        policy=policy,
        suppressed_by_entitlement=suppressed_by_entitlement,
        suppressed_by_artefact=suppressed_by_artefact or {},
        item_citation=item.citation,
    )
    blockers.extend(coverage_blockers)

    mandatory = [row for row in coverage if row.mandatory]
    total = len(mandatory)
    satisfied = sum(1 for row in mandatory if row.state in _SATISFIED)
    # C3 COMPLETENESS. Integer arithmetic throughout and no float anywhere, so the number is
    # identical on every platform and in every replay. ``total`` is never zero, by rule D4.
    completeness = (100 * satisfied // total) if total else 0

    return EvidenceAssessment(
        links=tuple(links),
        coverage=coverage,
        withheld=tuple(withheld),
        blockers=tuple(blockers),
        accepted_by_requirement=accepted_by_requirement,
        out_of_scope_dropped=dropped,
        satisfied_mandatory=satisfied,
        total_mandatory=total,
        completeness_pct=completeness,
    )


_SATISFIED = frozenset({CoverageState.COVERED, CoverageState.PARTIAL})

_WITHHOLD_BLOCKER: dict[EvidenceStatus, tuple[BlockerKind, Severity]] = {
    EvidenceStatus.WITHHELD_PRIVILEGED: (BlockerKind.PRIVILEGE_HOLD, Severity.HIGH),
    EvidenceStatus.WITHHELD_RESTRICTED_TRANSFER: (BlockerKind.RESTRICTED_TRANSFER, Severity.HIGH),
}


def _withhold_blockers(
    withheld: Sequence[WithholdRecord], item_citation: Citation
) -> list[Blocker]:
    """One blocker per withhold that a human has to decide about.

    The silent-withhold row raises none: its whole point is that the fact of the filing is
    restricted, and a blocker naming it would put it back on the surfaces the rule removed it
    from. It still appears on the withholding schedule with its identifier and its basis.
    """
    out: list[Blocker] = []
    for record in withheld:
        pair = _WITHHOLD_BLOCKER.get(record.status)
        if pair is None:
            continue
        kind, severity = pair
        out.append(
            Blocker(
                kind=kind,
                severity=severity,
                detail=f"{record.doc_id} withheld: {record.stated_basis}",
                citation=record.citation or item_citation,
            )
        )
    return out


def _coverage(
    requirements: Sequence[ArtefactRequirement],
    links: Sequence[EvidenceLink],
    *,
    policy: ExamPolicy,
    suppressed_by_entitlement: int,
    suppressed_by_artefact: Mapping[ArtefactClass, int],
    item_citation: Citation,
) -> tuple[tuple[ArtefactCoverage, ...], dict[str, tuple[EvidenceLink, ...]], list[Blocker]]:
    """Rules C1 to C4: the per-artefact determination, capped accepted links, and the blockers."""
    rows: list[ArtefactCoverage] = []
    accepted_by_requirement: dict[str, tuple[EvidenceLink, ...]] = {}
    blockers: list[Blocker] = []

    for requirement in requirements:
        mine = [link for link in links if link.requirement_id == requirement.requirement_id]
        # A7 rank preserved, then capped. The engine never re-ranks.
        accepted = tuple(link for link in mine if link.status is EvidenceStatus.ACCEPTED)[
            : max(0, policy.max_evidence_per_requirement)
        ]
        stale = [link for link in mine if link.status is EvidenceStatus.STALE]
        denied = [link for link in mine if link.status is EvidenceStatus.DENIED_NO_ENTITLEMENT]
        held = [link for link in mine if link.status in WITHHELD_STATUSES]
        surviving = list(accepted) + stale + denied + held
        accepted_by_requirement[requirement.requirement_id] = accepted

        # ATTRIBUTED where the store attributed, over-broad where it did not. An empty split with
        # a non-zero total is a store that counted but could not say of what, and reading zero
        # there would turn "you may not read this" into "the firm holds nothing".
        suppressed_here = (
            suppressed_by_artefact.get(requirement.artefact, 0)
            if suppressed_by_artefact
            else suppressed_by_entitlement
        )
        state, reason = _state_for(
            accepted=accepted,
            stale=stale,
            denied=denied,
            held=held,
            surviving=surviving,
            suppressed_for_artefact=suppressed_here,
        )
        if state is CoverageState.MISSING:
            blockers.append(
                Blocker(
                    kind=BlockerKind.MISSING_ARTEFACT,
                    severity=Severity.HIGH,
                    detail=f"no admissible {requirement.artefact.value} was produced",
                    requirement_id=requirement.requirement_id,
                    citation=item_citation,
                )
            )
        if stale:
            blockers.append(
                Blocker(
                    kind=BlockerKind.STALE_EVIDENCE,
                    severity=Severity.MEDIUM,
                    detail=(
                        f"{requirement.artefact.value} is supported by evidence outside the "
                        "review period"
                    ),
                    requirement_id=requirement.requirement_id,
                    citation=stale[0].citation,
                )
            )
        rows.append(
            ArtefactCoverage(
                artefact=requirement.artefact,
                state=state,
                requirement_id=requirement.requirement_id,
                mandatory=requirement.mandatory,
                accepted=accepted,
                withheld=(),
                reason=reason,
            )
        )
    return tuple(rows), accepted_by_requirement, blockers


def _state_for(
    *,
    accepted: Sequence[EvidenceLink],
    stale: Sequence[EvidenceLink],
    denied: Sequence[EvidenceLink],
    held: Sequence[EvidenceLink],
    surviving: Sequence[EvidenceLink],
    suppressed_for_artefact: int,
) -> tuple[CoverageState, str]:
    """Rule C2, in order, plus rule C4's refusal to collapse DENIED into MISSING.

    ``suppressed_for_artefact`` is the count the store refused for THIS requirement's class, so
    the denial sentence is only produced where a document of that class was actually suppressed.
    """
    if not surviving:
        if denied or suppressed_for_artefact > 0:
            return (
                CoverageState.DENIED,
                "responsive documents exist that this caller is not entitled to read",
            )
        return CoverageState.MISSING, "the firm produced no admissible document of this class"
    if not accepted and not stale:
        if denied and not held:
            return CoverageState.DENIED, "every candidate was refused to this caller"
        return CoverageState.WITHHELD, "every candidate was withheld with a stated basis"
    if not accepted:
        return CoverageState.STALE, "only evidence outside the review period survived"
    if held or denied or stale:
        return (
            CoverageState.PARTIAL,
            "produced, with at least one withheld, denied or stale sibling",
        )
    return CoverageState.COVERED, "produced in full and within the review period"
