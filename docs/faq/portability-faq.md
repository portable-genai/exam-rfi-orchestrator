# Portability FAQ

For architecture, cloud and exit planning.

### What is the lock-in surface?

The `src/exam_rfi_orchestrator/adapters/gcp/` directory, and nothing else. The domain imports only
the standard library and the owned kits; every outbound dependency crosses a Protocol in `ports/`;
and one settings file maps each port to an adapter family. A purity check in the gate scans the
`domain/` and `ports/` trees and fails on any cloud import, so this is enforced rather than
described.

### What are the three profiles?

| Profile | For | Adapters |
|---|---|---|
| `local` | laptops, CI, demos | fixture corpus, obligation register, evidence packs, prior answers and case store, plus a deterministic narration stub. No SDK, no network, no credentials. |
| `gcp` | the managed deployment | `enterprise-knowledge-base`-backed knowledge base, managed obligations and evidence packs, a Firestore case store, a managed model for narration, `agent-observability` for audit and traces. |
| `onprem` | a client-hosted install | fail-fast placeholders naming the client system to bind. |

Selection is one variable, `EXAMRFI_PROFILE`, and it is three-state: unset, set-and-empty and
set-and-valid are distinct, with no silent fallback.

### Is the portability claim tested, or just documented?

Tested. `make portability` runs named checks and exits non-zero on any failure, and the contract
tests in `tests/contract/` run the same behavioural suite against every bound adapter family. The
purity scan is part of the offline gate.

### The managed adapters refuse. Does that not break the portability claim?

It is the opposite, and it is worth being precise about the current state. The managed
knowledge-base, obligations, evidence-pack and case-store adapters **refuse correctly when
unconfigured** rather than degrading to a fixture, so an incomplete managed profile fails loudly
instead of serving laptop data to production. What is genuinely unfinished is their **live payload
parsing**, which is unwired, and no live upstream has ever been exercised. That is declared here
rather than left to be discovered.

### Can it run with no model at all?

Yes, and that is deterministic-only mode. Bind the local narration stub and every consequential
field is byte-identical run to run: the decomposition requirement, the ladder, the clocks,
coverage, completeness, consistency, exhibit numbers, disposition, blockers and approvals are all
pure stdlib. What you lose is the drafted prose, the topic suggestion, the assertion normalisation
and the advisory artefact proposal, none of which is an argument to any engine function.

Unsetting `EXAMRFI_GENERATION_MODEL` also makes the managed adapter refuse, which is a
deterministic-only mode by accident rather than a designed operator action. The model card lists
making it a designed one as an open control.

### How do we actually exit?

1. Set `EXAMRFI_PROFILE=onprem` and implement the placeholder adapters against your own systems.
   The Protocols in `ports/` are the whole contract.
2. Export the data. Cases, packs and the audit stream are append-only JSON records with no
   managed-service-specific fields.
3. Drop `adapters/gcp/` and the `infra/terraform/` stack. Nothing in `domain/` references either.

### What has to be replaced on the way out, specifically?

`KnowledgeBasePort` (ACL-aware retrieval, the big one), `ObligationsPort`, `EvidencePacksPort`,
`CaseStorePort`, `GenerationPort` (optional, see above), `IdentityPort`, `AuditSinkPort`,
`ObservabilityTracerPort` and `ReviewRouterPort`.

The knowledge base is the dependency that matters most: entitlement-aware retrieval is the control
that keeps a pack from containing something the caller may not see, and this service does not
implement it.

### Is the data residency claim portable too?

The region is chosen once and shared across `config/settings.yaml`,
`infra/terraform/render.tf.json` and the Terraform `region` / `allowed_regions` pair, and the
Terraform tests refuse a region outside the allowlist at plan time. Cross-border restriction on
individual documents is a separate thing, decided by the corpus's handling tags and enforced by
the admissibility ladder's A6 rule.
