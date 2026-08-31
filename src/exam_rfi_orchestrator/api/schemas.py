"""API request/response schemas (Pydantic) mapped to and from the pure-domain models.

WHAT THE REQUEST DELIBERATELY DOES NOT CARRY: an actor, a tenant, entitlements, ACL labels, a
permitted transfer scope, a required-approvals count, a release state, or any field that would
GRANT a waiver or an extension rather than name one. Entitlements come from
``principal.entitlement_principals()``, the tenant from the principal, the transfer scope from
the policy's transfer matrix, the approval count from the engine, and both waivers and extensions
from the case store. A schema accepting any of them would let a caller widen what may be
retrieved, unlock a privileged document, move a regulatory deadline or lower the approval bar.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from ..domain.kernel import Citation
from ..domain.models import (
    ArtefactCoverage,
    ArtefactRequirement,
    Blocker,
    Exhibit,
    ItemAssessment,
    NarrativeDraft,
    ObligationRef,
    ResponsePack,
    SlaClock,
    WithholdRecord,
)


class CitationModel(BaseModel):
    source_id: str
    title: str
    snippet: str = ""


class RequestItemModel(BaseModel):
    item_ref: str
    question: str
    #: A topic value, and the caller declares it. Empty is REFUSED with a 422 that names what the
    #: classifier would have suggested: the topic is the retrieval and responsiveness key, so a
    #: guessed one changes which documents are admissible and what the pack says the firm holds.
    topic: str = ""
    requested_artefacts: list[str] = []
    #: Empty means unassigned, which is a blocker rather than a default.
    owner: str = ""
    item_due_on: date | None = None
    evidence_pack_ref: str = ""


class PriorAnswerModel(BaseModel):
    answer_id: str
    submitted_on: date
    item_ref: str
    topic: str
    assertion_key: str
    assertion_value: str


class ResponsePackRequest(BaseModel):
    request_id: str
    regulator: str
    reference: str
    instrument: str
    regime: str
    jurisdiction: str
    received_on: date
    period_start: date
    period_end: date
    regulator_due_on: date | None = None
    #: The evaluation date. Absent means the server resolves it and ECHOES the resolved value, so
    #: a replay is exact and the demo and the evaluation stay byte-stable.
    as_of: date | None = None
    #: A LOOKUP KEY into the case store. A reference that resolves to nothing moves no date.
    extension_ref: str = ""
    #: A LOOKUP KEY into the case store. A client-asserted waiver unlocks nothing.
    waiver_ref: str = ""
    items: list[RequestItemModel] = []
    prior_answers: list[PriorAnswerModel] = []


class SlaModel(BaseModel):
    due_on: date
    original_due_on: date | None = None
    due_basis: str
    internal_due_on: date
    extension_request_by: date
    business_days_remaining: int
    band: str
    breached: bool
    buffer_consumed: bool
    calendar_id: str
    calendar_version: str
    regime_source: str = ""

    @classmethod
    def of(cls, sla: SlaClock) -> SlaModel:
        return cls(
            due_on=sla.due_on,
            original_due_on=sla.original_due_on,
            due_basis=sla.due_basis,
            internal_due_on=sla.internal_due_on,
            extension_request_by=sla.extension_request_by,
            business_days_remaining=sla.business_days_remaining,
            band=sla.band.value,
            breached=sla.breached,
            buffer_consumed=sla.buffer_consumed,
            calendar_id=sla.calendar_id,
            calendar_version=sla.calendar_version,
            regime_source=sla.regime_source,
        )


class RequirementModel(BaseModel):
    requirement_id: str
    artefact: str
    description: str
    mandatory: bool
    source_rule: str

    @classmethod
    def of(cls, requirement: ArtefactRequirement) -> RequirementModel:
        return cls(
            requirement_id=requirement.requirement_id,
            artefact=requirement.artefact.value,
            description=requirement.description,
            mandatory=requirement.mandatory,
            source_rule=requirement.source_rule,
        )


class CoverageModel(BaseModel):
    artefact: str
    state: str
    mandatory: bool
    reason: str = ""

    @classmethod
    def of(cls, row: ArtefactCoverage) -> CoverageModel:
        return cls(
            artefact=row.artefact.value,
            state=row.state.value,
            mandatory=row.mandatory,
            reason=row.reason,
        )


class BlockerModel(BaseModel):
    kind: str
    severity: str
    detail: str
    requirement_id: str = ""
    citation: CitationModel

    @classmethod
    def of(cls, blocker: Blocker) -> BlockerModel:
        return cls(
            kind=blocker.kind.value,
            severity=blocker.severity.value,
            detail=blocker.detail,
            requirement_id=blocker.requirement_id,
            citation=_citation(blocker.citation),
        )


class ExhibitModel(BaseModel):
    exhibit_no: str
    index_no: str = ""
    doc_id: str
    title: str
    artefact: str
    as_of: date
    locator: str = ""
    origin: str = ""
    redacted: bool = False

    @classmethod
    def of(cls, exhibit: Exhibit) -> ExhibitModel:
        return cls(
            exhibit_no=exhibit.exhibit_no,
            index_no=exhibit.index_no,
            doc_id=exhibit.doc_id,
            title=exhibit.title,
            artefact=exhibit.artefact.value,
            as_of=exhibit.as_of,
            locator=exhibit.locator,
            origin=exhibit.origin,
            redacted=exhibit.redacted,
        )


class WithholdModel(BaseModel):
    doc_id: str
    #: Empty for a silent-withhold row: in several regimes the existence of the filing is itself
    #: restricted, so the identifier and the basis travel and the title does not.
    title: str = ""
    artefact: str
    status: str
    basis_rule: str
    stated_basis: str

    @classmethod
    def of(cls, record: WithholdRecord) -> WithholdModel:
        return cls(
            doc_id=record.doc_id,
            title=record.title,
            artefact=record.artefact.value,
            status=record.status.value,
            basis_rule=record.basis_rule,
            stated_basis=record.stated_basis,
        )


class ObligationModel(BaseModel):
    obligation_id: str
    rule_ref: str = ""
    title: str

    @classmethod
    def of(cls, obligation: ObligationRef) -> ObligationModel:
        return cls(
            obligation_id=obligation.obligation_id,
            rule_ref=obligation.rule_ref,
            title=obligation.title,
        )


class NarrativeModel(BaseModel):
    text: str = ""
    drafted: bool = False
    model_authored: bool = False
    grounded: bool = False
    discard_reason: str = ""
    proposed_artefacts: list[str] = []

    @classmethod
    def of(cls, draft: NarrativeDraft) -> NarrativeModel:
        return cls(
            text=draft.text,
            drafted=draft.drafted,
            model_authored=draft.model_authored,
            grounded=draft.grounded,
            discard_reason=draft.discard_reason,
            proposed_artefacts=[artefact.value for artefact in draft.proposed_artefacts],
        )


class ItemResponse(BaseModel):
    item_ref: str
    topic: str
    owner: str = ""
    disposition: str
    severity: str
    decision: str
    requires_human_review: bool
    #: Where the escalation WENT (rule R8). Empty only when the item did not escalate.
    review_ref: str = ""
    completeness_pct: int
    satisfied_mandatory: int
    total_mandatory: int
    out_of_scope_dropped: int
    suppressed_by_entitlement: int
    release_state: str
    release_blockers: list[str] = []
    required_approvals: int
    sla: SlaModel
    requirements: list[RequirementModel] = []
    coverage: list[CoverageModel] = []
    blockers: list[BlockerModel] = []
    exhibits: list[ExhibitModel] = []
    withheld: list[WithholdModel] = []
    obligations: list[ObligationModel] = []
    narrative: NarrativeModel
    citations: list[CitationModel] = []

    @classmethod
    def of(cls, item: ItemAssessment, *, review_ref: str = "") -> ItemResponse:
        return cls(
            item_ref=item.item_ref,
            topic=item.topic.value,
            owner=item.owner,
            disposition=item.disposition.value,
            severity=item.severity.value,
            decision=item.decision.value,
            requires_human_review=item.requires_human_review,
            review_ref=review_ref,
            completeness_pct=item.completeness_pct,
            satisfied_mandatory=item.satisfied_mandatory,
            total_mandatory=item.total_mandatory,
            out_of_scope_dropped=item.out_of_scope_dropped,
            suppressed_by_entitlement=item.suppressed_by_entitlement,
            release_state=item.release_state.value,
            release_blockers=[kind.value for kind in item.release_blockers],
            required_approvals=item.required_approvals,
            sla=SlaModel.of(item.sla),
            requirements=[RequirementModel.of(r) for r in item.requirements],
            coverage=[CoverageModel.of(c) for c in item.coverage],
            blockers=[BlockerModel.of(b) for b in item.blockers],
            exhibits=[ExhibitModel.of(e) for e in item.exhibits],
            withheld=[WithholdModel.of(w) for w in item.withheld],
            obligations=[ObligationModel.of(o) for o in item.obligations],
            narrative=NarrativeModel.of(item.narrative),
            citations=[_citation(c) for c in item.citations],
        )


class ResponsePackResponse(BaseModel):
    request_id: str
    reference: str
    regulator: str
    instrument: str
    regime: str
    #: The RESOLVED evaluation date, always echoed so a replay is exact.
    as_of: date
    disposition: str
    severity: str
    decision: str
    summary: str
    #: Always true for a pack: the response is maker-checker approved before it leaves the firm.
    requires_human_review: bool
    #: Never empty for a pack: rule R8's evidence that the approval was ROUTED, not merely flagged.
    review_ref: str = ""
    release_state: str
    release_blockers: list[str] = []
    required_approvals: int
    completeness_pct: int
    sla: SlaModel
    items: list[ItemResponse] = []
    document_index: list[ExhibitModel] = []
    withholding_schedule: list[WithholdModel] = []
    blockers: list[BlockerModel] = []
    cover_note: NarrativeModel
    citations: list[CitationModel] = []

    @classmethod
    def from_domain(
        cls,
        pack: ResponsePack,
        *,
        regime: str = "",
        review_ref: str = "",
        item_reviews: dict[str, str] | None = None,
    ) -> ResponsePackResponse:
        routed = item_reviews or {}
        return cls(
            request_id=pack.request_id,
            reference=pack.reference,
            regulator=pack.regulator,
            instrument=pack.instrument.value,
            regime=regime,
            as_of=pack.as_of,
            disposition=pack.disposition.value,
            severity=pack.severity.value,
            decision=pack.decision.value,
            summary=pack.summary,
            requires_human_review=pack.requires_human_review,
            review_ref=review_ref,
            release_state=pack.release_state.value,
            release_blockers=[kind.value for kind in pack.release_blockers],
            required_approvals=pack.required_approvals,
            completeness_pct=pack.completeness_pct,
            sla=SlaModel.of(pack.sla),
            items=[
                ItemResponse.of(item, review_ref=routed.get(item.item_ref, ""))
                for item in pack.items
            ],
            document_index=[ExhibitModel.of(e) for e in pack.document_index],
            withholding_schedule=[WithholdModel.of(w) for w in pack.withholding_schedule],
            blockers=[BlockerModel.of(b) for b in pack.blockers],
            cover_note=NarrativeModel.of(pack.cover_note),
            citations=[_citation(c) for c in pack.citations],
        )


class HealthResponse(BaseModel):
    status: str
    profile: str
    region: str
    #: Provenance the UI banner states on every page: where the runtime sits and which model
    #: answers. Derived server-side so the UI never guesses (org decision, 2026-08-30).
    runtime: str = "local"  # "gcp" | "local"
    generator_model: str = "no-model"


def _citation(citation: Citation) -> CitationModel:
    return CitationModel(
        source_id=citation.source_id, title=citation.title, snippet=citation.snippet
    )
