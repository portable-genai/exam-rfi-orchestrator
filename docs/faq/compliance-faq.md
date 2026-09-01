# Compliance FAQ

For compliance, legal and the second line.

### Does this service decide privilege?

No, and that boundary is the product. It NAMES the basis on a withholding schedule and holds the
document; a lawyer decides. `PRIVILEGE_HOLD` is a release blocker, not a resolution.

The input side is what deserves your attention: privilege, restricted-filing status and
cross-border restriction are decided by the **corpus's handling tags**, which this service reads
and does not derive. A mislabelled document is produced. A document wrongly tagged privileged is
withheld from a regulator entitled to it. Treat the governance of that tagging as part of this
system's control environment even though it lives outside the repo.

### Can this service file, or release, anything?

No. There is no code path in this service that returns `released`, and it does not transmit to a
regulator. Every outcome comes back held for a checker (rule R8), and the approval count is a
deterministic engine output.

It also does not grant, request or infer an extension. A reference on the wire is a lookup key
into the case store; a client assertion moves no date.

### Are the deadlines defensible?

The arithmetic is: signed business-day counting on a **named, versioned calendar**, with the
regulator's date, the internal buffer and the regime cap all applied deterministically and
reproducibly from the audit record.

Two honest caveats. A **missing public holiday shifts every internal due date in the unsafe
direction**, and nothing in the code can detect a merely stale calendar; own it, version it and
put a review date on it. And `received_on` and `regulator_due_on` are **caller-supplied**: the
service cites them and cannot verify them against the regulator's letter.

### Which regulations does this claim to satisfy?

None, by itself, and the repo is unusually explicit about this: **no window, buffer, band,
staleness limit, withhold tag, holiday or approval rule shipped here is claimed to be currently
correct in law.** All of it is configured in `config/settings.yaml` and owned by your counsel. The
crosswalk in [`../../COMPLIANCE.md`](../../COMPLIANCE.md) maps the build's controls to principles;
your jurisdiction and your supervisor's expectations are yours to state.

### Where does the data live, and is residency enforced or just documented?

Enforced at the infrastructure layer: the region is set once and shared across the settings file,
`render.tf.json` and the Terraform `region` / `allowed_regions` pair, with Org Policy
resource-location constraints, a regional CMEK ring and a dry-run-first VPC-SC perimeter. Per
document, cross-border restriction is a separate control, applied by the ladder's A6 rule from the
document's own handling tag.

The case store is the gap: it is Firestore in the managed profile with **no API entry in
`apis.tf`, no CMEK service-agent binding in `kms.tf`, no least-privilege role in `iam.tf` and no
`vpc_sc.tf` entry**. A service enabled with no CMEK binding encrypts under Google-managed keys and
looks identical in the console, so treat that as open work rather than a detail.

### How long is the audit trail kept, and can it be edited?

It is written to a locked WORM bucket with a retention lock, so it cannot be edited or deleted
before the retention period expires. The lock is irreversible: confirm `retention_days` with your
records function before the first apply.

### What model-risk evidence exists?

Today: the deterministic engine's test suite, and an offline eval with `disposition_accuracy`,
`clock_accuracy`, `completeness_accuracy`, `withhold_precision`, `blocker_recall`,
`entitlement_safety`, `citation_grounding >= 0.99` and `pii_safety >= 0.99`. The narration
contract is scored against RAW model output through the same pure functions the service enforces,
so `citation_grounding` can genuinely go red.

Two limits stated plainly, because they are the ones that matter:

- **Decomposition recall is unmeasured and unmeasurable offline.** Turning a question into the
  artefacts it demands is a draft a checker corrects, not a completeness guarantee.
- **Prior-answer consistency has good precision and unmeasured recall.**

And a scoping point: the corpus, obligation register, evidence packs, prior answers and regulator
are all FIXTURES. A green self-test proves the engine is consistent with its own corpus, not that a
real submission would be defensible. The remaining open controls are listed in
[`../model-card.md`](../model-card.md).

### Anything that looks like a control and is not?

Yes, one worth knowing. `min_completeness_pct_for_release` ships at 100, which is correct for a
regulator submission and also exactly how an exam lead learns to ignore the release state. It is a
default to argue with rather than a setting to lower quietly.

A second: under the shipped tag configuration the A5 silent-withhold rule is redundant, because
`SAR_CONFIDENTIAL` sits in both `silent_withhold_tags` and `hard_withhold_tags`. Nothing pins a
configuration in which a silent tag is not also a hard tag, which is the only case where A5 is
load bearing. If you configure one, add a test that pins it.

### What is still open at go-live?

The managed adapters' live payload parsing, the case store's cloud resources, the Hrz1 guardrail
binding, Hrz5 and Hrz3 wiring, register rows that exercise the regime caps, and the model-card
controls (pinned model and version, token budget, documented kill switch, retrieval cache,
reasoning trace, managed-profile evaluation).
