"""The deadline: signed business-day arithmetic on a named, versioned calendar (rules K1 to K5).

A supervisor asks "on what date was this due, and why". Both halves have to be answerable from
the record years later, on a machine with no model and no network, so the whole of this module is
stdlib arithmetic over inputs that were recorded: the calendar and its version, the received
date, any stated date, the named regime and any extension the case store resolved.

Two facts that are never merged. ``breached`` means the regulator's own date has passed.
``buffer_consumed`` means the internal maker-checker date has passed. A submission can be inside
the regulator's date and already past the point where a checker could realistically read it, and
an exam lead needs to see that as its own fact rather than infer it.

Pure stdlib: no ports, no I/O, no model, and NO CLOCK. ``as_of`` is passed in, which is what
makes a submission replayable.
"""

from __future__ import annotations

from datetime import date, timedelta

from .kernel import Severity
from .models import (
    BusinessCalendar,
    ExamPolicy,
    Instrument,
    RegulatorRequest,
    RequestItem,
    SlaClock,
)

__all__ = [
    "add_business_days",
    "business_days_between",
    "compute_clock",
    "is_business_day",
    "subtract_business_days",
]


def is_business_day(day: date, calendar: BusinessCalendar) -> bool:
    """True when ``day`` is neither a weekend day nor a holiday on this calendar."""
    return day.weekday() not in calendar.weekend_days and day not in calendar.holidays


def add_business_days(start: date, count: int, calendar: BusinessCalendar) -> date:
    """``count`` business days after ``start`` (0 returns ``start`` untouched)."""
    if count < 0:
        return subtract_business_days(start, -count, calendar)
    current = start
    remaining = count
    while remaining > 0:
        current += timedelta(days=1)
        if is_business_day(current, calendar):
            remaining -= 1
    return current


def subtract_business_days(start: date, count: int, calendar: BusinessCalendar) -> date:
    """``count`` business days before ``start`` (0 returns ``start`` untouched)."""
    current = start
    remaining = max(0, count)
    while remaining > 0:
        current -= timedelta(days=1)
        if is_business_day(current, calendar):
            remaining -= 1
    return current


def business_days_between(start: date, end: date, calendar: BusinessCalendar) -> int:
    """SIGNED business days from ``start`` to ``end``, counting the end and not the start.

    Negative when ``end`` is in the past, which is what makes "the buffer is already gone" a
    number rather than a flag somebody has to remember to set.
    """
    if end == start:
        return 0
    step = 1 if end > start else -1
    current = start
    counted = 0
    while current != end:
        current += timedelta(days=step)
        if is_business_day(current, calendar):
            counted += 1
    return counted * step


def _band(remaining: int, policy: ExamPolicy) -> Severity:
    """The first band whose CEILING the remaining business days fall at or under, else LOW."""
    for ceiling, band in policy.sla_bands:
        if remaining <= ceiling:
            return band
    return Severity.LOW


def _stated_due(request: RegulatorRequest, item: RequestItem | None) -> date | None:
    if item is not None and item.item_due_on is not None:
        return item.item_due_on
    return request.regulator_due_on


def compute_clock(
    request: RegulatorRequest,
    item: RequestItem | None,
    *,
    as_of: date,
    policy: ExamPolicy,
    extension_on: date | None = None,
) -> SlaClock:
    """Compute the deadline for one item, or for the request when ``item`` is ``None``.

    * **K1 STATED DATE**: an item date, else the request date, with basis ``regulator_stated``.
      A stated date is never lengthened by policy.
    * **K2 POLICY WINDOW**: with no stated date, ``received_on`` plus the instrument's window in
      business days on the jurisdiction calendar, basis ``policy_window:<instrument>``.
    * **K3 REGIME CAP**: when the named regime fixes a window, take the earlier of the two and
      record ``regime_cap:<regime>``. Every shipped register row fixes no window, so this rule
      is held by unit tests rather than by a golden case, and the documentation says so.
    * **K4 EXTENSION**: the date moves only when the CASE STORE resolved the reference for this
      tenant. ``original_due_on`` retains the pre-extension date and the basis becomes
      ``extension:<ref>``. An extension is never inferred, granted or requested here.
    * **K5 INTERNAL CLOCK AND BANDS**: the internal date is the regulator date less the review
      buffer, the extension-by date is it less the notice period, and the band is the first
      ceiling the remaining business days fall under.
    """
    calendar = policy.calendar_for(request.jurisdiction)
    regime = policy.regime_register.get(request.regime)
    regime_source = regime.source if regime is not None else ""

    stated = _stated_due(request, item)
    if stated is not None:
        due_on = stated
        due_basis = "regulator_stated"
    else:
        window = policy.response_windows.get(request.instrument.value)
        if window is None:
            raise ValueError(
                f"no response window configured for instrument {request.instrument.value!r} and "
                "the notice stated no date; configure policy.response_windows rather than "
                "letting a deadline be guessed"
            )
        due_on = add_business_days(request.received_on, window, calendar)
        due_basis = f"policy_window:{request.instrument.value}"

    if regime is not None and regime.fixed_response_window_days > 0:
        capped = _regime_due(
            request, regime.fixed_response_window_days, regime.calendar_clock, calendar
        )
        if capped < due_on:
            due_on = capped
            due_basis = f"regime_cap:{regime.regime}"

    original_due_on: date | None = None
    if extension_on is not None and request.extension_ref:
        original_due_on = due_on
        due_on = extension_on
        due_basis = f"extension:{request.extension_ref}"

    internal_due_on = subtract_business_days(due_on, policy.review_buffer_business_days, calendar)
    extension_request_by = subtract_business_days(
        due_on, policy.extension_notice_business_days, calendar
    )
    remaining = business_days_between(as_of, internal_due_on, calendar)
    return SlaClock(
        due_on=due_on,
        internal_due_on=internal_due_on,
        due_basis=due_basis,
        extension_request_by=extension_request_by,
        business_days_remaining=remaining,
        band=_band(remaining, policy),
        breached=as_of > due_on,
        buffer_consumed=remaining < 0,
        calendar_id=calendar.id,
        calendar_version=calendar.version,
        regime_source=regime_source,
        original_due_on=original_due_on,
    )


def _regime_due(
    request: RegulatorRequest, window: int, calendar_clock: bool, calendar: BusinessCalendar
) -> date:
    """The date a fixed-window regime sets, on calendar days or business days as it declares."""
    if calendar_clock:
        return request.received_on + timedelta(days=window)
    return add_business_days(request.received_on, window, calendar)


#: Named here so a caller can reason about the instrument set without importing the enum twice.
INSTRUMENTS: tuple[str, ...] = tuple(instrument.value for instrument in Instrument)
