"""The deadline: signed business-day arithmetic, the due basis, and what may move a date.

A supervisor's first question is "on what date was this due, and why". Both halves have to be
answerable from the record years later, so every rule that sets a date is exercised here against
a fixed calendar rather than against today's.

The regime-cap rule (K3) gets its own tests because NO golden case exercises it: every shipped
register row fixes no response window, which is what an exam request list, an RFI, a thematic
review and a skilled-person scope all do in practice. The rule ships live so an adopter whose
counsel identifies a regime that DOES fix one configures it rather than patching code, and these
are the only thing holding it. ``DEMO.md`` says so rather than implying a golden case covers it.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from exam_rfi_orchestrator.domain.kernel import Severity
from exam_rfi_orchestrator.domain.models import BusinessCalendar, Instrument, RegimeRef
from exam_rfi_orchestrator.domain.policy import DEFAULT_POLICY
from exam_rfi_orchestrator.domain.sla_clock import (
    add_business_days,
    business_days_between,
    compute_clock,
    is_business_day,
    subtract_business_days,
)

from tests.fixtures import sample_cases

_CALENDAR = DEFAULT_POLICY.calendar_for("SG")
_AS_OF = sample_cases.AS_OF


def _clock(item_due: date | None = None, **request_overrides: object) -> object:
    request = sample_cases.request(**request_overrides)
    item = replace(sample_cases.ROUTINE_ITEM, item_due_on=item_due)
    return compute_clock(request, item, as_of=_AS_OF, policy=DEFAULT_POLICY)


# --------------------------------------------------------------------------------------- #
# The arithmetic
# --------------------------------------------------------------------------------------- #
def test_weekends_and_the_configured_holidays_are_not_business_days() -> None:
    assert is_business_day(date(2027, 3, 15), _CALENDAR)  # a Monday
    assert not is_business_day(date(2027, 3, 13), _CALENDAR)  # a Saturday
    assert not is_business_day(date(2027, 5, 1), _CALENDAR)  # a configured holiday


def test_business_day_arithmetic_skips_the_weekend() -> None:
    # Friday plus one business day is the following Monday.
    assert add_business_days(date(2027, 3, 12), 1, _CALENDAR) == date(2027, 3, 15)
    assert subtract_business_days(date(2027, 3, 15), 1, _CALENDAR) == date(2027, 3, 12)
    assert add_business_days(date(2027, 3, 15), 0, _CALENDAR) == date(2027, 3, 15)


def test_the_gap_between_two_dates_is_SIGNED() -> None:
    """A negative count is what makes "the buffer is already gone" a number, not a flag."""
    assert business_days_between(date(2027, 3, 15), date(2027, 3, 19), _CALENDAR) == 4
    assert business_days_between(date(2027, 3, 19), date(2027, 3, 15), _CALENDAR) == -4
    assert business_days_between(date(2027, 3, 15), date(2027, 3, 15), _CALENDAR) == 0


def test_a_holiday_lengthens_the_elapsed_calendar_time_but_not_the_business_count() -> None:
    """The whole reason the holiday list matters: a stale one shifts every internal due date."""
    # Thursday 5 August plus two business days. The Monday is a configured holiday, so the
    # answer is the Tuesday. Drop the holiday from the list and the answer moves a day EARLIER,
    # which is the unsafe direction and the reason calendar_version is pinned on every clock.
    assert add_business_days(date(2027, 8, 5), 2, _CALENDAR) == date(2027, 8, 10)
    without = BusinessCalendar(id="SG", version="stale", holidays=())
    assert add_business_days(date(2027, 8, 5), 2, without) == date(2027, 8, 9)


# --------------------------------------------------------------------------------------- #
# What sets the date (K1 to K4)
# --------------------------------------------------------------------------------------- #
def test_a_stated_item_date_wins_over_the_request_date_and_over_policy() -> None:
    clock = _clock(item_due=date(2027, 3, 19))
    assert clock.due_on == date(2027, 3, 19)  # type: ignore[attr-defined]
    assert clock.due_basis == "regulator_stated"  # type: ignore[attr-defined]


def test_with_no_stated_date_the_instrument_window_applies_on_the_calendar() -> None:
    clock = _clock(regulator_due_on=None)
    assert clock.due_basis == "policy_window:rfi"  # type: ignore[attr-defined]
    assert clock.due_on == add_business_days(  # type: ignore[attr-defined]
        date(2027, 3, 1), DEFAULT_POLICY.response_windows["rfi"], _CALENDAR
    )


def test_an_unconfigured_instrument_window_refuses_rather_than_guessing_a_deadline() -> None:
    policy = replace(DEFAULT_POLICY, response_windows={})
    request = sample_cases.request(regulator_due_on=None)
    with pytest.raises(ValueError, match="response_windows"):
        compute_clock(request, None, as_of=_AS_OF, policy=policy)


def test_the_internal_date_and_the_extension_by_date_come_off_the_regulator_date() -> None:
    clock = _clock(item_due=date(2027, 4, 30))
    assert clock.internal_due_on == subtract_business_days(  # type: ignore[attr-defined]
        date(2027, 4, 30), DEFAULT_POLICY.review_buffer_business_days, _CALENDAR
    )
    assert clock.extension_request_by == subtract_business_days(  # type: ignore[attr-defined]
        date(2027, 4, 30), DEFAULT_POLICY.extension_notice_business_days, _CALENDAR
    )


def test_breach_and_buffer_consumed_are_separate_recorded_facts() -> None:
    """A submission can be inside the regulator's date and already past the checker's."""
    inside_but_late = _clock(item_due=date(2027, 3, 19))
    assert inside_but_late.breached is False  # type: ignore[attr-defined]
    assert inside_but_late.buffer_consumed is True  # type: ignore[attr-defined]

    past = _clock(item_due=date(2027, 3, 10))
    assert past.breached is True  # type: ignore[attr-defined]
    assert past.buffer_consumed is True  # type: ignore[attr-defined]


def test_the_band_is_the_first_ceiling_the_remaining_days_fall_under() -> None:
    assert _clock(item_due=date(2027, 4, 30)).band is Severity.LOW  # type: ignore[attr-defined]
    assert _clock(item_due=date(2027, 3, 30)).band is Severity.MEDIUM  # type: ignore[attr-defined]
    assert _clock(item_due=date(2027, 3, 24)).band is Severity.HIGH  # type: ignore[attr-defined]
    assert _clock(item_due=date(2027, 3, 19)).band is Severity.CRITICAL  # type: ignore[attr-defined]


def test_an_extension_moves_the_date_only_when_the_STORE_resolved_it() -> None:
    request = sample_cases.request(regulator_due_on=None, extension_ref="EXT-FICTIONAL-2027-52")
    not_resolved = compute_clock(request, None, as_of=_AS_OF, policy=DEFAULT_POLICY)
    assert not_resolved.due_basis == "policy_window:rfi"
    assert not_resolved.original_due_on is None

    resolved = compute_clock(
        request, None, as_of=_AS_OF, policy=DEFAULT_POLICY, extension_on=date(2027, 6, 30)
    )
    assert resolved.due_on == date(2027, 6, 30)
    assert resolved.due_basis == "extension:EXT-FICTIONAL-2027-52"
    assert resolved.original_due_on == not_resolved.due_on, (
        "the pre-extension date must survive, or the record cannot show what moved"
    )


def test_a_resolved_extension_with_no_reference_on_the_request_moves_nothing() -> None:
    """Belt and braces: the reference is the key, so an answer with no key grants nothing."""
    request = sample_cases.request(regulator_due_on=None)
    clock = compute_clock(
        request, None, as_of=_AS_OF, policy=DEFAULT_POLICY, extension_on=date(2027, 6, 30)
    )
    assert clock.due_basis == "policy_window:rfi"


# --------------------------------------------------------------------------------------- #
# The regime cap (K3): shipped live, exercised by NOTHING but this file
# --------------------------------------------------------------------------------------- #
def _with_regime(**fields: object) -> object:
    row = RegimeRef(
        regime="capped-regime",
        title="A regime that fixes a window (FICTIONAL)",
        source="the adopter's own counsel",
        **fields,  # type: ignore[arg-type]
    )
    register = dict(DEFAULT_POLICY.regime_register)
    register["capped-regime"] = row
    return replace(DEFAULT_POLICY, regime_register=register)


def test_every_shipped_regime_row_fixes_no_response_window() -> None:
    """The claim the demo and the docs make, held to the wall rather than repeated in prose."""
    for row in DEFAULT_POLICY.regime_register.values():
        assert row.fixed_response_window_days == 0, (
            f"{row.regime} now fixes a window; the docs say no shipped row does, so one of the "
            "two has to move"
        )


def test_a_configured_regime_window_caps_a_later_stated_date() -> None:
    policy = _with_regime(fixed_response_window_days=5)
    request = sample_cases.request(regime="capped-regime", regulator_due_on=date(2027, 4, 30))
    clock = compute_clock(request, None, as_of=_AS_OF, policy=policy)  # type: ignore[arg-type]
    assert clock.due_on == add_business_days(date(2027, 3, 1), 5, _CALENDAR)
    assert clock.due_basis == "regime_cap:capped-regime"


def test_a_configured_regime_window_never_LENGTHENS_a_stated_date() -> None:
    policy = _with_regime(fixed_response_window_days=90)
    request = sample_cases.request(regime="capped-regime", regulator_due_on=date(2027, 3, 19))
    clock = compute_clock(request, None, as_of=_AS_OF, policy=policy)  # type: ignore[arg-type]
    assert clock.due_on == date(2027, 3, 19)
    assert clock.due_basis == "regulator_stated"


def test_a_calendar_clock_regime_counts_calendar_days_not_business_days() -> None:
    policy = _with_regime(fixed_response_window_days=5, calendar_clock=True)
    request = sample_cases.request(regime="capped-regime", regulator_due_on=date(2027, 4, 30))
    clock = compute_clock(request, None, as_of=_AS_OF, policy=policy)  # type: ignore[arg-type]
    assert clock.due_on == date(2027, 3, 6), "a calendar-day regime must not skip the weekend"


# --------------------------------------------------------------------------------------- #
# The calendar is PINNED on the clock
# --------------------------------------------------------------------------------------- #
def test_the_clock_records_the_calendar_it_computed_against() -> None:
    clock = _clock()
    assert clock.calendar_id == "SG"  # type: ignore[attr-defined]
    assert clock.calendar_version == _CALENDAR.version  # type: ignore[attr-defined]


def test_an_unconfigured_jurisdiction_says_so_on_the_clock_rather_than_looking_normal() -> None:
    """The fallback carries ``unconfigured``, not a plausible version string."""
    fallback = DEFAULT_POLICY.calendar_for("ZZ")
    assert isinstance(fallback, BusinessCalendar)
    assert fallback.version == "unconfigured"


def test_an_unknown_requesting_jurisdiction_permits_only_itself() -> None:
    """Fail-closed: an unconfigured matrix must not permit every transfer."""
    assert DEFAULT_POLICY.permitted_transfers("ZZ") == frozenset({"ZZ"})
    assert DEFAULT_POLICY.permitted_transfers("SG") == frozenset({"SG", "HK"})


def test_every_instrument_has_a_configured_response_window() -> None:
    """An instrument with no window makes a dateless notice unanswerable, so none may lack one."""
    for instrument in Instrument:
        assert instrument.value in DEFAULT_POLICY.response_windows
