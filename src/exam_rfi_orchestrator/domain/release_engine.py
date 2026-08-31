"""Disposition, severity, the release gate, dual control and the pack roll-up (S, R and P rules).

Three questions that are deliberately kept apart, because collapsing them is how a taxonomy ends
up wider than the rules that populate it:

* :class:`~.models.Disposition` answers "can this answer be produced in time".
* :class:`~.models.ReleaseState` plus the named release blockers answer "may it leave the firm".
* The kernel ``Severity`` is the escalation band the audit event and the review payload speak.

An ON_TRACK item below the completeness floor is still blocked from release, and that is not a
contradiction: the work is on schedule and the answer is not yet complete enough to send.

``RELEASED`` has no producer anywhere in this service. Release happens in the human-review
console, by a person, and an operator sends the production. That invariant is only worth
something because it has been watched fail: a planted mutant that returns ``RELEASED`` is run
against the guard, and ``docs/practices-audit.md`` records that it was observed failing first.

Pure stdlib: no ports, no I/O, no model, no clock.
"""

from __future__ import annotations

from collections.abc import Sequence

from .kernel import Decision, Severity
from .models import (
    SATISFIED_STATES,
    SEVERITY_RANK,
    WITHHELD_STATUSES,
    ArtefactCoverage,
    Blocker,
    BlockerKind,
    Disposition,
    EvidenceLink,
    EvidenceStatus,
    ExamPolicy,
    ItemAssessment,
    ReleaseState,
    SlaClock,
    worse,
)

__all__ = [
    "escalation",
    "item_disposition",
    "item_severity",
    "pack_blockers",
    "pack_completeness",
    "pack_disposition",
    "rank_blockers",
    "release_blockers",
    "required_approvals",
    "worst_severity",
]

#: Dispositions in escalation order, so "the worst item disposition" is a table lookup.
_DISPOSITION_RANK: dict[Disposition, int] = {
    Disposition.ON_TRACK: 0,
    Disposition.AT_RISK: 1,
    Disposition.BLOCKED: 2,
    Disposition.BREACH: 3,
}

_BLOCKING = frozenset({Severity.HIGH, Severity.CRITICAL})


def worst_severity(blockers: Sequence[Blocker]) -> Severity:
    """The worst blocker severity, LOW when there are none."""
    band = Severity.LOW
    for blocker in blockers:
        band = worse(band, blocker.severity)
    return band


def item_disposition(
    blockers: Sequence[Blocker], sla: SlaClock, links: Sequence[EvidenceLink]
) -> Disposition:
    """Rule S1. Breach beats blocked beats at risk, and nothing lowers a disposition."""
    if sla.breached:
        return Disposition.BREACH
    if any(blocker.severity in _BLOCKING for blocker in blockers):
        return Disposition.BLOCKED
    unsettled = any(
        link.status in WITHHELD_STATUSES or link.status is EvidenceStatus.STALE for link in links
    )
    if blockers or sla.band in _BLOCKING or unsettled:
        return Disposition.AT_RISK
    return Disposition.ON_TRACK


def item_severity(blockers: Sequence[Blocker], sla: SlaClock) -> Severity:
    """Rule S2. The worse of the worst blocker and the clock band, then one floor that only rises.

    A privilege hold floors the severity at HIGH, because a privilege call is a lawyer's decision
    and never a workflow's. No model output takes part in any of this, and there is no path that
    lowers a severity or clears the review flag.
    """
    band = worse(worst_severity(blockers), sla.band)
    if any(blocker.kind is BlockerKind.PRIVILEGE_HOLD for blocker in blockers):
        band = worse(band, Severity.HIGH)
    return band


def escalation(severity: Severity) -> tuple[bool, Decision]:
    """Rule S3. HIGH and CRITICAL escalate; everything else is allowed and still routes as a pack.

    An item that does not escalate is not unsupervised: its pack still routes. Manufacturing an
    exception for a clean item is how an exam lead is trained to approve without reading, and
    then the one that mattered goes out too.
    """
    escalate = severity in _BLOCKING
    return escalate, Decision.ESCALATED if escalate else Decision.ALLOWED


def release_blockers(
    blockers: Sequence[Blocker], completeness_pct: int, policy: ExamPolicy
) -> tuple[BlockerKind, ...]:
    """Rule R2. The named kinds a checker must clear, plus the completeness floor.

    Release is a SEPARATE question from disposition. An ON_TRACK item below the floor is still
    blocked from release, and the checker is handed rule names rather than a score.
    """
    seen: dict[BlockerKind, None] = {}
    for blocker in blockers:
        seen.setdefault(blocker.kind, None)
    if completeness_pct < policy.min_completeness_pct_for_release:
        seen.setdefault(BlockerKind.BELOW_MIN_COMPLETENESS, None)
    return tuple(seen)


def required_approvals(
    *, outcome_kind: str, instrument: str, severity: Severity, policy: ExamPolicy
) -> int:
    """Rule R3, and the ENGINE is the single owner of this number.

    Two approvals when the outcome kind demands dual control, when the instrument does, or when
    the severity is CRITICAL. ``adapters/_review_payload.py`` reads this off the outcome and has
    no approvals rule of its own; a contract test asserts it, because a shipped severity-keyed
    table and this rule disagree the first time an instrument-driven case appears at low
    severity, which is exactly the skilled-person case.
    """
    if outcome_kind in policy.dual_control_kinds:
        return 2
    if instrument in policy.dual_control_instruments:
        return 2
    if severity is Severity.CRITICAL:
        return 2
    return 1


def rank_blockers(blockers: Sequence[Blocker]) -> tuple[Blocker, ...]:
    """Worst first, then by requirement and kind, so two runs rank a pack identically."""
    return tuple(
        sorted(
            blockers,
            key=lambda blocker: (
                -SEVERITY_RANK[blocker.severity],
                blocker.requirement_id,
                blocker.kind.value,
            ),
        )
    )


def pack_disposition(items: Sequence[ItemAssessment]) -> Disposition:
    """Rule P1. The worst item disposition, and an empty pack is not on track by default."""
    if not items:
        return Disposition.BLOCKED
    return max((item.disposition for item in items), key=lambda d: _DISPOSITION_RANK[d])


def pack_completeness(items: Sequence[ItemAssessment]) -> int:
    """Rule P1. Integer mean of the item completeness values, never a float."""
    if not items:
        return 0
    return sum(item.completeness_pct for item in items) // len(items)


def pack_blockers(items: Sequence[ItemAssessment]) -> tuple[Blocker, ...]:
    """Rule P1. Every item blocker, worst first, then by item and kind."""
    collected: list[Blocker] = []
    for item in items:
        collected.extend(item.blockers)
    return rank_blockers(collected)


def coverage_is_satisfied(row: ArtefactCoverage) -> bool:
    """Whether one coverage row counts towards completeness (rule C3's numerator)."""
    return row.state in SATISFIED_STATES


#: Every outcome this service returns carries this state, and nothing here produces the other one.
HELD: ReleaseState = ReleaseState.HELD_FOR_CHECKER
