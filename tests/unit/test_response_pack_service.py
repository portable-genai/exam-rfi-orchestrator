"""The response-pack service end to end, over the real local adapters.

The engine modules are tested in isolation elsewhere. What this file holds is the WIRING: that
the pipeline masks before it writes, refuses to draft with nothing to draft from, numbers an
annex the same way twice, records the board row, and hands back an outcome held for a checker.

Three of these are falsification tests: each names the defect it would catch and is written so
that removing the guard makes it fail rather than making it silently useless.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import replace
from datetime import date

import pytest
from hex_service_kit.serialization import to_jsonable

from exam_rfi_orchestrator.config import (
    Container,
    Settings,
    build_container,
)
from exam_rfi_orchestrator.domain.artefact_taxonomy import decompose
from exam_rfi_orchestrator.domain.exhibit_index import renumber_document_index
from exam_rfi_orchestrator.domain.kernel import Citation, Decision, Severity
from exam_rfi_orchestrator.domain.models import (
    ArtefactClass,
    BlockerKind,
    Disposition,
    ObligationRef,
    ReleaseState,
    RequestItem,
    RequestTopic,
)
from exam_rfi_orchestrator.domain.response_pack_service import ResponsePackService
from exam_rfi_orchestrator.ports.generation import GenerationRequest, GenerationResponse
from exam_rfi_orchestrator.services import build_service

from tests.fixtures import sample_cases

#: A snippet from the privileged memo in the fixture corpus. Quoting a withheld document is
#: producing it, so this string must never appear on any surface.
_PRIVILEGED_PHRASE = "prepared for the purpose of legal proceedings"


def _container(**overrides: object) -> Container:
    base: dict[str, object] = {
        "profile": "local",
        "audit_path": ":memory:",
        "tenant": sample_cases.TENANT,
    }
    base.update(overrides)
    return build_container(Settings(**base))  # type: ignore[arg-type]


def _assess(
    item: RequestItem,
    *,
    container: Container | None = None,
    request: object | None = None,
    prior_answers: tuple[object, ...] = (),
    tenant: str = sample_cases.TENANT,
) -> object:
    resolved = container or _container()
    return build_service(resolved).assess_item(
        request or sample_cases.REQUEST,  # type: ignore[arg-type]
        item,
        actor=sample_cases.ACTOR,
        tenant=tenant,
        as_of=sample_cases.AS_OF,
        prior_answers=prior_answers,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------------------- #
# The pipeline's shape
# --------------------------------------------------------------------------------------- #
def test_a_fully_evidenced_item_is_on_track_cited_indexed_and_not_escalated() -> None:
    assessment = _assess(sample_cases.ROUTINE_ITEM)
    assert assessment.disposition is Disposition.ON_TRACK  # type: ignore[attr-defined]
    assert assessment.severity is Severity.LOW  # type: ignore[attr-defined]
    assert assessment.decision is Decision.ALLOWED  # type: ignore[attr-defined]
    assert assessment.requires_human_review is False  # type: ignore[attr-defined]
    assert assessment.completeness_pct == 100  # type: ignore[attr-defined]
    assert assessment.citations, "an answer with no provenance is not shippable"
    assert assessment.exhibits  # type: ignore[attr-defined]
    assert assessment.release_state is ReleaseState.HELD_FOR_CHECKER  # type: ignore[attr-defined]


def test_every_requirement_records_the_rule_that_produced_it() -> None:
    """Decomposition is inspectable rather than a black box a checker has to trust."""
    assessment = _assess(sample_cases.ROUTINE_ITEM)
    rules = {req.source_rule.split(":", 1)[0] for req in assessment.requirements}  # type: ignore[attr-defined]
    assert rules <= {"D1", "D2", "D3", "D4"}
    assert "D1" in rules, "the regulator's own words produced no requirement"
    assert "D2" in rules, "the topic playbook produced no requirement"


def test_the_obligation_register_sets_a_floor_the_question_cannot_lower() -> None:
    """Rule D3: a badly worded question decomposes to no fewer artefacts than the register wants.

    The credit-risk register row demands an issue log, which that topic's playbook does not list
    and which this question does not ask for. It is required anyway.
    """
    bare = RequestItem(
        item_ref="9.a",
        question="Set out the approach to credit risk.",
        topic=RequestTopic.CREDIT_RISK,
        requested_artefacts=(),
        owner="Head of Credit (FICTIONAL)",
    )
    assessment = _assess(bare)
    by_artefact = {req.artefact: req.source_rule for req in assessment.requirements}  # type: ignore[attr-defined]
    assert ArtefactClass.ISSUE_LOG in by_artefact
    assert by_artefact[ArtefactClass.ISSUE_LOG].startswith("D3:obligation:OBL-CRD-001")


def test_an_item_with_no_obligation_records_the_explicit_string_not_a_guess() -> None:
    """A guessed rule reference in a regulator response is worse than an honest gap."""
    assessment = _assess(
        RequestItem(
            item_ref="4.b",
            question="Provide the model documentation and independent validation reports.",
            topic=RequestTopic.MODEL_RISK,
            owner="Head of Model Risk (FICTIONAL)",
        )
    )
    obligations = assessment.obligations  # type: ignore[attr-defined]
    assert [row.obligation_id for row in obligations] == ["obligations:none"]
    assert "no obligation text available" in obligations[0].title


def test_empty_retrieval_is_a_blocker_and_never_an_ungrounded_answer() -> None:
    """Rule G1: with nothing admissible the generation port is not called at all."""
    assessment = _assess(
        RequestItem(
            item_ref="4.b",
            question="Provide the model documentation and independent validation reports.",
            topic=RequestTopic.MODEL_RISK,
            owner="Head of Model Risk (FICTIONAL)",
        )
    )
    assert assessment.narrative.drafted is False  # type: ignore[attr-defined]
    assert assessment.narrative.text == ""  # type: ignore[attr-defined]
    assert BlockerKind.NO_ADMISSIBLE_EVIDENCE in {b.kind for b in assessment.blockers}  # type: ignore[attr-defined]
    assert assessment.completeness_pct == 0  # type: ignore[attr-defined]


def test_an_unowned_item_can_never_be_on_track() -> None:
    unowned = replace(sample_cases.ROUTINE_ITEM, owner="")
    assessment = _assess(unowned)
    assert BlockerKind.NO_OWNER in {b.kind for b in assessment.blockers}  # type: ignore[attr-defined]
    assert assessment.disposition is not Disposition.ON_TRACK  # type: ignore[attr-defined]


class _ProposingGeneration:
    """A generation port that proposes an extra artefact class on every job it is given.

    The offline stub proposes nothing on the classify path, so the whole "a proposal cannot
    change an outcome" claim was scored over a model that never proposed anything.
    """

    def __init__(self, inner: object) -> None:
        self._inner = inner

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        response = self._inner.generate(request)  # type: ignore[attr-defined]
        payload = json.loads(response.text)
        if "topic" in request.response_keys:
            payload["artefacts"] = [ArtefactClass.CUSTOMER_FILE.value]
        if "narrative" in request.response_keys:
            payload["proposed_artefacts"] = [ArtefactClass.CUSTOMER_FILE.value]
        return GenerationResponse(text=json.dumps(payload), model=response.model)


def test_no_model_output_changes_a_requirement_a_count_or_a_disposition() -> None:
    """The model proposes, and the proposal reaches a human and nothing else.

    A requirement is not a label: it moves ``total_mandatory``, and through it the completeness
    percentage, a coverage state, the disposition, the severity, the review flag and the release
    blockers. A model that could add one would own an outcome, which the invariant forbids in
    every profile. This is the falsification: the model here DOES propose a class the item never
    asked for, the proposal is visible on the draft where a checker reads it, and every
    consequential number is identical to the run without it.
    """
    container = _container()
    baseline = _assess(sample_cases.ROUTINE_ITEM, container=container)
    proposing = _container()
    service = _service_with(proposing, generation=_ProposingGeneration(proposing.generation))
    assessed = service.assess_item(
        sample_cases.REQUEST,
        sample_cases.ROUTINE_ITEM,
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        as_of=sample_cases.AS_OF,
    )
    assert ArtefactClass.CUSTOMER_FILE in assessed.narrative.proposed_artefacts, (
        "the model proposed nothing, so this test is checking nothing"
    )
    wanted = [row.artefact for row in baseline.requirements]  # type: ignore[attr-defined]
    assert [row.artefact for row in assessed.requirements] == wanted
    assert all(
        row.source_rule.split(":", 1)[0] in {"D1", "D2", "D3", "D4"}
        and "model" not in row.source_rule
        for row in assessed.requirements
    ), "a requirement names a model as the rule that produced it"
    assert assessed.total_mandatory == baseline.total_mandatory  # type: ignore[attr-defined]
    assert assessed.completeness_pct == baseline.completeness_pct  # type: ignore[attr-defined]
    assert assessed.disposition is baseline.disposition  # type: ignore[attr-defined]
    assert assessed.severity is baseline.severity  # type: ignore[attr-defined]
    assert assessed.requires_human_review is baseline.requires_human_review  # type: ignore[attr-defined]
    assert assessed.release_blockers == baseline.release_blockers  # type: ignore[attr-defined]
    states = [row.state for row in baseline.coverage]  # type: ignore[attr-defined]
    assert [row.state for row in assessed.coverage] == states


def test_decomposition_takes_only_declared_inputs() -> None:
    """The structural half: a third input to decomposition is how the model gets back in.

    The union is the regulator's own words, the firm's playbook and the obligation register.
    Adding a fourth source is a decision somebody has to make on purpose, and this is what makes
    them read the rule above before they make it.
    """
    assert list(inspect.signature(decompose).parameters) == ["item", "obligations"], (
        "decomposition grew an input; if it carries model output, the model sets a requirement"
    )


def test_a_suppressed_document_never_denies_a_class_the_firm_simply_does_not_hold() -> None:
    """End to end over the shipped corpus: the denial sentence stays attached to its own class.

    The caller sees only ``group:analyst``, so the store suppresses two committee minutes. The
    item also asks for a transaction sample, of which the governance corpus holds nothing and of
    which nothing was suppressed. Reporting that one as DENIED would tell a supervisor "you are
    not entitled to read this" about a document that does not exist.
    """
    item = RequestItem(
        item_ref="6.a",
        question="Provide the board and risk-committee minutes and the attendance records.",
        topic=RequestTopic.GOVERNANCE,
        requested_artefacts=(ArtefactClass.TRANSACTION_SAMPLE,),
        owner="Company Secretariat (FICTIONAL)",
    )
    narrowed = sample_cases.request(entitlements=sample_cases.NARROW_ENTITLEMENTS)
    assessment = _assess(item, request=narrowed)
    states = {row.artefact.value: row.state.value for row in assessment.coverage}  # type: ignore[attr-defined]
    assert states["committee_minutes"] == "denied"
    assert states["transaction_sample"] == "missing"
    assert assessment.suppressed_by_entitlement == 2  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------- #
# Redact before anything, and never quote a withheld document
# --------------------------------------------------------------------------------------- #
def test_personal_data_is_masked_before_the_audit_write_and_on_every_surface() -> None:
    container = _container()
    assessment = _assess(sample_cases.PII_ITEM, container=container)
    records = container.audit.log.read_all()  # type: ignore[attr-defined]
    assert records, "an audit event should have been recorded"
    surfaces = json.dumps(records) + json.dumps(to_jsonable(assessment), sort_keys=True)
    assert sample_cases.PLANTED_NRIC not in surfaces
    assert "REDACTED" in surfaces, "nothing was masked, so the check proved nothing"
    assert records[-1]["actor"] == sample_cases.ACTOR
    assert container.audit.log.verify_chain().ok  # type: ignore[attr-defined]


class _PlantedObligations:
    """An obligation register whose row names a person, which is an ordinary register row.

    The shipped fixture register carries no personal data, so the whole suite and all eleven
    golden cases scored the obligations path safe over a case they could not see. The managed
    adapter reads an EXTERNAL register: a row saying who owns a control, or who an alert is
    escalated to, is exactly the row a real one holds.
    """

    _PLANTED = f"Maintain the control (FICTIONAL), owned by {sample_cases.PLANTED_NRIC}"

    def obligations_for(self, topic: RequestTopic, jurisdiction: str) -> tuple[ObligationRef, ...]:
        return (
            ObligationRef(
                obligation_id="OBL-FICTIONAL-999",
                rule_ref="handbook/data-protection/2",
                title=self._PLANTED,
                required_artefacts=(ArtefactClass.POLICY,),
                citation=Citation(
                    source_id="obligation:OBL-FICTIONAL-999",
                    title=self._PLANTED,
                    snippet=f"escalate to {sample_cases.PLANTED_NRIC} on receipt (FICTIONAL)",
                ),
            ),
        )


def _service_with(container: Container, **ports: object) -> ResponsePackService:
    """The real service with one port swapped, so a single seam can be probed in isolation."""
    bound: dict[str, object] = {
        "knowledge_base": container.knowledge_base,
        "obligations": container.obligations,
        "evidence_packs": container.evidence_packs,
        "generation": container.generation,
        "case_store": container.case_store,
        "policy": container.settings.policy,
    }
    bound.update(ports)
    return ResponsePackService(container.audit, container.tracer, **bound)  # type: ignore[arg-type]


def test_obligation_register_text_is_masked_like_every_other_inbound_text() -> None:
    """The register is a port, not a fixture seam, and its rows reach the caller and the console.

    ``obligations`` and ``citations`` are on the outcome the API serialises and the UI renders,
    so a register row naming a person leaves the service unless it is masked on the way in.
    """
    container = _container()
    service = _service_with(container, obligations=_PlantedObligations())
    assessment = service.assess_item(
        sample_cases.REQUEST,
        sample_cases.ROUTINE_ITEM,
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        as_of=sample_cases.AS_OF,
    )
    outcome = json.dumps(to_jsonable(assessment), sort_keys=True)
    records = json.dumps(container.audit.log.read_all())  # type: ignore[attr-defined]
    assert "OBL-FICTIONAL-999" in outcome, "the planted register row never reached the outcome"
    assert sample_cases.PLANTED_NRIC not in outcome, (
        "the obligation register leaked personal data onto the outcome that leaves the service"
    )
    assert sample_cases.PLANTED_NRIC not in records
    assert "REDACTED" in outcome, "nothing was masked, so this proved nothing"


def test_the_audit_write_masks_on_its_own_and_not_because_something_upstream_did() -> None:
    """The last line of defence on the immutable record, falsified in isolation.

    Every other mask sits upstream of this one, so with the pipeline intact the audit write can
    be deleted whole and every test stays green: that is a guard observed only green. The write
    is therefore exercised DIRECTLY, with text no upstream stage ever touched, which is also the
    real shape of the risk (a new inbound field, an added call site, a future caller).
    """
    container = _container()
    service = _service_with(container)
    raw = f"item 3.a: blocked complainant {sample_cases.PLANTED_NRIC}"
    # The private boundary is called on purpose: there is no public seam that reaches it with
    # unmasked text, which is exactly why nothing was holding it.
    service._write_audit(
        "assess_item",
        sample_cases.ACTOR,
        Decision.ESCALATED,
        Severity.HIGH,
        raw,
        (
            Citation(
                source_id="doc:kb-dpr-cus-01",
                title=f"Customer file for {sample_cases.PLANTED_NRIC} (FICTIONAL)",
                snippet=f"Contact NRIC {sample_cases.PLANTED_NRIC} (FICTIONAL).",
            ),
        ),
    )
    record = container.audit.log.read_all()[-1]  # type: ignore[attr-defined]
    written = json.dumps(record)
    assert sample_cases.PLANTED_NRIC not in written, "the WORM record kept a raw identifier"
    assert "REDACTED" in written, "nothing was masked, so this proved nothing"
    assert "doc:kb-dpr-cus-01" in written, "the citation's source id must survive masking"


def test_a_withheld_document_is_never_quoted_indexed_or_narrated() -> None:
    """The falsification target: withholding that still leaks the content is not withholding."""
    assessment = _assess(sample_cases.PII_ITEM)
    surfaces = json.dumps(to_jsonable(assessment), sort_keys=True)
    assert _PRIVILEGED_PHRASE not in surfaces
    withheld_ids = {record.doc_id for record in assessment.withheld}  # type: ignore[attr-defined]
    assert withheld_ids, "the schedule is empty, so this test is checking nothing"
    assert not withheld_ids & {exhibit.doc_id for exhibit in assessment.exhibits}  # type: ignore[attr-defined]
    citations = assessment.citations  # type: ignore[attr-defined]
    cited = {c.source_id.split(":", 1)[1] for c in citations if c.source_id.startswith("doc:")}
    assert not withheld_ids & cited


def test_the_audit_summary_carries_the_due_basis_the_calendar_and_every_withhold_basis() -> None:
    """The four questions a supervisor asks have to be answerable from the trail alone."""
    container = _container()
    _assess(sample_cases.PII_ITEM, container=container)
    summary = str(container.audit.log.read_all()[-1]["redacted_summary"])  # type: ignore[attr-defined]
    assert "due_basis=regulator_stated" in summary
    assert "calendar=SG@" in summary
    assert "kb-dpr-leg-01:A4" in summary
    assert "kb-dpr-sar-01:A5" in summary


# --------------------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------------------- #
def test_the_same_inputs_produce_the_same_annex_twice() -> None:
    """A resubmission that cannot be diffed against the original cannot be cross-referenced."""
    first = _assess(sample_cases.ROUTINE_ITEM)
    second = _assess(sample_cases.ROUTINE_ITEM)
    assert [e.exhibit_no for e in first.exhibits] == [e.exhibit_no for e in second.exhibits]  # type: ignore[attr-defined]
    assert [e.doc_id for e in first.exhibits] == [e.doc_id for e in second.exhibits]  # type: ignore[attr-defined]


def test_the_document_index_renumbers_contiguously_and_keeps_the_cross_reference() -> None:
    container = _container()
    service = build_service(container)
    items = [
        service.assess_item(
            sample_cases.REQUEST,
            item,
            actor=sample_cases.ACTOR,
            tenant=sample_cases.TENANT,
            as_of=sample_cases.AS_OF,
        )
        for item in (sample_cases.ROUTINE_ITEM, sample_cases.PII_ITEM)
    ]
    index = renumber_document_index(items)
    assert [row.index_no for row in index] == [
        f"IDX-{position:03d}" for position in range(1, len(index) + 1)
    ]
    assert all(row.exhibit_no.startswith("EX-") for row in index)


# --------------------------------------------------------------------------------------- #
# The pack
# --------------------------------------------------------------------------------------- #
def test_a_pack_of_clean_items_still_routes_and_is_held_for_a_checker() -> None:
    container = _container()
    service = build_service(container)
    item = service.assess_item(
        sample_cases.REQUEST,
        sample_cases.ROUTINE_ITEM,
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        as_of=sample_cases.AS_OF,
    )
    pack = service.assemble_pack(
        sample_cases.REQUEST,
        (item,),
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        as_of=sample_cases.AS_OF,
    )
    assert pack.disposition is Disposition.ON_TRACK
    assert pack.decision is Decision.ESCALATED
    assert pack.requires_human_review is True
    assert pack.required_approvals == 2
    assert pack.release_state is ReleaseState.HELD_FOR_CHECKER
    assert pack.document_index and pack.cover_note.drafted


def test_the_pack_rolls_up_the_worst_item_and_the_integer_mean_of_completeness() -> None:
    container = _container()
    service = build_service(container)
    items = [
        service.assess_item(
            sample_cases.REQUEST,
            item,
            actor=sample_cases.ACTOR,
            tenant=sample_cases.TENANT,
            as_of=sample_cases.AS_OF,
            prior_answers=sample_cases.PRIOR_ANSWERS,
        )
        for item in (sample_cases.ROUTINE_ITEM, sample_cases.ESCALATING_ITEM)
    ]
    pack = service.assemble_pack(
        sample_cases.REQUEST,
        items,
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        as_of=sample_cases.AS_OF,
    )
    assert pack.disposition is Disposition.BLOCKED
    assert pack.severity is Severity.CRITICAL
    assert pack.completeness_pct == sum(i.completeness_pct for i in items) // len(items)
    assert BlockerKind.BELOW_MIN_COMPLETENESS in pack.release_blockers


# --------------------------------------------------------------------------------------- #
# The board, the waiver and the extension
# --------------------------------------------------------------------------------------- #
def test_assessing_an_item_writes_the_open_item_board_row() -> None:
    container = _container()
    service = build_service(container)
    assessment = _assess(sample_cases.ROUTINE_ITEM, container=container)
    board = service.open_items(sample_cases.TENANT, sample_cases.ENTITLEMENTS)
    assert [row.item_ref for row in board] == [assessment.item_ref]  # type: ignore[attr-defined]
    assert board[0].internal_due_on == assessment.sla.internal_due_on  # type: ignore[attr-defined]

    service.record_case(
        sample_cases.REQUEST,
        assessment,  # type: ignore[arg-type]
        tenant=sample_cases.TENANT,
        review_ref="review-FICTIONAL-1",
    )
    assert service.open_items(sample_cases.TENANT, sample_cases.ENTITLEMENTS)[0].review_ref == (
        "review-FICTIONAL-1"
    )


def test_the_board_is_filtered_against_the_readers_entitlements() -> None:
    container = _container()
    service = build_service(container)
    _assess(sample_cases.ROUTINE_ITEM, container=container)
    assert service.open_items(sample_cases.TENANT, sample_cases.ENTITLEMENTS)
    # A reader lacking one of the row's labels sees nothing, and an empty principal sees only
    # untagged rows. Fail-closed, decided in the query rather than after it.
    assert service.open_items(sample_cases.TENANT, frozenset({"group:analyst"})) == ()
    assert service.open_items("other-bank", sample_cases.ENTITLEMENTS) == ()


def test_a_client_asserted_extension_reference_moves_nothing_under_the_wrong_tenant() -> None:
    """The pair that proves a reference is a lookup key and never a grant."""
    request = sample_cases.request(
        request_id="EXAM-2027-0052",
        regulator_due_on=None,
        extension_ref="EXT-FICTIONAL-2027-52",
    )
    item = replace(sample_cases.ROUTINE_ITEM, item_ref="1", item_due_on=None)
    resolved = _assess(item, request=request, tenant=sample_cases.TENANT)
    refused = _assess(item, request=request, tenant="other-bank")
    assert resolved.sla.due_basis == "extension:EXT-FICTIONAL-2027-52"  # type: ignore[attr-defined]
    assert refused.sla.due_basis == "policy_window:rfi"  # type: ignore[attr-defined]
    assert refused.sla.due_on < resolved.sla.due_on  # type: ignore[attr-defined]


def test_a_named_evidence_pack_that_does_not_exist_is_an_error_not_an_empty_result() -> None:
    item = replace(
        sample_cases.ROUTINE_ITEM, evidence_pack_ref="PACK-DOES-NOT-EXIST", item_ref="8.a"
    )
    with pytest.raises(LookupError):
        _assess(item)


def test_a_reused_pack_gets_no_shortcut_through_the_admissibility_ladder() -> None:
    """Every packed document is paired, dated and tagged like a corpus hit, or dropped."""
    item = RequestItem(
        item_ref="8.a",
        question="Provide the outsourcing register entry and the current contract.",
        topic=RequestTopic.OUTSOURCING_THIRD_PARTY,
        owner="Third Party Management Office (FICTIONAL)",
        evidence_pack_ref="PACK-FICTIONAL-OUT-2027-01",
    )
    assessment = _assess(item)
    assert assessment.out_of_scope_dropped == 3  # type: ignore[attr-defined]
    reused = {e.doc_id for e in assessment.exhibits if e.origin == "evidence_pack"}  # type: ignore[attr-defined]
    assert reused, "the pack contributed nothing, so the reuse path is untested"
    dropped = {"pk-out-cus-01", "pk-out-txn-01", "pk-out-off-01"}
    assert not dropped & {link.doc_id for link in assessment.links}  # type: ignore[attr-defined]


def test_the_evaluation_date_is_an_input_so_a_submission_replays() -> None:
    """No clock reaches the engine: the same inputs on a different day give the same answer."""
    first = _assess(sample_cases.ROUTINE_ITEM)
    later = build_service(_container()).assess_item(
        sample_cases.REQUEST,
        sample_cases.ROUTINE_ITEM,
        actor=sample_cases.ACTOR,
        tenant=sample_cases.TENANT,
        as_of=date(2027, 3, 15),
    )
    assert first.sla == later.sla  # type: ignore[attr-defined]
