"""The service half of the model pills: which model ANSWERED, and whether it searched.

The console shows two pills at the top right: the model that answered the last request, and
``Search`` when that answer used an online search tool. Both come from response headers the kit
emits (``install_answer_provenance`` in ``api/app.py``) for whatever the generation adapters
NOTED as they called. Before a request is answered the pill shows ``generator_model`` from
``/healthz``, so that value must be the model the bound adapter calls.

Sampling is per call site: drafting the narrative is FREE (no temperature sent at all, because
some models reject the parameter), while classification and normalisation are PINNED at 0.0
because their output is compared against closed vocabularies and the engine's own facts.
"""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from hex_service_kit import provenance

from exam_rfi_orchestrator.adapters.gcp.generation import CloudGenerationAdapter
from exam_rfi_orchestrator.adapters.local.generation import LocalGenerationAdapter
from exam_rfi_orchestrator.config import Settings
from exam_rfi_orchestrator.domain import narration
from exam_rfi_orchestrator.ports.generation import GenerationRequest, GenerationResponse

from tests import REPO_ROOT
from tests.fixtures import sample_cases

ANSWERED_BY = "x-answered-by"
SEARCH_USED = "x-search-used"
STUB_MODEL = "deterministic-offline-stub"


@pytest.fixture(autouse=True)
def _local_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """CI targets run with no profile exported; this suite states the one it proves."""
    monkeypatch.setenv("EXAMRFI_PROFILE", "local")


def _pack(api_client: TestClient) -> dict[str, str]:
    response = api_client.post(
        "/v1/response-pack",
        json=sample_cases.wire_body(sample_cases.ROUTINE_ITEM),
        headers={"X-Dev-Persona": "approver"},
    )
    assert response.status_code == 200, response.text
    return dict(response.headers)


def test_the_local_stub_answers_as_the_model_the_pill_already_names(
    api_client: TestClient,
) -> None:
    headers = _pack(api_client)
    assert headers[ANSWERED_BY] == STUB_MODEL
    assert headers[ANSWERED_BY] == api_client.get("/healthz").json()["generator_model"]
    assert SEARCH_USED not in headers, "no search tool is attached to any call here"


def test_a_call_that_searched_says_so_and_the_next_request_starts_fresh(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = LocalGenerationAdapter.generate

    def searching(self: LocalGenerationAdapter, request: GenerationRequest) -> GenerationResponse:
        provenance.note_search()
        return original(self, request)

    monkeypatch.setattr(LocalGenerationAdapter, "generate", searching)
    headers = _pack(api_client)
    assert headers[SEARCH_USED] == "true"
    assert headers[ANSWERED_BY] == STUB_MODEL
    monkeypatch.setattr(LocalGenerationAdapter, "generate", original)
    assert SEARCH_USED not in _pack(api_client)


def test_a_request_that_called_no_model_names_none(api_client: TestClient) -> None:
    response = api_client.get("/healthz")
    assert ANSWERED_BY not in response.headers
    assert SEARCH_USED not in response.headers


# --------------------------------------------------------------------------------------- #
# Sampling per call site, and the managed adapter through a fake SDK.
# --------------------------------------------------------------------------------------- #
def _narrative_request() -> GenerationRequest:
    return narration.build_narrative_request(
        item_ref="RFI-1",
        question="Provide the board minutes.",
        completeness_pct=50,
        satisfied=1,
        total=2,
        business_days_remaining=4,
        exhibits=(),
    )


def test_drafting_is_free_and_classification_and_normalisation_are_pinned() -> None:
    assert _narrative_request().temperature is None
    assert narration.build_classify_request("RFI-1", "board minutes").temperature == 0.0
    assert narration.build_normalise_request("RFI-1", (), ("key",)).temperature == 0.0


class _FakeModels:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(text='{"narrative": "drafted"}')


def _fake_genai(monkeypatch: pytest.MonkeyPatch) -> _FakeModels:
    models = _FakeModels()
    genai = types.ModuleType("google.genai")
    genai_types = types.ModuleType("google.genai.types")
    genai_types.GenerateContentConfig = lambda **kw: SimpleNamespace(**kw)  # type: ignore[attr-defined]
    genai.types = genai_types  # type: ignore[attr-defined]
    genai.Client = lambda **_: SimpleNamespace(models=models)  # type: ignore[attr-defined]
    google = sys.modules.get("google") or types.ModuleType("google")
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setattr(google, "genai", genai, raising=False)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", genai_types)
    return models


def _gcp_settings() -> Settings:
    return Settings(profile="gcp", generation_model="gemini-test-model")


def test_the_managed_adapter_notes_its_model_and_drafts_with_no_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = _fake_genai(monkeypatch)
    settings = _gcp_settings()
    with provenance.scope() as record:
        CloudGenerationAdapter(settings).generate(_narrative_request())
    assert record.models == ["gemini-test-model"]
    assert record.search_used is False
    (call,) = models.calls
    assert call["model"] == "gemini-test-model"
    assert not hasattr(call["config"], "temperature"), "drafting sends no temperature"


def test_a_pinned_request_reaches_the_managed_config(monkeypatch: pytest.MonkeyPatch) -> None:
    models = _fake_genai(monkeypatch)
    CloudGenerationAdapter(_gcp_settings()).generate(
        narration.build_classify_request("RFI-1", "board minutes")
    )
    assert models.calls[0]["config"].temperature == 0.0


def test_generator_model_is_the_model_the_managed_adapter_calls() -> None:
    assert _gcp_settings().generator_model == "gemini-test-model"


def test_the_hard_reasoning_flag_does_not_exist() -> None:
    settings_file = (REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    assert "use_hard_reasoning" not in settings_file
    for source in sorted((REPO_ROOT / "src").rglob("*.py")):
        assert "use_hard_reasoning" not in source.read_text(encoding="utf-8"), source
