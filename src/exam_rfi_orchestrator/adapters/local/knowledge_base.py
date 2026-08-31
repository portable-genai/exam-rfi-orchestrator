"""Local KnowledgeBaseReadPort: a deterministic, obviously fictional governed corpus.

Stands in for the enterprise knowledge base offline. Every document carries what the
admissibility ladder actually reads: ACL labels, handling tags, an owning jurisdiction, an
effective date and a locator. The corpus deliberately spans privileged material, a restricted
filing and a document held outside the permitted transfer scope, so the WHOLE ladder runs with no
network and no store.

It FILTERS by the caller's entitlements and reports COUNTS of what it suppressed, and only
counts: a total, and the same total split by artefact class. That is the property the port exists
for: an empty answer with a non-zero suppression count means "responsive documents exist that you
may not read", which is a different statement from "the firm holds nothing responsive", and only
one of them may be made to a supervisor. The split is what keeps the first statement attached to
the class it is true of, instead of to every class the item happened to ask for.

An unseeded topic returns an EMPTY items tuple with ``corpus_reached`` true, because empty is a
legitimate answer that rule G1 turns into "no draft". It never raises for an unknown topic: a
reach failure is the managed and on-premises families' job to report.
"""

from __future__ import annotations

from datetime import date

from ...config import Settings
from ...domain.models import (
    ArtefactClass,
    EvidenceItem,
    RequestTopic,
    RetrievalQuery,
    RetrievalResult,
    SensitivityTag,
)

_SG = "SG"
_JP = "JP"

#: Entitlement labels the seeded personas carry. Named once so the corpus and the demo agree.
_RISK = frozenset({"group:risk"})
_ANALYST = frozenset({"group:analyst"})
_APPROVER = frozenset({"group:approver"})


def _document(
    doc_id: str,
    title: str,
    artefact: ArtefactClass,
    topic: RequestTopic,
    as_of: date,
    *,
    acl: frozenset[str] = _RISK,
    jurisdiction: str = _SG,
    tags: tuple[SensitivityTag, ...] = (),
    locator: str = "",
    snippet: str = "",
) -> EvidenceItem:
    return EvidenceItem(
        doc_id=doc_id,
        title=title,
        artefact=artefact,
        topic=topic,
        as_of=as_of,
        owning_jurisdiction=jurisdiction,
        sensitivity=tags,
        acl_labels=acl,
        locator=locator,
        snippet=snippet,
        origin="corpus",
    )


#: The seeded corpus, keyed by topic. Every party is obviously fictional and every address is an
#: ``.example`` domain. One planted national identifier exists so the redaction proof has an
#: independent literal to look for rather than trusting the pattern pack to agree with itself.
_CORPUS: dict[RequestTopic, tuple[EvidenceItem, ...]] = {
    RequestTopic.AML_FINANCIAL_CRIME: (
        _document(
            "kb-aml-pol-01",
            "Financial crime policy (FICTIONAL)",
            ArtefactClass.POLICY,
            RequestTopic.AML_FINANCIAL_CRIME,
            date(2026, 6, 30),
            locator="s.4.2",
            snippet="Board-approved financial crime policy in force for the period (FICTIONAL).",
        ),
        _document(
            "kb-aml-proc-01",
            "Transaction monitoring procedure (FICTIONAL)",
            ArtefactClass.PROCEDURE,
            RequestTopic.AML_FINANCIAL_CRIME,
            date(2026, 9, 30),
            locator="s.2",
            snippet="Alert handling and escalation steps for monitoring output (FICTIONAL).",
        ),
        _document(
            "kb-aml-ctl-01",
            "Monitoring control test result (FICTIONAL)",
            ArtefactClass.CONTROL_TEST_RESULT,
            RequestTopic.AML_FINANCIAL_CRIME,
            date(2026, 11, 30),
            locator="table 3",
            snippet="Independent testing of monitoring rules, no exceptions raised (FICTIONAL).",
        ),
        _document(
            "kb-aml-txn-01",
            "Transaction sample extract (FICTIONAL)",
            ArtefactClass.TRANSACTION_SAMPLE,
            RequestTopic.AML_FINANCIAL_CRIME,
            date(2027, 1, 31),
            locator="rows 1 to 40",
            snippet="Sampled transactions for the review period (FICTIONAL).",
        ),
        _document(
            "kb-aml-mi-01",
            "Board monitoring management information, first quarter (FICTIONAL)",
            ArtefactClass.MANAGEMENT_INFORMATION,
            RequestTopic.AML_FINANCIAL_CRIME,
            date(2026, 12, 31),
            locator="slide 6",
            snippet="Monitoring volumes reported to the board (FICTIONAL).",
        ),
        _document(
            "kb-aml-mi-02",
            "Board monitoring management information, second quarter (FICTIONAL)",
            ArtefactClass.MANAGEMENT_INFORMATION,
            RequestTopic.AML_FINANCIAL_CRIME,
            date(2027, 2, 28),
            locator="slide 7",
            snippet="Monitoring volumes reported to the board (FICTIONAL).",
        ),
    ),
    RequestTopic.TECHNOLOGY_AND_CYBER: (
        _document(
            "kb-tec-pol-01",
            "Screening platform control policy (FICTIONAL)",
            ArtefactClass.POLICY,
            RequestTopic.TECHNOLOGY_AND_CYBER,
            date(2026, 7, 31),
            locator="s.3",
            snippet="Control objectives for the screening platform (FICTIONAL).",
        ),
        _document(
            "kb-tec-proc-01",
            "Screening exception remediation procedure (FICTIONAL)",
            ArtefactClass.PROCEDURE,
            RequestTopic.TECHNOLOGY_AND_CYBER,
            date(2026, 8, 31),
            locator="s.5",
            snippet="Steps for remediating a screening exception (FICTIONAL).",
        ),
        _document(
            "kb-tec-ctl-01",
            "Screening platform independent test, superseded (FICTIONAL)",
            ArtefactClass.CONTROL_TEST_RESULT,
            RequestTopic.TECHNOLOGY_AND_CYBER,
            date(2024, 1, 31),
            locator="table 1",
            snippet="Independent testing far older than the review period (FICTIONAL).",
        ),
        _document(
            "kb-tec-mi-01",
            "Screening exception management information (FICTIONAL)",
            ArtefactClass.MANAGEMENT_INFORMATION,
            RequestTopic.TECHNOLOGY_AND_CYBER,
            date(2027, 1, 31),
            locator="slide 4",
            snippet=(
                "Open screening exceptions by age. "
                "[assert:sanctions_screening_vendor=Halcyon Screening (FICTIONAL)]"
            ),
        ),
    ),
    RequestTopic.DATA_PRIVACY: (
        _document(
            "kb-dpr-pol-01",
            "Personal data handling policy (FICTIONAL)",
            ArtefactClass.POLICY,
            RequestTopic.DATA_PRIVACY,
            date(2026, 5, 31),
            locator="s.1",
            snippet="Handling rules for customer personal data (FICTIONAL).",
        ),
        _document(
            "kb-dpr-proc-01",
            "Outage customer contact procedure (FICTIONAL)",
            ArtefactClass.PROCEDURE,
            RequestTopic.DATA_PRIVACY,
            date(2026, 10, 31),
            locator="s.2",
            snippet="Contacting affected clients after a service outage (FICTIONAL).",
        ),
        _document(
            "kb-dpr-leg-01",
            "Legal analysis of the payments outage (FICTIONAL)",
            ArtefactClass.ISSUE_LOG,
            RequestTopic.DATA_PRIVACY,
            date(2027, 1, 15),
            tags=(SensitivityTag.LEGALLY_PRIVILEGED,),
            locator="memo",
            snippet="Advice prepared for the purpose of legal proceedings (FICTIONAL).",
        ),
        _document(
            "kb-dpr-cus-01",
            "Affected client file (FICTIONAL)",
            ArtefactClass.CUSTOMER_FILE,
            RequestTopic.DATA_PRIVACY,
            date(2027, 2, 10),
            tags=(SensitivityTag.PERSONAL_DATA,),
            locator="file 12",
            snippet="Complainant NRIC S1234567D contacted on the outage (FICTIONAL).",
        ),
        _document(
            "kb-dpr-sar-01",
            "Restricted filing record (FICTIONAL)",
            ArtefactClass.CUSTOMER_FILE,
            RequestTopic.DATA_PRIVACY,
            date(2027, 1, 20),
            tags=(SensitivityTag.SAR_CONFIDENTIAL,),
            locator="filing",
            snippet="The existence of this filing is itself restricted (FICTIONAL).",
        ),
        _document(
            "kb-dpr-cus-02",
            "Affected client file held offshore (FICTIONAL)",
            ArtefactClass.CUSTOMER_FILE,
            RequestTopic.DATA_PRIVACY,
            date(2027, 2, 5),
            jurisdiction=_JP,
            tags=(SensitivityTag.PERSONAL_DATA, SensitivityTag.CROSS_BORDER_RESTRICTED),
            locator="file 44",
            snippet="Client record held outside the requesting jurisdiction (FICTIONAL).",
        ),
    ),
    RequestTopic.OPERATIONAL_RESILIENCE: (
        _document(
            "kb-ops-pol-01",
            "Impact tolerance statement (FICTIONAL)",
            ArtefactClass.POLICY,
            RequestTopic.OPERATIONAL_RESILIENCE,
            date(2026, 6, 15),
            locator="s.2",
            snippet="Impact tolerances for the payments service (FICTIONAL).",
        ),
        _document(
            "kb-ops-ra-01",
            "Severe but plausible scenario assessment (FICTIONAL)",
            ArtefactClass.RISK_ASSESSMENT,
            RequestTopic.OPERATIONAL_RESILIENCE,
            date(2026, 11, 15),
            locator="s.4",
            snippet="Scenario set and assessed impact for payments (FICTIONAL).",
        ),
        _document(
            "kb-ops-ctl-01",
            "Scenario test result (FICTIONAL)",
            ArtefactClass.CONTROL_TEST_RESULT,
            RequestTopic.OPERATIONAL_RESILIENCE,
            date(2027, 2, 20),
            locator="table 2",
            snippet="Most recent scenario test outcome for payments (FICTIONAL).",
        ),
    ),
    RequestTopic.GOVERNANCE: (
        _document(
            "kb-gov-pol-01",
            "Governance framework (FICTIONAL)",
            ArtefactClass.POLICY,
            RequestTopic.GOVERNANCE,
            date(2026, 5, 20),
            acl=_ANALYST,
            locator="s.1",
            snippet="Committee structure and delegated authorities (FICTIONAL).",
        ),
        _document(
            "kb-gov-min-01",
            "Risk committee minute (FICTIONAL)",
            ArtefactClass.COMMITTEE_MINUTES,
            RequestTopic.GOVERNANCE,
            date(2026, 12, 5),
            acl=_APPROVER,
            locator="minute 4",
            snippet="Remediation programme approval recorded (FICTIONAL).",
        ),
        _document(
            "kb-gov-min-02",
            "Board minute (FICTIONAL)",
            ArtefactClass.COMMITTEE_MINUTES,
            RequestTopic.GOVERNANCE,
            date(2027, 2, 12),
            acl=_APPROVER,
            locator="minute 9",
            snippet="Terms of reference approved by the board (FICTIONAL).",
        ),
        _document(
            "kb-gov-org-01",
            "Committee attendance and roles (FICTIONAL)",
            ArtefactClass.ORG_AND_ROLES,
            RequestTopic.GOVERNANCE,
            date(2026, 9, 1),
            acl=_ANALYST,
            locator="appendix A",
            snippet="Attendance record and role descriptions (FICTIONAL).",
        ),
    ),
    RequestTopic.CONDUCT_AND_COMPLAINTS: (
        _document(
            "kb-con-proc-01",
            "Complaints handling procedure (FICTIONAL)",
            ArtefactClass.PROCEDURE,
            RequestTopic.CONDUCT_AND_COMPLAINTS,
            date(2026, 8, 20),
            locator="s.3",
            snippet="End to end complaint handling steps (FICTIONAL).",
        ),
        _document(
            "kb-con-iss-01",
            "Complaint root-cause analysis (FICTIONAL)",
            ArtefactClass.ISSUE_LOG,
            RequestTopic.CONDUCT_AND_COMPLAINTS,
            date(2027, 1, 10),
            locator="s.2",
            snippet="Root causes for the highest-volume categories (FICTIONAL).",
        ),
        _document(
            "kb-con-mi-01",
            "Complaints management information (FICTIONAL)",
            ArtefactClass.MANAGEMENT_INFORMATION,
            RequestTopic.CONDUCT_AND_COMPLAINTS,
            date(2027, 2, 15),
            locator="slide 2",
            snippet="Complaint volumes by category (FICTIONAL).",
        ),
        _document(
            "kb-con-mi-02",
            "Complaints management information, prior year (FICTIONAL)",
            ArtefactClass.MANAGEMENT_INFORMATION,
            RequestTopic.CONDUCT_AND_COMPLAINTS,
            date(2025, 6, 30),
            locator="slide 2",
            snippet="Complaint volumes from before the review period (FICTIONAL).",
        ),
    ),
    RequestTopic.OUTSOURCING_THIRD_PARTY: (
        _document(
            "kb-out-pol-01",
            "Outsourcing policy (FICTIONAL)",
            ArtefactClass.POLICY,
            RequestTopic.OUTSOURCING_THIRD_PARTY,
            date(2026, 7, 10),
            locator="s.2",
            snippet="Outsourcing governance and register requirements (FICTIONAL).",
        ),
        _document(
            "kb-out-con-01",
            "Payments processor master agreement (FICTIONAL)",
            ArtefactClass.THIRD_PARTY_CONTRACT,
            RequestTopic.OUTSOURCING_THIRD_PARTY,
            date(2026, 6, 1),
            locator="clause 14",
            snippet="Master services agreement for payment processing (FICTIONAL).",
        ),
        _document(
            "kb-out-ra-01",
            "Third-party risk assessment (FICTIONAL)",
            ArtefactClass.RISK_ASSESSMENT,
            RequestTopic.OUTSOURCING_THIRD_PARTY,
            date(2026, 10, 10),
            locator="s.6",
            snippet="Assessment of the payments processor arrangement (FICTIONAL).",
        ),
        _document(
            "kb-out-ctl-01",
            "Outsourcing control test result (FICTIONAL)",
            ArtefactClass.CONTROL_TEST_RESULT,
            RequestTopic.OUTSOURCING_THIRD_PARTY,
            date(2027, 1, 25),
            locator="table 5",
            snippet="Testing of outsourcing oversight controls (FICTIONAL).",
        ),
    ),
}


def corpus_documents() -> dict[str, EvidenceItem]:
    """Every seeded document by id, so an oracle can check the ENGINE against the CORPUS.

    The evaluation's entitlement and withhold oracles must not read the engine's own labels back:
    a metric scored from the thing it is checking is a green tick over an empty set. They read
    this instead, which is the fixture the store answers from.
    """
    return {document.doc_id: document for documents in _CORPUS.values() for document in documents}


class LocalKnowledgeBaseAdapter:
    """Answer retrieval from a deterministic fixture corpus (no store, no network, no SDK)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search(self, query: RetrievalQuery) -> RetrievalResult:
        wanted = set(query.artefacts)
        responsive = [
            document
            for document in _CORPUS.get(query.topic, ())
            if not wanted or document.artefact in wanted
        ]
        # The ACL filter runs HERE, in the store, and a count of what it refused is the only
        # thing that travels: a total, plus the same total split by artefact class so the engine
        # can say "you are not entitled to read this" about the class it actually happened to.
        # Neither carries a title or an id. The engine re-checks the survivors anyway (rule A1),
        # which is defence in depth rather than duplication.
        entitled: list[EvidenceItem] = []
        by_artefact: dict[ArtefactClass, int] = {}
        for document in responsive:
            if document.acl_labels <= query.entitlements:
                entitled.append(document)
                continue
            by_artefact[document.artefact] = by_artefact.get(document.artefact, 0) + 1
        return RetrievalResult(
            items=tuple(entitled[: max(0, query.limit)]),
            suppressed_by_entitlement=sum(by_artefact.values()),
            suppressed_by_artefact=by_artefact,
            corpus_reached=True,
        )
