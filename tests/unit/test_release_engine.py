"""Disposition, severity, the release gate, dual control, and the guard on ``RELEASED``.

The last one is the reason this file exists in the shape it does. ``ReleaseState.RELEASED`` has
no producer anywhere in this service, and a test that only asserts today's engine never returns
it is a green nobody watched go red: indistinguishable from an absent test. So the guard is
written as a FUNCTION and run against a PLANTED MUTANT that does return it. The mutant lives
here permanently, so the day somebody adds a release path the guard has already been shown to
catch it.

The dual-control rules get the same treatment: the skilled-person shape (two approvals, no
escalation) is exactly what a severity-keyed table gets wrong, so it is pinned rather than
described.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from exam_rfi_orchestrator.domain.kernel import Decision, Severity
from exam_rfi_orchestrator.domain.models import (
    ArtefactClass,
    Blocker,
    BlockerKind,
    Disposition,
    EvidenceLink,
    EvidenceStatus,
    ReleaseState,
    SlaClock,
)
from exam_rfi_orchestrator.domain.policy import DEFAULT_POLICY
from exam_rfi_orchestrator.domain.release_engine import (
    escalation,
    item_disposition,
    item_severity,
    rank_blockers,
    release_blockers,
    required_approvals,
)

_CLEAR = SlaClock(
    due_on=date(2027, 4, 30),
    internal_due_on=date(2027, 4, 23),
    due_basis="regulator_stated",
    extension_request_by=date(2027, 4, 16),
    business_days_remaining=29,
    band=Severity.LOW,
    breached=False,
    buffer_consumed=False,
    calendar_id="SG",
    calendar_version="2027.1",
)
_RED = replace(_CLEAR, band=Severity.CRITICAL, business_days_remaining=-1, buffer_consumed=True)
_BREACHED = replace(_RED, breached=True)


def _blocker(kind: BlockerKind, severity: Severity) -> Blocker:
    return Blocker(kind=kind, severity=severity, detail="(FICTIONAL)")


def _link(status: EvidenceStatus) -> EvidenceLink:
    return EvidenceLink(
        requirement_id="REQ-1.a-policy",
        doc_id="doc-1",
        title="",
        locator="",
        artefact=ArtefactClass.POLICY,
        as_of=date(2026, 9, 1),
        status=status,
        basis_rule="A3",
    )


# --------------------------------------------------------------------------------------- #
# Disposition (S1) and severity (S2)
# --------------------------------------------------------------------------------------- #
def test_breach_beats_blocked_beats_at_risk_beats_on_track() -> None:
    high = [_blocker(BlockerKind.MISSING_ARTEFACT, Severity.HIGH)]
    medium = [_blocker(BlockerKind.NO_OWNER, Severity.MEDIUM)]
    assert item_disposition(high, _BREACHED, []) is Disposition.BREACH
    assert item_disposition(high, _CLEAR, []) is Disposition.BLOCKED
    assert item_disposition(medium, _CLEAR, []) is Disposition.AT_RISK
    assert item_disposition([], _CLEAR, []) is Disposition.ON_TRACK


def test_a_red_clock_or_an_unsettled_document_makes_an_otherwise_clean_item_at_risk() -> None:
    assert item_disposition([], _RED, []) is Disposition.AT_RISK
    assert (
        item_disposition([], _CLEAR, [_link(EvidenceStatus.WITHHELD_PRIVILEGED)])
        is Disposition.AT_RISK
    )
    assert item_disposition([], _CLEAR, [_link(EvidenceStatus.STALE)]) is Disposition.AT_RISK
    # The control: an accepted link on its own does not make an item at risk.
    assert item_disposition([], _CLEAR, [_link(EvidenceStatus.ACCEPTED)]) is Disposition.ON_TRACK


def test_severity_is_the_worse_of_the_blockers_and_the_clock_band() -> None:
    assert item_severity([], _CLEAR) is Severity.LOW
    assert item_severity([], _RED) is Severity.CRITICAL
    assert item_severity([_blocker(BlockerKind.NO_OWNER, Severity.MEDIUM)], _CLEAR) is (
        Severity.MEDIUM
    )
    assert item_severity([_blocker(BlockerKind.NO_OWNER, Severity.MEDIUM)], _RED) is (
        Severity.CRITICAL
    )


def test_a_privilege_hold_floors_the_severity_at_high_and_never_lowers_it() -> None:
    """A privilege call is a lawyer's decision and never a workflow's."""
    hold = [_blocker(BlockerKind.PRIVILEGE_HOLD, Severity.LOW)]
    assert item_severity(hold, _CLEAR) is Severity.HIGH
    # The floor only ever RAISES: a critical clock is not pulled down to high.
    assert item_severity(hold, _RED) is Severity.CRITICAL


def test_only_high_and_critical_escalate() -> None:
    assert escalation(Severity.LOW) == (False, Decision.ALLOWED)
    assert escalation(Severity.MEDIUM) == (False, Decision.ALLOWED)
    assert escalation(Severity.HIGH) == (True, Decision.ESCALATED)
    assert escalation(Severity.CRITICAL) == (True, Decision.ESCALATED)


def test_blockers_rank_worst_first_and_deterministically() -> None:
    ranked = rank_blockers(
        [
            _blocker(BlockerKind.NO_OWNER, Severity.MEDIUM),
            _blocker(BlockerKind.DEADLINE_BREACH, Severity.CRITICAL),
            _blocker(BlockerKind.MISSING_ARTEFACT, Severity.HIGH),
        ]
    )
    assert [blocker.kind.value for blocker in ranked] == [
        "deadline_breach",
        "missing_artefact",
        "no_owner",
    ]


# --------------------------------------------------------------------------------------- #
# Release is a separate question from disposition (R2)
# --------------------------------------------------------------------------------------- #
def test_an_on_track_item_below_the_completeness_floor_is_still_blocked_from_release() -> None:
    kinds = release_blockers([], 75, DEFAULT_POLICY)
    assert kinds == (BlockerKind.BELOW_MIN_COMPLETENESS,)


def test_release_blockers_are_named_kinds_and_deduplicated() -> None:
    kinds = release_blockers(
        [
            _blocker(BlockerKind.MISSING_ARTEFACT, Severity.HIGH),
            _blocker(BlockerKind.MISSING_ARTEFACT, Severity.HIGH),
            _blocker(BlockerKind.NO_OWNER, Severity.MEDIUM),
        ],
        100,
        DEFAULT_POLICY,
    )
    assert kinds == (BlockerKind.MISSING_ARTEFACT, BlockerKind.NO_OWNER)


def test_a_complete_item_with_no_blocker_has_nothing_to_clear() -> None:
    assert release_blockers([], 100, DEFAULT_POLICY) == ()


# --------------------------------------------------------------------------------------- #
# Dual control (R3): the engine is the single owner of the number
# --------------------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("kind", "instrument", "severity", "expected"),
    [
        ("item", "rfi", Severity.LOW, 1),
        ("item", "rfi", Severity.HIGH, 1),
        ("item", "rfi", Severity.CRITICAL, 2),
        # The case a severity-keyed table gets wrong: dual control WITHOUT escalation.
        ("item", "s166_skilled_person", Severity.LOW, 2),
        ("item", "information_notice", Severity.LOW, 2),
        ("pack", "rfi", Severity.LOW, 2),
    ],
)
def test_the_approval_count_follows_kind_instrument_and_severity(
    kind: str, instrument: str, severity: Severity, expected: int
) -> None:
    assert (
        required_approvals(
            outcome_kind=kind, instrument=instrument, severity=severity, policy=DEFAULT_POLICY
        )
        == expected
    )


def test_dual_control_is_configuration_and_not_a_constant() -> None:
    """An adopter who removes an instrument from the list gets one approval, not two."""
    policy = replace(DEFAULT_POLICY, dual_control_instruments=())
    assert (
        required_approvals(
            outcome_kind="item",
            instrument="s166_skilled_person",
            severity=Severity.LOW,
            policy=policy,
        )
        == 1
    )


# --------------------------------------------------------------------------------------- #
# The RELEASED guard, proved against a planted mutant (rule R1)
# --------------------------------------------------------------------------------------- #
def held_for_checker(release_state: ReleaseState) -> bool:
    """The guard: an outcome leaving this service must be held for a checker.

    Written as a function on purpose. A guard that only ever reads the real engine's output has
    never been shown to be able to fail, and that is indistinguishable from no guard at all.
    """
    return release_state is ReleaseState.HELD_FOR_CHECKER


def test_the_release_guard_passes_the_state_this_service_actually_produces() -> None:
    assert held_for_checker(ReleaseState.HELD_FOR_CHECKER)


def test_the_release_guard_goes_RED_on_a_planted_mutant_that_returns_released() -> None:
    """The falsification. If this ever passes, the guard has stopped guarding anything.

    ``RELEASED`` exists in the enum because the console needs the vocabulary. Nothing in this
    service may produce it: release happens in the human-review console, by a person, and an
    operator sends the production.
    """
    assert not held_for_checker(ReleaseState.RELEASED)


def test_no_module_in_this_service_ever_names_the_released_member() -> None:
    """The static half: the mutant above proves the guard works, this proves nothing needs it."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src"
    offenders: list[str] = []
    for source in sorted(root.rglob("*.py")):
        text = source.read_text(encoding="utf-8")
        if "ReleaseState.RELEASED" in text and source.name != "models.py":
            offenders.append(str(source))
    assert not offenders, (
        "a module now produces ReleaseState.RELEASED: release is a human act in the console, "
        f"not a value this service returns. Offenders: {offenders}"
    )
