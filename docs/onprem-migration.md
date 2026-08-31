# On-prem migration (the reversibility proof, P-12)

The `onprem` profile ships fail-fast `NotImplementedError` placeholders for every port, so the
exit path is explicit rather than implied.

The identity placeholder is the one with a serving consequence, so it refuses with a STATUS and a
REASON rather than a bare crash: `OnPremIdentityUnimplementedError` is both a
`NotImplementedError` (the exit family's uniform refusal, which the contract suite and
`scripts/portability_demo.py` assert for every port) and an `EndUserAuthUnavailableError`, so
`POST /v1/response-pack` answers 501 with the message below instead of a 500 with no body. Until it is
replaced, no end user can be authenticated at all, and the loopback exposure guard treats the
deployment accordingly: see the exposure section of [runbook.md](runbook.md).

## Steps
1. Set `EXAMRFI_PROFILE=onprem`. A primary path that needs an unbound port
   fails fast with a message pointing here.
2. Implement each port against the client's own stack:
   - `AuditSinkPort` -> the client's append-only WORM store (the commons hash-chained log is a
     drop-in reference; the audit trail exports as JSON Lines and reloads with the chain intact).
   - `IdentityPort` -> the client's OIDC/SAML IdP (verify the assertion server-side; keep
     discarding any client-asserted actor). Set `end_user_auth = VERIFIED` on the new class
     (`ports/identity.py`). That declaration is what tells the exposure guard the end-user routes
     are authenticated, and it is what lifts the loopback bound; an adapter that omits it is read
     as client-asserted, which is the fail-closed default and not a bug in the guard.
   - `ReviewRouterPort` -> the client's own maker-checker queue. Rule R8 does not relax on exit:
     a consequential result must still reach a human, so this placeholder RAISES rather than
     returning quietly. An adapter that dropped the escalation would leave the service
     auto-executing with the appearance of review.
   - `KnowledgeBaseReadPort` -> the client's own governed corpus, with its ACL labels, handling
     tags, owning jurisdictions and effective dates carried onto each candidate. A placeholder
     returning an empty success would be worse than one that raises: an empty answer here is not
     an error, it is the statement "the firm holds no responsive evidence", and that is what
     would go to the supervisor over somebody's signature. Report
     `suppressed_by_entitlement` honestly; it is what separates "you may not read this" from
     "this does not exist". Attribute it by artefact class in `suppressed_by_artefact` too, or
     that sentence is said about every class the item asked for, including the ones the firm
     genuinely holds nothing of. An adapter that cannot attribute leaves the split empty and the
     engine keeps the over-broad reading rather than understating a denial.
   - `ObligationsReadPort` -> the client's own obligation register, read-only. An empty success
     looks exactly like "this topic has no obligations", which removes every rule D3 mandatory
     requirement from the completeness denominator and leaves a submission with no regulatory
     anchor while the service looks entirely healthy.
   - `EvidencePackReadPort` -> the client's own assembled control-evidence packs. Keep the two
     failure semantics apart: an unknown obligation id is an empty tuple, an unknown pack
     reference RAISES. Collapsing them makes "that pack does not exist" indistinguishable from
     "that pack is empty", and only one of those is a coverage result.
   - `GenerationPort` -> the client's own model. Deliberately NOT absent-and-degrading like the
     tracer: a placeholder returning empty text produces a pack with no cover note that still
     looks complete. The model owns no number, so binding a weaker one changes no figure.
   - `CaseStorePort` -> the client's own case store. All four methods raise, and for `waiver()`
     and `extension()` that is load-bearing: returning `None` means "no such record exists",
     which would SILENTLY withhold a waived document and SILENTLY refuse to move a granted
     deadline. An unwired store must say it is unwired.
3. Bind the new adapters under `onprem` in `config/settings.yaml` (and in
   `config.DEFAULT_BINDINGS`, which the settings test holds equal to it) and run the gate.

No domain code changes: that is the point of the hexagon.
