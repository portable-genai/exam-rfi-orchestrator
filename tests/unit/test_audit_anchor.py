"""The external head anchor is WIRED, so a truncated audit trail is detectable (check C9).

The runbook has always told the operator to keep an anchor on a different volume. That is only
advice unless the service can actually be configured to write one, so this suite proves the
whole path: ``config/settings.yaml`` -> ``Settings.audit_anchor_path`` -> the commons audit log.

Why it matters, precisely: the hash chain detects an in-place edit, an interior deletion and a
reorder, because each of those breaks a link. It CANNOT detect a truncated tail, because
dropping the newest rows leaves a shorter chain that verifies perfectly. The tests below assert
both halves of that: with an anchor the truncation is caught, and without one the same
truncation passes unnoticed. The second assertion is the point. It is what stops the anchor from
being quietly dropped later by someone who reads the first test as "the chain catches tampering".
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hex_service_kit.audit import AuditChainError

from exam_rfi_orchestrator.adapters.local.audit import (
    LocalAuditAdapter,
)
from exam_rfi_orchestrator.adapters.local.tracer import (
    LocalNoopTracerAdapter,
)
from exam_rfi_orchestrator.config import (
    Settings,
    _read_settings_file,
    build_container,
)
from exam_rfi_orchestrator.domain.response_pack_service import (
    ResponsePackService,
)

from tests.fixtures import sample_cases

#: These tests are about the audit chain, not about tracing, so the service gets the offline
#: no-op rather than a mock nobody would assert on.
_NOOP_TRACER = LocalNoopTracerAdapter(Settings(profile="local"))

_ANCHOR_ENV = "EXAMRFI_AUDIT_ANCHOR"


def _durable_settings(tmp_path: Path, *, anchored: bool) -> Settings:
    """A durable store, with the anchor deliberately on a DIFFERENT directory tree."""
    store = tmp_path / "store" / "audit.sqlite3"
    anchor = tmp_path / "witness" / "audit-head.anchor"
    anchor.parent.mkdir(parents=True, exist_ok=True)
    return Settings(
        profile="local",
        audit_path=str(store),
        audit_anchor_path=str(anchor) if anchored else "",
    )


def _service(settings: Settings, audit: LocalAuditAdapter) -> ResponsePackService:
    container = build_container(settings)
    return ResponsePackService(
        audit,
        _NOOP_TRACER,
        knowledge_base=container.knowledge_base,
        obligations=container.obligations,
        evidence_packs=container.evidence_packs,
        generation=container.generation,
        case_store=container.case_store,
        policy=container.settings.policy,
    )


def _assess(service: ResponsePackService, item: object) -> None:
    service.assess_item(
        sample_cases.REQUEST,
        item,  # type: ignore[arg-type]
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        as_of=sample_cases.AS_OF,
    )


def _record_three(settings: Settings) -> LocalAuditAdapter:
    """Drive the REAL service path, so what gets anchored is what the service writes."""
    container = build_container(settings)
    audit = container.audit
    assert isinstance(audit, LocalAuditAdapter)
    service = _service(settings, audit)
    for item in (
        sample_cases.ESCALATING_ITEM,
        sample_cases.ROUTINE_ITEM,
        sample_cases.PII_ITEM,
    ):
        _assess(service, item)
    return audit


def _truncate_tail(audit: LocalAuditAdapter) -> None:
    """Drop the newest row the way an attacker with file access would: triggers first."""
    conn = audit.log._conn
    conn.execute("DROP TRIGGER audit_log_no_delete")
    conn.execute("DELETE FROM audit_log WHERE seq = (SELECT MAX(seq) FROM audit_log)")
    conn.commit()


def test_the_configured_anchor_is_actually_written(tmp_path: Path) -> None:
    settings = _durable_settings(tmp_path, anchored=True)
    audit = _record_three(settings)
    anchor = Path(settings.audit_anchor_path)
    assert anchor.is_file(), "no anchor file was written, so nothing witnesses the chain head"
    assert audit.verify().ok


def test_a_truncated_tail_is_detected_because_of_the_anchor(tmp_path: Path) -> None:
    audit = _record_three(_durable_settings(tmp_path, anchored=True))
    assert audit.verify().ok

    _truncate_tail(audit)

    report = audit.verify()
    assert not report.ok, "a truncated audit trail was reported as intact"
    assert "anchor" in report.detail


def test_without_the_anchor_the_same_truncation_is_invisible(tmp_path: Path) -> None:
    """The control case: this is exactly what the wiring buys, so it must be shown to fail."""
    audit = _record_three(_durable_settings(tmp_path, anchored=False))
    _truncate_tail(audit)
    report = audit.verify()
    assert report.ok, (
        "the unanchored chain now detects truncation on its own; if the commons gained that "
        "ability, revisit this suite rather than deleting the anchor wiring"
    )


def test_an_append_after_truncation_cannot_relaunder_the_anchor(tmp_path: Path) -> None:
    """Fail closed: one ordinary append must not re-anchor the store as it now stands."""
    settings = _durable_settings(tmp_path, anchored=True)
    audit = _record_three(settings)
    anchored_before = Path(settings.audit_anchor_path).read_text(encoding="utf-8")

    _truncate_tail(audit)

    with pytest.raises(AuditChainError):
        _assess(_service(settings, audit), sample_cases.ESCALATING_ITEM)
    assert Path(settings.audit_anchor_path).read_text(encoding="utf-8") == anchored_before


def test_the_anchor_path_comes_from_the_settings_file_three_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unset means no anchor; a set value wins; set-and-empty names nothing, as everywhere."""
    path = tmp_path / "settings.yaml"
    # Built by concatenation, not an f-string: a literal brace pair in a templated file is a
    # template opener, and this file is rendered before it is ever run.
    path.write_text("audit_anchor_path: ${" + _ANCHOR_ENV + ":-}\n", encoding="utf-8")

    monkeypatch.delenv(_ANCHOR_ENV, raising=False)
    assert _read_settings_file(path)["audit_anchor_path"] == ""

    monkeypatch.setenv(_ANCHOR_ENV, str(tmp_path / "elsewhere.anchor"))
    loaded = _read_settings_file(path)
    assert loaded["audit_anchor_path"] == str(tmp_path / "elsewhere.anchor")
    assert Settings.load(path).audit_anchor_path == str(tmp_path / "elsewhere.anchor")


def test_the_shipped_settings_file_exposes_the_anchor_as_an_operator_knob() -> None:
    """A field nobody can set from configuration is a field nobody will set."""
    from tests import REPO_ROOT

    text = (REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "audit_anchor_path:" in text
    assert _ANCHOR_ENV in text
