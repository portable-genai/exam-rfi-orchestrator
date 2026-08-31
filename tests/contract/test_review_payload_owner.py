"""The approval count has exactly ONE owner, and this is the file that keeps it that way.

The review payload builder used to carry a module-level severity-keyed dual-control tuple and
compute ``required_approvals`` itself. The engine now decides it under rule R3, and two owners of
one number disagree the first time an instrument-driven case appears at low severity: a
skilled-person review demands dual control and never escalates, so a severity table sends it for
one approval while the service says two.

Two halves, and both are needed:

* **Behaviour.** The payload's number equals the outcome's, for a case where a severity table
  would get it wrong. That is the claim.
* **Source.** The adapter module names no severity in an approvals decision. That is what stops
  the table coming back in a shape the behavioural test happens not to cover, and the mutant
  below is the exact string the defect took.
"""

from __future__ import annotations

from dataclasses import replace

from exam_rfi_orchestrator.adapters import _review_payload
from exam_rfi_orchestrator.adapters._review_payload import result_to_review
from exam_rfi_orchestrator.domain.kernel import Severity

from .canonical import CANONICAL_RESULT
from tests.fixtures import sample_cases

_SOURCE = _review_payload.__file__


def _source() -> str:
    from pathlib import Path

    return Path(_SOURCE).read_text(encoding="utf-8")


def _code_only(source: str) -> str:
    """``source`` with whole-line comments and the module docstring's prose dropped.

    Deliberate: this module EXPLAINS the table it replaced, and a guard that could not tell code
    from prose would forbid explaining the very defect it guards.
    """
    lines = source.splitlines()
    body: list[str] = []
    in_doc = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('"""'):
            in_doc = not in_doc or stripped.endswith('"""') and len(stripped) > 3
            in_doc = not in_doc if stripped == '"""' else in_doc
            continue
        if in_doc or stripped.startswith("#"):
            continue
        body.append(line)
    return "\n".join(body)


def test_the_payload_carries_the_number_the_engine_decided() -> None:
    review = result_to_review(
        CANONICAL_RESULT, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT
    )
    assert review.required_approvals == CANONICAL_RESULT.required_approvals


def test_the_payload_follows_the_outcome_even_where_a_severity_table_would_not() -> None:
    """The skilled-person shape: dual control at LOW severity, and no escalation at all.

    A severity-keyed table returns 1 here. The engine returns 2. Only one of them is the rule.
    """
    dual_at_low = replace(
        CANONICAL_RESULT,
        severity=Severity.LOW,
        requires_human_review=False,
        required_approvals=2,
    )
    review = result_to_review(dual_at_low, maker=sample_cases.ACTOR, tenant=sample_cases.TENANT)
    assert review.severity == Severity.LOW.value
    assert review.required_approvals == 2


def test_a_pack_and_an_item_get_different_source_keys() -> None:
    """A console that merged them would collapse two reviews with two different readers."""
    item = result_to_review(CANONICAL_RESULT, maker=sample_cases.ACTOR)
    pack = result_to_review(
        replace(CANONICAL_RESULT, outcome_kind="pack"), maker=sample_cases.ACTOR
    )
    assert item.source_key != pack.source_key
    assert item.source_key.endswith(":item")
    assert pack.source_key.endswith(":pack")
    assert item.action.endswith(":item")
    assert pack.action.endswith(":pack")


def test_the_payload_builder_has_no_approvals_rule_of_its_own() -> None:
    """The drift guard. The mutant is the exact shape the defect took before it was removed.

    ``_DUAL_CONTROL = (Severity.CRITICAL,)`` plus ``2 if result.severity in _DUAL_CONTROL else 1``
    is a second owner of a number the engine already decides, and it is wrong for every
    instrument-driven case. Nothing in this module may name a severity while computing approvals.
    """
    code = _code_only(_source())
    assert "required_approvals=outcome.required_approvals" in code, (
        "the payload no longer READS the approval count off the outcome"
    )
    for mutant in (
        "_DUAL_CONTROL",
        "in _DUAL_CONTROL else",
        "Severity.CRITICAL",
        "severity in",
    ):
        assert mutant not in code, (
            f"an independent approvals rule is back in the payload builder: {mutant!r}. "
            "Rule R3 lives in domain/release_engine.py and has exactly one owner."
        )


def test_the_guard_can_see_the_mutant_it_names() -> None:
    """A scanner that cannot go red is decoration, not a gate."""
    planted = _code_only(
        "_DUAL_CONTROL = (Severity.CRITICAL,)\n"
        "approvals = 2 if outcome.severity in _DUAL_CONTROL else 1\n"
    )
    assert "_DUAL_CONTROL" in planted
    assert "severity in" in planted
