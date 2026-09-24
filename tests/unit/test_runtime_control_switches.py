"""Review routing has a switch, default on, and every caller says what happened to a hand-off.

The fleet's runtime-control contract (2026-09-24). Review routing is the one cheap runtime
control this service has: ``EXAMRFI_REVIEW_ROUTING`` is read in three states; off binds a
disabled router and says so at startup; on under the managed profile refuses to boot without a
console; and the API (the pack and each escalated item), the agent tool and the CLI report
``review_routing`` rather than failing an already-assessed request when the console is
unreachable.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from exam_rfi_orchestrator.adapters.controls import (
    DisabledReviewRouter,
    RecordingReviewRouter,
    ReviewRouting,
)
from exam_rfi_orchestrator.agent import tools
from exam_rfi_orchestrator.cli.main import main as cli_main
from exam_rfi_orchestrator.config import (
    REVIEW_ROUTING_ENV,
    Container,
    ControlSwitches,
    ProfileChoice,
    Settings,
    build_container,
    warn_switched_off,
)
from exam_rfi_orchestrator.envread import ConfiguredEmptyError

from tests.conftest import LOOPBACK_PEER, local_settings, reimport
from tests.fixtures import sample_cases

_APPROVER = {"X-Dev-Persona": "approver"}
_LOCAL_ROUTE = "exam_rfi_orchestrator.adapters.local.review_router.LocalReviewRouter.route"
_ESCALATED: Any = SimpleNamespace(requires_human_review=True)
_CLEAN: Any = SimpleNamespace(requires_human_review=False)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(REVIEW_ROUTING_ENV, raising=False)
    monkeypatch.delenv("HUMAN_REVIEW_URL", raising=False)


def _client() -> TestClient:
    """A fresh local app, so its per-process container reads this test's posture."""
    return TestClient(reimport("exam_rfi_orchestrator.api.app").app, client=LOOPBACK_PEER)


def _managed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "exam_rfi_orchestrator.config.resolve_profile",
        lambda environ=None: ProfileChoice(profile="gcp", explicit=True),
    )


class _Accepting:
    def route(self, result: Any, *, maker: str, tenant: str = "") -> str:
        return "review-1"


class _Refusing:
    def route(self, result: Any, *, maker: str, tenant: str = "") -> str:
        raise ConnectionError("console unreachable")


# --------------------------------------------------------------------------- #
# Three states
# --------------------------------------------------------------------------- #
def test_routing_is_on_when_nothing_is_said() -> None:
    assert Settings.load().controls == ControlSwitches(review_routing=True)


def test_routing_switched_off_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "off")
    assert Settings.load().controls.switched_off() == (REVIEW_ROUTING_ENV,)


def test_an_emptied_switch_refuses_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "")
    with pytest.raises(ConfiguredEmptyError, match=REVIEW_ROUTING_ENV):
        Settings.load()


def test_an_unrecognised_switch_refuses_at_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "sometimes")
    with pytest.raises(ValueError, match=REVIEW_ROUTING_ENV):
        Settings.load()


# --------------------------------------------------------------------------- #
# Off binds the disabled router, and says so once
# --------------------------------------------------------------------------- #
def test_off_binds_the_disabled_router() -> None:
    settings = local_settings(controls=ControlSwitches(review_routing=False))
    assert isinstance(Container(settings).review_router, DisabledReviewRouter)


def test_on_binds_the_profile_router() -> None:
    assert not isinstance(Container(local_settings()).review_router, DisabledReviewRouter)


def test_the_off_posture_is_logged_once_however_many_containers(
    caplog: pytest.LogCaptureFixture,
) -> None:
    warn_switched_off.cache_clear()
    settings = local_settings(controls=ControlSwitches(review_routing=False))
    with caplog.at_level(logging.WARNING, logger="exam_rfi_orchestrator.config"):
        for _ in range(3):
            build_container(settings)
    assert caplog.text.count(REVIEW_ROUTING_ENV) == 1


# --------------------------------------------------------------------------- #
# On has to work: checked at boot under the managed profile
# --------------------------------------------------------------------------- #
def test_routing_on_under_gcp_without_a_console_refuses_at_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _managed(monkeypatch)
    with pytest.raises(ConfiguredEmptyError, match="HUMAN_REVIEW_URL"):
        Settings.load()


def test_routing_stated_off_under_gcp_needs_no_console(monkeypatch: pytest.MonkeyPatch) -> None:
    _managed(monkeypatch)
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "false")
    assert Settings.load().controls.review_routing is False


def test_routing_on_under_gcp_with_a_console_loads(monkeypatch: pytest.MonkeyPatch) -> None:
    _managed(monkeypatch)
    monkeypatch.setenv("HUMAN_REVIEW_URL", "https://review.example.test")
    assert Settings.load().review_url == "https://review.example.test"


# --------------------------------------------------------------------------- #
# The four routing outcomes
# --------------------------------------------------------------------------- #
def test_routing_outcomes_take_each_of_their_four_values() -> None:
    unrequired = RecordingReviewRouter(_Accepting())
    assert unrequired.route(_CLEAN, maker="m") == ""
    assert unrequired.outcome is ReviewRouting.NOT_REQUIRED

    routed = RecordingReviewRouter(_Accepting())
    assert routed.route(_ESCALATED, maker="m") == "review-1"
    assert routed.outcome is ReviewRouting.ROUTED

    off = RecordingReviewRouter(DisabledReviewRouter(local_settings()))
    assert off.route(_ESCALATED, maker="m") == ""
    assert off.outcome is ReviewRouting.OFF

    failed = RecordingReviewRouter(_Refusing())
    assert failed.route(_ESCALATED, maker="m") == ""
    assert failed.outcome is ReviewRouting.FAILED


def test_a_failed_hand_off_is_reported_and_logged_never_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    failed = RecordingReviewRouter(_Refusing())
    with caplog.at_level(logging.WARNING, logger="exam_rfi_orchestrator.adapters.controls"):
        assert failed.route(_ESCALATED, maker="m") == ""
    assert failed.outcome is ReviewRouting.FAILED
    assert "ConnectionError" in caplog.text


# --------------------------------------------------------------------------- #
# Every caller reports it: the API, the agent tool, the CLI
# --------------------------------------------------------------------------- #
def _pack(client: TestClient) -> Any:
    body = sample_cases.wire_body(sample_cases.ROUTINE_ITEM, sample_cases.ESCALATING_ITEM)
    return client.post("/v1/response-pack", json=body, headers=_APPROVER)


def _items(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["item_ref"]: item for item in body["items"]}


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with _client() as c:
        yield c


def test_the_api_reports_the_pack_and_each_item(client: TestClient) -> None:
    body = _pack(client).json()
    assert body["review_routing"] == "routed"
    assert body["review_ref"]
    items = _items(body)
    escalated = items[sample_cases.ESCALATING_ITEM.item_ref]
    assert escalated["requires_human_review"] is True
    assert escalated["review_routing"] == "routed"
    routine = items[sample_cases.ROUTINE_ITEM.item_ref]
    assert routine["requires_human_review"] is False
    assert routine["review_routing"] == "not_required"


def test_the_api_reports_routing_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(REVIEW_ROUTING_ENV, "off")
    with _client() as client:
        body = _pack(client).json()
    assert body["review_routing"] == "off"
    assert body["review_ref"] == ""
    assert _items(body)[sample_cases.ESCALATING_ITEM.item_ref]["review_routing"] == "off"


def test_the_api_reports_a_failed_hand_off_instead_of_failing_the_request(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.setattr(_LOCAL_ROUTE, _Refusing.route)
    response = _pack(client)
    assert response.status_code == 200
    assert response.json()["review_routing"] == "failed"
    assert response.json()["review_ref"] == ""
    escalated = _items(response.json())[sample_cases.ESCALATING_ITEM.item_ref]
    assert escalated["review_routing"] == "failed"


def _tool() -> dict[str, Any]:
    request = sample_cases.REQUEST
    item = sample_cases.ROUTINE_ITEM
    return tools.assess_request_item(
        request_id=request.request_id,
        reference=request.reference,
        regulator=request.regulator,
        instrument=request.instrument.value,
        regime=request.regime,
        jurisdiction=request.jurisdiction,
        received_on=request.received_on.isoformat(),
        period_start=request.period_start.isoformat(),
        period_end=request.period_end.isoformat(),
        regulator_due_on=(request.regulator_due_on.isoformat() if request.regulator_due_on else ""),
        as_of=sample_cases.AS_OF.isoformat(),
        item_ref=item.item_ref,
        question=item.question,
        topic=item.topic.value,
        owner=item.owner,
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        settings=local_settings(),
    )


def test_the_agent_tool_reports_the_hand_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # The tool asserts no entitlements, so the item is blocked and escalates (see the agent
    # surface tests): the routed path is the one under test.
    assert _tool()["review_routing"] == "routed"

    monkeypatch.setattr(_LOCAL_ROUTE, _Refusing.route)
    failed = _tool()
    assert failed["review_routing"] == "failed"
    assert failed["review_ref"] == ""


def test_the_cli_reports_the_hand_off(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    request_file = tmp_path / "request.json"
    body = sample_cases.wire_body(sample_cases.ROUTINE_ITEM, sample_cases.ESCALATING_ITEM)
    request_file.write_text(json.dumps(body, default=str), encoding="utf-8")
    args = ["respond", str(request_file), "--persona", "approver"]

    assert cli_main(args) == 0
    out = capsys.readouterr().out
    assert "human review hand-off : routed" in out
    assert "approval hand-off: routed" in out

    monkeypatch.setattr(_LOCAL_ROUTE, _Refusing.route)
    assert cli_main(args) == 0
    out = capsys.readouterr().out
    assert "human review hand-off : failed" in out
    assert "approval hand-off: failed" in out
