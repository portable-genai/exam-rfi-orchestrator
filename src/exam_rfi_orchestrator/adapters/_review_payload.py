"""Shared conversion from a reviewable outcome to a ``review-kit`` Review payload.

Lives in the adapter layer, not the pure domain, because it depends on the kit. The subject, the
summary and every citation snippet are redacted BEFORE they leave the process (the same
redact-before-anything rule the audit write obeys), using the shared ``pii-kit``, so no raw
identifier reaches the console over the wire; the console redacts again before its own audit
write (defence in depth). ``maker`` and ``tenant`` are asserted here and trusted by the console
because the caller is an authenticated service; per-hop on-behalf-of token exchange is the
deferred next layer.

THIS MODULE HAS NO APPROVALS RULE, DELIBERATELY. It used to own a module-level severity-keyed
dual-control tuple and compute ``required_approvals`` itself. The engine now owns that number
under rule R3, and two owners disagree the first time an instrument-driven case appears at low
severity: a skilled-person review demands dual control and never escalates, so a severity-keyed
table sends it for one approval while the service says two. The payload READS the number off the
outcome, and ``tests/contract/test_review_payload_owner.py`` fails the build if an independent
rule reappears here.

One builder, two artifact shapes. An item assessment and a whole response pack both satisfy
:class:`~..domain.models.ReviewableOutcome`, so R8 has one routing path rather than two payload
builders that drift apart. ``outcome_kind`` keeps the two apart in the console's source key, so
item exceptions and pack approvals are different reviews with different readers.
"""

from __future__ import annotations

import re

from pii_kit import NATIONAL_ID_PATTERNS, UNIVERSAL_PATTERNS, national_patterns_for
from pii_kit import redact as pii_redact
from review_kit import Citation as KitCitation
from review_kit import Review

from ..domain.models import ReviewableOutcome

#: Cap the citations carried on the wire: enough for a reviewer to trace the decision without
#: copying the whole evidence set into the console.
_MAX_CITATIONS = 8

#: The console is a SHARED sink: a request filed in one market may still quote another market's
#: national id, so the payload is scrubbed against every jurisdiction's rows plus the universal
#: email/phone rows, whatever this deployment's own ``domain.pii.JURISDICTIONS`` selects.
_ALL_PATTERNS = (
    *national_patterns_for(tuple(NATIONAL_ID_PATTERNS.keys())),
    *UNIVERSAL_PATTERNS,
)

_ACTION_PREFIX = "exam_rfi_orchestrator"
_SOD_GROUP = "exam_rfi_orchestrator-maker-checker"
_CATALOG_ID = "Cop2"


def _redact(text: str) -> str:
    """Mask every jurisdiction's identifiers plus email/phone, and normalise whitespace."""
    return re.sub(r"\s+", " ", pii_redact(text, _ALL_PATTERNS)).strip()


def _kit_citations(outcome: ReviewableOutcome) -> tuple[KitCitation, ...]:
    seen: set[str] = set()
    out: list[KitCitation] = []
    for citation in outcome.citations:
        if citation.source_id in seen:
            continue
        seen.add(citation.source_id)
        out.append(
            KitCitation(
                source_id=citation.source_id,
                title=_redact(citation.title),
                snippet=_redact(citation.snippet),
            )
        )
        if len(out) >= _MAX_CITATIONS:
            break
    return tuple(out)


def result_to_review(outcome: ReviewableOutcome, *, maker: str, tenant: str = "") -> Review:
    """Build the review a producer submits when an outcome routes (rule R8).

    ``required_approvals`` is READ off the outcome. There is no severity table here and there
    must never be one again: the engine decides dual control under rule R3, and a second owner of
    that number is a second answer to the same question.
    """
    return Review(
        action=f"{_ACTION_PREFIX}:{outcome.outcome_kind}",
        subject=_redact(outcome.subject),
        maker=maker,
        tenant=tenant,
        summary=_redact(outcome.summary),
        severity=outcome.severity.value,
        required_approvals=outcome.required_approvals,
        sod_group=_SOD_GROUP,
        case_ref=outcome.case_ref,
        # Producer-owned, tenant-scoped key so a retried delivery is idempotent at the console,
        # and so an item exception and a pack approval never collapse into one review.
        source_key=f"{_CATALOG_ID}:{outcome.case_ref}:{outcome.outcome_kind}",
        citations=_kit_citations(outcome),
    )
