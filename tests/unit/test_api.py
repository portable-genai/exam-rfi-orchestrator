"""API surface: verified-principal identity, derived authority, fail-closed S2S, headers.

The client comes from the shared ``api_client`` fixture, which pins a loopback peer: the
app-object exposure guard refuses the unauthenticated local posture to any other peer, and
TestClient's default peer is the literal host "testclient".

The vertical-specific half of this file is the DERIVATION: entitlements, tenant, transfer scope,
approval count, release state, waivers and extensions are all decided server-side, and a request
body that tried to carry any of them changes nothing. That is asserted by sending them and
checking they had no effect, because a schema that silently ignores a field and one that honours
it look identical until somebody sends it.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.fixtures import sample_cases

_TOKEN_ENV = "EXAMRFI_S2S_TOKEN"


def _post(client: TestClient, body: dict[str, object], persona: str = "approver") -> object:
    return client.post("/v1/response-pack", json=body, headers={"X-Dev-Persona": persona})


def test_the_pack_uses_the_verified_principal_and_always_routes(api_client: TestClient) -> None:
    resp = _post(api_client, sample_cases.wire_body(sample_cases.ROUTINE_ITEM))
    assert resp.status_code == 200
    body = resp.json()
    # Rule P2: a pack routes even when every item in it is clean.
    assert body["disposition"] == "on_track"
    assert body["requires_human_review"] is True
    assert body["review_ref"]
    assert body["required_approvals"] == 2
    assert body["release_state"] == "held_for_checker"
    assert body["as_of"] == sample_cases.AS_OF.isoformat(), "the resolved date must be echoed"


def test_the_item_carries_its_coverage_index_and_clock(api_client: TestClient) -> None:
    body = _post(api_client, sample_cases.wire_body(sample_cases.ROUTINE_ITEM)).json()
    item = body["items"][0]
    assert item["completeness_pct"] == 100
    assert item["satisfied_mandatory"] == item["total_mandatory"]
    assert {row["state"] for row in item["coverage"]} == {"covered"}
    assert item["exhibits"], "a fully evidenced item must index its exhibits"
    assert item["sla"]["due_basis"] == "regulator_stated"
    assert item["sla"]["calendar_version"], (
        "a deadline nobody can trace to a calendar is not evidence"
    )
    assert item["release_state"] == "held_for_checker"


def test_a_withheld_document_is_scheduled_and_never_indexed(api_client: TestClient) -> None:
    body = _post(api_client, sample_cases.wire_body(sample_cases.PII_ITEM)).json()
    schedule = body["withholding_schedule"]
    assert schedule, "the withholding schedule must carry every non-produced document"
    indexed = {row["doc_id"] for row in body["document_index"]}
    assert not indexed & {row["doc_id"] for row in schedule}
    silent = [row for row in schedule if row["status"] == "withheld_sar"]
    assert silent and all(not row["title"] for row in silent), (
        "a silent-withhold row must carry an identifier and a basis and no title"
    )
    assert sample_cases.PLANTED_NRIC not in resp_text(body)


def resp_text(body: object) -> str:
    import json

    return json.dumps(body, sort_keys=True)


def test_a_request_body_cannot_widen_authority(api_client: TestClient) -> None:
    """The schema ignores what it does not declare, and this proves the ignoring is real.

    Every field below would, if honoured, let a caller read what they are not entitled to,
    unlock a privileged document, move a regulatory deadline or lower the approval bar.
    """
    body = dict(sample_cases.wire_body(sample_cases.PII_ITEM))
    body.update(
        {
            "actor": "ghost@attacker.example",
            "tenant": "other-bank",
            "entitlements": ["group:approver", "group:everything"],
            "permitted_transfer_jurisdictions": ["JP"],
            "required_approvals": 1,
            "release_state": "released",
        }
    )
    answer = _post(api_client, body).json()
    assert answer["release_state"] == "held_for_checker"
    assert answer["required_approvals"] == 2
    schedule = {row["status"] for row in answer["withholding_schedule"]}
    assert "withheld_restricted_transfer" in schedule, (
        "a client-asserted transfer scope moved a document across a border"
    )


def test_an_unresolvable_waiver_reference_unlocks_nothing(api_client: TestClient) -> None:
    """A reference is a LOOKUP KEY. One that resolves to nothing leaves the document withheld."""
    body = dict(sample_cases.wire_body(sample_cases.PII_ITEM))
    body["waiver_ref"] = "WVR-DOES-NOT-EXIST"
    answer = _post(api_client, body).json()
    statuses = {row["status"] for row in answer["withholding_schedule"]}
    assert "withheld_privileged" in statuses


def test_an_unknown_instrument_regime_or_jurisdiction_is_422(api_client: TestClient) -> None:
    """Never a silent default: a guessed instrument picks a window, a guessed calendar a clock."""
    for field, value in (
        ("instrument", "made_up"),
        ("regime", "not-in-the-register"),
        ("jurisdiction", "ZZ"),
    ):
        body = dict(sample_cases.wire_body())
        body[field] = value
        resp = _post(api_client, body)
        assert resp.status_code == 422, f"{field} was accepted"
        assert field in resp.json()["detail"]


def test_an_empty_item_list_is_refused(api_client: TestClient) -> None:
    body = dict(sample_cases.wire_body())
    body["items"] = []
    assert _post(api_client, body).status_code == 422


def test_an_item_with_no_topic_is_refused_with_the_classifier_named_not_acted_on(
    api_client: TestClient,
) -> None:
    """The model may SUGGEST a topic and may not choose one.

    The topic is the retrieval key and rule A2's responsiveness filter, so a wrong one drops
    every document the firm holds for that question and the pack states that no admissible
    document of the class was produced. This is the falsification: the classifier here DOES have
    an answer (the offline stub classifies this question as ``aml_financial_crime``), the answer
    is named in the refusal so a person can act on it, and the request is refused anyway.
    """
    body = dict(sample_cases.wire_body())
    items = [dict(item) for item in body["items"]]  # type: ignore[arg-type]
    items[0]["topic"] = ""
    body["items"] = items
    answer = _post(api_client, body)
    assert answer.status_code == 422
    detail = answer.json()["detail"]
    assert "items[].topic" in detail
    assert "aml_financial_crime" in detail, "the suggestion a person would act on is not offered"


def test_an_unknown_artefact_class_or_prior_answer_topic_is_422_and_never_a_500(
    api_client: TestClient,
) -> None:
    """Every caller-supplied taxonomy value is validated, including the ones inside the lists.

    A member constructed straight from the wire raises ``ValueError``, which reaches the caller
    as a 500 and the operator as a stack trace. A typo is a caller error, and it is named.
    """
    artefacts = dict(sample_cases.wire_body())
    items = [dict(item) for item in artefacts["items"]]  # type: ignore[arg-type]
    items[0]["requested_artefacts"] = ["not_a_real_artefact"]
    artefacts["items"] = items
    resp = _post(api_client, artefacts)
    assert resp.status_code == 422
    assert "items[].requested_artefacts" in resp.json()["detail"]

    priors = dict(sample_cases.wire_body())
    priors["prior_answers"] = [
        {
            "answer_id": "PRIOR-FICTIONAL-2026-08",
            "submitted_on": "2026-08-14",
            "item_ref": "1.a",
            "topic": "not_a_real_topic",
            "assertion_key": "sanctions_screening_vendor",
            "assertion_value": "Northwind Screening (FICTIONAL)",
        }
    ]
    resp = _post(api_client, priors)
    assert resp.status_code == 422
    assert "prior_answers[].topic" in resp.json()["detail"]


def test_unknown_persona_is_401(api_client: TestClient) -> None:
    resp = _post(api_client, sample_cases.wire_body(), persona="ghost")
    assert resp.status_code == 401


def test_healthz_reports_profile_and_region(api_client: TestClient) -> None:
    body = api_client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["profile"] == "local"
    assert body["region"] == "asia-southeast1"


def test_healthz_states_the_provenance_the_ui_banner_renders(api_client: TestClient) -> None:
    """The service half of the banner contract (org decision, 2026-08-30).

    The UI must never infer either value. A console that read its runtime from
    ``window.location`` would be right until the deployment served through a proxy and
    wrong silently after that, so the service is asked and the service answers.
    """
    body = api_client.get("/healthz").json()
    assert body["runtime"] == "local"
    # This service DOES bind a generative port, so the banner names the stub as a stub rather
    # than reporting `no-model`. The two are different facts and a reviewer approving an
    # escalation is entitled to know which one they are reading.
    assert body["generator_model"] == "deterministic-offline-stub"


@pytest.mark.parametrize(
    ("profile", "expected"), [("local", "local"), ("gcp", "gcp"), ("onprem", "local")]
)
def test_the_runtime_follows_the_profile_and_onprem_is_not_gcp(profile: str, expected: str) -> None:
    """``onprem`` reads local, and that is the whole point of the profile.

    It runs on the adopter's own iron. Treating any non-local profile as "on GCP" would put
    the wrong sentence at the top of every page of the one deployment whose selling point is
    that it is not on GCP.
    """
    from exam_rfi_orchestrator.config import Settings

    assert Settings(profile=profile).runtime == expected


def test_the_onprem_banner_names_an_unimplemented_model_rather_than_a_stub() -> None:
    """A placeholder that raises must not advertise a model that never answers."""
    from exam_rfi_orchestrator.config import Settings

    assert Settings(profile="onprem").generator_model == "onprem-not-implemented"


def test_security_headers_present(api_client: TestClient) -> None:
    headers = api_client.get("/healthz").headers
    assert headers["Content-Security-Policy"] == "frame-ancestors 'self'"
    assert headers["X-Content-Type-Options"] == "nosniff"


@pytest.fixture()
def token_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv(_TOKEN_ENV, "s3cret-service-token")
    yield "s3cret-service-token"


def test_s2s_endpoint_open_when_secret_unset(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(_TOKEN_ENV, raising=False)
    assert api_client.post("/v1/audit/ping").status_code == 200


def test_s2s_endpoint_rejects_missing_token_when_enforced(
    api_client: TestClient, token_env: str
) -> None:
    assert api_client.post("/v1/audit/ping").status_code == 401


def test_s2s_endpoint_accepts_correct_token(api_client: TestClient, token_env: str) -> None:
    resp = api_client.post("/v1/audit/ping", headers={"Authorization": f"Bearer {token_env}"})
    assert resp.status_code == 200
