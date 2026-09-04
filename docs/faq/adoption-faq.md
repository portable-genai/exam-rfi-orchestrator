# Adoption FAQ

For engineering leads forking this repo. The full walkthrough is
[`../ADOPTING.md`](../ADOPTING.md); this page answers the questions that come up first.

### How do I rebrand it for my organisation?

One script:

```bash
python scripts/rename_fork.py --package acme_exam_rfi --env-prefix ACME \
    --resource acme-rfi --dry-run     # preview, writes nothing
python scripts/rename_fork.py --package acme_exam_rfi --env-prefix ACME \
    --resource acme-rfi --yes         # apply
```

It rewrites the package name (which is also the console script), the `EXAMRFI_` env prefix
including the bare token `infra/terraform/render.tf.json` carries as `render_env_prefix` and the
backticked form the docs carry, the Terraform `name_prefix` resource stem (`cop2-svc`) and the
distribution id. Add `--include-docs` to sweep Markdown prose too. It skips itself and renames the
package directory last. The catalog id `exam-rfi-orchestrator` is kept unless you pass `--catalog-id`.

Then recreate the venv (the distribution name changed) and run `make gate`.

**It touches no policy number and no handling tag.** A renamed fork carries a disclosure policy
your counsel has not read.

### If several institutions fork this, how does each take upstream fixes?

Track upstream by git tag and rebase your adopter-owned changes onto each release, rather than
merging `main` continuously. Upstream owns the vertical-neutral machinery, `ports/`, the contract
tests, the eval mechanics and the deploy stack; you own the whole `policy:` block, the fixtures,
the golden datasets, the `onprem` adapters, branding and the regulator crosswalk.

### What do we have to supply that is not in this repo?

- **Every policy number**, owned by counsel: windows, buffers, bands, staleness limits, withhold
  tags, holidays, approval rules.
- **A governed handling-tag scheme** on your document corpus, because those tags decide disclosure.
- **ACL-aware retrieval** behind `KnowledgeBasePort`, from `enterprise-knowledge-base` or your own index.
- **An obligation register** behind `ObligationsPort`, with rows that actually fix response windows
  if your regime caps them.
- **Evidence pack and case store** implementations.
- **A pinned generation model** in `EXAMRFI_GENERATION_MODEL`. There is no default.
- **Your IdP audience** on the deployed service.
- **Your own fixtures and golden datasets.**

### Can I retune the policy without touching engine code?

Yes. The `policy:` block in `config/settings.yaml` configures the response windows and buffers,
the severity bands, the staleness limits, the withhold tags, the named business calendars and
their holidays, the regime caps, `min_completeness_pct_for_release` and the approval rules.

Two things to be careful with. The **withhold ladder's order** (A1, A2, A4, A5, A6, A3) is a
disclosure control: A3 first would let a stale-but-privileged document be produced. And under the
shipped tags, A5 is redundant because `SAR_CONFIDENTIAL` is in both the silent and hard withhold
sets, so deleting A5 alone leaves the gate green. If you configure a silent tag that is not also a
hard tag, add a test that pins it.

### Does the gate run for my fork out of the box?

The offline gate does: `make gate` needs no network, no credentials and no cloud SDK. Hosted CI is
a different question. There are no HAND-WRITTEN workflow files to inherit: GitHub Actions is the
fleet's live CI, and every repository's caller is RENDERED from the reviewed job contract in
`org-metadata/ci/gcp/repository-policy.json`, never authored in the repository. **A repository
absent from that policy gets no caller and no required check, and nothing reports the
omission.** Register your fork, or stand up your own CI, before you rely on a gate.

### The eval reports high scores. Should we believe it?

Believe what it measures. The corpus, obligation register, evidence packs, prior answers and
regulator are all fixtures, so a green self-test proves the engine is consistent with **its own
corpus**. It is not evidence that a real submission would be defensible.

Two metrics are structurally absent rather than merely low: decomposition recall is unmeasurable
offline, and prior-answer consistency has unmeasured recall. Do not read their absence as a pass.

### How do I add a new outbound dependency?

Add a Protocol to `ports/`, implement it in all three adapter families, bind it in the `Container`
in `config.py`, and add a contract test so every family is held to the same behaviour. Do not
import a client library in `domain/`: the purity scan in the gate will fail, which is the point.

### Will the demo rot after I diverge?

`tests/unit/test_demo_surface.py` drives the whole arc inside the offline gate and fails if a step
has no expectation, and the hosted GitHub Actions check runs that gate on every pull request.
`make demo-selftest` runs the same arc headless on demand.

### What is still open?

The catalog row for `exam-rfi-orchestrator` carries the honest list. In short: the managed adapters' live payload
parsing is unwired and no live upstream has been exercised; the case store's Firestore resources
are absent from Terraform; `agent-guardrail-gateway`, `agent-observability` and `agent-registry` are unwired; the model-card controls (pinned model
and version, token budget, kill switch, retrieval cache, reasoning trace, managed-profile eval)
are open; and rule K3 is exercised by unit tests alone.
