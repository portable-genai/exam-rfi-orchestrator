"""Prove the metrics are not structurally falsely green (the two-part-scorer lesson).

A metric that has never been shown to go red is indistinguishable from an absent one, and this
organization's own history is a list of guards that only ever ran green. Two metrics get the
treatment here because both are scored over derived text and both would look fine over an empty
or broken input set:

* ``pii_safety``: the SAME summary with redaction on (green) and off (red).
* ``citation_grounding``: the SAME narration predicates over a grounded draft (green) and over a
  draft citing an exhibit outside the item's index (red). This is the one the evaluation scores
  RAW model output through, so it has to be able to reject real model output.
"""

from __future__ import annotations

from datetime import date

from agent_eval_kit import assert_can_go_red
from pii_kit import pack_leak, redact

from exam_rfi_orchestrator.domain import (
    narration,
)
from exam_rfi_orchestrator.domain.kernel import (
    Citation,
)
from exam_rfi_orchestrator.domain.models import (
    ArtefactClass,
    Exhibit,
)
from exam_rfi_orchestrator.domain.pii import (
    PII_PATTERNS,
)

_RAW_SUMMARY = (
    "MPA-FICTIONAL/EX/2027/0014 item 3.a: blocked completeness=75% "
    ":: complainant NRIC S1234567D on file"
)


def _pii_safety(summary: str) -> float:
    """1.0 unless a raw identifier (per the shared pack) survives into the summary."""
    return 0.0 if pack_leak(summary, PII_PATTERNS) else 1.0


def test_pii_safety_can_go_red() -> None:
    assert_can_go_red(
        _pii_safety,
        green=redact(_RAW_SUMMARY, PII_PATTERNS),  # redaction on: the NRIC is masked
        red=_RAW_SUMMARY,  # redaction off (the mutant): the raw NRIC survives
        threshold=0.99,
        metric="pii_safety",
    )


_EXHIBIT = Exhibit(
    exhibit_no="EX-1.a-01",
    doc_id="kb-aml-pol-01",
    title="Financial crime policy (FICTIONAL)",
    artefact=ArtefactClass.POLICY,
    as_of=date(2026, 6, 30),
    locator="s.4.2",
    citation=Citation(source_id="doc:kb-aml-pol-01", title="Financial crime policy (FICTIONAL)"),
)

_FACTS = narration.build_narrative_request(
    item_ref="1.a",
    question="Provide the financial-crime policy in force during the review period.",
    completeness_pct=100,
    satisfied=5,
    total=5,
    business_days_remaining=29,
    exhibits=(_EXHIBIT,),
).facts


def _citation_grounding(text: str) -> float:
    """1.0 only when the draft cites an exhibit in THIS item's index and invents no number.

    The same module-level predicates the service enforces, so the metric and the gate cannot
    disagree about what grounded means.
    """
    import json

    payload = json.dumps({"narrative": text, "proposed_artefacts": []})
    return 1.0 if narration.narrative_verdict(payload, _FACTS, ("EX-1.a-01",)).ok else 0.0


def test_citation_grounding_can_go_red() -> None:
    assert_can_go_red(
        _citation_grounding,
        green="The firm produces [EX-1.a-01]; 5 of 5 mandatory artefacts, 100 per cent.",
        red="The firm produces [EX-9.z-99] covering 4242 records.",
        threshold=0.99,
        metric="citation_grounding",
    )
