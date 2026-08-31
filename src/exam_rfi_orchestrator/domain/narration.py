"""The grounding contract: what the model may write, and what discards it whole (G1 to G3).

The model has four narrow, non-consequential jobs behind the generation port, and every one of
them has a deterministic validator here that DISCARDS bad output rather than repairing it:

1. **SUGGEST** a topic and a candidate artefact set for a free-text question. The suggestion goes
   to a PERSON: the surface refuses an item that declares no topic and names the suggestion in
   the refusal. It is not unioned into anything, because the topic is rule A2's responsiveness
   key and a wrong one drops every document the firm holds for that question.
2. **NORMALISE** a produced exhibit into asserted facts using only the closed assertion
   vocabulary, feeding the prior-answer conflict check.
3. **DRAFT** the per-item narrative and the pack cover note from INDEXED exhibits only.
4. **PROPOSE** additional artefact classes the playbook may have missed. Advisory in the literal
   sense: the proposal is displayed on the draft and is an argument to no engine function, so it
   enters no requirement, no count and no gate.

The model never sets an artefact requirement, a coverage state, a withhold, a deadline, a band, a
completeness number, an exhibit number, a disposition, a release blocker or an approval count,
and it is never shown a hard-withheld document at all: withheld candidates are removed from the
prompt inputs by the engine before the port is called.

Every request builder, parser and predicate below is a module-level PURE FUNCTION, so the
evaluation scores the RAW model output through the same contract the service enforces and the
citation-grounding metric can actually go red. Repairing a draft would move that contract outside
the pure domain, where the eval cannot reach it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

from ..ports.generation import GenerationRequest
from .models import ArtefactClass, Exhibit, RequestTopic

__all__ = [
    "GroundingVerdict",
    "build_classify_request",
    "build_narrative_request",
    "build_normalise_request",
    "citations_grounded",
    "fallback_narrative",
    "grounded_integers",
    "integers_grounded",
    "narrative_verdict",
    "parse_classification",
    "parse_facts",
    "parse_narrative",
]

#: Integer tokens, matched identically in the draft and in the engine facts so the two sides of
#: the grounding test cannot disagree about what an integer is.
_INT = re.compile(r"-?\d+")

#: An exhibit reference as the prompt asks for it, in square brackets.
_CITED = re.compile(r"\[([A-Za-z0-9._-]+)\]")

_DRAFT_SYSTEM = (
    "You draft one paragraph of a regulator response. You cite every claim with an exhibit "
    "reference in square brackets, you use only the exhibit references you were given, and you "
    "never write a number that is not in the facts block."
)

_CLASSIFY_SYSTEM = (
    "You suggest one topic and the artefact classes a supervisory question plainly asks for. "
    "You never decide what is required and nothing is computed from your answer: a person reads "
    "it and declares the topic themselves, and the firm's own playbook and the obligation "
    "register decide what must be produced."
)

_NORMALISE_SYSTEM = (
    "You normalise a produced exhibit into factual assertions using ONLY the assertion keys you "
    "were given. You never invent a key and you never restate an opinion as a fact."
)


class GroundingVerdict:
    """Why a draft was kept or discarded. ``reason`` is empty exactly when it was kept."""

    __slots__ = ("reason", "text")

    def __init__(self, text: str, reason: str = "") -> None:
        self.text = text
        self.reason = reason

    @property
    def ok(self) -> bool:
        return not self.reason


def grounded_integers(facts: Sequence[tuple[str, str]]) -> set[str]:
    """Every integer token appearing in the engine-owned facts: the grounded number set."""
    allowed: set[str] = set()
    for _key, value in facts:
        allowed.update(_INT.findall(value))
    return allowed


def integers_grounded(text: str, facts: Sequence[tuple[str, str]]) -> bool:
    """Rule G3: every integer in the draft is one the engine handed the model."""
    allowed = grounded_integers(facts)
    return all(token in allowed for token in _INT.findall(text))


def citations_grounded(text: str, exhibit_refs: Sequence[str]) -> bool:
    """Rule G2: the draft cites at least one exhibit, and only exhibits in THIS item's index."""
    cited = _CITED.findall(text)
    if not cited:
        return False
    known = set(exhibit_refs)
    return all(reference in known for reference in cited)


def _facts_for(
    *,
    item_ref: str,
    completeness_pct: int,
    satisfied: int,
    total: int,
    business_days_remaining: int,
    exhibits: Sequence[Exhibit],
) -> tuple[tuple[str, str], ...]:
    """The engine-owned figures the draft may cite, and the only thing that grounds it."""
    facts: list[tuple[str, str]] = [
        ("item_ref", item_ref),
        ("completeness_pct", str(completeness_pct)),
        ("satisfied_mandatory", str(satisfied)),
        ("total_mandatory", str(total)),
        ("business_days_remaining", str(business_days_remaining)),
    ]
    for exhibit in exhibits:
        # The exhibit reference is repeated INTO the value, not left as the key alone: the
        # grounded-integer set is built from fact VALUES, and a reference that appeared only as a
        # key would make every draft that cited it fail rule G3 on its own exhibit number.
        facts.append((exhibit.exhibit_no, f"{exhibit.exhibit_no} {exhibit.title}"))
    return tuple(facts)


def build_narrative_request(
    *,
    item_ref: str,
    question: str,
    completeness_pct: int,
    satisfied: int,
    total: int,
    business_days_remaining: int,
    exhibits: Sequence[Exhibit],
) -> GenerationRequest:
    """The exact drafting request the service sends, exposed so the eval scores the same path."""
    facts = _facts_for(
        item_ref=item_ref,
        completeness_pct=completeness_pct,
        satisfied=satisfied,
        total=total,
        business_days_remaining=business_days_remaining,
        exhibits=exhibits,
    )
    block = "\n".join(f"{key}={value}" for key, value in facts)
    references = ", ".join(exhibit.exhibit_no for exhibit in exhibits)
    prompt = (
        f"Question: {question}\n"
        f"Exhibits you may cite (and no others): {references}\n"
        f"Facts (use ONLY these numbers):\n{block}\n"
        'Return JSON of the form {"narrative": "<one paragraph>", '
        '"proposed_artefacts": ["<artefact class>", ...]}.'
    )
    return GenerationRequest(
        system=_DRAFT_SYSTEM,
        prompt=prompt,
        facts=facts,
        response_keys=("narrative", "proposed_artefacts"),
    )


def build_classify_request(item_ref: str, question: str) -> GenerationRequest:
    """The classification request. Its answer is a suggestion for a person and enters no rule."""
    topics = ", ".join(topic.value for topic in RequestTopic)
    artefacts = ", ".join(artefact.value for artefact in ArtefactClass)
    prompt = (
        f"Item: {item_ref}\nQuestion: {question}\n"
        f"Topics: {topics}\nArtefact classes: {artefacts}\n"
        'Return JSON of the form {"topic": "<topic>", "artefacts": ["<artefact class>", ...]}.'
    )
    return GenerationRequest(
        system=_CLASSIFY_SYSTEM, prompt=prompt, response_keys=("topic", "artefacts")
    )


def build_normalise_request(
    item_ref: str, exhibits: Sequence[Exhibit], known_keys: Sequence[str]
) -> GenerationRequest:
    """The normalisation request, over INDEXED exhibits only and a closed key vocabulary."""
    lines = "\n".join(
        f"{exhibit.exhibit_no}: {exhibit.title} :: {exhibit.citation.snippet}"
        for exhibit in exhibits
    )
    prompt = (
        f"Item: {item_ref}\nExhibits:\n{lines}\n"
        f"Assertion keys you may use (and no others): {', '.join(sorted(known_keys))}\n"
        'Return JSON of the form {"facts": [{"key": "<assertion key>", "value": "<value>", '
        '"exhibit": "<exhibit reference>"}, ...]}.'
    )
    return GenerationRequest(system=_NORMALISE_SYSTEM, prompt=prompt, response_keys=("facts",))


def _parsed(text: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_narrative(text: str) -> tuple[str, tuple[ArtefactClass, ...]] | None:
    """Parse raw model text into (narrative, proposed artefacts), or ``None`` if invalid.

    A malformed response is DISCARDED WHOLE, never repaired: repairing it would make the service
    the author of a claim the model failed to make properly.
    """
    parsed = _parsed(text)
    if parsed is None:
        return None
    narrative = parsed.get("narrative")
    if not isinstance(narrative, str) or not narrative.strip():
        return None
    proposed: list[ArtefactClass] = []
    raw = parsed.get("proposed_artefacts")
    if isinstance(raw, list):
        for value in raw:
            try:
                proposed.append(ArtefactClass(str(value)))
            except ValueError:
                continue
    return narrative.strip(), tuple(proposed)


def parse_classification(text: str) -> tuple[RequestTopic | None, tuple[ArtefactClass, ...]]:
    """Parse a suggestion, falling back to (None, ()) so nothing is suggested rather than guessed.

    An unparseable answer is not repaired and not partially salvaged into a topic: the caller
    reports "none could be proposed either" and the person declares the topic.
    """
    parsed = _parsed(text)
    if parsed is None:
        return None, ()
    topic: RequestTopic | None = None
    try:
        topic = RequestTopic(str(parsed.get("topic")))
    except ValueError:
        topic = None
    artefacts: list[ArtefactClass] = []
    raw = parsed.get("artefacts")
    if isinstance(raw, list):
        for value in raw:
            try:
                artefacts.append(ArtefactClass(str(value)))
            except ValueError:
                continue
    return topic, tuple(artefacts)


def parse_facts(text: str) -> tuple[tuple[str, str, str], ...]:
    """Parse normalised assertions as (key, value, exhibit reference) triples.

    An unknown key is NOT filtered here. Rule X1 raises a blocker for it, because dropping it
    silently is exactly what a model that renamed a key would buy.
    """
    parsed = _parsed(text)
    if parsed is None:
        return ()
    raw = parsed.get("facts")
    if not isinstance(raw, list):
        return ()
    out: list[tuple[str, str, str]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key", "")).strip()
        value = str(row.get("value", "")).strip()
        if not key or not value:
            continue
        out.append((key, value, str(row.get("exhibit", "")).strip()))
    return tuple(out)


def narrative_verdict(
    text: str, facts: Sequence[tuple[str, str]], exhibit_refs: Sequence[str]
) -> GroundingVerdict:
    """Apply rules G2 and G3 to raw model output and say which one rejected it.

    Used by the service AND by the evaluation's citation-grounding oracle, which is why it is a
    module-level function over raw text rather than a method on the service.
    """
    parsed = parse_narrative(text)
    if parsed is None:
        return GroundingVerdict("", "the response did not parse as the requested JSON shape")
    narrative, _proposed = parsed
    if not citations_grounded(narrative, exhibit_refs):
        return GroundingVerdict(
            narrative, "the draft cited no exhibit, or an exhibit outside this item's index"
        )
    if not integers_grounded(narrative, facts):
        return GroundingVerdict(narrative, "the draft carried an integer the engine facts do not")
    return GroundingVerdict(narrative)


def fallback_narrative(facts: Sequence[tuple[str, str]], exhibits: Sequence[Exhibit]) -> str:
    """A deterministic, grounded-by-construction paragraph assembled from the accepted links.

    Used whenever the model refused, failed or was discarded. It cites every exhibit and uses
    only figures the engine produced, so the fallback passes the same two predicates the model's
    output had to pass.
    """
    values = dict(facts)
    cited = " ".join(f"[{exhibit.exhibit_no}]" for exhibit in exhibits)
    return (
        f"Item {values.get('item_ref', '')}: the firm produces the exhibits listed at {cited}. "
        f"Mandatory artefacts satisfied: {values.get('satisfied_mandatory', '0')} of "
        f"{values.get('total_mandatory', '0')} "
        f"({values.get('completeness_pct', '0')} per cent). "
        "This paragraph was assembled deterministically from the accepted evidence."
    )
