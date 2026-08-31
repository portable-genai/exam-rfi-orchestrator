"""The PII pattern set this vertical redacts with, sourced from the shared `pii-kit`.

Row selection and ORDER are per-vertical (the commons deliberately does not bake them in): here
the national-ID rows run first and the universal email/phone rows last. A vertical with a
bare-digit account catch-all would order that last so it does not subsume a national id.

WHAT THIS VERTICAL ACTUALLY SEES, and why the selection matters more here than in most repos. An
exam response carries customer files, complaint records, transaction samples and correspondence,
so personal data arrives in the evidence itself and not only in the question. The rows below are
the jurisdictions this deployment serves; an identifier from a jurisdiction that is NOT in this
tuple is not masked at all, so every planted identifier in a fixture, a golden case or a demo is
validated against `pii-kit` before it lands. A plausible-looking identifier from an unlisted
jurisdiction would survive into an audit record and turn the pii_safety metric red on a rule
nobody would think to suspect.
"""

from __future__ import annotations

from pii_kit import UNIVERSAL_PATTERNS, Pattern, national_patterns_for

# The jurisdictions this deployment serves (override per client). Obviously synthetic data only.
JURISDICTIONS: tuple[str, ...] = ("SG", "HK", "JP", "AU")

PII_PATTERNS: tuple[Pattern, ...] = (
    *national_patterns_for(JURISDICTIONS),
    *UNIVERSAL_PATTERNS,
)
