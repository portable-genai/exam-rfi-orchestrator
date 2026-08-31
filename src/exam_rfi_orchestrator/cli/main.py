"""Minimal stdlib CLI: assemble one response pack from a request file (argparse, no extra deps).

The CLI resolves identity through the bound identity adapter exactly as the API does, so the
entitlements that decide what may be retrieved come from a resolved principal and never from the
file. Rule R8 applies here too: every escalated item and the pack itself are routed in the same
invocation that produced them.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from hex_service_kit.identity import RequestContext
from hex_service_kit.logging import configure_logging

from ..config import build_container
from ..domain.kernel import utcnow
from ..domain.models import (
    ArtefactClass,
    Instrument,
    PriorAnswer,
    RegulatorRequest,
    RequestItem,
    RequestTopic,
)
from ..services import build_service

#: Service name on every log line, matching what the API and the tracer report.
_SERVICE_NAME = "exam-rfi-orchestrator"


def _date(value: Any) -> date:
    return date.fromisoformat(str(value))


def _optional_date(value: Any) -> date | None:
    return None if value in (None, "") else _date(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exam_rfi_orchestrator")
    sub = parser.add_subparsers(dest="command", required=True)

    respond = sub.add_parser("respond", help="Assemble one response pack from a request file.")
    respond.add_argument("request_file", help="JSON file in the POST /v1/response-pack shape.")
    respond.add_argument(
        "--persona",
        default="",
        help="Seeded dev persona to resolve identity as (local profile only).",
    )

    args = parser.parse_args(argv)
    container = build_container()
    # Idempotent: a process that is both an API app and a CLI entry point configures once.
    configure_logging(container.settings.profile, service=_SERVICE_NAME)

    if args.command != "respond":  # pragma: no cover - argparse requires a subcommand
        return 2

    payload = json.loads(Path(args.request_file).read_text(encoding="utf-8"))
    headers = {"x-dev-persona": args.persona} if args.persona else {}
    principal = container.identity.resolve(RequestContext(headers=headers))
    tenant = principal.tenant or container.settings.tenant
    policy = container.settings.policy
    service = build_service(container)

    jurisdiction = str(payload["jurisdiction"])
    request = RegulatorRequest(
        request_id=str(payload["request_id"]),
        regulator=str(payload["regulator"]),
        reference=str(payload["reference"]),
        instrument=Instrument(str(payload["instrument"])),
        regime=str(payload["regime"]),
        jurisdiction=jurisdiction,
        received_on=_date(payload["received_on"]),
        period_start=_date(payload["period_start"]),
        period_end=_date(payload["period_end"]),
        regulator_due_on=_optional_date(payload.get("regulator_due_on")),
        extension_ref=str(payload.get("extension_ref", "")),
        waiver_ref=str(payload.get("waiver_ref", "")),
        entitlements=frozenset(principal.entitlement_principals()),
        permitted_transfer_jurisdictions=policy.permitted_transfers(jurisdiction),
    )
    as_of = _optional_date(payload.get("as_of")) or utcnow().date()
    prior_answers = tuple(
        PriorAnswer(
            answer_id=str(row["answer_id"]),
            submitted_on=_date(row["submitted_on"]),
            item_ref=str(row["item_ref"]),
            topic=RequestTopic(str(row["topic"])),
            assertion_key=str(row["assertion_key"]),
            assertion_value=str(row["assertion_value"]),
        )
        for row in payload.get("prior_answers", [])
    )

    assessments = []
    for row in payload["items"]:
        item = RequestItem(
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
        assessment = service.assess_item(
            request,
            item,
            actor=principal.actor,
            tenant=tenant,
            as_of=as_of,
            prior_answers=[p for p in prior_answers if p.item_ref == item.item_ref],
        )
        print(
            f"{assessment.item_ref}: {assessment.disposition.value} "
            f"{assessment.completeness_pct}% ({assessment.severity.value})"
        )
        if assessment.requires_human_review:
            # Rule R8 on the CLI path too: the same escalation, the same router. A surface that
            # only printed the flag would be a second place for an escalation to stop.
            reference = container.review_router.route(
                assessment, maker=principal.actor, tenant=tenant
            )
            service.record_case(request, assessment, tenant=tenant, review_ref=reference)
            print(f"  routed to human review: {reference}")
        assessments.append(assessment)

    pack = service.assemble_pack(
        request, assessments, actor=principal.actor, tenant=tenant, as_of=as_of
    )
    print(
        f"pack {pack.request_id}: {pack.disposition.value} {pack.completeness_pct}% "
        f"release={pack.release_state.value} approvals={pack.required_approvals}"
    )
    # P2: a pack always routes, including a clean one.
    pack_ref = container.review_router.route(pack, maker=principal.actor, tenant=tenant)
    print(f"  routed for approval: {pack_ref}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
