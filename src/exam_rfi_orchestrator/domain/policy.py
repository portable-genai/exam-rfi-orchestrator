"""The adopter-owned policy block: shipped reference values, and the parser that reads them.

Every number an exam response turns on lives here or in the ``policy:`` section of
``config/settings.yaml``, never as a module constant inside an engine. That is the whole point:
a firm's second line can read these rules, argue about them and change them with a configuration
review and an audit trail, rather than with a release.

The parser is PURE STDLIB and takes a plain mapping, so the settings loader stays in
``config.py`` while the meaning of the block stays in the domain, where the tests that matter
can reach it with no file and no environment.

Every value below is REFERENCE policy. It is not legal advice, it is not current-in-law, and the
adopter's counsel owns it. The two that deserve an argument before deployment:

* ``min_completeness_pct_for_release`` ships at 100, which makes most real items unreleasable.
  That is the correct posture for a regulator submission and it is also exactly how an exam lead
  is trained to ignore the release state. It is configuration because an adopter will need to
  argue about it, and shipping the strictest value is a default to argue with rather than a
  recommendation.
* ``silent_withhold_tags`` ships with the suspicious-activity tag, so that row carries an
  identifier and a basis and no title. That asymmetry against the privilege row is a legal
  position, which is why it is configuration and not a constant.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from .kernel import Severity
from .models import BusinessCalendar, ExamPolicy, Instrument, RegimeRef, SensitivityTag

__all__ = ["DEFAULT_POLICY", "policy_from_mapping"]

#: Reference response windows in BUSINESS days, one per instrument, applied only when the notice
#: itself states no date (rule K2). A stated date is never lengthened by policy.
_RESPONSE_WINDOWS: dict[str, int] = {
    Instrument.EXAM_REQUEST_LIST.value: 20,
    Instrument.RFI.value: 15,
    Instrument.S166_SKILLED_PERSON.value: 30,
    Instrument.THEMATIC_REVIEW.value: 20,
    Instrument.INFORMATION_NOTICE.value: 10,
}

#: Reference holiday sets. A hand-maintained list is a real weakness: a missing public holiday
#: shifts every internal due date by a day, in the unsafe direction, and nothing in this repo can
#: detect a calendar that is merely out of date. ``version`` is what makes a recomputation years
#: later show WHICH list was used, and the runbook makes review a standing item.
_SG_HOLIDAYS: tuple[date, ...] = (
    date(2027, 1, 1),
    date(2027, 5, 1),
    date(2027, 8, 9),
    date(2027, 12, 25),
)
_HK_HOLIDAYS: tuple[date, ...] = (
    date(2027, 1, 1),
    date(2027, 5, 1),
    date(2027, 7, 1),
    date(2027, 12, 25),
)

_CALENDARS: dict[str, BusinessCalendar] = {
    "SG": BusinessCalendar(id="SG", version="2027.1", holidays=_SG_HOLIDAYS),
    "HK": BusinessCalendar(id="HK", version="2027.1", holidays=_HK_HOLIDAYS),
}

#: Where evidence may lawfully come FROM, keyed by the REQUESTING jurisdiction. An unknown
#: requester resolves to a set containing only itself (see ``ExamPolicy.permitted_transfers``).
_TRANSFER_MATRIX: dict[str, frozenset[str]] = {
    "SG": frozenset({"SG", "HK"}),
    "HK": frozenset({"HK", "SG"}),
    "JP": frozenset({"JP"}),
    "AU": frozenset({"AU"}),
}

#: The named-regime register. EVERY shipped row carries ``fixed_response_window_days = 0``,
#: meaning the regime fixes no response window and the notice's own date governs. The rule that
#: reads this (K3) ships live and unit-tested precisely so an adopter whose counsel identifies a
#: regime that DOES fix a window configures it here rather than patching code.
_REGIMES: dict[str, RegimeRef] = {
    "supervisory-information-request": RegimeRef(
        regime="supervisory-information-request",
        title="Supervisory request for information",
        source="the adopter's own supervisory handbook, cited by the notice",
        fixed_response_window_days=0,
        note="No fixed statutory window: the notice states its own date.",
    ),
    "skilled-person-review": RegimeRef(
        regime="skilled-person-review",
        title="Skilled person / independent expert review",
        source="the adopter's own supervisory handbook, cited by the notice",
        fixed_response_window_days=0,
        note="The scope document states the reporting dates; no fixed window applies.",
    ),
    "thematic-supervisory-review": RegimeRef(
        regime="thematic-supervisory-review",
        title="Thematic supervisory review",
        source="the adopter's own supervisory handbook, cited by the notice",
        fixed_response_window_days=0,
        note="No fixed statutory window: the letter states its own date.",
    ),
}

#: The shipped reference policy. A deployment overrides any part of it from the settings file.
DEFAULT_POLICY = ExamPolicy(
    response_windows=dict(_RESPONSE_WINDOWS),
    transfer_matrix=dict(_TRANSFER_MATRIX),
    calendars=dict(_CALENDARS),
    regime_register=dict(_REGIMES),
)


def _int(block: Mapping[str, Any], key: str, fallback: int) -> int:
    raw = block.get(key)
    return fallback if raw is None else int(raw)


def _bool(block: Mapping[str, Any], key: str, fallback: bool) -> bool:
    raw = block.get(key)
    return fallback if raw is None else bool(raw)


def _tags(raw: Any, fallback: tuple[SensitivityTag, ...]) -> tuple[SensitivityTag, ...]:
    if raw is None:
        return fallback
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ValueError("policy withhold tags must be a list of sensitivity tag values")
    return tuple(SensitivityTag(str(value)) for value in raw)


def _strings(raw: Any, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return fallback
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ValueError("policy expects a list of strings here")
    return tuple(str(value) for value in raw)


def _bands(
    raw: Any, fallback: tuple[tuple[int, Severity], ...]
) -> tuple[tuple[int, Severity], ...]:
    """Parse ``[{ceiling: 0, band: critical}, ...]`` into the ordered ceiling table.

    Order is preserved exactly as written, because the bands are checked in order and the first
    match wins. Sorting them here would silently reinterpret a file somebody wrote deliberately.
    """
    if raw is None:
        return fallback
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ValueError("policy 'sla_bands' must be a list of {ceiling, band} mappings")
    out: list[tuple[int, Severity]] = []
    for row in raw:
        if not isinstance(row, Mapping):
            raise ValueError("policy 'sla_bands' rows must be mappings with ceiling and band")
        out.append((int(row["ceiling"]), Severity(str(row["band"]))))
    if not out:
        raise ValueError(
            "policy 'sla_bands' is present but empty; a band table of nothing bands nothing"
        )
    return tuple(out)


def _windows(raw: Any, fallback: Mapping[str, int]) -> dict[str, int]:
    if raw is None:
        return dict(fallback)
    if not isinstance(raw, Mapping):
        raise ValueError("policy 'response_windows' must be a mapping of instrument to days")
    return {str(Instrument(str(key)).value): int(value) for key, value in raw.items()}


def _matrix(raw: Any, fallback: Mapping[str, frozenset[str]]) -> dict[str, frozenset[str]]:
    if raw is None:
        return dict(fallback)
    if not isinstance(raw, Mapping):
        raise ValueError("policy 'transfer_matrix' must be a mapping of jurisdiction to a list")
    return {str(key): frozenset(str(v) for v in value) for key, value in raw.items()}


def _calendars(raw: Any, fallback: Mapping[str, BusinessCalendar]) -> dict[str, BusinessCalendar]:
    if raw is None:
        return dict(fallback)
    if not isinstance(raw, Mapping):
        raise ValueError("policy 'calendars' must be a mapping of jurisdiction to a calendar")
    out: dict[str, BusinessCalendar] = {}
    for key, value in raw.items():
        if not isinstance(value, Mapping):
            raise ValueError(f"policy 'calendars.{key}' must be a mapping")
        version = str(value.get("calendar_version") or "").strip()
        if not version:
            raise ValueError(
                f"policy 'calendars.{key}' has no calendar_version. An unversioned holiday list "
                "cannot be pinned on a deadline, and a stale one shifts every internal due date "
                "silently and in the unsafe direction."
            )
        out[str(key)] = BusinessCalendar(
            id=str(key),
            version=version,
            weekend_days=tuple(int(d) for d in value.get("weekend_days") or (5, 6)),
            holidays=tuple(_as_date(d) for d in value.get("holidays") or ()),
        )
    return out


def _regimes(raw: Any, fallback: Mapping[str, RegimeRef]) -> dict[str, RegimeRef]:
    if raw is None:
        return dict(fallback)
    if not isinstance(raw, Mapping):
        raise ValueError("policy 'regime_register' must be a mapping of regime id to a row")
    out: dict[str, RegimeRef] = {}
    for key, value in raw.items():
        if not isinstance(value, Mapping):
            raise ValueError(f"policy 'regime_register.{key}' must be a mapping")
        out[str(key)] = RegimeRef(
            regime=str(key),
            title=str(value.get("title") or ""),
            source=str(value.get("source") or ""),
            fixed_response_window_days=int(value.get("fixed_response_window_days") or 0),
            calendar_clock=bool(value.get("calendar_clock") or False),
            note=str(value.get("note") or ""),
        )
    return out


def _as_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def policy_from_mapping(block: Mapping[str, Any] | None) -> ExamPolicy:
    """Build an :class:`ExamPolicy` from the settings file's ``policy:`` mapping.

    An absent block takes :data:`DEFAULT_POLICY` wholesale. A PRESENT block overrides only the
    keys it names, so an adopter who wants a different review buffer does not have to restate
    the holiday calendars to keep them.
    """
    if not block:
        return DEFAULT_POLICY
    return ExamPolicy(
        response_windows=_windows(block.get("response_windows"), DEFAULT_POLICY.response_windows),
        review_buffer_business_days=_int(
            block, "review_buffer_business_days", DEFAULT_POLICY.review_buffer_business_days
        ),
        extension_notice_business_days=_int(
            block, "extension_notice_business_days", DEFAULT_POLICY.extension_notice_business_days
        ),
        evidence_max_age_days=_int(
            block, "evidence_max_age_days", DEFAULT_POLICY.evidence_max_age_days
        ),
        sla_bands=_bands(block.get("sla_bands"), DEFAULT_POLICY.sla_bands),
        min_completeness_pct_for_release=_int(
            block,
            "min_completeness_pct_for_release",
            DEFAULT_POLICY.min_completeness_pct_for_release,
        ),
        max_evidence_per_requirement=_int(
            block, "max_evidence_per_requirement", DEFAULT_POLICY.max_evidence_per_requirement
        ),
        hard_withhold_tags=_tags(
            block.get("hard_withhold_tags"), DEFAULT_POLICY.hard_withhold_tags
        ),
        silent_withhold_tags=_tags(
            block.get("silent_withhold_tags"), DEFAULT_POLICY.silent_withhold_tags
        ),
        privilege_requires_waiver=_bool(
            block, "privilege_requires_waiver", DEFAULT_POLICY.privilege_requires_waiver
        ),
        transfer_matrix=_matrix(block.get("transfer_matrix"), DEFAULT_POLICY.transfer_matrix),
        calendars=_calendars(block.get("calendars"), DEFAULT_POLICY.calendars),
        regime_register=_regimes(block.get("regime_register"), DEFAULT_POLICY.regime_register),
        dual_control_instruments=_strings(
            block.get("dual_control_instruments"), DEFAULT_POLICY.dual_control_instruments
        ),
        dual_control_kinds=_strings(
            block.get("dual_control_kinds"), DEFAULT_POLICY.dual_control_kinds
        ),
    )
