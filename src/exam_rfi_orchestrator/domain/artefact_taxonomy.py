"""Decomposition: turning one numbered question into the artefacts it demands (rules D1 to D4).

The whole rule set is a UNION of three DECLARED inputs. What the regulator explicitly named, what
the firm's own playbook says a question on this topic needs, and what the obligation register
demands are all added together and nothing is ever removed.

NO MODEL OUTPUT IS ONE OF THEM, and that is deliberate rather than an omission. A requirement
changes ``total_mandatory``, and through it the completeness percentage, a coverage state, the
disposition, the severity, the review flag and the release blockers, so a model that could add
one would own an outcome. It was once argued that unioning a proposal in was safe because a
union only ever widens: that is true of the artefact set and false of everything downstream, and
the shipped behaviour was that a single proposed class moved completeness from 100 to 83 and the
disposition from at-risk to blocked. The model's suggestions are advisory and are shown to the
human who can act on them (a narrative draft carries them, and an item with no declared topic is
refused with the model's suggestion NAMED), never fed back into this function.

Decomposition is the weakest deterministic link in this service and the documentation says so
rather than implying completeness. A question phrased unusually matches no requested artefact,
and if its topic is also wrong it falls to rule D4's single default requirement. The union with
the playbook and the register holds the floor; decomposition RECALL is unmeasured and
unmeasurable offline. The honest position is that decomposition is a draft a checker corrects.

Pure stdlib: no ports, no I/O, no model, no clock.
"""

from __future__ import annotations

from collections.abc import Sequence

from .models import (
    ARTEFACT_ORDER,
    ArtefactClass,
    ArtefactRequirement,
    ObligationRef,
    RequestItem,
    RequestTopic,
)

__all__ = ["REQUIRED_ARTEFACTS", "decompose"]

#: The topic playbook: one row per :class:`RequestTopic`, saying what an answer on that topic
#: needs whatever the question happened to ask for. Producing less than the regulator asked is
#: non-responsive; producing less than the firm's own playbook is indefensible.
REQUIRED_ARTEFACTS: dict[RequestTopic, tuple[ArtefactClass, ...]] = {
    RequestTopic.GOVERNANCE: (
        ArtefactClass.POLICY,
        ArtefactClass.COMMITTEE_MINUTES,
        ArtefactClass.ORG_AND_ROLES,
    ),
    RequestTopic.AML_FINANCIAL_CRIME: (
        ArtefactClass.POLICY,
        ArtefactClass.PROCEDURE,
        ArtefactClass.CONTROL_TEST_RESULT,
        ArtefactClass.TRANSACTION_SAMPLE,
        ArtefactClass.MANAGEMENT_INFORMATION,
    ),
    RequestTopic.CONDUCT_AND_COMPLAINTS: (
        ArtefactClass.PROCEDURE,
        ArtefactClass.ISSUE_LOG,
        ArtefactClass.MANAGEMENT_INFORMATION,
    ),
    RequestTopic.CREDIT_RISK: (
        ArtefactClass.POLICY,
        ArtefactClass.RISK_ASSESSMENT,
        ArtefactClass.MANAGEMENT_INFORMATION,
    ),
    RequestTopic.OPERATIONAL_RESILIENCE: (
        ArtefactClass.POLICY,
        ArtefactClass.RISK_ASSESSMENT,
        ArtefactClass.CONTROL_TEST_RESULT,
    ),
    RequestTopic.DATA_PRIVACY: (
        ArtefactClass.POLICY,
        ArtefactClass.PROCEDURE,
        ArtefactClass.ISSUE_LOG,
        ArtefactClass.CUSTOMER_FILE,
    ),
    RequestTopic.MODEL_RISK: (
        ArtefactClass.POLICY,
        ArtefactClass.RISK_ASSESSMENT,
        ArtefactClass.CONTROL_TEST_RESULT,
    ),
    RequestTopic.OUTSOURCING_THIRD_PARTY: (
        ArtefactClass.POLICY,
        ArtefactClass.THIRD_PARTY_CONTRACT,
        ArtefactClass.RISK_ASSESSMENT,
        ArtefactClass.CONTROL_TEST_RESULT,
    ),
    RequestTopic.CAPITAL_AND_LIQUIDITY: (
        ArtefactClass.POLICY,
        ArtefactClass.SYSTEM_EXTRACT,
        ArtefactClass.MANAGEMENT_INFORMATION,
    ),
    RequestTopic.TECHNOLOGY_AND_CYBER: (
        ArtefactClass.POLICY,
        ArtefactClass.PROCEDURE,
        ArtefactClass.CONTROL_TEST_RESULT,
        ArtefactClass.MANAGEMENT_INFORMATION,
    ),
}

_DESCRIPTIONS: dict[str, str] = {
    "D1": "named by the regulator in the question",
    "D2": "required by the topic playbook",
    "D3": "required by the obligation register",
    "D4": "the default narrative statement, because nothing else was required",
}


def _requirement_id(item_ref: str, artefact: ArtefactClass) -> str:
    """A stable, replayable requirement id. Same inputs, same id, forever."""
    return f"REQ-{item_ref}-{artefact.value}"


def decompose(
    item: RequestItem,
    obligations: Sequence[ObligationRef] = (),
) -> tuple[ArtefactRequirement, ...]:
    """Decompose one item into its required artefacts, in declaration order.

    * **D1 REQUESTED**: what the regulator explicitly named is always in the set.
    * **D2 PLAYBOOK**: union in :data:`REQUIRED_ARTEFACTS` for the item's topic.
    * **D3 OBLIGATION**: union in every obligation's ``required_artefacts``, mandatory, with the
      obligation id recorded as the source rule.
    * **D4 DEFAULT**: an empty union yields exactly one mandatory narrative statement, because
      zero requirements reads as trivially one hundred per cent complete.

    Every input is DECLARED: the regulator's own words, the firm's playbook and the register.
    The rule that produced each requirement is recorded on it, so a checker reads WHY an artefact
    is required rather than trusting a black box, and no rule id here can name a model.
    """
    sources: dict[ArtefactClass, str] = {}

    for artefact in item.requested_artefacts:
        sources.setdefault(artefact, "D1:regulator_request")

    for artefact in REQUIRED_ARTEFACTS.get(item.topic, ()):
        sources.setdefault(artefact, f"D2:playbook:{item.topic.value}")

    for obligation in obligations:
        for artefact in obligation.required_artefacts:
            sources.setdefault(artefact, f"D3:obligation:{obligation.obligation_id}")

    if not sources:
        sources[ArtefactClass.NARRATIVE_STATEMENT] = "D4:default_narrative"

    ordered = sorted(sources, key=lambda artefact: ARTEFACT_ORDER[artefact])
    return tuple(
        ArtefactRequirement(
            requirement_id=_requirement_id(item.item_ref, artefact),
            item_ref=item.item_ref,
            artefact=artefact,
            description=_describe(artefact, sources[artefact]),
            mandatory=True,
            source_rule=sources[artefact],
            citation=item.citation,
        )
        for artefact in ordered
    )


def _describe(artefact: ArtefactClass, source_rule: str) -> str:
    rule = source_rule.split(":", 1)[0]
    reason = _DESCRIPTIONS.get(rule, source_rule)
    if rule == "D3":
        reason = f"{reason} ({source_rule.rsplit(':', 1)[-1]})"
    return f"{artefact.value.replace('_', ' ')}: {reason}"
