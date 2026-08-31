"""A span carries structure, never content, and this is the test that keeps it that way.

A trace backend is not the WORM audit trail. It has no redaction stage, a wider read
audience and no retention rule written against a regulator's requirement, so anything
content-shaped that reaches a span attribute has left the boundary that redaction exists to
hold, and left it silently: nothing fails, nothing logs, and the leak is discovered by
whoever opens the trace viewer.

The pressure this resists is real and reasonable-sounding. Someone debugging a slow or wrong
assessment adds "just the question text" to the span, because that is the one thing the trace
does not tell them. The allowlist test below is what turns that from a quiet regression into a
failed build. In this vertical the pressure is worse than usual: the obvious things to add are
the item reference and the document titles, and a document title is the fact a withholding rule
exists to keep off surfaces.
"""

from __future__ import annotations

from contextlib import contextmanager

from exam_rfi_orchestrator.config import (
    Settings,
    build_container,
)
from exam_rfi_orchestrator.domain.response_pack_service import (
    ResponsePackService,
)

from tests.fixtures import sample_cases

#: Obviously fictional, and shaped like the identifiers redaction is meant to catch, so a
#: span that carried the question text would fail on this string rather than on a subtlety.
_PLANTED_IDENTIFIER = sample_cases.PLANTED_NRIC
_ACTOR = sample_cases.ACTOR

#: The complete set of attribute keys a span may carry. Adding to this is a decision about what
#: leaves the trust boundary, so it is made here rather than at the call site.
_ALLOWED_ATTRIBUTES = {"action", "actor"}

#: The two units of work this service opens a span for.
_EXPECTED_SPANS = ["exam.assess_item", "exam.assemble_pack"]


class _RecordingTracer:
    """Captures span names and attributes. Satisfies ObservabilityTracerPort structurally."""

    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, str]]] = []

    @contextmanager
    def span(self, name: str, **attributes: str):  # type: ignore[no-untyped-def]
        self.spans.append((name, dict(attributes)))
        yield

    def record_token_usage(self, usage: object, model: str) -> None:
        return None


def _run() -> _RecordingTracer:
    tracer = _RecordingTracer()
    container = build_container(
        Settings(profile="local", audit_path=":memory:", tenant=sample_cases.TENANT)
    )
    service = ResponsePackService(
        container.audit,
        tracer,  # type: ignore[arg-type]
        knowledge_base=container.knowledge_base,
        obligations=container.obligations,
        evidence_packs=container.evidence_packs,
        generation=container.generation,
        case_store=container.case_store,
        policy=container.settings.policy,
    )
    assessment = service.assess_item(
        sample_cases.REQUEST,
        sample_cases.PII_ITEM,
        actor=_ACTOR,
        tenant=sample_cases.TENANT,
        as_of=sample_cases.AS_OF,
    )
    service.assemble_pack(
        sample_cases.REQUEST,
        (assessment,),
        actor=_ACTOR,
        tenant=sample_cases.TENANT,
        as_of=sample_cases.AS_OF,
    )
    return tracer


def test_each_unit_of_work_opens_exactly_one_span() -> None:
    assert [name for name, _ in _run().spans] == _EXPECTED_SPANS


def test_the_span_carries_the_structural_attributes_an_operator_needs() -> None:
    _, attributes = _run().spans[0]
    assert attributes["action"] == "assess_item"
    assert attributes["actor"] == _ACTOR


def test_the_attribute_keys_are_a_fixed_allowlist() -> None:
    """Widening this set is a trust-boundary decision, so it cannot happen by accident."""
    for _, attributes in _run().spans:
        assert set(attributes) == _ALLOWED_ATTRIBUTES, (
            "a new span attribute appeared; confirm it is structural, then widen "
            "_ALLOWED_ATTRIBUTES here deliberately"
        )


def test_no_attribute_value_carries_the_question_a_reference_or_a_document_title() -> None:
    emitted = " ".join(value for _, attributes in _run().spans for value in attributes.values())
    assert _PLANTED_IDENTIFIER not in emitted
    assert "outage" not in emitted.lower(), "the question text reached a span attribute"
    assert "3.a" not in emitted, "the item reference reached a span attribute"
    assert "legal analysis" not in emitted.lower(), "a document title reached a span attribute"
