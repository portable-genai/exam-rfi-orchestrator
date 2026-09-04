# Adopting this repo as your base

This repository (`exam-rfi-orchestrator`, the Regulatory Exam and RFI Orchestrator) is a **common base** that a bank
or other regulated firm forks to build its own **exam and inquiry response engine**: a service
that decomposes each regulator question into the artefacts it demands, runs ACL-aware retrieval to
assemble a cited evidence pack, deterministically tracks deadlines, owners, SLA clocks and
completeness, and drafts the response narrative and document index for maker-checker approval. It
ships a reusable hexagonal core (a pure-stdlib domain, typed ports, three swappable adapter
profiles, a green offline gate) plus a fully worked artefact taxonomy and admissibility ladder you
can keep, retune, or replace.

**Read [`model-card.md`](model-card.md) and the "What this does NOT do" section of the README
before anything else.** This service does not file, does not grant extensions, does not decide
privilege and does not release a pack. Those boundaries are the product.

This guide is the step-by-step for making it yours. It has two halves: a **mechanical rebrand**
(one script) and the **human decisions** the script cannot make for you.

> Related reading: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (the port table and topology),
> [`CONTRIBUTING.md`](../CONTRIBUTING.md) (adding an adapter, adding a port), the
> [`faq/`](faq/) directory, [`model-card.md`](model-card.md) (the model boundary),
> [`practices-audit.md`](practices-audit.md) (the per-check verdict).

---

## 1. What you keep vs what you rewrite

The core is hexagonal, and the boundary between reusable machinery and the exam vertical is a
physical module split with an enforced dependency direction. `domain/kernel.py` owns the
vertical-neutral contracts and imports nothing from the vertical.

| Layer | Where | For a new vertical |
|---|---|---|
| **Vertical-neutral machinery** | `domain/kernel.py`, `domain/errors.py`, every Protocol in `ports/`, the container wiring in `config.py` | keep untouched |
| **Policy (your numbers, sets and words)** | everything the `policy:` block in `config/settings.yaml` configures: the response windows and buffers, the severity bands, the staleness limits, the withhold tags, the named business calendars and their holidays, the regime caps, `min_completeness_pct_for_release`, and the approval rules; plus the jurisdiction rows in `domain/pii.py` and the metric thresholds in `eval/run_eval.py` | change deliberately (see section 4) |
| **Vertical (the artifacts themselves)** | the `exam-rfi-orchestrator` models in `domain/models.py`, the artefact taxonomy (`artefact_taxonomy.py`), the admissibility ladder (`coverage_engine.py`), the clocks (`sla_clock.py`), the release gate (`release_engine.py`), the consistency check (`consistency.py`), the exhibit numbering (`exhibit_index.py`), the orchestrator (`response_pack_service.py`), the fixture corpora and the eval golden sets | rewrite for your regime |

## 2. Core-vs-adopter-owned files (so upstream merges stay mechanical)

- **Upstream-owned** (take our changes): the vertical-neutral machinery above, `ports/`,
  `tests/contract/`, the eval harness mechanics, the hexagon wiring and the deploy stack in
  `infra/terraform/`.
- **Adopter-owned** (yours; expect to edit): the whole `policy:` block in `config/settings.yaml`,
  the fixture corpora and golden datasets, `adapters/onprem/*`, UI theming,
  `infra/terraform/terraform.tfvars`, and the regulator crosswalk in `COMPLIANCE.md`.

Track upstream via git tags; rebase your adopter-owned changes onto each release rather than
merging `main` continuously.

## 3. The mechanical rebrand (one script)

`scripts/rename_fork.py` rewrites the package name (`exam_rfi_orchestrator`, which is also the
console script), the `EXAMRFI_` env prefix (including the bare `EXAMRFI` that
`infra/terraform/render.tf.json` carries as `render_env_prefix`, and the backticked form the docs
carry), the cloud resource stem (`cop2-svc`, the Terraform `name_prefix`) and the distribution /
git id in one pass. Preview first, then apply:

```bash
# Preview (writes nothing):
python scripts/rename_fork.py --package acme_exam_rfi --env-prefix ACME \
    --resource acme-rfi --dry-run

# Apply:
python scripts/rename_fork.py --package acme_exam_rfi --env-prefix ACME \
    --resource acme-rfi --yes

# Then recreate the environment (the distribution name changed) and prove it is green:
python3.12 -m venv .venv && source .venv/bin/activate
make install
make gate
```

`--dist` defaults to the `--resource` value. `--resource` is validated against the same
`^[a-z][a-z0-9-]{2,18}$` regex the Terraform `name_prefix` variable enforces, so a stem the stack
would refuse fails here instead of at plan time. Add `--include-docs` to sweep Markdown prose too.
The script skips itself and renames `src/exam_rfi_orchestrator/` last. The catalog id `exam-rfi-orchestrator` is
kept unless you pass `--catalog-id`. **It touches no handling tag and no policy number**, so a
renamed fork carries a disclosure policy its counsel has never read.

## 4. The human decisions (the script can't make these)

1. **Every policy number is yours, and the shipped ones assert nothing about your law.** The
   README says this and it is the most important sentence in the repo: no window, buffer, band,
   staleness limit, withhold tag, holiday or approval rule shipped here is claimed to be currently
   correct in any jurisdiction. Your counsel owns them.
2. **The handling tags decide disclosure, and they are the corpus's.** Privilege, restricted-filing
   status and cross-border restriction are read from the document's handling tags, not derived
   here. A mislabelled document is produced; a document wrongly tagged privileged is withheld from
   a regulator entitled to it. Before go-live, satisfy yourself that the tagging is governed, and
   treat that governance as part of this system's control environment even though it lives
   outside this repo.
3. **The withhold ladder's ORDER is load-bearing.** `coverage_engine.py` evaluates A1, A2, A4, A5,
   A6, A3, and the comment explains why: running the staleness rule A3 first would give a
   stale-but-privileged document a status that treats it as usable, and it would be produced. If
   you add a rule, place it deliberately and add a case that proves the ordering.
   One caveat worth knowing: under the SHIPPED tag configuration the A5 silent-withhold loop is
   redundant, because `SAR_CONFIDENTIAL` sits in both `silent_withhold_tags` and
   `hard_withhold_tags`, so deleting A5 alone leaves the gate green. Nothing pins a configuration
   in which a silent tag is not also a hard tag, and that is the only case where A5 is load
   bearing. If you configure one, add a test that pins it.
4. **The business calendars.** Deadlines are signed business-day arithmetic on a named, versioned
   calendar. A **missing public holiday shifts every internal due date in the unsafe direction**,
   and nothing in the code can detect a merely stale calendar. Own the holiday set, version it,
   and put a review date on it.
5. **Caller-supplied dates move the deadline.** `received_on`, `regulator_due_on` and the prior
   answers are supplied by the caller and move the deadline and the conflict check. The service
   cites them; it cannot verify them against the regulator's letter. Decide who checks.
6. **`min_completeness_pct_for_release` ships at 100.** That is correct for a regulator submission
   and also exactly how an exam lead learns to ignore the release state. Argue with it
   deliberately rather than lowering it quietly.
7. **The regime caps are barely exercised.** Rule K3 is covered by unit tests alone, because every
   shipped register row fixes no response window. If your regime caps a window, add register rows
   that exercise it.
8. **Region / residency.** Set `config/settings.yaml:region`, `infra/terraform/render.tf.json:render_region`
   and the Terraform `region` / `allowed_regions` pair together, and re-run the residency tests.
9. **Identity / IdP.** This repo owns no login flow. Wire your issuer on the deployed service and
   set `EXAMRFI_IAP_AUDIENCE`. An unset or emptied audience refuses every caller.
10. **The generation model.** `EXAMRFI_GENERATION_MODEL` has no default and the managed adapter
    refuses without it. Pin a model, confirm it is served in your region, and record it in
    [`model-card.md`](model-card.md).
11. **Reference data is fictional.** The corpus, obligation register, evidence packs, prior answers
    and regulator are all fixtures. **Do not run against real supervisory correspondence without
    your own security, legal and model-risk sign-off.**
12. **Eval golden set.** Rebuild it for your taxonomy and policy: a fork inherits a green gate that
    measures the WRONG numbers until you do.
13. **Deployment posture.** Review the Dockerfile, `infra/terraform/` and the loopback-by-default
    binding. The WORM lock is irreversible: confirm `retention_days` before the first apply. This
    vertical's own resources are NOT in the stack: the managed case store is Firestore with no API
    in `apis.tf`, no CMEK service-agent binding in `kms.tf`, no least-privilege role in `iam.tf`
    and no `vpc_sc.tf` entry. A service enabled with no CMEK binding encrypts under Google-managed
    keys and looks identical in the console.

## 5. Do not duplicate the platform

- `enterprise-knowledge-base`: the ACL-aware retrieval this service depends on, reached as
  a PORT. Do not build a second index here.
- `human-review-console` human-review / maker-checker console: every outcome is routed to it (rule R8). There is
  no `released` path in this service.
- `agent-registry`: publish the A2A card at `/.well-known/agent-card.json`.
- `model-quality-gate` eval / quality gate: owns promotion verdicts.
- `agent-observability` plus immutable WORM audit.
- `agent-guardrail-gateway`: **not bound**; rule R1 applies the moment untrusted document text
  reaches a live model, which it does here.

The managed knowledge-base, obligations, evidence-pack and case-store adapters refuse correctly
when unconfigured, but their live payload parsing is unwired and no live upstream has ever been
exercised. That is adoption work.

## 6. Adoption checklist

- [ ] Read [`model-card.md`](model-card.md) and the README's "What this does NOT do".
- [ ] Ran `scripts/rename_fork.py`, recreated the venv, `make gate` green.
- [ ] Had counsel own every policy number: windows, buffers, bands, staleness limits, withhold
      tags, approval rules.
- [ ] Satisfied yourself that document handling tags are governed, because they decide disclosure.
- [ ] Reviewed the withhold ladder's order, and pinned a configuration where a silent tag is not
      also a hard tag if you have one.
- [ ] Owned, versioned and dated the business calendars, knowing a missing holiday fails unsafe.
- [ ] Decided who verifies caller-supplied `received_on` and `regulator_due_on`.
- [ ] Argued with `min_completeness_pct_for_release` rather than lowering it quietly.
- [ ] Added register rows that exercise the regime caps.
- [ ] Set the region in all three places and re-ran the Terraform residency tests.
- [ ] Wired your IdP audience and pinned `EXAMRFI_GENERATION_MODEL`.
- [ ] Replaced every fixture corpus and rebuilt the golden datasets.
- [ ] Added the case store's Firestore API, CMEK binding, IAM role and perimeter entry.
- [ ] Wired the live payload parsing on the managed adapters and exercised a real upstream.
- [ ] Recorded your baseline upstream tag so you can take future fixes.
