"""The scripted, offline demo: the REAL services, synthetic data, an audit-first output view.

This is the demo as CODE (practices check F1), not a slide deck and not a recording. Every step
below drives the actual response-pack service, the actual fixture corpus and obligation register,
the actual hash-chained audit store and the actual rule-R8 review router over the ``local``
profile, so a step that stops being true stops passing rather than stops being mentioned.

Three properties make it worth running in front of somebody:

* **Nothing is faked.** No stub service, no pre-baked JSON. The deadlines, the coverage states,
  the withholding bases, the exhibit numbers, the routing references and the tamper verdict are
  produced by the shipped code.
* **It is bounded.** The demo proves an offline, single-process seam. It does not prove a live
  knowledge base, retrieval recall, a running on-premises deployment, or that any shipped policy
  number is correct in law. See ``DEMO.md`` for the full bounds.
* **It is replayable.** Same inputs, same output, every time, because every consequential step is
  deterministic and the evaluation date is passed IN rather than read from a clock.

Run it directly to write the audit-view JSON, then render that JSON to static pages::

    make demo-static

or drive it one step at a time with ``demo_server.py`` and ``walkthrough.py`` (``make demo``).

Every party, address and identifier here is obviously fictional: an invented supervisor that
carries FICTIONAL in its own name, ``.example`` domains, RFC 5737 and RFC 3849 literals, and a
synthetic national id that exists only to prove redaction happened.

MAINTAINER NOTE: this file is rendered from a template, so no line may change length with the
package or service name. Every cookiecutter value is bound to a short module constant below and
referenced through it, and every import line is short enough that a long package name cannot
push it past the formatter's limit.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from hex_service_kit.audit import HashChainedAuditLog
from hex_service_kit.identity import RequestContext
from hex_service_kit.serialization import to_jsonable

from exam_rfi_orchestrator.config import (
    Settings,
    build_container,
)
from exam_rfi_orchestrator.domain import (
    kernel,
    models,
)
from exam_rfi_orchestrator.domain.pii import (
    JURISDICTIONS,
)
from exam_rfi_orchestrator.services import (
    build_service,
)


def loaded_cloud_sdks() -> tuple[str, ...]:
    """Every managed-SDK module currently importable in THIS interpreter, sorted.

    Public because the demo, the walkthrough's checks and the test suite all ask the same
    question and must not each answer it slightly differently.
    """
    return tuple(sorted(name for name in sys.modules if name.split(".")[0] == "google"))


#: Rendered identity, bound once so no other line's length depends on how long a name is.
SERVICE_NAME = "Regulatory Exam and RFI Orchestrator"
CATALOG_ID = "Cop2"
REPOSITORY = "exam-rfi-orchestrator"

# --------------------------------------------------------------------------------------- #
# Synthetic data. Fictional parties, .example domains, RFC 5737 / RFC 3849 literals only.
# --------------------------------------------------------------------------------------- #

#: The VERIFIED principal the demo attributes work to. A client never asserts this.
ACTOR = "analyst@bank.example"
TENANT = "demo-bank"

#: What the verified principal is entitled to read. Derived server-side in every real surface;
#: named here because the demo drives the service directly rather than through the API.
ENTITLEMENTS = frozenset({"group:analyst", "group:risk", "group:approver"})

#: The evaluation date, passed IN so the clocks are byte-stable. The API resolves its own and
#: echoes it; the demo and the evaluation pin one so a rehearsal today matches one next month.
AS_OF = date(2027, 3, 15)

#: A planted identifier, so the redaction panel has an independent literal to look for rather
#: than trusting the pattern pack to agree with itself. Checksum-valid, which the SG row needs.
PLANTED_NRIC = "S1234567D"

#: A snippet from the privileged memo in the fixture corpus. The redaction beat asserts this
#: never appears anywhere, which is a different claim from "the identifier was masked".
PRIVILEGED_PHRASE = "prepared for the purpose of legal proceedings"

REGULATOR = "Meridian Prudential Authority (FICTIONAL)"
REFERENCE = "MPA-FICTIONAL/EX/2027/0014"
SKILLED_PERSON_REFERENCE = "MPA-FICTIONAL/EX/2027/0041"


def _request(**overrides: Any) -> models.RegulatorRequest:
    base: dict[str, Any] = {
        "request_id": "EXAM-2027-0014",
        "regulator": REGULATOR,
        "reference": REFERENCE,
        "instrument": models.Instrument.RFI,
        "regime": "supervisory-information-request",
        "jurisdiction": "SG",
        "received_on": date(2027, 3, 1),
        "period_start": date(2026, 4, 1),
        "period_end": date(2027, 2, 28),
        "regulator_due_on": date(2027, 4, 30),
        "entitlements": ENTITLEMENTS,
    }
    base.update(overrides)
    return models.RegulatorRequest(**base)


ROUTINE_ITEM = models.RequestItem(
    item_ref="1.a",
    question=(
        "Provide the financial-crime policy in force during the review period and the "
        "transaction-monitoring management information reported to the board for the two "
        "quarters ending in the period. Direct any queries to rfi.desk@meridian-bank.example."
    ),
    topic=models.RequestTopic.AML_FINANCIAL_CRIME,
    requested_artefacts=(
        models.ArtefactClass.POLICY,
        models.ArtefactClass.MANAGEMENT_INFORMATION,
    ),
    owner="Head of Financial Crime (FICTIONAL)",
)

ESCALATING_ITEM = models.RequestItem(
    item_ref="2.c",
    question=(
        "Provide the results of independent testing of sanctions screening for the review "
        "period and the remediation status of every exception raised. Case officer contact "
        "casework@meridian-bank.example."
    ),
    topic=models.RequestTopic.TECHNOLOGY_AND_CYBER,
    requested_artefacts=(models.ArtefactClass.CONTROL_TEST_RESULT,),
    owner="",
    item_due_on=date(2027, 3, 19),
)

PII_ITEM = models.RequestItem(
    item_ref="3.a",
    question=(
        "Provide all internal correspondence and legal analysis concerning the payments outage "
        "in the review period, together with the customer files of every affected client. "
        "Complainant NRIC " + PLANTED_NRIC + ", contacted from 192.0.2.10 and 2001:db8::7."
    ),
    topic=models.RequestTopic.DATA_PRIVACY,
    requested_artefacts=(models.ArtefactClass.ISSUE_LOG, models.ArtefactClass.CUSTOMER_FILE),
    owner="Data Protection Officer (FICTIONAL)",
)

SKILLED_PERSON_ITEM = models.RequestItem(
    item_ref="2",
    question=(
        "Provide the terms of reference and the governance arrangements for the skilled person "
        "review, together with the board minute approving them. Programme mailbox "
        "s166.programme@meridian-bank.example."
    ),
    topic=models.RequestTopic.GOVERNANCE,
    owner="Skilled Person Programme Office (FICTIONAL)",
)

#: The named regimes and the jurisdiction calendars this demo's requests actually use. The
#: opened beat asserts every one is present in the configured policy, so a demo cannot open over
#: a policy block that happens to be missing the row the next beat needs.
REQUIRED_REGIMES: tuple[str, ...] = ("supervisory-information-request", "skilled-person-review")
REQUIRED_CALENDARS: tuple[str, ...] = ("SG",)

#: The prior submission the escalating item contradicts. This is the control an exam lead cannot
#: get from a keyword engine and cannot get from a reviewer reading a long pack late at night.
PRIOR_ANSWERS: tuple[models.PriorAnswer, ...] = (
    models.PriorAnswer(
        answer_id="PRIOR-FICTIONAL-2026-08",
        submitted_on=date(2026, 8, 14),
        item_ref="2.c",
        topic=models.RequestTopic.TECHNOLOGY_AND_CYBER,
        assertion_key="sanctions_screening_vendor",
        assertion_value="Northwind Screening (FICTIONAL)",
    ),
)


# --------------------------------------------------------------------------------------- #
# The presenter arc
# --------------------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Step:
    """One presenter beat: what it shows, and the sentence the presenter reads aloud."""

    key: str
    label: str
    narration: str


#: The scripted arc, in order. ``walkthrough.py`` asserts the server reaches each key in turn
#: and carries an expectation per key, so a step added here without an expectation there fails
#: the self-test rather than silently extending the demo.
STEPS: tuple[Step, ...] = (
    Step(
        key="opened",
        label="Bound offline, and the release policy is configuration",
        narration=(
            "The whole stack comes up from one settings file with no cloud project and no "
            "credentials, which is why this runs on a plane. Look at the policy panel rather "
            "than the binding panel. The review buffer, the amber and red day counts, the "
            "staleness window, the tags we will never produce and the holiday calendar with its "
            "version are all read from configuration. They are your numbers, not ours: changing "
            "one is a configuration review with an audit trail, not a release. And note what the "
            "regime register says for an exam request list: no fixed response window, the "
            "notice's own date governs. That row exists so nobody hardcodes a number they read "
            "somewhere."
        ),
    ),
    Step(
        key="routine",
        label="A fully evidenced item: decided, cited, indexed, and no reviewer woken",
        narration=(
            "This is what a good item looks like, and the boring part is worth dwelling on. The "
            "due date, the completeness number and the band are stdlib arithmetic over recorded "
            "inputs, so they replay identically years from now, and the exhibit numbers came out "
            "of a sort rather than a model, which is why a resubmission diffs cleanly against "
            "the original. The model wrote the sentence and cited only documents that were "
            "actually retrieved and actually admissible. Nothing is routed for this item. "
            "Manufacturing a review for a clean item is how you train an exam lead to approve "
            "without reading, and then the one that mattered goes out too."
        ),
    ),
    Step(
        key="escalation",
        label="A consequential item: cited blockers, escalated AND routed",
        narration=(
            "Separate reasons, each cited, each replayable. Look at the last one. The firm told "
            "this regulator in an earlier submission that screening ran on one vendor, and the "
            "evidence behind this answer says another. No keyword engine finds that, and no "
            "reviewer reading a long pack late at night finds it either. Note also what did not "
            "happen: the flag alone is not the escalation. The reference on screen is where it "
            "went, and had the console been unreachable the managed router would have refused "
            "rather than swallowed it. And notice what the reviewer is handed, which is not a "
            "score but the names of the rules that fired. A reviewer who cannot see why cannot "
            "check anything."
        ),
    ),
    Step(
        key="redaction",
        label="Masked on the way in, withheld by rule, and recorded either way",
        narration=(
            "Two failures avoided here, and people conflate them. Masking is about the record: "
            "it happens on the way in, because redacting after an immutable write is too late. "
            "Withholding is a legal call: the engine names the basis, a lawyer decides, and the "
            "schedule still tells the regulator that a document exists and why it is not "
            "produced, because a document silently dropped from a production is how an honest "
            "late answer becomes a misleading one. Now look at the restricted-filing row: "
            "identifier and basis, no title. In several regimes the existence of that filing is "
            "itself restricted. That asymmetry is a policy setting in your configuration, and "
            "your counsel should confirm it before you deploy. This engine flags privilege; it "
            "never decides it."
        ),
    ),
    Step(
        key="review_queue",
        label="What the checker receives, and the exam lead's open-item board",
        narration=(
            "This is the maker-checker. The maker is the verified principal, never anything the "
            "browser sent. The pack routes even though one item in it is clean, because the "
            "contract is that a regulator response is approved before it leaves, so a good pack "
            "routes for approval rather than for rescue. Two approvals on the skilled-person "
            "item as well, and that item never escalated: dual control and escalation are "
            "different questions, and the engine is the single place that answers the first, so "
            "the console and the service can no longer disagree. Nothing leaves the firm from "
            "this process: the console records the approvals and an operator releases. There is "
            "no code path in this service that returns released."
        ),
    ),
    Step(
        key="audit",
        label="The trail answers the supervisor's four questions, and exports in an open format",
        narration=(
            "Append-only and hash-chained, with the head anchored on a different volume under "
            "different credentials. That anchor is not decoration: the chain alone cannot see a "
            "truncated tail, because dropping the newest rows leaves a shorter chain that "
            "verifies perfectly. It exports to JSON Lines with the hashes, so a consumer "
            "re-verifies the trail without ever running this codebase. What you are exporting "
            "matters more here than in most systems: it is the reasoning behind every document "
            "you declined to produce, in a format a supervisor's own tooling can check."
        ),
    ),
    Step(
        key="tamper",
        label="A rewritten withhold basis is detected, not merely discouraged",
        narration=(
            "We picked that field deliberately. If somebody can quietly change the record of "
            "what you withheld and why, every other control in this demo is decoration. File "
            "access beats a database trigger, and a store that claims otherwise is describing a "
            "policy rather than a control. The guarantee is tamper-evident, not tamper-proof: a "
            "rewrite cannot pass unnoticed, and the report names which record broke, so an "
            "auditor knows exactly where the trustworthy part of the trail ends and which part "
            "of the production to re-derive."
        ),
    ),
    Step(
        key="portability",
        label="The exit path fails fast rather than answering a regulator with silence",
        narration=(
            "One environment variable, no domain module touched. This matters more here than in "
            "most verticals. A retrieval seam returning an empty tuple instead of raising would "
            "not look broken: it would look like a firm that holds no responsive evidence, and "
            "that is what would go to the supervisor over somebody's signature. So it raises. A "
            "placeholder that succeeds quietly turns an unwired system into a false statement. "
            "What this proves is bounded: every port is swappable and every unimplemented seam "
            "is named. It does not prove a running on-premises deployment exists, and we will "
            "not claim it does."
        ),
    ),
)

STEP_KEYS: tuple[str, ...] = tuple(step.key for step in STEPS)


# --------------------------------------------------------------------------------------- #
# Panels: the audit-first output view (the result, its evidence, the findings, what is next)
# --------------------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Row:
    """One labelled fact in a panel. ``tone`` drives the colour, never the meaning."""

    label: str
    value: str
    tone: str = ""


@dataclass(frozen=True, slots=True)
class Panel:
    """One block of the output view: a title, labelled facts, and an interpretation."""

    title: str
    rows: tuple[Row, ...] = ()
    note: str = ""
    tone: str = ""


@dataclass(frozen=True, slots=True)
class StepResult:
    """Everything one step produced, ready to render or to assert against."""

    key: str
    label: str
    narration: str
    panels: tuple[Panel, ...] = ()
    facts: dict[str, Any] = field(default_factory=dict)


Produced = tuple[list[Panel], dict[str, Any]]


class DemoRun:
    """A live demo, advanced one step at a time over the real services.

    The run owns a working directory holding the durable audit store and its external anchor.
    They are separate directories on purpose: an anchor that lives beside the store it witnesses
    is rewritten by whatever rewrites the store.
    """

    def __init__(self, workdir: Path | None = None) -> None:
        # What was ALREADY loaded before this run began. The offline claim is that the demo
        # imports no cloud SDK, and in a live `python scripts/demo.py` nothing else has loaded
        # one, so the delta and the absolute set are the same list. In a shared pytest process
        # they are not: any other module in the suite may legitimately have imported google for
        # its own reasons (the IAP negative matrix does), and a claim measured as an absolute
        # would then be decided by test ordering rather than by the demo. The absolute form of
        # the claim is still made, in fresh interpreters, by `scripts/portability_demo.py`, by
        # the headless walkthrough and by `tests/unit/test_demo_surface.py`.
        self._cloud_sdk_before = frozenset(loaded_cloud_sdks())
        self._tempdir: tempfile.TemporaryDirectory[str] | None = None
        if workdir is None:
            self._tempdir = tempfile.TemporaryDirectory(prefix="demo-run-")
            workdir = Path(self._tempdir.name)
        self.workdir = workdir
        self.audit_path = workdir / "store" / "audit.sqlite3"
        self.anchor_path = workdir / "anchor" / "head.json"
        # The audit store creates its own parent; the ANCHOR does not, because it is meant to
        # live on a volume somebody provisioned deliberately rather than one a library invented.
        # An operator therefore has to create that directory too; the demo does it here so the
        # first run of `make demo` in a fresh checkout does not fail on a missing path.
        self.anchor_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings = Settings(
            profile="local",
            audit_path=str(self.audit_path),
            audit_anchor_path=str(self.anchor_path),
            tenant=TENANT,
        )
        self.container = build_container(self.settings)
        self.policy = self.settings.policy
        self.service = build_service(self.container)
        self.request = _request(
            permitted_transfer_jurisdictions=self.policy.permitted_transfers("SG")
        )
        self.skilled_person_request = _request(
            request_id="EXAM-2027-0041",
            reference=SKILLED_PERSON_REFERENCE,
            instrument=models.Instrument.S166_SKILLED_PERSON,
            regime="skilled-person-review",
            permitted_transfer_jurisdictions=self.policy.permitted_transfers("SG"),
        )
        self.results: list[StepResult] = []
        self.assessments: list[models.ItemAssessment] = []
        self.items = 0
        self.escalated = 0
        self.routed = 0
        self.chain_ok = True
        self.pack: models.ResponsePack | None = None
        self._perform(STEPS[0])

    # -------------------------------------------------------------- control

    @property
    def index(self) -> int:
        """Index of the step most recently performed."""
        return len(self.results) - 1

    @property
    def done(self) -> bool:
        return len(self.results) >= len(STEPS)

    def advance(self) -> StepResult:
        """Perform the next step, or re-return the last one when the arc is finished."""
        if self.done:
            return self.results[-1]
        return self._perform(STEPS[len(self.results)])

    def run_to_end(self) -> None:
        while not self.done:
            self.advance()

    def _perform(self, step: Step) -> StepResult:
        handler: Callable[[], Produced] = getattr(self, "_step_" + step.key)
        panels, facts = handler()
        result = StepResult(
            key=step.key,
            label=step.label,
            narration=step.narration,
            panels=tuple(panels),
            facts=facts,
        )
        self.results.append(result)
        return result

    # -------------------------------------------------------------- steps

    def _step_opened(self) -> Produced:
        bindings = [
            Row(port, self.settings.adapters[port][self.settings.profile].split(":")[-1])
            for port in sorted(self.settings.adapters)
        ]
        profiles = sorted({name for table in self.settings.adapters.values() for name in table})
        sdk = [name for name in loaded_cloud_sdks() if name not in self._cloud_sdk_before]
        policy = self.policy
        deployment = Panel(
            title="Deployment",
            rows=(
                Row("Service", SERVICE_NAME),
                Row("Catalog id", CATALOG_ID),
                Row("Profile", self.settings.profile, "ok"),
                Row("Profiles bound for every port", ", ".join(profiles)),
                Row("Residency region", self.settings.region),
                Row("Jurisdiction PII packs", ", ".join(JURISDICTIONS)),
                Row("Model", self.settings.generator_model),
            ),
            note=(
                "One environment variable selects the adapter family for every port. Nothing "
                "below was edited to make the service run offline."
            ),
        )
        adapters = Panel(
            title="Bound adapters",
            rows=tuple(bindings),
            note="The binding map lives in config/settings.yaml, not in the code.",
        )
        windows = ", ".join(
            f"{name}={days}d" for name, days in sorted(policy.response_windows.items())
        )
        bands = ", ".join(f"<={ceiling}d {band.value}" for ceiling, band in policy.sla_bands)
        calendars = ", ".join(
            f"{cal.id}@{cal.version}" for cal in sorted(policy.calendars.values(), key=_calendar_id)
        )
        regimes = ", ".join(
            f"{ref.regime}={ref.fixed_response_window_days}d"
            for ref in sorted(policy.regime_register.values(), key=_regime_id)
        )
        policy_panel = Panel(
            title="The policy, read from configuration",
            rows=(
                Row("Response windows (business days)", windows),
                Row("Review buffer", str(policy.review_buffer_business_days) + " business days"),
                Row(
                    "Extension notice",
                    str(policy.extension_notice_business_days) + " business days",
                ),
                Row("SLA band ceilings", bands),
                Row("Staleness window", str(policy.evidence_max_age_days) + " days"),
                Row("Completeness floor for release", str(policy.min_completeness_pct_for_release)),
                Row("Never produced", _tags(policy.hard_withhold_tags)),
                Row("Produced with no title", _tags(policy.silent_withhold_tags)),
                Row("Transfer matrix", _matrix(policy)),
                Row("Named regimes (fixed window)", regimes, "ok"),
                Row("Calendars", calendars),
                Row("Dual control", ", ".join(policy.dual_control_instruments) + ", pack"),
            ),
            note=(
                "Every number here is the adopter's, read from config/settings.yaml and owned by "
                "their counsel. Every shipped regime row fixes NO response window, so the "
                "notice's own date governs; the cap rule ships live so an adopter configures a "
                "window rather than patching code."
            ),
            tone="ok",
        )
        findings = Panel(
            title="Findings",
            rows=(
                Row("Cloud SDK modules imported", ", ".join(sdk) or "none", "bad" if sdk else "ok"),
                Row("Credentials required", "none", "ok"),
                Row("Network required", "none", "ok"),
            ),
            note=(
                "The managed adapters import their SDK lazily, so this profile runs with none "
                "installed at all."
            ),
            tone="bad" if sdk else "ok",
        )
        facts = {
            "profile": self.settings.profile,
            "sdk_modules": sdk,
            "profiles": profiles,
            "generator_model": self.settings.generator_model,
            "response_windows": sorted(policy.response_windows),
            "regimes": sorted(policy.regime_register),
            "calendars": sorted(policy.calendars),
            "calendar_versions": sorted(cal.version for cal in policy.calendars.values()),
            "band_ceilings": [ceiling for ceiling, _band in policy.sla_bands],
            "hard_withhold_tags": [tag.value for tag in policy.hard_withhold_tags],
            "silent_withhold_tags": [tag.value for tag in policy.silent_withhold_tags],
            "min_completeness_pct_for_release": policy.min_completeness_pct_for_release,
        }
        return [deployment, adapters, policy_panel, findings], facts

    def _step_routine(self) -> Produced:
        panels, facts = self._item_panels(ROUTINE_ITEM, expect_routing=False)
        assessment = self.assessments[-1]
        # Determinism, shown rather than asserted in prose: the same inputs through a second,
        # independent service instance must produce the same annex.
        replay = build_service(build_container(Settings(profile="local", tenant=TENANT)))
        again = replay.assess_item(
            self.request,
            ROUTINE_ITEM,
            actor=ACTOR,
            tenant=TENANT,
            as_of=AS_OF,
        )
        same = [e.exhibit_no for e in assessment.exhibits] == [e.exhibit_no for e in again.exhibits]
        cited = _cited_references(assessment.narrative.text)
        known = {exhibit.exhibit_no for exhibit in assessment.exhibits}
        grounded = bool(cited) and cited <= known
        panels.append(
            Panel(
                title="Deterministic by construction",
                rows=(
                    Row("Exhibit numbers", ", ".join(sorted(known))),
                    Row(
                        "Reproduced on a second run",
                        "yes" if same else "NO",
                        "ok" if same else "bad",
                    ),
                    Row(
                        "Every cited exhibit is in this item's index",
                        "yes" if grounded else "NO",
                        "ok" if grounded else "bad",
                    ),
                    Row("Draft written by", _author(assessment.narrative.model_authored)),
                ),
                note=(
                    "The numbering comes out of a sort, so a resubmission diffs cleanly against "
                    "the original. The model wrote the sentence and cited only what was indexed."
                ),
                tone="ok" if same and grounded else "bad",
            )
        )
        facts["exhibits_reproduce"] = same
        facts["narrative_grounded"] = grounded
        return panels, facts

    def _step_escalation(self) -> Produced:
        panels, facts = self._item_panels(
            ESCALATING_ITEM, expect_routing=True, prior_answers=PRIOR_ANSWERS
        )
        assessment = self.assessments[-1]
        known_kinds = {kind.value for kind in models.BlockerKind}
        named = all(kind.value in known_kinds for kind in assessment.release_blockers)
        conflict = [
            blocker
            for blocker in assessment.blockers
            if blocker.kind is models.BlockerKind.PRIOR_ANSWER_CONFLICT
        ]
        panels.append(
            Panel(
                title="What the reviewer is handed",
                rows=tuple(
                    Row(blocker.kind.value, blocker.detail, "bad")
                    for blocker in assessment.blockers
                )
                or (Row("blockers", "NONE", "bad"),),
                note=(
                    "Named rules, not a score. A reviewer who cannot see which rule fired cannot "
                    "check anything, and a free-text reason is a decision nobody can replay."
                ),
                tone="bad",
            )
        )
        facts["release_blockers_named"] = named
        facts["prior_answer_conflict"] = bool(conflict)
        facts["release_blockers"] = [kind.value for kind in assessment.release_blockers]
        return panels, facts

    def _step_redaction(self) -> Produced:
        panels, facts = self._item_panels(PII_ITEM, expect_routing=True)
        assessment = self.assessments[-1]
        recorded = str(self.container.audit.log.read_all()[-1]["redacted_summary"])
        surfaces = json.dumps(to_jsonable(assessment), sort_keys=True) + recorded
        leaked = PLANTED_NRIC in surfaces
        privileged_leak = PRIVILEGED_PHRASE in surfaces
        silent = [
            record
            for record in assessment.withheld
            if record.status is models.EvidenceStatus.WITHHELD_SAR
        ]
        silent_titled = any(record.title for record in silent)
        panels.append(
            Panel(
                title="Redact before the write",
                rows=(
                    Row("Identifier in the submitted text", PLANTED_NRIC, "warn"),
                    Row(
                        "Identifier anywhere in the record or the outcome",
                        "PRESENT" if leaked else "absent",
                        "bad" if leaked else "ok",
                    ),
                    Row("Stored summary", recorded),
                ),
                note=(
                    "The record is immutable, so a redaction pass after the write would be too "
                    "late. Masking happens on the way in, before the engine and before the model."
                ),
                tone="bad" if leaked else "ok",
            )
        )
        panels.append(
            Panel(
                title="Withholding schedule",
                rows=tuple(
                    Row(
                        record.doc_id,
                        record.status.value
                        + " ("
                        + record.basis_rule
                        + "): "
                        + (record.title or "title withheld"),
                        "warn",
                    )
                    for record in assessment.withheld
                )
                or (Row("schedule", "EMPTY", "bad"),),
                note=(
                    "A withheld document is RECORDED, never silently dropped. The restricted "
                    "filing carries an identifier and a basis and no title, because in several "
                    "regimes the existence of the filing is itself restricted."
                ),
                tone="ok" if silent and not silent_titled else "bad",
            )
        )
        facts["planted_identifier_leaked"] = leaked
        facts["privileged_snippet_leaked"] = privileged_leak
        facts["withheld"] = [
            {"doc_id": r.doc_id, "basis_rule": r.basis_rule, "title": r.title}
            for r in assessment.withheld
        ]
        facts["silent_withhold_titled"] = silent_titled
        return panels, facts

    def _step_review_queue(self) -> Produced:
        # The pack is the artifact a supervisor actually receives, so it is assembled here and
        # routed unconditionally: a clean pack routes for APPROVAL rather than for rescue.
        pack = self.service.assemble_pack(
            self.request, self.assessments, actor=ACTOR, tenant=TENANT, as_of=AS_OF
        )
        self.pack = pack
        pack_ref = self.container.review_router.route(pack, maker=ACTOR, tenant=TENANT)
        # Counted HERE, before the panels read it: a findings row that renders red while the
        # walkthrough's own check passes is a demo that argues with itself on screen.
        self.routed += 1

        # Dual control is a DIFFERENT question from escalation, so it is shown on an item that
        # demands two approvals and never escalates.
        skilled = self.service.assess_item(
            self.skilled_person_request,
            SKILLED_PERSON_ITEM,
            actor=ACTOR,
            tenant=TENANT,
            as_of=AS_OF,
        )

        pending = list(self.container.review_router.outbox.pending())
        rows: list[Row] = []
        leaked = False
        approvals_match = True
        by_case = {a.case_ref: a for a in self.assessments}
        by_case[pack.case_ref] = pack  # type: ignore[assignment]
        for entry in pending:
            payload = to_jsonable(entry)
            serialised = json.dumps(payload, sort_keys=True)
            leaked = leaked or PLANTED_NRIC in serialised or PRIVILEGED_PHRASE in serialised
            review = entry.review
            outcome = by_case.get(str(review.case_ref))
            if outcome is not None and review.required_approvals != outcome.required_approvals:
                approvals_match = False
            rows.append(
                Row(
                    str(review.source_key),
                    f"{review.severity} / approvals {review.required_approvals} / "
                    f"maker {review.maker}",
                )
            )
        queue = Panel(
            title="Outbound review queue",
            rows=tuple(rows) or (Row("queue", "empty", "bad"),),
            note=(
                "Queued, not submitted. The reference the caller received says exactly that, so "
                "a buffered escalation is never mistaken for a reviewed one. Item exceptions and "
                "the pack approval carry different source keys, so a console cannot merge them."
            ),
        )
        board = self.service.open_items(TENANT, ENTITLEMENTS)
        board_panel = Panel(
            title="The exam lead's open-item board",
            rows=tuple(
                Row(
                    f"{case.request_id} {case.item_ref}",
                    f"{case.disposition.value} / band {case.band.value} / internal due "
                    f"{case.internal_due_on.isoformat()} / {case.business_days_remaining} business "
                    f"days / {case.completeness_pct}% / review {case.review_ref or 'none'}",
                )
                for case in board
            )
            or (Row("board", "EMPTY", "bad"),),
            note=(
                "Read back under the caller's entitlements, with the ACL filter applied in the "
                "query. Without this store the SLA clock is a calculation rather than a clock."
            ),
        )
        dual = Panel(
            title="Dual control is not escalation",
            rows=(
                Row("Skilled-person item", skilled.item_ref),
                Row("Escalated", str(skilled.requires_human_review)),
                Row("Required approvals", str(skilled.required_approvals), "ok"),
                Row("Release state", skilled.release_state.value, "ok"),
            ),
            note=(
                "Two approvals on an item that never escalated. The engine owns that number and "
                "the review payload builder reads it, so the console and the service cannot "
                "disagree the way a severity-keyed table in the adapter would."
            ),
            tone="ok"
            if skilled.required_approvals == 2 and not skilled.requires_human_review
            else "bad",
        )
        findings = Panel(
            title="Findings",
            rows=(
                Row("Escalated items", str(self.escalated)),
                Row(
                    "Routed to review",
                    str(self.routed),
                    "ok" if self.routed == self.escalated + 1 else "bad",
                ),
                Row("Pack review reference", pack_ref, "ok" if pack_ref else "bad"),
                Row(
                    "Approvals match the engine's number",
                    "yes" if approvals_match else "NO",
                    "ok" if approvals_match else "bad",
                ),
                Row(
                    "Personal data or a withheld snippet on the wire",
                    "LEAKED" if leaked else "none",
                    "bad" if leaked else "ok",
                ),
            ),
            note=(
                "Every escalation is accounted for and the pack routes on top of them. A flag "
                "with no routing reference is auto-execution with extra steps."
            ),
            tone="bad" if leaked or not approvals_match else "ok",
        )
        actions = Panel(
            title="Next actions",
            rows=(
                Row("Checker", "open the pack review and record the two approvals"),
                Row("Operator", "release the production; this console cannot"),
            ),
        )
        facts = {
            "pending": len(pending),
            "wire_leak": leaked,
            "pack_review_ref": pack_ref,
            "approvals_match": approvals_match,
            "board_rows": len(board),
            "dual_control_without_escalation": (
                skilled.required_approvals == 2 and not skilled.requires_human_review
            ),
            "pack_release_state": pack.release_state.value,
            "pack_required_approvals": pack.required_approvals,
        }
        return [queue, board_panel, dual, findings, actions], facts

    def _step_audit(self) -> Produced:
        log = self.container.audit.log
        report = self.container.audit.verify()
        self.chain_ok = report.ok
        export = self.workdir / "export" / "audit.jsonl"
        export.parent.mkdir(parents=True, exist_ok=True)
        written = log.export_jsonl(export)
        restored = HashChainedAuditLog(":memory:")
        reloaded = restored.import_jsonl(export)
        round_trip = restored.verify_chain()
        anchored = bool(self.settings.audit_anchor_path) and self.anchor_path.exists()
        summaries = [str(entry.get("redacted_summary", "")) for entry in log.read_all()]
        with_basis = all("due_basis=" in text for text in summaries)
        with_calendar = all("calendar=" in text for text in summaries)
        withhold_bases = [text for text in summaries if "withheld=kb-dpr-" in text]
        trail = Panel(
            title="Audit trail",
            rows=(
                Row("Records", str(report.entries)),
                Row("Hash-chained", str(report.chained)),
                Row(
                    "Unverifiable (unchained)",
                    str(report.legacy),
                    "ok" if report.legacy == 0 else "bad",
                ),
                Row("Verdict", report.detail, "ok" if report.ok else "bad"),
                Row(
                    "External head anchor",
                    "configured" if anchored else "absent",
                    "ok" if anchored else "warn",
                ),
                Row(
                    "Every record names its due basis and calendar version",
                    "yes" if with_basis and with_calendar else "NO",
                    "ok" if with_basis and with_calendar else "bad",
                ),
            ),
            note=(
                "The chain alone cannot detect a truncated tail: dropping the newest rows leaves "
                "a shorter chain that verifies perfectly. The anchor, kept on a different "
                "volume, is what closes that gap."
            ),
            tone="ok" if report.ok else "bad",
        )
        portable = Panel(
            title="Open-format round trip",
            rows=(
                Row("Exported records", str(written)),
                Row("Reloaded into a fresh store", str(reloaded)),
                Row(
                    "Chain after reload",
                    round_trip.detail,
                    "ok" if round_trip.ok else "bad",
                ),
                Row(
                    "Withholding bases survive the round trip",
                    "yes" if withhold_bases else "NO",
                    "ok" if withhold_bases else "bad",
                ),
            ),
            note=(
                "JSON Lines with the hashes included, so a consumer can re-verify the trail "
                "without this codebase. What you export here is the reasoning behind every "
                "document you declined to produce."
            ),
            tone="ok" if round_trip.ok else "bad",
        )
        facts = {
            "chain_ok": report.ok,
            "entries": report.entries,
            "exported": written,
            "round_trip_ok": round_trip.ok,
            "anchored": anchored,
            "due_basis_recorded": with_basis,
            "calendar_version_recorded": with_calendar,
            "withhold_bases_recorded": bool(withhold_bases),
        }
        return [trail, portable], facts

    def _step_tamper(self) -> Produced:
        before = self.container.audit.verify()
        target = _rewrite_a_record(self.audit_path)
        after = self.container.audit.verify()
        self.chain_ok = after.ok
        detected = (not after.ok) and after.first_bad_seq == target
        attack = Panel(
            title="The tamper",
            rows=(
                Row("Append-only triggers", "dropped by the attacker", "warn"),
                Row("Record rewritten in place", "seq " + str(target), "warn"),
                Row("What was changed", "a blocked, routed item read as allowed and low", "warn"),
                Row("Verdict before the rewrite", before.detail, "ok"),
            ),
            note=(
                "File access beats a database trigger. A store that claims otherwise is "
                "describing a policy, not a control."
            ),
        )
        findings = Panel(
            title="Findings",
            rows=(
                Row("Chain intact", "YES" if after.ok else "no", "bad" if after.ok else "ok"),
                Row("First broken record", str(after.first_bad_seq), "ok"),
                Row("Detail", after.detail),
                Row(
                    "Named the exact rewritten record",
                    "yes" if detected else "no",
                    "ok" if detected else "bad",
                ),
            ),
            note=(
                "Tamper-EVIDENT, not tamper-proof. The guarantee is that a rewrite cannot pass "
                "unnoticed, and that the report names which record broke."
            ),
            tone="ok" if detected else "bad",
        )
        actions = Panel(
            title="Next actions",
            rows=(
                Row("Operator", "restore from the exported JSONL and re-anchor deliberately"),
                Row("Auditor", "treat every record from seq " + str(target) + " on as suspect"),
            ),
        )
        facts = {"tampered_seq": target, "detected": detected, "chain_ok": after.ok}
        return [attack, findings, actions], facts

    def _step_portability(self) -> Produced:
        onprem = build_container(Settings(profile="onprem", tenant=TENANT))
        rows: list[Row] = []
        refused: list[str] = []
        absent: list[str] = []
        for port, call in EXIT_CALLS.items():
            expected_absent = port in EXIT_ABSENT
            try:
                call(onprem)
            except NotImplementedError as exc:
                if expected_absent:  # pragma: no cover - a raising diagnostic seam is the defect
                    rows.append(Row(port, "REFUSED, but is meant to be absent", "bad"))
                else:
                    refused.append(port)
                    rows.append(Row(port, "refused: " + str(exc).split(":")[0], "ok"))
            else:
                if expected_absent:
                    absent.append(port)
                    rows.append(Row(port, "absent, by design (a diagnostic, not a control)", "ok"))
                else:  # pragma: no cover - a silent success is the failure this step looks for
                    rows.append(Row(port, "SUCCEEDED SILENTLY", "bad"))
        exit_panel = Panel(
            title="Exit profile (onprem)",
            rows=tuple(rows),
            note=(
                "Selected by one environment variable. No domain module was edited and no "
                "import changed."
            ),
            tone="ok" if len(refused) + len(absent) == len(EXIT_CALLS) else "bad",
        )
        bounds = Panel(
            title="What this does and does not prove",
            rows=(
                Row("Proved", "every port is swappable and every seam is named"),
                Row("Proved", "an unimplemented seam refuses instead of dropping work"),
                Row("NOT proved", "a live knowledge base, register or evidence-pack source"),
                Row("NOT proved", "retrieval recall, or that any policy number is correct in law"),
                Row("NOT proved", "a running on-premises deployment exists"),
            ),
            note=(
                "Bounded claims are the point. Run scripts/portability_demo.py for the full "
                "seam tour, with a pass or fail per named check."
            ),
        )
        return [exit_panel, bounds], {"refused": sorted(refused), "absent": sorted(absent)}

    # -------------------------------------------------------------- helpers

    def _item_panels(
        self,
        item: models.RequestItem,
        *,
        expect_routing: bool,
        prior_answers: tuple[models.PriorAnswer, ...] = (),
    ) -> Produced:
        assessment = self.service.assess_item(
            self.request,
            item,
            actor=ACTOR,
            tenant=TENANT,
            as_of=AS_OF,
            prior_answers=prior_answers,
        )
        self.assessments.append(assessment)
        self.items += 1
        review_ref = ""
        if assessment.requires_human_review:
            self.escalated += 1
            review_ref = self.container.review_router.route(assessment, maker=ACTOR, tenant=TENANT)
            self.service.record_case(self.request, assessment, tenant=TENANT, review_ref=review_ref)
            self.routed += 1
        consistent = bool(review_ref) == expect_routing == assessment.requires_human_review
        sla = assessment.sla
        decision = Panel(
            title="Item " + assessment.item_ref + ": " + assessment.disposition.value,
            rows=(
                Row("Topic", assessment.topic.value),
                Row("Owner", assessment.owner or "UNASSIGNED"),
                Row(
                    "Completeness",
                    f"{assessment.satisfied_mandatory} of {assessment.total_mandatory} mandatory "
                    f"artefacts ({assessment.completeness_pct}%)",
                ),
                Row("Severity", assessment.severity.value),
                Row("Decision", assessment.decision.value),
                Row("Requires human review", str(assessment.requires_human_review)),
                Row(
                    "Routed to review",
                    review_ref or "not routed (no escalation)",
                    "ok" if consistent else "bad",
                ),
                Row("Release state", assessment.release_state.value, "ok"),
                Row("Required approvals", str(assessment.required_approvals)),
                Row("Attributed to", ACTOR),
            ),
            note=(
                "Every number here is stdlib arithmetic over recorded inputs. A model would "
                "narrate this result; it never produces it, and it never releases it."
            ),
            tone="ok" if consistent else "bad",
        )
        clock = Panel(
            title="The clock",
            rows=(
                Row("Due", sla.due_on.isoformat() + " (" + sla.due_basis + ")"),
                Row("Internal due (after the review buffer)", sla.internal_due_on.isoformat()),
                Row("Business days remaining", str(sla.business_days_remaining)),
                Row("Band", sla.band.value),
                Row("Ask for an extension by", sla.extension_request_by.isoformat()),
                Row("Breached", str(sla.breached), "bad" if sla.breached else "ok"),
                Row("Buffer consumed", str(sla.buffer_consumed)),
                Row("Calendar", sla.calendar_id + "@" + sla.calendar_version),
            ),
            note=(
                "The calendar version is pinned on the record, so a deadline recomputed years "
                "later either matches or the record shows which input moved."
            ),
        )
        coverage = Panel(
            title="Coverage",
            rows=tuple(
                Row(row.artefact.value, row.state.value + ": " + row.reason)
                for row in assessment.coverage
            )
            or (Row("coverage", "NONE", "bad"),),
            note=(
                "The percentage opens into these rows. Denied and missing are rendered "
                "separately on purpose: only one of them says the firm holds no such document."
            ),
        )
        index = Panel(
            title="Document index",
            rows=tuple(
                Row(
                    exhibit.exhibit_no,
                    exhibit.title + " (" + exhibit.artefact.value + ", " + exhibit.locator + ")",
                )
                for exhibit in assessment.exhibits
            )
            or (Row("index", "no admissible evidence was retrieved", "warn"),),
            note="Numbered by a deterministic sort, so two runs produce the same annex.",
        )
        evidence = Panel(
            title="Evidence",
            rows=tuple(
                Row(citation.title or citation.source_id, citation.snippet or citation.source_id)
                for citation in assessment.citations
            )
            or (Row("citations", "NONE", "bad"),),
            note="Every claim carries its source. An uncited claim is a hallucination risk.",
        )
        facts = {
            "item_ref": assessment.item_ref,
            "disposition": assessment.disposition.value,
            "severity": assessment.severity.value,
            "completeness_pct": assessment.completeness_pct,
            "requires_human_review": assessment.requires_human_review,
            "review_ref": review_ref,
            "consistent": consistent,
            "release_state": assessment.release_state.value,
            "required_approvals": assessment.required_approvals,
            "exhibits": [exhibit.exhibit_no for exhibit in assessment.exhibits],
            "blockers": [blocker.kind.value for blocker in assessment.blockers],
            "due_basis": sla.due_basis,
            "calendar_version": sla.calendar_version,
        }
        return [decision, clock, coverage, index, evidence], facts

    # -------------------------------------------------------------- state

    def state(self) -> dict[str, Any]:
        """The whole run as JSON-safe data: what the UI renders and the walkthrough asserts."""
        current = self.results[-1]
        return {
            "service": SERVICE_NAME,
            "catalog_id": CATALOG_ID,
            "repository": REPOSITORY,
            "profile": self.settings.profile,
            "region": self.settings.region,
            "step": current.key,
            "step_index": self.index,
            "step_count": len(STEPS),
            "label": current.label,
            "next": "" if self.done else STEPS[len(self.results)].label,
            "done": self.done,
            "totals": {
                "cases": self.items,
                "escalated": self.escalated,
                "routed": self.routed,
                "chain_ok": self.chain_ok,
            },
            "steps": [_step_to_dict(result) for result in self.results],
        }


def _tags(tags: tuple[models.SensitivityTag, ...]) -> str:
    return ", ".join(tag.value for tag in tags)


def _author(model_authored: bool) -> str:
    return "model" if model_authored else "engine (the model draft was discarded)"


def _calendar_id(calendar: models.BusinessCalendar) -> str:
    return calendar.id


def _regime_id(regime: models.RegimeRef) -> str:
    return regime.regime


def _matrix(policy: models.ExamPolicy) -> str:
    return "; ".join(
        f"{key} <- {', '.join(sorted(value))}"
        for key, value in sorted(policy.transfer_matrix.items())
    )


def _cited_references(text: str) -> set[str]:
    """Every ``[EX-...]`` reference a draft cited, so the demo can check them against the index."""
    out: set[str] = set()
    for chunk in text.split("["):
        head, sep, _rest = chunk.partition("]")
        if sep and head:
            out.add(head)
    return out


def _step_to_dict(result: StepResult) -> dict[str, Any]:
    return {
        "key": result.key,
        "label": result.label,
        "narration": result.narration,
        "facts": result.facts,
        "panels": [
            {
                "title": panel.title,
                "note": panel.note,
                "tone": panel.tone,
                "rows": [
                    {"label": row.label, "value": row.value, "tone": row.tone} for row in panel.rows
                ],
            }
            for panel in result.panels
        ],
    }


def _rewrite_a_record(store: Path) -> int:
    """Drop the append-only triggers and rewrite one INTERIOR record, as an attacker would.

    Returns the ``seq`` that was rewritten. An interior row is chosen deliberately: rewriting
    the newest row is the easy case, and the chain has to catch a rewrite in the middle of the
    trail too. The fields changed are the ones that would make a late, incomplete production look
    like a clean one: the decision, the band, and the record of what was withheld.
    """
    conn = sqlite3.connect(store)
    try:
        conn.execute("DROP TRIGGER IF EXISTS audit_log_no_update")
        conn.execute("DROP TRIGGER IF EXISTS audit_log_no_delete")
        rows = conn.execute("SELECT seq, event_json FROM audit_log ORDER BY seq ASC").fetchall()
        if len(rows) < 3:
            raise RuntimeError("the tamper step needs an interior record to rewrite")
        middle = rows[len(rows) // 2]
        payload = json.loads(middle[1])
        payload["decision"] = "allowed"
        payload["severity"] = "low"
        summary = str(payload.get("redacted_summary", ""))
        payload["redacted_summary"] = summary.replace("withheld=kb-dpr-leg-01:A4", "withheld=none")
        conn.execute(
            "UPDATE audit_log SET event_json = ? WHERE seq = ?",
            (json.dumps(payload, sort_keys=True, separators=(",", ":")), int(middle[0])),
        )
        conn.commit()
        return int(middle[0])
    finally:
        conn.close()


def _exit_request() -> models.RegulatorRequest:
    return _request(permitted_transfer_jurisdictions=frozenset({"SG"}))


def _exit_audit(container: Any) -> Any:
    return container.audit.record(
        kernel.AuditEvent(
            action="assess_item",
            actor=ACTOR,
            decision=kernel.Decision.ESCALATED,
            severity=kernel.Severity.HIGH,
            redacted_summary=REFERENCE + " item 2.c: blocked",
        )
    )


#: A minimal escalated outcome for the exit tour, built here rather than assessed, so the tour
#: exercises the ROUTER seam and not the whole pipeline behind it.
EXIT_OUTCOME = models.ItemAssessment(
    item_ref="2.c",
    subject=REFERENCE + " item 2.c",
    case_ref="EXAM-2027-0014:2.c",
    topic=models.RequestTopic.TECHNOLOGY_AND_CYBER,
    owner="",
    sla=models.SlaClock(
        due_on=date(2027, 3, 19),
        internal_due_on=date(2027, 3, 12),
        due_basis="regulator_stated",
        extension_request_by=date(2027, 3, 5),
        business_days_remaining=-1,
        band=kernel.Severity.CRITICAL,
        breached=False,
        buffer_consumed=True,
        calendar_id="SG",
        calendar_version="2027.1",
    ),
    narrative=models.NarrativeDraft(),
    disposition=models.Disposition.BLOCKED,
    severity=kernel.Severity.HIGH,
    decision=kernel.Decision.ESCALATED,
    summary=REFERENCE + " item 2.c: blocked",
    requires_human_review=True,
    required_approvals=2,
    citations=(kernel.Citation(source_id="item:EXAM-2027-0014:2.c", title="Request item 2.c"),),
)


def _exit_review(container: Any) -> Any:
    return container.review_router.route(EXIT_OUTCOME, maker=ACTOR, tenant=TENANT)


def _exit_identity(container: Any) -> Any:
    # The persona header is deliberately present. It is what the OFFLINE family answers, so
    # sending it proves the exit family refuses the call itself rather than merely lacking an
    # input: a placeholder that returned a principal for a client-written header would be worse
    # than one that raises.
    return container.identity.resolve(RequestContext(headers={"x-dev-persona": "approver"}))


def _exit_tracer(container: Any) -> Any:
    with container.tracer.span("exit.tour", action="portability"):
        return None


def _exit_evaluation(container: Any) -> Any:
    return container.evaluation.gate("eval/datasets/golden_cases.jsonl")


def _exit_knowledge_base(container: Any) -> Any:
    return container.knowledge_base.search(
        models.RetrievalQuery(
            item_ref="1.a",
            topic=models.RequestTopic.AML_FINANCIAL_CRIME,
            artefacts=(models.ArtefactClass.POLICY,),
            period_start=date(2026, 4, 1),
            period_end=date(2027, 2, 28),
            entitlements=ENTITLEMENTS,
        )
    )


def _exit_obligations(container: Any) -> Any:
    return container.obligations.obligations_for(models.RequestTopic.AML_FINANCIAL_CRIME, "SG")


def _exit_evidence_packs(container: Any) -> Any:
    return container.evidence_packs.packs_for("OBL-OUT-001")


def _exit_generation(container: Any) -> Any:
    from exam_rfi_orchestrator.ports.generation import GenerationRequest

    return container.generation.generate(
        GenerationRequest(system="exit tour", prompt="exit tour", response_keys=("narrative",))
    )


def _exit_case_store(container: Any) -> Any:
    return container.case_store.waiver("WVR-FICTIONAL-2027-11", TENANT)


#: The calls the exit profile must REFUSE, one per port with an exit placeholder. Add a port,
#: add a row: a seam nobody calls is a seam nobody knows is unimplemented.
#:
#: IDENTITY is the load-bearing one and it was the one missing in the template's own history.
#: What the bound identity adapter DECLARES is the single flag the exposure guard reads before it
#: stands down and lets the process bind every interface, so a portability tour that toured every
#: seam except that one was skipping the seam whose exit behaviour matters most.
EXIT_CALLS: dict[str, Callable[[Any], Any]] = {
    "audit": _exit_audit,
    "identity": _exit_identity,
    "review_router": _exit_review,
    "tracer": _exit_tracer,
    "evaluation": _exit_evaluation,
    "knowledge_base": _exit_knowledge_base,
    "obligations": _exit_obligations,
    "evidence_packs": _exit_evidence_packs,
    "generation": _exit_generation,
    "case_store": _exit_case_store,
}

#: Ports whose exit placeholder is deliberately ABSENT rather than refusing.
#:
#: Every other seam raises on-prem because a placeholder that returned successfully would convert
#: real work into a silent no-op. Tracing is the exception on purpose: it is a diagnostic, it
#: carries no compliance claim, and making it fatal would force every on-prem operator to stand up
#: a tracing stack before the service would serve a request. So for these the tour asserts the
#: OPPOSITE, that the call completes, and a tracer that started raising would fail this tour.
EXIT_ABSENT: frozenset[str] = frozenset({"tracer"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the scripted offline demo end to end.")
    parser.add_argument(
        "output",
        nargs="?",
        default="demo.json",
        help="where to write the audit-view JSON (default: demo.json)",
    )
    parser.add_argument("--quiet", action="store_true", help="write the JSON and print nothing")
    args = parser.parse_args(argv)

    run = DemoRun()
    run.run_to_end()
    state = run.state()
    Path(args.output).write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    if not args.quiet:
        for step in state["steps"]:
            print("[" + step["key"] + "] " + step["label"])
        totals = state["totals"]
        print(
            "items="
            + str(totals["cases"])
            + " escalated="
            + str(totals["escalated"])
            + " routed="
            + str(totals["routed"])
        )
        print("wrote " + args.output)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
