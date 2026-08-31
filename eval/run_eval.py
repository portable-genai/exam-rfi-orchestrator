#!/usr/bin/env python3
"""Evaluation gate for Regulatory Exam and RFI Orchestrator (Cop2).

Two named layers via ``--mode`` (the scaffold is ``agent_eval_kit.eval_main``):

* **smoke** (default) - the offline pre-merge check CI runs on every change: it drives the real
  ``ResponsePackService`` against the golden set with SDK-free local adapters and scores the
  metrics below.
* **gate** - the promotion verdict from the shared promotion authority (requires the ``gcp``
  profile), resolved through the container's ``EvaluationGatePort`` so the authority is a
  binding like every other port rather than a client constructed here.

EVERY ORACLE IS INDEPENDENT OF THE ENGINE'S OWN LABELS, and that is the point of this file. A
metric scored from the thing it is checking is a green tick over an empty set. So:

* ``entitlement_safety`` re-checks every emitted document id's ACL labels against the case
  entitlements, reading the CORPUS rather than the engine's verdicts;
* ``withhold_precision`` asserts that no document carrying a hard-withhold tag in the corpus
  appears in any index, citation, narrative or review payload;
* ``citation_grounding`` scores the RAW model output through the same module-level narration
  predicates the service enforces, so a stub that started producing ungrounded text would go red
  here rather than being quietly discarded and counted as a pass;
* ``blocker_recall`` is MICRO-averaged over the expected blockers themselves, not averaged over
  cases: a case that expects none contributes to neither side of the fraction instead of taking
  a free 1.0 for producing nothing, and the run refuses outright if no case expects one;
* ``pii_safety`` keeps the two-part scorer: the pattern-pack scan plus an independent
  planted-literal check that fires even if a pattern row is broken.

Exit is ``0`` iff every metric meets its threshold (and, in gate mode, the authority agrees).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from agent_eval_kit import EvalMetricResult, EvalReport, eval_main
from hex_service_kit.serialization import to_jsonable
from pii_kit import pack_leak

from exam_rfi_orchestrator.adapters.local.audit import (
    LocalAuditAdapter,
)
from exam_rfi_orchestrator.adapters.local.evidence_packs import (
    pack_documents,
)
from exam_rfi_orchestrator.adapters.local.knowledge_base import (
    corpus_documents,
)
from exam_rfi_orchestrator.config import (
    Settings,
    build_container,
)
from exam_rfi_orchestrator.domain import (
    narration,
)
from exam_rfi_orchestrator.domain.models import (
    ArtefactClass,
    EvidenceItem,
    Instrument,
    ItemAssessment,
    PriorAnswer,
    RegulatorRequest,
    RequestItem,
    RequestTopic,
)
from exam_rfi_orchestrator.domain.pii import (
    PII_PATTERNS,
)
from exam_rfi_orchestrator.domain.response_pack_service import (
    ResponsePackService,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATASET = _REPO_ROOT / "eval" / "datasets" / "golden_cases.jsonl"

THRESHOLDS: dict[str, float] = {
    "disposition_accuracy": 1.00,
    "clock_accuracy": 1.00,
    "completeness_accuracy": 1.00,
    "withhold_precision": 1.00,
    "blocker_recall": 1.00,
    "citation_grounding": 0.99,
    "entitlement_safety": 1.00,
    "pii_safety": 0.99,
}


def _load(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cases.append(json.loads(line))
    if not cases:
        raise SystemExit(f"{path}: golden dataset is empty")
    return cases


def _mean(scores: list[float]) -> float:
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _optional_date(value: Any) -> date | None:
    return None if value in (None, "") else date.fromisoformat(str(value))


def _request(case: Mapping[str, Any], policy: Any) -> RegulatorRequest:
    header = case["request"]
    jurisdiction = str(header["jurisdiction"])
    return RegulatorRequest(
        request_id=str(header["request_id"]),
        regulator=str(header["regulator"]),
        reference=str(header["reference"]),
        instrument=Instrument(str(header["instrument"])),
        regime=str(header["regime"]),
        jurisdiction=jurisdiction,
        received_on=date.fromisoformat(str(header["received_on"])),
        period_start=date.fromisoformat(str(header["period_start"])),
        period_end=date.fromisoformat(str(header["period_end"])),
        regulator_due_on=_optional_date(header.get("regulator_due_on")),
        extension_ref=str(header.get("extension_ref", "")),
        waiver_ref=str(header.get("waiver_ref", "")),
        # Server-derived in every real surface, and derived here too: a golden row may not widen
        # the transfer scope any more than a request body may.
        entitlements=frozenset(case["entitlements"]),
        permitted_transfer_jurisdictions=policy.permitted_transfers(jurisdiction),
    )


def _item(case: Mapping[str, Any]) -> RequestItem:
    row = case["item"]
    return RequestItem(
        item_ref=str(row["item_ref"]),
        question=str(row["question"]),
        topic=RequestTopic(str(row["topic"])),
        requested_artefacts=tuple(
            ArtefactClass(value) for value in row.get("requested_artefacts", [])
        ),
        owner=str(row.get("owner", "")),
        item_due_on=_optional_date(row.get("item_due_on")),
        evidence_pack_ref=str(row.get("evidence_pack_ref", "")),
    )


def _prior_answers(case: Mapping[str, Any]) -> tuple[PriorAnswer, ...]:
    return tuple(
        PriorAnswer(
            answer_id=str(row["answer_id"]),
            submitted_on=date.fromisoformat(str(row["submitted_on"])),
            item_ref=str(row["item_ref"]),
            topic=RequestTopic(str(row["topic"])),
            assertion_key=str(row["assertion_key"]),
            assertion_value=str(row["assertion_value"]),
        )
        for row in case.get("prior_answers", [])
    )


def _all_documents() -> dict[str, EvidenceItem]:
    """The fixture corpus AND the packed documents, by id: the oracles' source of truth."""
    documents = corpus_documents()
    documents.update(pack_documents())
    return documents


def _clock_matches(assessment: ItemAssessment, expected: Mapping[str, Any]) -> bool:
    sla = assessment.sla
    if sla.due_on.isoformat() != str(expected["due_on"]):
        return False
    if sla.due_basis != str(expected["due_basis"]):
        return False
    if sla.band.value != str(expected["band"]):
        return False
    if sla.breached is not bool(expected["breached"]):
        return False
    if sla.buffer_consumed is not bool(expected["buffer_consumed"]):
        return False
    original = expected.get("original_due_on")
    if original is not None:
        return sla.original_due_on is not None and sla.original_due_on.isoformat() == str(original)
    # A clock with no calendar version is a deadline nobody can trace to a holiday list.
    return bool(sla.calendar_version)


def _coverage_matches(assessment: ItemAssessment, expected: Mapping[str, Any]) -> bool:
    produced = {row.artefact.value: row.state.value for row in assessment.coverage}
    return produced == dict(expected["coverage"])


def _withhold_matches(assessment: ItemAssessment, expected: Mapping[str, Any]) -> bool:
    produced = sorted(
        (record.doc_id, record.status.value, record.basis_rule) for record in assessment.withheld
    )
    wanted = sorted(
        (str(row["doc_id"]), str(row["status"]), str(row["basis_rule"]))
        for row in expected.get("withheld", [])
    )
    return produced == wanted


def _emitted_document_ids(assessment: ItemAssessment) -> set[str]:
    """Every document id that reached a surface a regulator or a reviewer would see."""
    ids = {exhibit.doc_id for exhibit in assessment.exhibits}
    for citation in assessment.citations:
        if citation.source_id.startswith("doc:"):
            ids.add(citation.source_id.split(":", 1)[1])
    return ids


def _entitlement_safe(
    assessment: ItemAssessment, entitlements: frozenset[str], documents: Mapping[str, EvidenceItem]
) -> bool:
    """Re-check every emitted id against the CORPUS's labels, not the engine's verdicts."""
    for doc_id in _emitted_document_ids(assessment):
        document = documents.get(doc_id)
        if document is None:
            continue
        if not document.acl_labels <= entitlements:
            return False
    return True


def _withhold_precise(
    assessment: ItemAssessment,
    serialised: str,
    hard_withheld: Sequence[str],
    documents: Mapping[str, EvidenceItem],
) -> bool:
    """No hard-withheld document may be indexed, cited, quoted or put on the wire."""
    emitted = _emitted_document_ids(assessment)
    for doc_id in hard_withheld:
        if doc_id in emitted:
            return False
        document = documents[doc_id]
        if document.snippet and document.snippet in serialised:
            return False
        if document.title and document.title in assessment.narrative.text:
            return False
    return True


def run_smoke(dataset: Path) -> EvalReport:  # noqa: PLR0914 - one local per named metric
    cases = _load(dataset)
    settings = Settings(profile="local", audit_path=":memory:", tenant="demo-bank")
    container = build_container(settings)
    audit = container.audit
    assert isinstance(audit, LocalAuditAdapter)
    policy = settings.policy
    documents = _all_documents()
    hard_tags = set(policy.hard_withhold_tags)
    hard_withheld = [
        doc_id for doc_id, document in documents.items() if hard_tags & set(document.sensitivity)
    ]
    if not hard_withheld:
        raise SystemExit(
            "the fixture corpus holds no hard-withheld document, so withhold_precision would "
            "score a green tick over an empty set"
        )

    service = ResponsePackService(
        audit,
        container.tracer,
        knowledge_base=container.knowledge_base,
        obligations=container.obligations,
        evidence_packs=container.evidence_packs,
        generation=container.generation,
        case_store=container.case_store,
        policy=policy,
    )

    disposition: list[float] = []
    clock: list[float] = []
    completeness: list[float] = []
    withhold: list[float] = []
    blockers_wanted = 0
    blockers_found = 0
    grounding: list[float] = []
    entitlement: list[float] = []
    payloads: list[str] = []

    for case in cases:
        expected = case["expected"]
        entitlements = frozenset(case["entitlements"])
        request = _request(case, policy)
        item = _item(case)
        assessment = service.assess_item(
            request,
            item,
            actor="eval-bot",
            tenant=str(case["tenant"]),
            as_of=date.fromisoformat(str(case["as_of"])),
            prior_answers=_prior_answers(case),
        )
        serialised = json.dumps(to_jsonable(assessment), sort_keys=True)
        payloads.append(serialised)

        disposition.append(
            1.0
            if (
                assessment.disposition.value == expected["disposition"]
                and assessment.severity.value == expected["severity"]
                and assessment.decision.value == expected["decision"]
                and assessment.requires_human_review is bool(expected["requires_human_review"])
                and assessment.required_approvals == int(expected["required_approvals"])
                and assessment.release_state.value == "held_for_checker"
                and sorted(kind.value for kind in assessment.release_blockers)
                == sorted(expected["release_blockers"])
            )
            else 0.0
        )
        clock.append(1.0 if _clock_matches(assessment, expected) else 0.0)
        completeness.append(
            1.0
            if (
                assessment.completeness_pct == int(expected["completeness_pct"])
                and _coverage_matches(assessment, expected)
                and assessment.out_of_scope_dropped == int(expected["out_of_scope_dropped"])
                and assessment.suppressed_by_entitlement
                == int(expected["suppressed_by_entitlement"])
            )
            else 0.0
        )
        withhold.append(
            1.0
            if (
                _withhold_matches(assessment, expected)
                and _withhold_precise(assessment, serialised, hard_withheld, documents)
            )
            else 0.0
        )
        produced_kinds = {blocker.kind.value for blocker in assessment.blockers}
        wanted_kinds = set(expected["blocker_kinds"])
        # MICRO-averaged, over blockers rather than over cases. A per-case mean gave a case that
        # expects no blocker a free 1.0, which is a green tick over an empty set: five of the
        # golden cases expect none, so five elevenths of the score was awarded for checking
        # nothing and a real regression on the rest could still clear the threshold. A case with
        # no expected blocker now contributes to neither side of the fraction, and its "produced
        # no blocker" claim is scored by disposition_accuracy, which pins the release blockers.
        blockers_wanted += len(wanted_kinds)
        blockers_found += len(wanted_kinds & produced_kinds)
        entitlement.append(1.0 if _entitlement_safe(assessment, entitlements, documents) else 0.0)
        grounding.append(
            _grounding_score(container, assessment, item, bool(expected["narrative_drafted"]))
        )

    # pii_safety: no raw identifier may survive into an audit record OR into an outcome that
    # leaves this service. The pack scan uses the same rows the redactor masks with; the
    # planted-literal check is an independent oracle that fires even if a row is broken.
    records = [str(entry.get("redacted_summary", "")) for entry in audit.log.read_all()]
    surfaces = records + payloads
    planted = [str(case["planted"]) for case in cases if case.get("planted")]
    if not planted:
        raise SystemExit("no planted identifier in the golden set; pii_safety would prove nothing")
    pack_leaked = any(pack_leak(text, PII_PATTERNS) for text in surfaces)
    literal_leaked = any(token in text for token in planted for text in surfaces)
    pii_safety = 0.0 if (pack_leaked or literal_leaked) else 1.0

    # A denominator of zero is a dataset that expects no blocker anywhere, which would score this
    # metric 1.000 over nothing at all. Refuse rather than report it.
    if blockers_wanted == 0:
        raise SystemExit(
            "no golden case expects a blocker, so blocker_recall would be a green tick over an "
            "empty set"
        )

    results = tuple(
        EvalMetricResult.scored(name, value, THRESHOLDS[name])
        for name, value in (
            ("disposition_accuracy", _mean(disposition)),
            ("clock_accuracy", _mean(clock)),
            ("completeness_accuracy", _mean(completeness)),
            ("withhold_precision", _mean(withhold)),
            ("blocker_recall", round(blockers_found / blockers_wanted, 4)),
            ("citation_grounding", _mean(grounding)),
            ("entitlement_safety", _mean(entitlement)),
            ("pii_safety", pii_safety),
        )
    )
    return EvalReport(dataset=str(dataset), results=results, n_examples=len(cases))


def _grounding_score(
    container: Any, assessment: ItemAssessment, item: RequestItem, expect_draft: bool
) -> float:
    """Score the RAW model output through the same predicates the service enforces.

    An item with no admissible evidence scores 1.0 for producing no ungrounded sentence rather
    than 0.0 for producing nothing: rule G1 means the generation port is not called at all, and
    declining to draft is the correct behaviour, not a failure to draft.
    """
    if not assessment.exhibits:
        return 0.0 if expect_draft else 1.0
    request = narration.build_narrative_request(
        item_ref=item.item_ref,
        question=item.question,
        completeness_pct=assessment.completeness_pct,
        satisfied=assessment.satisfied_mandatory,
        total=assessment.total_mandatory,
        business_days_remaining=assessment.sla.business_days_remaining,
        exhibits=assessment.exhibits,
    )
    response = container.generation.generate(request)
    verdict = narration.narrative_verdict(
        response.text, request.facts, [exhibit.exhibit_no for exhibit in assessment.exhibits]
    )
    return 1.0 if verdict.ok else 0.0


def run_gate(dataset: Path) -> tuple[EvalReport, bool]:
    settings = Settings.load()
    if settings.profile != "gcp":
        raise SystemExit(
            "--mode gate is the promotion authority and requires "
            f"EXAMRFI_PROFILE=gcp (got {settings.profile!r}); "
            "run --mode smoke for the offline pre-merge check."
        )
    # Resolved through the CONTAINER, not by constructing a client here. The binding is then
    # configuration like every other port: an on-prem deployment gets an explicit refusal instead
    # of a client pointed at a service it does not run, and a repo cannot quietly grow a second,
    # differently-configured route to the same authority.
    container = build_container(settings)
    report = container.evaluation.evaluate(str(dataset))
    if not isinstance(report, EvalReport):
        raise SystemExit("EvaluationGatePort.evaluate did not return an EvalReport")
    return report, bool(container.evaluation.gate(str(dataset)))


if __name__ == "__main__":
    raise SystemExit(
        eval_main(
            smoke=run_smoke,
            gate=run_gate,
            default_dataset=DEFAULT_DATASET,
            description="Offline / promotion-authority evaluation gate for Cop2.",
        )
    )
