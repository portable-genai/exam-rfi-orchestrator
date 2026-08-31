"""Vertical artifact models: the supervisory request, its evidence and the response pack.

The artifacts THIS vertical produces, as opposed to the vertical-neutral machinery in
``kernel.py``. The service's own name is deliberately not substituted into this docstring: a
rendered line whose length depends on ``friendly_name`` fails the repo's own format check for
no reason but the length of its name.

Everything here is frozen, slotted and pure stdlib, because everything here has to replay years
later on a machine with no model, no corpus and no network. Three properties are load-bearing
and are called out where they apply:

* **Declaration order is policy** for :class:`ArtefactClass`. It is the primary sort key for
  exhibit numbering, so moving a member renumbers historical exhibits.
* **A lookup key is never a grant.** ``extension_ref`` and ``waiver_ref`` name a record the case
  store resolves; a client assertion moves no deadline and unlocks no document.
* **Denied is not missing.** ``you are not entitled to see this`` and ``the firm holds no such
  document`` are materially different statements to a regulator, and only one of them is true.

A fork building a different vertical rewrites this module and keeps ``kernel.py`` untouched.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from hex_service_kit.enums import LenientStrEnum

from .kernel import Citation, Decision, Severity, utcnow

#: Escalation order for the kernel band, so "the worse of two severities" is one function
#: rather than a comparison written differently in each engine module.
SEVERITY_RANK: dict[Severity, int] = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


def worse(left: Severity, right: Severity) -> Severity:
    """The more severe of two bands. Never lowers, which is the only direction allowed."""
    return left if SEVERITY_RANK[left] >= SEVERITY_RANK[right] else right


#: The citation a field carries when nothing cited it. Shared because a frozen dataclass is
#: immutable, and present because several models carry a citation after defaulted fields.
NO_CITATION = Citation(source_id="", title="")


class Instrument(LenientStrEnum):
    """The supervisory instrument the request arrived as.

    Deliberately carries no incident-notification member. Fixed-hour incident clocks belong to
    the resilience and fraud verticals, and carrying one here would let this service compute a
    confident statutory deadline for work it does not do. The instrument selects the policy
    response window when the notice states no date, and it selects dual control.
    """

    EXAM_REQUEST_LIST = "exam_request_list"
    RFI = "rfi"
    S166_SKILLED_PERSON = "s166_skilled_person"
    THEMATIC_REVIEW = "thematic_review"
    INFORMATION_NOTICE = "information_notice"


class RequestTopic(LenientStrEnum):
    """The subject-matter category of one numbered question.

    The key into the artefact playbook, into the obligations port and into retrieval, AND rule
    A2's responsiveness filter, which is why it is declared by the caller and never chosen here.
    A model may SUGGEST one from free text and the suggestion reaches a person: a wrong topic
    drops every candidate carrying the right one, so the pack would state that the firm produced
    no admissible document of a class it holds. Widening the artefact set is the harmless half of
    a classification; picking the key is not, and only the first half was ever true.
    """

    GOVERNANCE = "governance"
    AML_FINANCIAL_CRIME = "aml_financial_crime"
    CONDUCT_AND_COMPLAINTS = "conduct_and_complaints"
    CREDIT_RISK = "credit_risk"
    OPERATIONAL_RESILIENCE = "operational_resilience"
    DATA_PRIVACY = "data_privacy"
    MODEL_RISK = "model_risk"
    OUTSOURCING_THIRD_PARTY = "outsourcing_third_party"
    CAPITAL_AND_LIQUIDITY = "capital_and_liquidity"
    TECHNOLOGY_AND_CYBER = "technology_and_cyber"


class ArtefactClass(LenientStrEnum):
    """The canonical taxonomy every question decomposes into and every document is classified as.

    DECLARATION ORDER IS LOAD-BEARING: it is the primary sort key for exhibit numbering, so the
    order is policy and moving a member renumbers historical exhibits.
    ``NARRATIVE_STATEMENT`` is last and is the default requirement rule D4 emits, so an item can
    never decompose to zero requirements and read as trivially complete.
    """

    POLICY = "policy"
    PROCEDURE = "procedure"
    COMMITTEE_MINUTES = "committee_minutes"
    ORG_AND_ROLES = "org_and_roles"
    CONTROL_TEST_RESULT = "control_test_result"
    RISK_ASSESSMENT = "risk_assessment"
    ISSUE_LOG = "issue_log"
    THIRD_PARTY_CONTRACT = "third_party_contract"
    SYSTEM_EXTRACT = "system_extract"
    TRANSACTION_SAMPLE = "transaction_sample"
    CUSTOMER_FILE = "customer_file"
    MANAGEMENT_INFORMATION = "management_information"
    NARRATIVE_STATEMENT = "narrative_statement"


#: Position of each artefact class in the declaration order above, so the exhibit sort reads a
#: table rather than re-deriving it. Built once, from the enum, so the two cannot disagree.
ARTEFACT_ORDER: dict[ArtefactClass, int] = {
    artefact: index for index, artefact in enumerate(ArtefactClass)
}


class SensitivityTag(LenientStrEnum):
    """Handling tags the corpus carries on a document.

    ``LEGALLY_PRIVILEGED`` is withheld unless a STORED waiver resolves. ``SAR_CONFIDENTIAL`` is
    the silent withhold (identifier and basis survive, title and snippet do not, because in
    several regimes the existence of a suspicious-activity filing is itself restricted).
    ``CROSS_BORDER_RESTRICTED`` is conditional on the transfer matrix. ``PERSONAL_DATA`` is
    informational only, because masking is unconditional and never depends on a tag.
    """

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    LEGALLY_PRIVILEGED = "legally_privileged"
    SAR_CONFIDENTIAL = "sar_confidential"
    PERSONAL_DATA = "personal_data"
    CROSS_BORDER_RESTRICTED = "cross_border_restricted"


class EvidenceStatus(LenientStrEnum):
    """The engine's verdict on ONE candidate document for ONE requirement.

    Set by the first matching admissibility rule, whose id is recorded alongside it as the basis.
    Note what is absent: a status for a non-responsive document. Those are dropped and counted,
    never given a row, because listing a document nobody asked for tells a supervisor about
    material outside the request.
    """

    ACCEPTED = "accepted"
    DENIED_NO_ENTITLEMENT = "denied_no_entitlement"
    WITHHELD_PRIVILEGED = "withheld_privileged"
    WITHHELD_SAR = "withheld_sar"
    WITHHELD_RESTRICTED_TRANSFER = "withheld_restricted_transfer"
    STALE = "stale"
    OUT_OF_PERIOD = "out_of_period"


#: The statuses that mean "this document was deliberately not produced". Every one of them earns
#: a row on the withholding schedule, because a document silently dropped from a production is
#: how an honest late answer becomes a misleading one.
WITHHELD_STATUSES: frozenset[EvidenceStatus] = frozenset(
    {
        EvidenceStatus.WITHHELD_PRIVILEGED,
        EvidenceStatus.WITHHELD_SAR,
        EvidenceStatus.WITHHELD_RESTRICTED_TRANSFER,
    }
)


class CoverageState(LenientStrEnum):
    """The determination for ONE required artefact class within one item.

    ``PARTIAL`` means produced with at least one withheld, denied or stale sibling, which is the
    state a supervisor most often challenges, so it is named rather than folded into
    ``COVERED``. ``DENIED`` is separated from ``MISSING`` deliberately and never collapses into
    it.
    """

    COVERED = "covered"
    PARTIAL = "partial"
    STALE = "stale"
    WITHHELD = "withheld"
    DENIED = "denied"
    MISSING = "missing"


#: Coverage states that count towards the completeness numerator (rule C3).
SATISFIED_STATES: frozenset[CoverageState] = frozenset(
    {CoverageState.COVERED, CoverageState.PARTIAL}
)


class BlockerKind(LenientStrEnum):
    """Every reason an item or a pack cannot be released, as a CLOSED set.

    Closed on purpose: disposition, severity and the release gate are functions of the blocker
    list, so a free-text reason would be a decision nobody can replay. A reviewer is handed
    these names rather than a score, because a reviewer who cannot see which rule fired cannot
    check anything.
    """

    MISSING_ARTEFACT = "missing_artefact"
    DENIED_NO_ENTITLEMENT = "denied_no_entitlement"
    PRIVILEGE_HOLD = "privilege_hold"
    RESTRICTED_TRANSFER = "restricted_transfer"
    STALE_EVIDENCE = "stale_evidence"
    NO_OWNER = "no_owner"
    PRIOR_ANSWER_CONFLICT = "prior_answer_conflict"
    UNRECOGNISED_ASSERTION = "unrecognised_assertion"
    NO_ADMISSIBLE_EVIDENCE = "no_admissible_evidence"
    UNGROUNDED_DRAFT = "ungrounded_draft"
    BELOW_MIN_COMPLETENESS = "below_min_completeness"
    DEADLINE_BREACH = "deadline_breach"


class Disposition(LenientStrEnum):
    """The WORKFLOW state of an item or a pack: can this answer be produced in time.

    Deliberately separate from :class:`ReleaseState`, which answers a different question (may it
    leave the firm), and from the kernel ``Severity``, which is the escalation band the audit
    event and the review payload speak. Collapsing the three is how a taxonomy ends up wider
    than the rules that populate it.
    """

    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BLOCKED = "blocked"
    BREACH = "breach"


class ReleaseState(LenientStrEnum):
    """May this leave the firm? Every outcome this engine returns carries ``HELD_FOR_CHECKER``.

    ``RELEASED`` exists in the enum and NO code path in this service produces it: release
    happens in the human-review console, by a person, and an operator sends the production. The
    guard is only an invariant if it has been watched go red, so it is proved against a planted
    mutant that returns ``RELEASED``.
    """

    HELD_FOR_CHECKER = "held_for_checker"
    RELEASED = "released"


@dataclass(frozen=True, slots=True)
class BusinessCalendar:
    """One jurisdiction's business-day calendar.

    ``version`` is recorded on every clock and in every audit record, because a stale holiday
    list shifts a deadline silently and in the unsafe direction, and a deadline recomputed years
    later must either match or show which input moved.
    """

    id: str
    version: str
    weekend_days: tuple[int, ...] = (5, 6)
    holidays: tuple[date, ...] = ()


@dataclass(frozen=True, slots=True)
class RegimeRef:
    """One named public regime the request cites, and what it does to the clock.

    ``fixed_response_window_days == 0`` means the regime fixes NO response window and the
    notice's own date governs, which is what every shipped reference row says. The row exists
    precisely so nobody hardcodes a number they read somewhere: an adopter whose counsel
    identifies a regime that does fix a window configures it here and the cap rule bites, with
    ``due_basis`` naming the regime rather than a constant in code.
    """

    regime: str
    title: str
    source: str
    fixed_response_window_days: int = 0
    calendar_clock: bool = False
    note: str = ""


@dataclass(frozen=True, slots=True)
class ExamPolicy:
    """The adopter-owned policy block, parsed from the ``policy:`` section of the settings file.

    No window, buffer, band ceiling, staleness limit, withhold tag, holiday or approval rule
    stays a module constant. ``sla_bands`` are CEILINGS on business days remaining to the
    INTERNAL due date, checked in order, otherwise LOW. ``transfer_matrix`` maps the REQUESTING
    jurisdiction to the evidence jurisdictions that may lawfully be transferred to it, and an
    unknown requesting jurisdiction resolves to a set containing only itself, which is the
    fail-closed reading. Every number is reference policy and the adopter's counsel owns it.
    """

    response_windows: Mapping[str, int] = field(default_factory=dict)
    review_buffer_business_days: int = 5
    extension_notice_business_days: int = 10
    evidence_max_age_days: int = 400
    sla_bands: tuple[tuple[int, Severity], ...] = (
        (0, Severity.CRITICAL),
        (3, Severity.HIGH),
        (8, Severity.MEDIUM),
    )
    min_completeness_pct_for_release: int = 100
    max_evidence_per_requirement: int = 5
    hard_withhold_tags: tuple[SensitivityTag, ...] = (
        SensitivityTag.LEGALLY_PRIVILEGED,
        SensitivityTag.SAR_CONFIDENTIAL,
    )
    silent_withhold_tags: tuple[SensitivityTag, ...] = (SensitivityTag.SAR_CONFIDENTIAL,)
    privilege_requires_waiver: bool = True
    transfer_matrix: Mapping[str, frozenset[str]] = field(default_factory=dict)
    calendars: Mapping[str, BusinessCalendar] = field(default_factory=dict)
    regime_register: Mapping[str, RegimeRef] = field(default_factory=dict)
    dual_control_instruments: tuple[str, ...] = (
        Instrument.S166_SKILLED_PERSON.value,
        Instrument.INFORMATION_NOTICE.value,
    )
    dual_control_kinds: tuple[str, ...] = ("pack",)

    def permitted_transfers(self, jurisdiction: str) -> frozenset[str]:
        """Where evidence may lawfully come FROM for a requester in ``jurisdiction``.

        An unknown requesting jurisdiction resolves to a set containing only itself. That is the
        fail-closed reading: an unconfigured matrix must not permit every transfer.
        """
        known = self.transfer_matrix.get(jurisdiction)
        return known if known is not None else frozenset({jurisdiction})

    def calendar_for(self, jurisdiction: str) -> BusinessCalendar:
        """The named jurisdiction's calendar, or an unversioned weekend-only fallback.

        The fallback carries the version string ``unconfigured`` rather than a plausible one, so
        a clock computed against no holiday list says so on its own face.
        """
        known = self.calendars.get(jurisdiction)
        if known is not None:
            return known
        return BusinessCalendar(id=jurisdiction or "unknown", version="unconfigured")


@dataclass(frozen=True, slots=True)
class RegulatorRequest:
    """The request-list header.

    ``entitlements`` is NEVER read from a request body: the API fills it from
    ``principal.entitlement_principals()`` and the CLI from the resolved principal, so no caller
    can widen what may be retrieved. ``permitted_transfer_jurisdictions`` is likewise derived,
    from :meth:`ExamPolicy.permitted_transfers`. ``extension_ref`` and ``waiver_ref`` are LOOKUP
    KEYS into the case store, never grants. ``regulator_due_on`` of ``None`` means the
    instrument stated no date, which is what makes the policy window apply.
    """

    request_id: str
    regulator: str
    reference: str
    instrument: Instrument
    regime: str
    jurisdiction: str
    received_on: date
    period_start: date
    period_end: date
    regulator_due_on: date | None = None
    extension_ref: str = ""
    waiver_ref: str = ""
    entitlements: frozenset[str] = frozenset()
    permitted_transfer_jurisdictions: frozenset[str] = frozenset()
    citation: Citation = NO_CITATION


@dataclass(frozen=True, slots=True)
class RequestItem:
    """One numbered question, the replayable unit of work.

    ``requested_artefacts`` is what the regulator explicitly named and may be empty for a prose
    question. ``owner`` empty means unassigned, which is a blocker rather than a default: an
    exam answer with no named owner has nobody to challenge when the supervisor pushes back.
    ``item_due_on`` of ``None`` means the request-level deadline applies.
    """

    item_ref: str
    question: str
    topic: RequestTopic
    requested_artefacts: tuple[ArtefactClass, ...] = ()
    owner: str = ""
    item_due_on: date | None = None
    evidence_pack_ref: str = ""
    citation: Citation = NO_CITATION


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    """The DTO the knowledge-base port takes.

    It lives in the domain next to the engine that consumes it, so the port imports the domain
    and the domain imports no port. ``entitlements`` are the server-verified principals; a
    request-body identifier can only narrow them and can never widen them.
    """

    item_ref: str
    topic: RequestTopic
    artefacts: tuple[ArtefactClass, ...]
    period_start: date
    period_end: date
    entitlements: frozenset[str] = frozenset()
    limit: int = 20


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """One candidate document as retrieval or a reused evidence pack returns it.

    It carries the handling tags and ACL labels that are the inputs to the admissibility ladder,
    so entitlement and withhold decisions are made in the pure domain and are testable with no
    store. ``locator`` is the page or section anchor that makes a citation actionable rather
    than decorative. ``origin`` says whether it came from the corpus or a reused pack, and a
    reused pack gets no shortcut.
    """

    doc_id: str
    title: str
    artefact: ArtefactClass
    topic: RequestTopic
    as_of: date
    owning_jurisdiction: str
    sensitivity: tuple[SensitivityTag, ...] = ()
    acl_labels: frozenset[str] = frozenset()
    locator: str = ""
    snippet: str = ""
    origin: str = "corpus"


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """What the knowledge-base port returns, and the reason it is not a bare tuple.

    ``suppressed_by_entitlement`` is the COUNT of responsive documents the store refused to
    serve this principal, and only the count: no title, no id, nothing that leaks what was
    withheld. It is what turns an empty answer into "responsive documents exist that you may not
    read" rather than "the firm holds nothing responsive". A regulator told the second when the
    first is true has been given a materially false statement.

    ``suppressed_by_artefact`` is that same count SPLIT BY ARTEFACT CLASS, and it is what stops
    the statement being made about the wrong class. An item-level total says only that something
    was suppressed somewhere in the item, so a requirement for which the firm genuinely holds
    nothing would read "you are not entitled to read this" on the strength of a suppression that
    happened for a different class entirely. The split carries a class and a count and still no
    title and no id. A store that cannot attribute leaves it empty, and the engine then falls
    back to the deliberately over-broad item-level reading rather than understating a denial.
    """

    items: tuple[EvidenceItem, ...] = ()
    suppressed_by_entitlement: int = 0
    suppressed_by_artefact: Mapping[ArtefactClass, int] = field(default_factory=dict)
    corpus_reached: bool = True


@dataclass(frozen=True, slots=True)
class EvidencePack:
    """A pre-assembled control-mapping evidence pack, reused rather than rebuilt.

    Its documents enter the candidate set on identical terms: every admissibility rule applies,
    so reuse can never become a route around the release rules.
    """

    pack_ref: str
    obligation_id: str
    title: str
    assembled_on: date
    items: tuple[EvidenceItem, ...] = ()
    citation: Citation = NO_CITATION


@dataclass(frozen=True, slots=True)
class ObligationRef:
    """One obligation read from the obligation register, the single system of record.

    ``required_artefacts`` is what makes rule D3 bite: the register, not the question's wording,
    sets the floor on what must be produced.
    """

    obligation_id: str
    rule_ref: str
    title: str
    required_artefacts: tuple[ArtefactClass, ...] = ()
    citation: Citation = NO_CITATION


@dataclass(frozen=True, slots=True)
class PriorAnswer:
    """A factual assertion the firm has ALREADY made to this regulator.

    Supplied by the caller from the audit trail of prior packs and used only by the consistency
    rule. This is the control an exam lead cares about most and that no keyword engine has: a
    submission that contradicts what was said six months ago, which is how an honest late answer
    becomes a misleading one.
    """

    answer_id: str
    submitted_on: date
    item_ref: str
    topic: RequestTopic
    assertion_key: str
    assertion_value: str
    citation: Citation = NO_CITATION


@dataclass(frozen=True, slots=True)
class AssertedFact:
    """A fact normalised out of a produced exhibit. The MODEL produces these; the ENGINE compares.

    ``assertion_key`` must be a member of ``KNOWN_ASSERTION_KEYS`` in ``consistency.py``, and an
    unrecognised key raises a blocker rather than being ignored, because a model that renamed a
    key would otherwise silently switch the conflict check off.
    """

    assertion_key: str
    assertion_value: str
    citation: Citation = NO_CITATION


@dataclass(frozen=True, slots=True)
class WithholdRecord:
    """One document deliberately not produced, and why: the withholding schedule.

    A withheld document is RECORDED, never silently dropped, because a regulator who later finds
    it existed will ask why it was not on the schedule and "the software dropped it" is not an
    answer. Where the basis names a tag in ``ExamPolicy.silent_withhold_tags``, ``title`` and
    ``citation`` are empty and only ``doc_id``, ``status`` and ``basis_rule`` survive.
    """

    doc_id: str
    title: str
    artefact: ArtefactClass
    status: EvidenceStatus
    basis_rule: str
    stated_basis: str
    citation: Citation | None = None


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    """The engine's verdict on one candidate for one requirement.

    ``basis_rule`` names the admissibility rule id that decided it, which is what lets a
    reviewer and an auditor read WHY rather than infer it years later from a status column.
    """

    requirement_id: str
    doc_id: str
    title: str
    locator: str
    artefact: ArtefactClass
    as_of: date
    status: EvidenceStatus
    basis_rule: str
    origin: str = "corpus"
    citation: Citation = NO_CITATION


@dataclass(frozen=True, slots=True)
class ArtefactRequirement:
    """One artefact the item demands.

    ``source_rule`` records which decomposition rule and which input produced it (the
    regulator's own words, the topic playbook, or a named obligation), so decomposition is
    inspectable rather than a black box a checker has to trust.
    """

    requirement_id: str
    item_ref: str
    artefact: ArtefactClass
    description: str
    mandatory: bool
    source_rule: str
    citation: Citation = NO_CITATION


@dataclass(frozen=True, slots=True)
class ArtefactCoverage:
    """The per-required-artefact determination the completeness percentage is computed from.

    The number on the screen can always be expanded into the rows that produced it. A percentage
    nobody can open is a score, and a score is what this design exists to avoid handing a
    reviewer.
    """

    artefact: ArtefactClass
    state: CoverageState
    requirement_id: str
    mandatory: bool
    accepted: tuple[EvidenceLink, ...] = ()
    withheld: tuple[WithholdRecord, ...] = ()
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Blocker:
    """One reason an item cannot be released, always cited.

    ``severity`` is a kernel ``Severity`` so the escalation band, the audit event and the review
    payload all speak one vocabulary. The ``DENIED_NO_ENTITLEMENT`` detail names a COUNT and
    nothing else.
    """

    kind: BlockerKind
    severity: Severity
    detail: str
    requirement_id: str = ""
    citation: Citation = NO_CITATION


@dataclass(frozen=True, slots=True)
class SlaClock:
    """The deterministic deadline.

    ``internal_due_on`` is the regulator date less the maker-checker review buffer, because the
    date that actually binds an exam team is the internal one. ``extension_request_by`` is the
    last business day an extension can still credibly be asked for. ``due_basis`` names the RULE
    that set the date and ``calendar_version`` pins the holiday list used, so a deadline
    recomputed years later either matches or the record shows exactly which input moved.
    ``breached`` (past the regulator date) and ``buffer_consumed`` (past the internal date) are
    separate facts and are never merged.
    """

    due_on: date
    internal_due_on: date
    due_basis: str
    extension_request_by: date
    business_days_remaining: int
    band: Severity
    breached: bool
    buffer_consumed: bool
    calendar_id: str
    calendar_version: str
    regime_source: str = ""
    original_due_on: date | None = None


@dataclass(frozen=True, slots=True)
class Exhibit:
    """One numbered entry in the document index.

    ``exhibit_no`` is produced by a deterministic sort within the item and ``index_no``
    renumbers contiguously across the pack, so two runs over the same inputs produce the same
    annex and a resubmission is diffable against the original.
    """

    exhibit_no: str
    doc_id: str
    title: str
    artefact: ArtefactClass
    as_of: date
    locator: str
    origin: str = "corpus"
    redacted: bool = False
    index_no: str = ""
    citation: Citation = NO_CITATION


@dataclass(frozen=True, slots=True)
class NarrativeDraft:
    """The only thing in the pack the model may have written.

    ``drafted`` is False exactly when there was no admissible evidence to draft from;
    ``model_authored`` is False whenever the draft was discarded and the deterministic fallback
    used, and ``discard_reason`` names which grounding rule rejected it. ``proposed_artefacts``
    is advisory and enters no count, no coverage state, no severity and no release decision.
    """

    text: str = ""
    drafted: bool = False
    model_authored: bool = False
    grounded: bool = False
    discard_reason: str = ""
    proposed_artefacts: tuple[ArtefactClass, ...] = ()
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class ItemAssessment:
    """The consequential per-item result and the first of the two routable outcomes.

    The last six fields are deliberately the R8 review envelope, so ``_review_payload.py`` routes
    it without the pure domain importing a surface type. ``subject`` is the human-readable case
    label; ``case_ref`` is the request id plus the item ref and is what the console keys on.
    ``required_approvals`` is read OFF this object by the payload builder and never decided a
    second time.
    """

    item_ref: str
    subject: str
    case_ref: str
    topic: RequestTopic
    owner: str
    sla: SlaClock
    narrative: NarrativeDraft
    disposition: Disposition
    severity: Severity
    decision: Decision
    summary: str
    requires_human_review: bool
    outcome_kind: str = "item"
    requirements: tuple[ArtefactRequirement, ...] = ()
    coverage: tuple[ArtefactCoverage, ...] = ()
    links: tuple[EvidenceLink, ...] = ()
    withheld: tuple[WithholdRecord, ...] = ()
    exhibits: tuple[Exhibit, ...] = ()
    obligations: tuple[ObligationRef, ...] = ()
    blockers: tuple[Blocker, ...] = ()
    completeness_pct: int = 0
    satisfied_mandatory: int = 0
    total_mandatory: int = 0
    out_of_scope_dropped: int = 0
    suppressed_by_entitlement: int = 0
    release_state: ReleaseState = ReleaseState.HELD_FOR_CHECKER
    release_blockers: tuple[BlockerKind, ...] = ()
    required_approvals: int = 1
    citations: tuple[Citation, ...] = ()


@dataclass(frozen=True, slots=True)
class ResponsePack:
    """The submission roll-up, the artifact that actually leaves the firm.

    ``requires_human_review`` is True and ``decision`` is ESCALATED unconditionally, including
    for a fully on-track pack: the contract is that the response is maker-checker approved
    before it goes, so a clean pack routes for APPROVAL rather than for rescue, with two
    approvals because ``pack`` is in ``ExamPolicy.dual_control_kinds``. ``release_state`` is
    ``HELD_FOR_CHECKER`` and no code path changes it.
    """

    request_id: str
    subject: str
    case_ref: str
    regulator: str
    reference: str
    instrument: Instrument
    as_of: date
    sla: SlaClock
    cover_note: NarrativeDraft
    disposition: Disposition
    severity: Severity
    decision: Decision
    summary: str
    outcome_kind: str = "pack"
    items: tuple[ItemAssessment, ...] = ()
    document_index: tuple[Exhibit, ...] = ()
    withholding_schedule: tuple[WithholdRecord, ...] = ()
    blockers: tuple[Blocker, ...] = ()
    completeness_pct: int = 0
    release_state: ReleaseState = ReleaseState.HELD_FOR_CHECKER
    release_blockers: tuple[BlockerKind, ...] = ()
    required_approvals: int = 2
    requires_human_review: bool = True
    citations: tuple[Citation, ...] = ()


@runtime_checkable
class ReviewableOutcome(Protocol):
    """What rule R8 needs from an outcome, whatever shape the outcome has.

    Both :class:`ItemAssessment` and :class:`ResponsePack` satisfy it, so the review router and
    the payload builder have ONE routing path for two artifact shapes rather than two payload
    builders that drift apart. ``typing`` is stdlib, so the core purity scan stays green.

    It is also what lets the payload builder drop a severity-keyed dual-control table and read
    ``required_approvals`` off the outcome: the engine is the single owner of that number.

    Every member is declared READ-ONLY, as a property rather than a bare annotation. That is not
    style: a bare annotation on a Protocol declares a settable variable, which a frozen dataclass
    can never satisfy, and every outcome this service produces is frozen on purpose.
    """

    @property
    def subject(self) -> str: ...

    @property
    def case_ref(self) -> str: ...

    @property
    def outcome_kind(self) -> str: ...

    @property
    def severity(self) -> Severity: ...

    @property
    def decision(self) -> Decision: ...

    @property
    def summary(self) -> str: ...

    @property
    def requires_human_review(self) -> bool: ...

    @property
    def required_approvals(self) -> int: ...

    @property
    def citations(self) -> tuple[Citation, ...]: ...


@dataclass(frozen=True, slots=True)
class CaseRecord:
    """The persisted case state behind the exam lead's open-item board.

    Without it the SLA clock is a calculation rather than a clock: nobody can see the open
    request list. It carries ``acl_labels`` so the store filters rows against the READER's
    entitlements in the query, which is where object-level authorisation from data tags lands.
    """

    request_id: str
    item_ref: str
    tenant: str
    owner: str
    disposition: Disposition
    band: Severity
    due_on: date
    internal_due_on: date
    business_days_remaining: int
    completeness_pct: int
    review_ref: str = ""
    acl_labels: frozenset[str] = frozenset()
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True, slots=True)
class WaiverRecord:
    """A recorded privilege waiver, resolved from the case store BY REFERENCE.

    It exists as a type precisely so a waiver can never be a client assertion: the request
    carries a lookup key, a key that resolves to nothing leaves the document withheld, and an
    expired or wrong-tenant record is the same as no record.
    """

    ref: str
    tenant: str
    scope: str
    granted_by: str
    expires_on: date
    citation: Citation = NO_CITATION
