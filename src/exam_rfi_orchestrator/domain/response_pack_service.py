"""The response-pack service: decompose, retrieve, admit, clock, draft, gate, record, route.

The consequential act here is not classifying a case. It is assembling the citation-backed,
deadline-tracked, withholding-logged answer to a supervisor's numbered questions and holding its
release behind a checker. Every part of that is pure stdlib and replayable; the model narrates,
classifies and normalises, and owns none of it.

The service keeps the template's shape exactly: one span per unit of work with structural
attributes only, redaction before the audit write, citations on every result, and rule R8 routing
at the surface that called it.

TWO UNITS OF WORK, TWO SPANS. :meth:`ResponsePackService.assess_item` is the replayable unit and
the thing a golden case pins. :meth:`ResponsePackService.assemble_pack` is the artifact a
supervisor actually receives: one contiguously numbered annex, one withholding schedule, one
cover note. Both satisfy the same reviewable-outcome Protocol, so R8 has one routing path.

WHERE REDACTION SITS. Every inbound text is masked the moment it enters the service, before the
engine, before the model and before the audit write: the caller's question, every retrieved title
and snippet, AND every obligation-register row, because the register is an external system of
record whose rows name people. Masking after an immutable write is too late, and masking at each
call site is a rule somebody eventually forgets. The audit write masks AGAIN, deliberately: it is
the last line of defence on the immutable record and it is guarded by its own test rather than by
the upstream masks happening to have run.

Rule R1: every one of the three generation-port calls this service makes (:meth:`propose_topic`'s
classification, :meth:`_draft`'s narration, :meth:`_normalise`'s fact extraction) goes through
:meth:`ResponsePackService._generate_screened`, which screens the bound
:class:`~..ports.guardrail.GuardrailPort` INPUT on the prompt AS SENT (the one string that carries
every caller-controlled field: the item reference, the question, every retrieved title and
snippet) before it reaches the model, and OUTPUT on the model's answer before that text is parsed
or used. The text each screen hands back is the text used from then on, exactly as given.

A refusal, and a guardrail that raised instead of deciding, are both audited ``Decision.BLOCKED``
(never carrying the refused text) BEFORE :class:`~.errors.GuardrailBlockedError` reaches the call
site. Narration is optional here by design, so each call site then drops the model's contribution
WHOLE, exactly as it does for a model that could not be reached: the draft falls back to the
deterministic paragraph with an ``ungrounded_draft`` blocker, the topic suggestion is absent, the
normalised facts are absent. Never a partial model result and never unscreened text. An audit sink
that refuses the BLOCKED record is not swallowed: its error reaches the caller.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date

from pii_kit import redact

from ..ports.audit import AuditSinkPort
from ..ports.case_store import CaseStorePort
from ..ports.evidence_packs import EvidencePackReadPort
from ..ports.generation import GenerationPort, GenerationRequest, GenerationResponse
from ..ports.guardrail import GuardrailPort
from ..ports.knowledge_base import KnowledgeBaseReadPort
from ..ports.obligations import ObligationsReadPort
from ..ports.observability import ObservabilityTracerPort
from . import narration
from .artefact_taxonomy import decompose
from .consistency import KNOWN_ASSERTION_KEYS, check_consistency
from .coverage_engine import assess_evidence
from .errors import GuardrailBlockedError
from .exhibit_index import number_exhibits, renumber_document_index
from .kernel import AuditEvent, Citation, Decision, Direction, Severity, utcnow
from .models import (
    ArtefactClass,
    AssertedFact,
    Blocker,
    BlockerKind,
    CaseRecord,
    EvidenceItem,
    EvidenceStatus,
    ExamPolicy,
    Exhibit,
    ItemAssessment,
    NarrativeDraft,
    ObligationRef,
    PriorAnswer,
    RegulatorRequest,
    ReleaseState,
    RequestItem,
    RequestTopic,
    ResponsePack,
    RetrievalQuery,
    SlaClock,
    WithholdRecord,
    worse,
)
from .pii import PII_PATTERNS
from .release_engine import (
    escalation,
    item_disposition,
    item_severity,
    pack_blockers,
    pack_completeness,
    pack_disposition,
    rank_blockers,
    release_blockers,
    required_approvals,
)
from .sla_clock import compute_clock

__all__ = ["ResponsePackService"]

#: Span names, module constants so the traced names are greppable and stable.
_ITEM_SPAN = "exam.assess_item"
_PACK_SPAN = "exam.assemble_pack"

#: Cap the citations carried on an outcome: enough to trace the answer, not the whole corpus.
_MAX_CITATIONS = 12

#: What an item records when the obligation register returns nothing. The explicit string and a
#: citation naming the register, never a guessed rule reference.
_NO_OBLIGATION = ObligationRef(
    obligation_id="obligations:none",
    rule_ref="",
    title="no obligation text available (obligation register returned none)",
    citation=Citation(
        source_id="obligations:none",
        title="Obligation register",
        snippet="the register returned no obligation for this topic and jurisdiction",
    ),
)


def _mask(text: str) -> str:
    return redact(text, PII_PATTERNS)


def _refusal(direction: Direction, reason: str) -> str:
    """What a refused screen says: the direction and the guardrail's reason, never the text."""
    return f"blocked by guardrail ({direction.value}): {reason}"


class _GenerationFailed(Exception):
    """The generation port itself could not answer: "no model text", like a guardrail refusal.

    Kept distinct from every other error so a call site degrades on exactly the two "no model
    text" outcomes and nothing else: an audit sink refusing a BLOCKED record must still fail
    the request rather than be absorbed into a degraded draft.
    """


class ResponsePackService:
    """Assemble a citation-backed, deadline-tracked response to a supervisory request."""

    def __init__(
        self,
        audit: AuditSinkPort,
        tracer: ObservabilityTracerPort,
        *,
        knowledge_base: KnowledgeBaseReadPort,
        obligations: ObligationsReadPort,
        evidence_packs: EvidencePackReadPort,
        generation: GenerationPort,
        guardrail: GuardrailPort,
        case_store: CaseStorePort,
        policy: ExamPolicy,
    ) -> None:
        self._audit = audit
        self._tracer = tracer
        self._knowledge_base = knowledge_base
        self._obligations = obligations
        self._evidence_packs = evidence_packs
        self._generation = generation
        self._guardrail = guardrail
        self._case_store = case_store
        self._policy = policy

    # ------------------------------------------------------------------ rule R1

    def _generate_screened(
        self, request: GenerationRequest, *, actor: str, action: str, job: str
    ) -> GenerationResponse:
        """One generation call, screened INPUT before and OUTPUT after (rule R1).

        Raises :class:`~.errors.GuardrailBlockedError` (already audited BLOCKED) when either
        screen refuses or cannot decide, and :class:`_GenerationFailed` when the model itself
        could not answer. Both mean "no model text": the caller degrades on either. Anything
        else, an audit sink refusing the BLOCKED record included, propagates.
        """
        prompt = self._screen(request.prompt, Direction.INPUT, actor=actor, action=action, job=job)
        try:
            response = self._generation.generate(replace(request, prompt=prompt))
        except Exception as exc:  # noqa: BLE001 - any model failure is "no model text"
            raise _GenerationFailed(str(exc)) from exc
        text = self._screen(response.text, Direction.OUTPUT, actor=actor, action=action, job=job)
        return replace(response, text=text)

    def _screen(self, text: str, direction: Direction, *, actor: str, action: str, job: str) -> str:
        """Screen one text in one direction; return the text to use from here on, or refuse.

        The returned text is the verdict's ``sanitized_text`` exactly as given, including an
        empty string: a screen that redacted everything has not asked for the original back.
        A block, and a guardrail that raised instead of deciding, both fail CLOSED after an
        audited BLOCKED record. When that record cannot be written either, the guardrail's own
        error propagates (with a note saying so) rather than a degradable refusal: a refusal
        nobody audited must fail the request, not vanish into a fallback draft.
        """
        try:
            verdict = self._guardrail.screen(text, direction)
        except Exception as exc:
            reason = f"guardrail unavailable ({type(exc).__name__})"
            try:
                self._audit_blocked(actor, action, job, direction, reason)
            except Exception as audit_exc:
                exc.add_note(f"the BLOCKED audit record could not be written: {audit_exc!r}")
                raise exc from None
            raise GuardrailBlockedError(_refusal(direction, reason)) from exc
        if not verdict.allowed or verdict.sanitized_text is None:
            reason = verdict.reason or "refused"
            self._audit_blocked(actor, action, job, direction, reason)
            raise GuardrailBlockedError(_refusal(direction, reason))
        return verdict.sanitized_text

    def _audit_blocked(
        self, actor: str, action: str, job: str, direction: Direction, reason: str
    ) -> None:
        """Audit a guardrail refusal BEFORE the call site degrades (rule R1/R2).

        Never carries the refused text, nor the item reference or question, because either may
        be the very thing refused: only which job was refused, in which direction, and why. No
        severity, because nothing has been scored when a generation call is screened.
        """
        self._audit.record(
            AuditEvent(
                action=action,
                actor=actor,
                decision=Decision.BLOCKED,
                severity=None,
                redacted_summary=_mask(f"{job} {direction.value} blocked: {reason}"),
                citations=(),
                timestamp=utcnow(),
            )
        )

    # ------------------------------------------------------------------ classification

    def propose_topic(
        self, item_ref: str, question: str, *, actor: str
    ) -> tuple[RequestTopic | None, tuple[ArtefactClass, ...]]:
        """Ask the model to SUGGEST a topic and artefacts for a free-text question (job 1 of four).

        The answer is a suggestion for a person, and nothing here consumes it: it enters no
        requirement, no retrieval query and no coverage state. That is not squeamishness about
        the model, it is what the topic does. The topic is rule A2's responsiveness key, so a
        candidate carrying a different one is dropped as out of scope: classify a governance
        question as credit risk and every governance document the firm holds is dropped and the
        pack states that no admissible document of that class was produced. A classification can
        therefore NARROW the answer, which is why the surface refuses an item with no declared
        topic and names this suggestion in the refusal rather than acting on it.

        An unparseable, unreachable or guardrail-refused classification returns ``(None, ())``,
        and the refusal then names no suggestion rather than inventing one. A guardrail refusal
        is audited BLOCKED first (rule R1).
        """
        request = narration.build_classify_request(item_ref, _mask(question))
        try:
            response = self._generate_screened(
                request, actor=actor, action="propose_topic", job="classify"
            )
        except (GuardrailBlockedError, _GenerationFailed):
            return None, ()
        return narration.parse_classification(response.text)

    # ------------------------------------------------------------------ the item

    def assess_item(
        self,
        request: RegulatorRequest,
        item: RequestItem,
        *,
        actor: str,
        tenant: str,
        as_of: date,
        prior_answers: Sequence[PriorAnswer] = (),
    ) -> ItemAssessment:
        """Assess one numbered question: the replayable unit of work.

        Every input is declared by the caller or read from a system of record. There is no model
        argument, because there is nothing a model may contribute to this call's outcome.

        The span wraps the whole unit and carries STRUCTURAL attributes only: the action and the
        actor, never the question, an item reference or a document title. A span is not a
        redacted sink.
        """
        with self._tracer.span(_ITEM_SPAN, action="assess_item", actor=actor):
            return self._assess_item(
                request,
                item,
                actor=actor,
                tenant=tenant,
                as_of=as_of,
                prior_answers=prior_answers,
            )

    def _assess_item(
        self,
        request: RegulatorRequest,
        item: RequestItem,
        *,
        actor: str,
        tenant: str,
        as_of: date,
        prior_answers: Sequence[PriorAnswer],
    ) -> ItemAssessment:
        item = self._redacted_item(request, item)
        blockers: list[Blocker] = []

        obligations = self._read_obligations(item.topic, request.jurisdiction)
        requirements = decompose(item, obligations)

        retrieval = self._knowledge_base.search(
            RetrievalQuery(
                item_ref=item.item_ref,
                topic=item.topic,
                artefacts=tuple(requirement.artefact for requirement in requirements),
                period_start=request.period_start,
                period_end=request.period_end,
                entitlements=request.entitlements,
            )
        )
        candidates = list(retrieval.items) + self._pack_candidates(item, obligations)
        candidates = [self._redacted_document(document) for document in candidates]

        waiver = self._case_store.waiver(request.waiver_ref, tenant) if request.waiver_ref else None
        evidence = assess_evidence(
            request,
            item,
            requirements,
            candidates,
            as_of=as_of,
            policy=self._policy,
            waiver=waiver,
            tenant=tenant,
            suppressed_by_entitlement=retrieval.suppressed_by_entitlement,
            suppressed_by_artefact=retrieval.suppressed_by_artefact,
        )
        blockers.extend(evidence.blockers)

        extension_on = (
            self._case_store.extension(request.extension_ref, tenant)
            if request.extension_ref
            else None
        )
        sla = compute_clock(
            request, item, as_of=as_of, policy=self._policy, extension_on=extension_on
        )
        if sla.breached:
            blockers.append(
                Blocker(
                    kind=BlockerKind.DEADLINE_BREACH,
                    severity=Severity.CRITICAL,
                    detail=(
                        f"the regulator's date {sla.due_on.isoformat()} has passed "
                        f"({sla.due_basis})"
                    ),
                    citation=item.citation,
                )
            )
        # N1 OWNERSHIP. An exam answer with no named owner has nobody to challenge when the
        # supervisor pushes back, so an unowned item can never be ON_TRACK.
        if not item.owner.strip():
            blockers.append(
                Blocker(
                    kind=BlockerKind.NO_OWNER,
                    severity=Severity.MEDIUM,
                    detail="the item is unassigned; no named owner can answer for it",
                    citation=item.citation,
                )
            )

        accepted = tuple(link for link in evidence.links if link.status is EvidenceStatus.ACCEPTED)
        exhibits = number_exhibits(item.item_ref, accepted)

        narrative, narrative_blockers = self._draft(
            item,
            exhibits,
            actor=actor,
            action="assess_item",
            completeness=evidence.completeness_pct,
            satisfied=evidence.satisfied_mandatory,
            total=evidence.total_mandatory,
            remaining=sla.business_days_remaining,
        )
        blockers.extend(narrative_blockers)

        facts = self._normalise(item, exhibits, actor=actor)
        consistency = check_consistency(facts, prior_answers)
        blockers.extend(consistency.blockers)

        disposition = item_disposition(blockers, sla, evidence.links)
        severity = item_severity(blockers, sla)
        escalate, decision = escalation(severity)
        ranked = rank_blockers(blockers)
        approvals = required_approvals(
            outcome_kind="item",
            instrument=request.instrument.value,
            severity=severity,
            policy=self._policy,
        )

        subject = f"{request.reference} item {item.item_ref}"
        case_ref = f"{request.request_id}:{item.item_ref}"
        summary = self._item_summary(
            subject,
            disposition.value,
            completeness=evidence.completeness_pct,
            satisfied=evidence.satisfied_mandatory,
            total=evidence.total_mandatory,
            sla=sla,
            blockers=ranked,
            withheld=evidence.withheld,
        )
        citations = self._citations(
            (item.citation, *(obligation.citation for obligation in obligations)),
            tuple(link.citation for link in accepted),
            consistency.citations,
        )

        assessment = ItemAssessment(
            item_ref=item.item_ref,
            subject=subject,
            case_ref=case_ref,
            topic=item.topic,
            owner=item.owner,
            sla=sla,
            narrative=narrative,
            disposition=disposition,
            severity=severity,
            decision=decision,
            summary=summary,
            requires_human_review=escalate,
            requirements=requirements,
            coverage=evidence.coverage,
            links=evidence.links,
            withheld=evidence.withheld,
            exhibits=exhibits,
            obligations=obligations,
            blockers=ranked,
            completeness_pct=evidence.completeness_pct,
            satisfied_mandatory=evidence.satisfied_mandatory,
            total_mandatory=evidence.total_mandatory,
            out_of_scope_dropped=evidence.out_of_scope_dropped,
            suppressed_by_entitlement=retrieval.suppressed_by_entitlement,
            # R1 RELEASE STATE. Every outcome carries this, and RELEASED has no producer here.
            release_state=ReleaseState.HELD_FOR_CHECKER,
            release_blockers=release_blockers(ranked, evidence.completeness_pct, self._policy),
            required_approvals=approvals,
            citations=citations,
        )
        self._write_audit("assess_item", actor, assessment.decision, severity, summary, citations)
        self.record_case(request, assessment, tenant=tenant)
        return assessment

    # ------------------------------------------------------------------ the pack

    def assemble_pack(
        self,
        request: RegulatorRequest,
        assessments: Sequence[ItemAssessment],
        *,
        actor: str,
        tenant: str,
        as_of: date,
    ) -> ResponsePack:
        """Roll the assessed items up into the production that leaves the firm.

        Rule P2: this always routes. ``requires_human_review`` is True and the decision is
        ESCALATED even for a fully on-track pack, because the contract is that a regulator
        response is maker-checker approved before it goes. A clean pack routes for APPROVAL
        rather than for rescue.
        """
        with self._tracer.span(_PACK_SPAN, action="assemble_pack", actor=actor):
            return self._assemble_pack(
                request, assessments, actor=actor, tenant=tenant, as_of=as_of
            )

    def _assemble_pack(
        self,
        request: RegulatorRequest,
        assessments: Sequence[ItemAssessment],
        *,
        actor: str,
        tenant: str,
        as_of: date,
    ) -> ResponsePack:
        items = tuple(assessments)
        extension_on = (
            self._case_store.extension(request.extension_ref, tenant)
            if request.extension_ref
            else None
        )
        sla = compute_clock(
            request, None, as_of=as_of, policy=self._policy, extension_on=extension_on
        )
        index = renumber_document_index(items)
        schedule = self._schedule(items)
        blockers = pack_blockers(items)
        completeness = pack_completeness(items)
        disposition = pack_disposition(items)
        severity = Severity.LOW
        for item in items:
            severity = worse(severity, item.severity)

        cover_note, _ = self._draft_cover_note(
            request, items, completeness, sla.business_days_remaining, index, actor=actor
        )
        subject = f"{request.reference} response pack"
        case_ref = request.request_id
        summary = self._pack_summary(subject, disposition.value, completeness, sla, blockers)
        citations: list[Citation] = [request.citation]
        for item in items:
            citations.extend(item.citations)

        pack = ResponsePack(
            request_id=request.request_id,
            subject=subject,
            case_ref=case_ref,
            regulator=request.regulator,
            reference=request.reference,
            instrument=request.instrument,
            as_of=as_of,
            sla=sla,
            cover_note=cover_note,
            disposition=disposition,
            severity=severity,
            # P2: unconditional. Nothing leaves the firm from this service.
            decision=Decision.ESCALATED,
            summary=summary,
            items=items,
            document_index=index,
            withholding_schedule=schedule,
            blockers=blockers,
            completeness_pct=completeness,
            release_state=ReleaseState.HELD_FOR_CHECKER,
            release_blockers=release_blockers(blockers, completeness, self._policy),
            required_approvals=required_approvals(
                outcome_kind="pack",
                instrument=request.instrument.value,
                severity=severity,
                policy=self._policy,
            ),
            requires_human_review=True,
            citations=self._citations(tuple(citations)),
        )
        self._write_audit(
            "assemble_pack", actor, Decision.ESCALATED, severity, summary, pack.citations
        )
        return pack

    # ------------------------------------------------------------------ the board

    def record_case(
        self,
        request: RegulatorRequest,
        assessment: ItemAssessment,
        *,
        tenant: str,
        review_ref: str = "",
    ) -> str:
        """Upsert the open-item board row for one assessed item.

        Called once by :meth:`assess_item` with no routing reference, and again by the surface
        once rule R8 has produced one, so the exam lead's board shows where an escalation went
        rather than an empty column that looks like an unwired seam.
        """
        return self._case_store.record(
            CaseRecord(
                request_id=request.request_id,
                item_ref=assessment.item_ref,
                tenant=tenant,
                owner=assessment.owner,
                disposition=assessment.disposition,
                band=assessment.sla.band,
                due_on=assessment.sla.due_on,
                internal_due_on=assessment.sla.internal_due_on,
                business_days_remaining=assessment.sla.business_days_remaining,
                completeness_pct=assessment.completeness_pct,
                review_ref=review_ref,
                acl_labels=request.entitlements,
                updated_at=utcnow(),
            )
        )

    def open_items(self, tenant: str, entitlements: frozenset[str]) -> tuple[CaseRecord, ...]:
        """The exam lead's board, filtered against the READER's entitlements in the query."""
        return self._case_store.open_items(tenant, entitlements)

    # ------------------------------------------------------------------ helpers

    def _redacted_item(self, request: RegulatorRequest, item: RequestItem) -> RequestItem:
        """Mask the question and build the item's own citation from the masked text."""
        question = _mask(item.question)
        return replace(
            item,
            question=question,
            citation=Citation(
                source_id=f"item:{request.request_id}:{item.item_ref}",
                title=f"{request.reference} item {item.item_ref}",
                # NOT truncated, unlike a citation that quotes a DOCUMENT. This is the caller's
                # own question, already masked, and it is the one place a reader can see that
                # masking happened at all. Cutting it at a fixed width hides the evidence.
                snippet=question,
            ),
        )

    @staticmethod
    def _redacted_document(document: EvidenceItem) -> EvidenceItem:
        """Mask a candidate's title and snippet before the engine, the model or the record."""
        return replace(document, title=_mask(document.title), snippet=_mask(document.snippet))

    def _read_obligations(
        self, topic: RequestTopic, jurisdiction: str
    ) -> tuple[ObligationRef, ...]:
        """Read the register, and mask it on the way in like every other inbound text.

        The register is an EXTERNAL system of record, not a fixture seam: a row naming the
        officer responsible for a control is an ordinary row, and its title and citation travel
        all the way onto the item's ``obligations`` and ``citations``, which is what the API
        serialises and the console renders. ``obligation_id`` is left alone because it is a
        lookup key: evidence packs are fetched by it, and masking a key breaks the join.
        """
        found = self._obligations.obligations_for(topic, jurisdiction)
        if not found:
            return (_NO_OBLIGATION,)
        return tuple(self._redacted_obligation(row) for row in found)

    @staticmethod
    def _redacted_obligation(obligation: ObligationRef) -> ObligationRef:
        """Mask every free-text field an obligation row carries, and its citation with it."""
        citation = obligation.citation
        return replace(
            obligation,
            rule_ref=_mask(obligation.rule_ref),
            title=_mask(obligation.title),
            citation=Citation(
                source_id=citation.source_id,
                title=_mask(citation.title),
                snippet=_mask(citation.snippet),
            ),
        )

    def _pack_candidates(
        self, item: RequestItem, obligations: Sequence[ObligationRef]
    ) -> list[EvidenceItem]:
        """Documents reused from assembled evidence packs, on identical admissibility terms."""
        collected: list[EvidenceItem] = []
        if item.evidence_pack_ref:
            collected.extend(self._evidence_packs.fetch(item.evidence_pack_ref).items)
        for obligation in obligations:
            if obligation.obligation_id == _NO_OBLIGATION.obligation_id:
                continue
            for pack in self._evidence_packs.packs_for(obligation.obligation_id):
                collected.extend(pack.items)
        return collected

    def _draft(
        self,
        item: RequestItem,
        exhibits: Sequence[Exhibit],
        *,
        actor: str,
        action: str,
        completeness: int,
        satisfied: int,
        total: int,
        remaining: int,
    ) -> tuple[NarrativeDraft, list[Blocker]]:
        """Rules G1 to G3: draft, or refuse to draft, and never repair.

        Rule R1: a guardrail refusal in either direction discards the model's draft WHOLE, like
        a model that could not be reached, and falls back to the deterministic paragraph.
        """
        if not exhibits:
            # G1 NO EVIDENCE, NO DRAFT. The generation port is NOT CALLED at all.
            return (
                NarrativeDraft(
                    drafted=False,
                    discard_reason="no admissible evidence was retrieved, so nothing was drafted",
                ),
                [
                    Blocker(
                        kind=BlockerKind.NO_ADMISSIBLE_EVIDENCE,
                        severity=Severity.HIGH,
                        detail=(
                            "no admissible evidence supports this item, so nothing was drafted"
                        ),
                        citation=item.citation,
                    )
                ],
            )

        request = narration.build_narrative_request(
            item_ref=item.item_ref,
            question=item.question,
            completeness_pct=completeness,
            satisfied=satisfied,
            total=total,
            business_days_remaining=remaining,
            exhibits=exhibits,
        )
        references = [exhibit.exhibit_no for exhibit in exhibits]
        fallback = narration.fallback_narrative(request.facts, exhibits)
        try:
            response = self._generate_screened(request, actor=actor, action=action, job="narrate")
        except GuardrailBlockedError as exc:
            return self._discarded(fallback, str(exc), item, exhibits)
        except _GenerationFailed as exc:  # a refusal is a rejected draft, never a crash
            return self._discarded(fallback, f"the generation port refused: {exc}", item, exhibits)

        verdict = narration.narrative_verdict(response.text, request.facts, references)
        if not verdict.ok:
            return self._discarded(fallback, verdict.reason, item, exhibits)

        parsed = narration.parse_narrative(response.text)
        proposed = parsed[1] if parsed is not None else ()
        return (
            NarrativeDraft(
                text=_mask(verdict.text),
                drafted=True,
                model_authored=True,
                grounded=True,
                proposed_artefacts=proposed,
                citations=tuple(exhibit.citation for exhibit in exhibits),
            ),
            [],
        )

    @staticmethod
    def _discarded(
        fallback: str, reason: str, item: RequestItem, exhibits: Sequence[Exhibit]
    ) -> tuple[NarrativeDraft, list[Blocker]]:
        """Discard the model's text WHOLE and fall back to the deterministic paragraph."""
        return (
            NarrativeDraft(
                text=fallback,
                drafted=True,
                model_authored=False,
                grounded=True,
                discard_reason=reason,
                citations=tuple(exhibit.citation for exhibit in exhibits),
            ),
            [
                Blocker(
                    kind=BlockerKind.UNGROUNDED_DRAFT,
                    severity=Severity.HIGH,
                    detail=f"the model draft was discarded: {reason}",
                    citation=item.citation,
                )
            ],
        )

    def _draft_cover_note(
        self,
        request: RegulatorRequest,
        items: Sequence[ItemAssessment],
        completeness: int,
        remaining: int,
        index: Sequence[Exhibit],
        *,
        actor: str,
    ) -> tuple[NarrativeDraft, list[Blocker]]:
        """The pack cover note, held to the same two grounding predicates as an item draft."""
        if not index:
            return (
                NarrativeDraft(
                    drafted=False,
                    discard_reason="the pack indexes no exhibit, so no cover note was drafted",
                ),
                [],
            )
        stub = RequestItem(
            item_ref=request.request_id,
            question=f"Cover note for {request.reference}",
            topic=items[0].topic if items else RequestTopic.GOVERNANCE,
            citation=request.citation,
        )
        return self._draft(
            stub,
            index,
            actor=actor,
            action="assemble_pack",
            completeness=completeness,
            satisfied=len(items),
            total=len(items),
            remaining=remaining,
        )

    @staticmethod
    def _schedule(items: Sequence[ItemAssessment]) -> tuple[WithholdRecord, ...]:
        """The consolidated withholding schedule, in item order then artefact order."""
        rows: list[WithholdRecord] = []
        for item in items:
            rows.extend(
                sorted(item.withheld, key=lambda record: (record.artefact.value, record.doc_id))
            )
        return tuple(rows)

    @staticmethod
    def _citations(*groups: Sequence[Citation]) -> tuple[Citation, ...]:
        """Deduplicate by source id, preserve order, and cap what travels."""
        seen: dict[str, Citation] = {}
        for group in groups:
            for citation in group:
                if not citation.source_id or citation.source_id in seen:
                    continue
                seen[citation.source_id] = citation
        return tuple(seen.values())[:_MAX_CITATIONS]

    def _normalise(
        self, item: RequestItem, exhibits: Sequence[Exhibit], *, actor: str
    ) -> tuple[AssertedFact, ...]:
        """Ask the model to normalise the produced exhibits into asserted facts (job 2 of four).

        The ENGINE compares them; the model only extracts them. An unrecognised key is NOT
        filtered here: rule X1 raises a blocker for it, because dropping it silently is exactly
        what a model that renamed a key would buy.

        Rule R1: a guardrail refusal (audited BLOCKED) yields no facts, like an unreachable
        model: the exhibit titles and snippets in this prompt are retrieved text, and a refused
        extraction contributes nothing rather than part of an answer.
        """
        if not exhibits:
            return ()
        request = narration.build_normalise_request(
            item.item_ref, exhibits, sorted(KNOWN_ASSERTION_KEYS)
        )
        try:
            response = self._generate_screened(
                request, actor=actor, action="assess_item", job="normalise"
            )
        except (GuardrailBlockedError, _GenerationFailed):
            return ()
        by_reference = {exhibit.exhibit_no: exhibit for exhibit in exhibits}
        out: list[AssertedFact] = []
        for key, value, reference in narration.parse_facts(response.text):
            exhibit = by_reference.get(reference)
            out.append(
                AssertedFact(
                    assertion_key=key,
                    assertion_value=_mask(value),
                    citation=exhibit.citation if exhibit is not None else item.citation,
                )
            )
        return tuple(out)

    @staticmethod
    def _item_summary(
        subject: str,
        disposition: str,
        *,
        completeness: int,
        satisfied: int,
        total: int,
        sla: SlaClock,
        blockers: Sequence[Blocker],
        withheld: Sequence[WithholdRecord],
    ) -> str:
        """The one line that reaches the audit record and the review console, already masked.

        It carries the due basis, the calendar version and every withhold basis on purpose: those
        are the three things a supervisor asks about years later, and a trail that does not carry
        them cannot answer without the running system.
        """
        kinds = ",".join(blocker.kind.value for blocker in blockers) or "none"
        bases = ";".join(f"{record.doc_id}:{record.basis_rule}" for record in withheld) or "none"
        return _mask(
            f"{subject}: {disposition} "
            f"completeness={completeness}% ({satisfied}/{total} mandatory) "
            f"due={sla.due_on.isoformat()} due_basis={sla.due_basis} "
            f"calendar={sla.calendar_id}@{sla.calendar_version} "
            f"blockers={kinds} withheld={bases}"
        )

    @staticmethod
    def _pack_summary(
        subject: str,
        disposition: str,
        completeness: int,
        sla: SlaClock,
        blockers: Sequence[Blocker],
    ) -> str:
        kinds = ",".join(blocker.kind.value for blocker in blockers) or "none"
        return _mask(
            f"{subject}: {disposition} completeness={completeness}% "
            f"due={sla.due_on.isoformat()} due_basis={sla.due_basis} "
            f"calendar={sla.calendar_id}@{sla.calendar_version} "
            f"blockers={kinds} release=held_for_checker"
        )

    def _write_audit(
        self,
        action: str,
        actor: str,
        decision: Decision,
        severity: Severity,
        summary: str,
        citations: Sequence[Citation],
    ) -> None:
        """Redact BEFORE the write: the raw identifiers never reach the WORM record."""
        self._audit.record(
            AuditEvent(
                action=action,
                actor=actor,
                decision=decision,
                severity=severity,
                redacted_summary=_mask(summary),
                citations=tuple(
                    Citation(
                        source_id=citation.source_id,
                        title=_mask(citation.title),
                        snippet=_mask(citation.snippet),
                    )
                    for citation in citations
                ),
                timestamp=utcnow(),
            )
        )
