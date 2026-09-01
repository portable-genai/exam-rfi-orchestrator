# FAQ index

Answers to the questions different teams ask when evaluating, adopting or reviewing this
repository as a common base for regulator exam and inquiry response. Each file is written for a
specific audience; skim the one that matches your role.

| FAQ | For | Answers |
|---|---|---|
| [security-faq.md](security-faq.md) | AppSec / security review | server-side identity, entitlement-aware retrieval, tenant isolation, secrets, supply chain, the audit chain, what is in and out of scope |
| [portability-faq.md](portability-faq.md) | Architecture / cloud / exit planning | no-lock-in, the three profiles, the sovereign exit, data export |
| [features-faq.md](features-faq.md) | Product / compliance / delivery | what the engine does, what is deterministic vs model-written, and the boundary with sibling catalog systems |
| [adoption-faq.md](adoption-faq.md) | Engineering leads forking the repo | rename, upstream fixes, extension points, what stays open |
| [compliance-faq.md](compliance-faq.md) | Compliance / legal / second line | disclosure posture, privilege, maker-checker, residency, retention, model-risk evidence |

**Two things to know before reading any of these.** First, the README's "What this does NOT do"
list is the product: this service does not file, does not grant extensions, does not decide
privilege and does not release a pack. Second, no policy number shipped here is claimed to be
currently correct in law; every window, band, tag and holiday is the adopter's.

These FAQs deliberately do **not** re-document capabilities owned by sibling systems. Where a
concern belongs to another repo (ACL-aware retrieval in Hrz2, the guardrail gateway Hrz1, the
agent registry Hrz3, the eval platform Hrz4, observability and WORM audit Hrz5, the human-review
console Hrz7), the FAQ points at it and explains the boundary. See
[features-faq.md](features-faq.md) for the full map.

Authority order for anything these pages disagree with: [`SPEC.md`](../../SPEC.md), then
[`ARCHITECTURE.md`](../../ARCHITECTURE.md), then [`COMPLIANCE.md`](../../COMPLIANCE.md), then
[`README.md`](../../README.md). These pages restate; they do not decide.
