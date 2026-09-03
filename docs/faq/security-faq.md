# Security FAQ

For AppSec and security review.

### Who is the actor on a decision, and can a caller assert it?

No. Identity is resolved server-side through `IdentityPort` and a caller-supplied identity is
never accepted. Under the `gcp` profile the IAP-injected assertion is verified at the edge against
a configured audience and IAP's own key set; `local` uses seeded dev personas; `onprem` is a
client IdP placeholder. An unset or emptied `EXAMRFI_IAP_AUDIENCE` refuses every caller rather
than verifying without one, because `verify_token` documents `audience=None` as "the audience is
not verified", which would accept any Google-signed token.

The negative matrix for that verifier lives in `tests/unit/test_iap_crypto_matrix.py`. It mints
its own key, signs its own assertions and runs the REAL verifier over them.

### How is entitlement enforced on retrieval?

Retrieval is ACL-aware and the entitlement decision belongs to the knowledge base (Hrz2), not to
this service. A candidate the caller is not entitled to see becomes a `DENIED_NO_ENTITLEMENT`
release blocker rather than a silent omission, so an incomplete pack is visible as incomplete.
`entitlement_safety` is a hard eval metric at 1.0.

### How is tenant isolation enforced?

Through the case store and the identity binding, on every read. A cross-tenant case reference is a
refusal rather than an empty result.

### What happens if the profile variable goes missing in production?

It refuses to start. Configuration is three-state throughout: unset, set-and-empty and
set-and-valid are distinct, and only the third proceeds. There is no silent fallback to a managed
adapter. The generation model id follows the same rule: unset and emptied both arrive as `""` and
the managed adapter refuses rather than picking a default.

### Can a model see a privileged document?

No. Hard-withheld candidates are removed from the prompt inputs by the engine **before** the
generation port is called, so privilege containment does not depend on the model behaving. The
model also cannot set a withhold, a coverage state or a disposition; those are engine outputs.

What the model can do is produce a bad draft, and every one of its four jobs has a deterministic
validator that discards output rather than repairing it. An unrecognised assertion becomes an
`UNRECOGNISED_ASSERTION` release blocker, not a silent pass.

The remaining exposure is prompt injection through document and question text, which is written by
parties outside this service. Hrz1 is **not** bound; rule R1 applies.

### Where does personal data go?

Masked before anything is audited, and the audit stores the redacted text. The jurisdiction rows
in `domain/pii.py` are policy you own; the shipped set is a reference. `pii_safety >= 0.99` is a
hard eval metric.

### How is the audit trail protected?

Audit events go to `AuditSinkPort`, backed by Hrz5's immutable WORM sink in the managed profile
and a locked WORM log bucket in the Terraform stack. The retention lock is irreversible; confirm
`retention_days` before the first apply.

### What about supply chain?

Both lockfiles are fully pinned and `pip-audit` runs over both as a hard gate in `make audit`. The
container base is digest-pinned and runs as non-root uid 10001. There are no GitHub Actions to
pin in this repository: the caller is RENDERED, never hand-written, so nothing here names an
action version. The two actions the fleet actually pins (in the reusable workflow and its
publisher) live in `.github` and are SHA-pinned there. The gate is the hosted GitHub Actions
check.

### What is deliberately out of scope?

- **Login.** This repo owns no authentication flow.
- **The document index and its ACLs.** Owned by Hrz2.
- **Guardrail screening.** Owned by Hrz1, not bound today.
- **Filing and release.** No code path here releases a pack.
- **The correctness of document handling tags.** Privilege, restricted-filing status and
  cross-border restriction are read from the corpus. That is a data-governance dependency, and it
  is the single most consequential input this service does not control.
