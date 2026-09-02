# DEMO: Regulatory Exam and RFI Orchestrator (Cop2)

Everything here runs **offline**: no cloud project, no credentials, no API key, no browser
engine, no bundler. That is the first thing to say out loud, because it is the claim the rest of
the demo rests on.

```bash
make install          # locked install from requirements-dev.lock
make demo             # the presenter-paced walkthrough (starts its own server)
```

## The eight-step walkthrough

`make demo` starts a loopback server, opens the page, and then waits for you at every step. The
narration is printed on **your terminal**, never on the page, so the audience sees only the clean
output view. At a prompt: **Enter** runs the step, a **number** jumps to that step, **r** restarts
the run, **q** quits.

Every step drives the real services. Nothing is pre-recorded, and every step is ASSERTED: if the
service does not actually reach the state the narration just claimed, the walkthrough says so and
exits non-zero.

| # | Step | The point to make |
|---|---|---|
| 1 | Bound offline, and the release policy is configuration | One variable binds every port with no cloud project and no credential. Then look at the POLICY panel rather than the binding panel: the review buffer, the band ceilings, the staleness window, the tags that are never produced and the holiday calendar with its version are all read from `config/settings.yaml`. They are the adopter's numbers. And the regime register says, for every shipped row, that the regime fixes NO response window: the notice's own date governs. That row exists so nobody hardcodes a number they read somewhere. |
| 2 | A fully evidenced item | Decomposed, retrieved, admitted, dated, indexed, cited, and NOT escalated. The due date, the completeness number and the band are stdlib arithmetic over recorded inputs, and the exhibit numbers came out of a SORT, which is why a resubmission diffs cleanly. Manufacturing a review here trains an exam lead to approve without reading. |
| 3 | A consequential item | Several cited blockers, including a contradiction with what the firm told this regulator in an earlier submission. Escalated AND routed in the same call (rule R8). The reviewer is handed the NAMES of the rules that fired, not a score. |
| 4 | Masked on the way in, withheld by rule | Two different controls in one beat. The planted identifier is masked BEFORE the audit write, because the record is immutable. Separately, three documents are not produced and each gets a schedule row with a stated basis; the restricted-filing row carries an identifier and a basis and NO title. |
| 5 | What the checker receives, and the open-item board | The item escalations plus exactly one pack review, which needs two approvals, each with the verified maker and the approval count read off the engine's outcome. Two approvals on a skilled-person item that never escalated: dual control and escalation are different questions. Beside it, the exam lead's board, read back under the caller's entitlements. |
| 6 | The audit trail | Hash-chained, externally anchored, and exportable to JSON Lines that reload elsewhere with the chain intact. Every record names its due basis, pins its calendar version and carries every withhold basis. |
| 7 | A rewritten withhold basis | An attacker with file access edits a blocked, routed item to read allowed and low and flips its withheld privileged document to produced. That is exactly the rewrite that makes a late, incomplete production look clean. The chain names the record. Tamper-EVIDENT, not tamper-proof. |
| 8 | The exit profile | The same calls on `onprem`, no code edited: every unimplemented seam refuses loudly rather than dropping the work. |

Step 7 is the one to linger on. A demo where nothing ever goes wrong is a sales deck; this one
shows a failure and shows that the system detects it. Step 4 is the one that decides whether a
compliance audience trusts the rest.

## The other three ways to run it

```bash
make demo-selftest    # unattended and headless, asserts every step, non-zero on failure
make demo-static      # demo.json plus out/index.html and out/step-*.html, for screenshots
make portability      # the executable portability claim: named checks, pass or fail each
```

`tests/unit/test_demo_surface.py` drives the whole arc inside the offline gate, and the
hosted Cloud Build check runs that gate on every pull request and every push to main, so the
demo cannot rot silently between showings. `scripts/README.md` documents each script and the
environment overrides.

## The claims, and their bounds

State the bounds yourself. An unbounded claim is the one an auditor disproves for you.

| Claimed | Proved by | NOT claimed |
|---|---|---|
| Runs with no cloud, credentials or network | the whole demo, plus `make gate` | that the managed profile works: that needs a project and lives in `tests/integration/` |
| Every consequential step is deterministic and replayable | steps 2 to 4, `make gate`, the golden set | that a model's narration is deterministic; it is not, and it decides nothing |
| Admissibility and the clock are computed with no model | steps 2 to 4, `tests/unit/` | that the corpus's handling tags are CORRECT; a mislabelled document is produced or withheld wrongly and this engine cannot tell |
| Redaction precedes the audit write | step 4 | that the model was never shown anything sensitive beyond what the ladder admitted |
| Every escalation is routed and the approval count has one owner | steps 3 and 5 | that a reviewer acted; the queue shows submitted, not reviewed |
| Exhibit numbering is stable across runs | step 2 | that decomposition found every artefact the question implies; recall is unmeasured |
| The audit record is tamper-evident and portable | steps 6 and 7, `make portability` | tamper-PROOF: file access beats any store |
| Every port is swappable and every seam is named | step 8, `make portability` | that an on-premises deployment exists, or model or infrastructure portability |

Say these bounds out loud, because an audience will otherwise assume the opposite:

- **No live upstream.** The knowledge base, the obligation register, the evidence packs, the prior
  answers and the supervisor are all FIXTURES in this repository. A green self-test proves the
  engine is consistent with its own corpus. It does not prove a real submission would be
  defensible, and the two failure modes this demo is proudest of showing, a contradicted prior
  answer and a wrongly produced privileged document, are exactly the ones that only really appear
  against a messy real corpus.
- **No model runs in this demo.** The generation port is bound to an offline stub that restates
  engine facts deterministically, and it says so on screen: the deployment panel names the model
  `deterministic-offline-stub`. So "the model wrote the sentence" in step 2 means the port a
  managed model would occupy wrote it. The claim the demo makes is that nothing the model writes
  decides anything, and that claim is the same either way. What it does NOT show is how a real
  model's narration reads, or how often it needs a reviewer.
- **Retrieval recall is not measured.** Nothing here says the corpus returned everything responsive.
- **No running on-premises deployment.** Step 8 proves every seam refuses; it proves nothing about
  a deployment nobody has stood up.
- **The holiday calendars may be stale.** Nothing in the code can detect a calendar that is merely
  out of date, and a missing public holiday shifts every internal due date in the unsafe
  direction. The version is recorded on every clock so a recomputation shows which list was used,
  and `docs/runbook.md` makes review a standing item. That is mitigation, not detection.
- **The regime-cap rule is exercised by NO golden case.** Every shipped register row fixes no
  response window, which is what an exam request list, an RFI, a thematic review and a
  skilled-person scope all do in practice. Rule K3 is held by unit tests alone
  (`tests/unit/test_sla_clock.py`), and it ships live so an adopter whose counsel identifies a
  regime that DOES fix a window configures it rather than patching code.
- **No shipped policy number is a claim about the law.** The completeness floor ships at the
  strictest value, which is a default to argue with rather than a recommendation, and the
  silent-withhold asymmetry is a legal position the adopter's counsel must confirm.

## The UI

```bash
make ui-install && make ui-dev     # http://localhost:3000, proxying to the service
```

Worth showing only if the audience cares about embedding. The point is not the screen: it is that
the browser never asserts who the user is, the service credential never leaves the server, and
framing and CORS are per-tenant allowlists that refuse a wildcard. See `ui/README.md`.

## Managed profile (gcp)

Set `EXAMRFI_PROFILE=gcp` and install the `[gcp]` extra; identity becomes
the platform's signed assertion and audit becomes the Cloud Logging WORM sink. This is NOT part
of the offline demo and needs a real project. See `docs/runbook.md`.
