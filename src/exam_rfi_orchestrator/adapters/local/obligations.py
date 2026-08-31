"""Local ObligationsReadPort: a deterministic fixture register with the upstream's contract shape.

Every obligation id is obviously fictional; the citations name the KIND of public source a real
register row would carry rather than inventing a rule reference. Every seeded pair returns real,
inspectable obligations with ``required_artefacts`` populated, so a producer cannot ship this
seam unwired and still see a green demo.

One pair is deliberately UNSEEDED (model risk in the shipped jurisdiction) so the "no obligation
text available" path runs offline rather than only in production. That path matters: an item with
no register anchor loses every rule D3 mandatory requirement from its completeness denominator,
and the service records the explicit string rather than guessing a rule reference.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.kernel import Citation
from ...domain.models import ArtefactClass, ObligationRef, RequestTopic

_SG = "SG"


def _obligation(
    obligation_id: str,
    rule_ref: str,
    title: str,
    artefacts: tuple[ArtefactClass, ...],
) -> ObligationRef:
    return ObligationRef(
        obligation_id=obligation_id,
        rule_ref=rule_ref,
        title=title,
        required_artefacts=artefacts,
        citation=Citation(
            source_id=f"obligation:{obligation_id}",
            title=title,
            snippet=f"Register row {rule_ref} (FICTIONAL reference into the obligation graph).",
        ),
    )


_REGISTER: dict[tuple[RequestTopic, str], tuple[ObligationRef, ...]] = {
    (RequestTopic.AML_FINANCIAL_CRIME, _SG): (
        _obligation(
            "OBL-AML-001",
            "handbook/financial-crime/4",
            "Maintain and test financial crime controls (FICTIONAL)",
            (ArtefactClass.POLICY, ArtefactClass.CONTROL_TEST_RESULT),
        ),
    ),
    (RequestTopic.TECHNOLOGY_AND_CYBER, _SG): (
        _obligation(
            "OBL-TEC-001",
            "handbook/technology-risk/7",
            "Independently test platform controls (FICTIONAL)",
            (ArtefactClass.CONTROL_TEST_RESULT,),
        ),
    ),
    (RequestTopic.DATA_PRIVACY, _SG): (
        _obligation(
            "OBL-DPR-001",
            "handbook/data-protection/2",
            "Govern the handling of customer personal data (FICTIONAL)",
            (ArtefactClass.POLICY, ArtefactClass.ISSUE_LOG),
        ),
    ),
    (RequestTopic.OPERATIONAL_RESILIENCE, _SG): (
        _obligation(
            "OBL-OPR-001",
            "handbook/operational-resilience/3",
            "Set impact tolerances and test against them (FICTIONAL)",
            (ArtefactClass.RISK_ASSESSMENT,),
        ),
    ),
    (RequestTopic.GOVERNANCE, _SG): (
        _obligation(
            "OBL-GOV-001",
            "handbook/governance/1",
            "Record committee decisions and delegated authorities (FICTIONAL)",
            (ArtefactClass.COMMITTEE_MINUTES,),
        ),
    ),
    (RequestTopic.CONDUCT_AND_COMPLAINTS, _SG): (
        _obligation(
            "OBL-CON-001",
            "handbook/conduct/5",
            "Analyse complaint root causes and act on them (FICTIONAL)",
            (ArtefactClass.ISSUE_LOG,),
        ),
    ),
    # This row deliberately demands an artefact the topic playbook does NOT list, so rule D3's
    # floor is exercised offline: the register, not the question's wording, decides the minimum.
    (RequestTopic.CREDIT_RISK, _SG): (
        _obligation(
            "OBL-CRD-001",
            "handbook/credit-risk/9",
            "Record and remediate credit-file exceptions (FICTIONAL)",
            (ArtefactClass.ISSUE_LOG,),
        ),
    ),
    (RequestTopic.OUTSOURCING_THIRD_PARTY, _SG): (
        _obligation(
            "OBL-OUT-001",
            "handbook/outsourcing/6",
            "Maintain an outsourcing register and oversee providers (FICTIONAL)",
            (ArtefactClass.THIRD_PARTY_CONTRACT,),
        ),
    ),
}


class LocalObligationsAdapter:
    """Answer obligation lookups from a deterministic fixture register (no network, no SDK)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def obligations_for(self, topic: RequestTopic, jurisdiction: str) -> tuple[ObligationRef, ...]:
        return _REGISTER.get((topic, jurisdiction), ())
