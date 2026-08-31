"""The grounding contract and the prior-answer conflict check, both proved against bad input.

Two model-facing rule sets live here, and both are worth testing the same way: feed them the
output a model actually produces when it goes wrong, and check the engine discards it rather
than repairing it.

* **Grounding (G2, G3).** A draft citing an exhibit outside this item's index, a draft citing
  nothing, a draft carrying an integer the engine never produced, and malformed JSON all have to
  be rejected. The fallback that replaces them is itself held to the same two predicates, so the
  replacement cannot be the thing that leaks.
* **Consistency (X1, X2).** A renamed assertion key must raise rather than switch the conflict
  check off silently, and a genuine contradiction must name BOTH values so a checker can see the
  contradiction rather than being told there is one.
"""

from __future__ import annotations

from datetime import date

from exam_rfi_orchestrator.domain import narration
from exam_rfi_orchestrator.domain.consistency import KNOWN_ASSERTION_KEYS, check_consistency
from exam_rfi_orchestrator.domain.kernel import Citation, Severity
from exam_rfi_orchestrator.domain.models import (
    ArtefactClass,
    AssertedFact,
    BlockerKind,
    Exhibit,
    PriorAnswer,
    RequestTopic,
)

_EXHIBIT = Exhibit(
    exhibit_no="EX-1.a-01",
    doc_id="kb-aml-pol-01",
    title="Financial crime policy (FICTIONAL)",
    artefact=ArtefactClass.POLICY,
    as_of=date(2026, 6, 30),
    locator="s.4.2",
    citation=Citation(source_id="doc:kb-aml-pol-01", title="Financial crime policy (FICTIONAL)"),
)

_REQUEST = narration.build_narrative_request(
    item_ref="1.a",
    question="Provide the financial-crime policy in force during the review period.",
    completeness_pct=100,
    satisfied=5,
    total=5,
    business_days_remaining=29,
    exhibits=(_EXHIBIT,),
)
_REFS = ("EX-1.a-01",)


def _payload(narrative: str) -> str:
    import json

    return json.dumps({"narrative": narrative, "proposed_artefacts": []})


# --------------------------------------------------------------------------------------- #
# Grounding
# --------------------------------------------------------------------------------------- #
def test_a_grounded_draft_is_kept() -> None:
    verdict = narration.narrative_verdict(
        _payload("The firm produces [EX-1.a-01]; 5 of 5 mandatory artefacts, 100 per cent."),
        _REQUEST.facts,
        _REFS,
    )
    assert verdict.ok
    assert verdict.reason == ""


def test_a_draft_citing_an_exhibit_outside_this_index_is_discarded_whole() -> None:
    verdict = narration.narrative_verdict(
        _payload("The firm produces [EX-9.z-99]."), _REQUEST.facts, _REFS
    )
    assert not verdict.ok
    assert "index" in verdict.reason


def test_a_draft_citing_nothing_at_all_is_discarded() -> None:
    verdict = narration.narrative_verdict(
        _payload("The firm produced everything requested."), _REQUEST.facts, _REFS
    )
    assert not verdict.ok


def test_a_draft_carrying_an_integer_the_engine_never_produced_is_discarded() -> None:
    verdict = narration.narrative_verdict(
        _payload("The firm produces [EX-1.a-01] covering 4242 records."), _REQUEST.facts, _REFS
    )
    assert not verdict.ok
    assert "integer" in verdict.reason


def test_malformed_model_output_is_discarded_rather_than_repaired() -> None:
    for bad in ("not json at all", "[]", '{"narrative": ""}', '{"note": "wrong key"}'):
        assert not narration.narrative_verdict(bad, _REQUEST.facts, _REFS).ok


def test_the_deterministic_fallback_passes_the_same_two_predicates() -> None:
    """The replacement for a discarded draft must not be the thing that leaks."""
    fallback = narration.fallback_narrative(_REQUEST.facts, (_EXHIBIT,))
    assert narration.citations_grounded(fallback, _REFS)
    assert narration.integers_grounded(fallback, _REQUEST.facts)


def test_the_offline_narrator_can_be_made_to_produce_an_ungrounded_draft() -> None:
    """A stub that could only produce good output would make the discard path unobservable."""
    from exam_rfi_orchestrator.adapters.local.generation import (
        UNGROUNDED_PROBE,
        LocalGenerationAdapter,
    )
    from exam_rfi_orchestrator.config import Settings
    from exam_rfi_orchestrator.ports.generation import GenerationRequest

    adapter = LocalGenerationAdapter(Settings(profile="local"))
    probe = GenerationRequest(
        system=_REQUEST.system,
        prompt=_REQUEST.prompt + "\n" + UNGROUNDED_PROBE,
        facts=_REQUEST.facts,
        response_keys=_REQUEST.response_keys,
    )
    verdict = narration.narrative_verdict(adapter.generate(probe).text, _REQUEST.facts, _REFS)
    assert not verdict.ok, "the probe response was accepted, so the discard path is untested"


def test_the_proposed_artefacts_parse_but_an_unknown_class_is_dropped_not_guessed() -> None:
    import json

    parsed = narration.parse_narrative(
        json.dumps(
            {
                "narrative": "The firm produces [EX-1.a-01].",
                "proposed_artefacts": ["issue_log", "not_a_class"],
            }
        )
    )
    assert parsed is not None
    assert parsed[1] == (ArtefactClass.ISSUE_LOG,)


def test_an_unparseable_classification_leaves_the_declared_topic_standing() -> None:
    assert narration.parse_classification("nonsense") == (None, ())
    assert narration.parse_classification('{"topic": "not_a_topic"}') == (None, ())


# --------------------------------------------------------------------------------------- #
# Consistency
# --------------------------------------------------------------------------------------- #
def _prior(value: str) -> PriorAnswer:
    return PriorAnswer(
        answer_id="PRIOR-FICTIONAL-2026-08",
        submitted_on=date(2026, 8, 14),
        item_ref="2.c",
        topic=RequestTopic.TECHNOLOGY_AND_CYBER,
        assertion_key="sanctions_screening_vendor",
        assertion_value=value,
        citation=Citation(source_id="prior:PRIOR-FICTIONAL-2026-08", title="Prior submission"),
    )


def _fact(key: str, value: str) -> AssertedFact:
    return AssertedFact(
        assertion_key=key,
        assertion_value=value,
        citation=Citation(source_id="doc:kb-tec-mi-01", title="Exception MI (FICTIONAL)"),
    )


def test_a_contradiction_with_a_prior_submission_is_raised_and_names_both_values() -> None:
    result = check_consistency(
        [_fact("sanctions_screening_vendor", "Halcyon Screening (FICTIONAL)")],
        [_prior("Northwind Screening (FICTIONAL)")],
    )
    assert [blocker.kind for blocker in result.blockers] == [BlockerKind.PRIOR_ANSWER_CONFLICT]
    detail = result.blockers[0].detail
    assert "Halcyon" in detail and "Northwind" in detail
    assert result.blockers[0].severity is Severity.HIGH
    # Both sides are traceable: the current exhibit on the blocker, the prior one returned.
    assert result.blockers[0].citation.source_id == "doc:kb-tec-mi-01"
    assert [c.source_id for c in result.citations] == ["prior:PRIOR-FICTIONAL-2026-08"]


def test_the_same_answer_written_differently_is_not_a_contradiction() -> None:
    result = check_consistency(
        [_fact("sanctions_screening_vendor", "  halcyon screening (FICTIONAL) ")],
        [_prior("Halcyon Screening (FICTIONAL)")],
    )
    assert result.blockers == ()


def test_a_renamed_assertion_key_raises_rather_than_switching_the_check_off() -> None:
    """Rule X1. Silence is exactly what a model that renamed a key would buy."""
    result = check_consistency(
        [_fact("screening_vendor_name", "Halcyon Screening (FICTIONAL)")],
        [_prior("Northwind Screening (FICTIONAL)")],
    )
    assert [blocker.kind for blocker in result.blockers] == [BlockerKind.UNRECOGNISED_ASSERTION]
    assert "screening_vendor_name" in result.blockers[0].detail


def test_the_assertion_vocabulary_is_closed_and_not_empty() -> None:
    """A vocabulary of nothing would make rule X1 fire on every fact, which is not a check."""
    assert KNOWN_ASSERTION_KEYS
    assert "sanctions_screening_vendor" in KNOWN_ASSERTION_KEYS
