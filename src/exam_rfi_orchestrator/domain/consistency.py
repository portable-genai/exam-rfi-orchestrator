"""Prior-answer consistency: does this pack contradict what the firm already told this regulator.

This is the control an exam lead cannot get from a keyword engine and cannot get from a reviewer
reading a long pack late at night. A submission that contradicts an answer given six months ago
is how an honest late answer becomes a misleading one, and giving a supervisor false or
misleading information is an offence in its own right in several regimes.

The vocabulary is CLOSED. A model normalises a produced exhibit into
:class:`~.models.AssertedFact` values, and an ``assertion_key`` outside
:data:`KNOWN_ASSERTION_KEYS` raises a blocker rather than being ignored, because a model that
renamed a key would otherwise silently switch the whole check off.

The honest bound, which the documentation repeats rather than implying more: this check has good
PRECISION and unmeasured RECALL. Nothing here stops a model mapping two genuinely different
assertions onto one key, or failing to extract an assertion at all.

Pure stdlib: no ports, no I/O, no model, no clock.
"""

from __future__ import annotations

from collections.abc import Sequence

from .kernel import Citation, Severity
from .models import AssertedFact, Blocker, BlockerKind, PriorAnswer

__all__ = ["KNOWN_ASSERTION_KEYS", "ConsistencyResult", "check_consistency"]

#: The closed vocabulary a normalisation may use. Adding a key is a deliberate decision made
#: here, with a golden case behind it, rather than something a prompt change can do by accident.
KNOWN_ASSERTION_KEYS: frozenset[str] = frozenset(
    {
        "sanctions_screening_vendor",
        "transaction_monitoring_vendor",
        "policy_owner_role",
        "policy_approval_body",
        "outsourced_provider",
        "model_validation_frequency",
        "complaints_root_cause_owner",
        "impact_tolerance_hours",
        "control_testing_frequency",
        "customer_records_location",
    }
)


class ConsistencyResult:
    """The blockers and the extra citations the consistency check produced.

    A plain class rather than a dataclass because it carries two tuples and nothing else, and
    naming them is the whole interface.
    """

    __slots__ = ("blockers", "citations")

    def __init__(self, blockers: tuple[Blocker, ...], citations: tuple[Citation, ...]) -> None:
        self.blockers = blockers
        self.citations = citations


def _normalise(value: str) -> str:
    return value.strip().casefold()


def check_consistency(
    facts: Sequence[AssertedFact], prior_answers: Sequence[PriorAnswer]
) -> ConsistencyResult:
    """Rules X1 and X2 over the facts normalised out of this item's produced exhibits.

    * **X1 UNRECOGNISED ASSERTION**: a key outside :data:`KNOWN_ASSERTION_KEYS` raises
      ``UNRECOGNISED_ASSERTION`` at MEDIUM. It is not silently dropped, because silence is
      exactly what a renamed key would buy.
    * **X2 PRIOR-ANSWER CONFLICT**: a fact whose value differs from any prior answer under the
      same key raises ``PRIOR_ANSWER_CONFLICT`` at HIGH. The detail names BOTH values, the
      blocker cites the current exhibit, and the prior citation is returned so both sides of the
      contradiction are traceable.
    """
    blockers: list[Blocker] = []
    citations: list[Citation] = []

    for fact in facts:
        if fact.assertion_key not in KNOWN_ASSERTION_KEYS:
            blockers.append(
                Blocker(
                    kind=BlockerKind.UNRECOGNISED_ASSERTION,
                    severity=Severity.MEDIUM,
                    detail=(
                        f"normalisation returned the key {fact.assertion_key!r}, which is not in "
                        "the closed assertion vocabulary, so no consistency check ran for it"
                    ),
                    citation=fact.citation,
                )
            )
            continue
        for prior in prior_answers:
            if prior.assertion_key != fact.assertion_key:
                continue
            if _normalise(prior.assertion_value) == _normalise(fact.assertion_value):
                continue
            blockers.append(
                Blocker(
                    kind=BlockerKind.PRIOR_ANSWER_CONFLICT,
                    severity=Severity.HIGH,
                    detail=(
                        f"{fact.assertion_key}: this pack says {fact.assertion_value!r}; "
                        f"submission {prior.answer_id} of {prior.submitted_on.isoformat()} said "
                        f"{prior.assertion_value!r}"
                    ),
                    citation=fact.citation,
                )
            )
            citations.append(prior.citation)

    return ConsistencyResult(tuple(blockers), tuple(citations))
