"""Local GenerationPort: a deterministic, SDK-free narrator, classifier and normaliser.

It stands in for a managed model in the gate, the tests and the demo. It never decides anything:
it restates the engine-owned facts it was handed and cites each exhibit reference in brackets, so
its draft is grounded BY CONSTRUCTION and still faces the same rule G2 and G3 validators a
managed model's output faces.

A silent empty return would let a producer ship the narration seam unwired and green, so this
always produces a real, inspectable payload.

THE SECOND SEEDED RESPONSE IS THE POINT OF THE PROBE MARKER. A stub that can only produce
grounded output makes the discard path unobservable, and a guard observed only green asserts
nothing. A prompt carrying :data:`UNGROUNDED_PROBE` gets a draft that cites an exhibit outside
the index AND carries an integer the facts do not contain, so both halves of the grounding
contract have something real to reject.
"""

from __future__ import annotations

import json
import re

from ...config import Settings
from ...domain.artefact_taxonomy import REQUIRED_ARTEFACTS
from ...domain.models import ArtefactClass, RequestTopic
from ...ports.generation import GenerationRequest, GenerationResponse

#: Put this in a prompt to make the offline narrator produce an UNGROUNDED draft on purpose.
UNGROUNDED_PROBE = "narration-probe:ungrounded"

#: The model id this adapter declares, so the provenance banner names a stub as a stub.
_MODEL = "deterministic-offline-stub"

#: How the fixture corpus carries a normalisable assertion. Obviously a fixture convention, and
#: deliberately visible: a reader can see exactly what the "model" extracted and from where.
_ASSERT = re.compile(r"\[assert:([a-z_]+)=([^\]]+)\]")

#: Keyword hints for the classification job. A stub for a model, so a keyword table is the honest
#: implementation: it is transparent and deterministic. What it returns is a SUGGESTION for a
#: person: no requirement, count, coverage state or disposition is computed from it anywhere.
_TOPIC_HINTS: tuple[tuple[RequestTopic, tuple[str, ...]], ...] = (
    (RequestTopic.AML_FINANCIAL_CRIME, ("financial crime", "money laundering", "monitoring")),
    (RequestTopic.TECHNOLOGY_AND_CYBER, ("screening", "platform", "cyber", "technology")),
    (RequestTopic.DATA_PRIVACY, ("personal data", "customer file", "privacy", "correspondence")),
    (RequestTopic.OPERATIONAL_RESILIENCE, ("resilience", "impact tolerance", "scenario")),
    (RequestTopic.GOVERNANCE, ("board", "committee", "governance", "terms of reference")),
    (RequestTopic.CONDUCT_AND_COMPLAINTS, ("complaint", "conduct", "root cause")),
    (RequestTopic.OUTSOURCING_THIRD_PARTY, ("outsourc", "third party", "provider", "vendor")),
    (RequestTopic.MODEL_RISK, ("model", "scorecard", "validation")),
    (RequestTopic.CREDIT_RISK, ("credit", "lending", "arrears")),
    (RequestTopic.CAPITAL_AND_LIQUIDITY, ("capital", "liquidity", "funding")),
)


class LocalGenerationAdapter:
    """Restate the request's engine facts deterministically (no model, no network, no SDK)."""

    _MODEL = _MODEL

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        keys = request.response_keys
        if "topic" in keys:
            payload = self._classify(request.prompt)
        elif "facts" in keys:
            payload = self._normalise(request.prompt)
        else:
            payload = self._narrate(request)
        return GenerationResponse(text=json.dumps(payload), model=_MODEL)

    # ------------------------------------------------------------------ jobs

    def _narrate(self, request: GenerationRequest) -> dict[str, object]:
        if UNGROUNDED_PROBE in request.prompt:
            # Both grounding rules have something to reject: an exhibit outside this item's
            # index, and an integer the engine never produced.
            return {
                "narrative": "The firm produces [EX-NOT-IN-INDEX-99] covering 4242 records.",
                "proposed_artefacts": [],
            }
        facts = dict(request.facts)
        cited = " ".join(
            f"[{key}]" for key in facts if key.startswith("EX-") or key.startswith("IDX-")
        )
        return {
            "narrative": (
                f"The firm responds to item {facts.get('item_ref', '')} and produces {cited}. "
                f"Mandatory artefacts satisfied: {facts.get('satisfied_mandatory', '0')} of "
                f"{facts.get('total_mandatory', '0')}, which is "
                f"{facts.get('completeness_pct', '0')} per cent complete."
            ),
            "proposed_artefacts": [ArtefactClass.NARRATIVE_STATEMENT.value],
        }

    @staticmethod
    def _classify(prompt: str) -> dict[str, object]:
        """Suggest a topic and the artefact classes that topic usually needs.

        The suggestion is deliberately NON-EMPTY. A stub that proposed nothing made the whole
        "a model proposal changes no outcome" claim unfalsifiable offline, because there was
        never a proposal to change one with.
        """
        lowered = prompt.lower()
        for topic, hints in _TOPIC_HINTS:
            if any(hint in lowered for hint in hints):
                suggested = REQUIRED_ARTEFACTS.get(topic, ())
                return {"topic": topic.value, "artefacts": [row.value for row in suggested]}
        return {"topic": "", "artefacts": []}

    @staticmethod
    def _normalise(prompt: str) -> dict[str, object]:
        facts: list[dict[str, str]] = []
        for line in prompt.splitlines():
            reference = line.split(":", 1)[0].strip()
            for key, value in _ASSERT.findall(line):
                facts.append({"key": key, "value": value.strip(), "exhibit": reference})
        return {"facts": facts}
