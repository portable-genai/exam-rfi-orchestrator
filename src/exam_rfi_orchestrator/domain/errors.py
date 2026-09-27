"""Domain-level errors the response-pack service raises.

Kept separate from ``kernel.py`` (data types only): a domain error names something the DOMAIN
decided, not a data shape, and adapter-level failures (unreachable host, missing config) raise
their own errors at the port boundary instead.
"""

from __future__ import annotations


class GuardrailBlockedError(RuntimeError):
    """Raised when the guardrail (rule R1) refuses a generation call's input or output.

    Also raised, chained to the adapter's own error, when the guardrail could not decide at all
    (its backend errored or timed out): an undecided screen is a refusal, never a pass.

    ``domain/response_pack_service.py`` audits every refusal as ``Decision.BLOCKED`` BEFORE this
    is raised, and each of its three generation call sites then drops the model's contribution
    WHOLE: the narration falls back to the deterministic paragraph (fixed text built from engine
    facts, flagged by an ``ungrounded_draft`` blocker), the topic suggestion is absent, the
    normalised facts are absent. The model never decides anything consequential in this service,
    so that is the same degradation as a model that could not be reached, and no model text a
    screen refused, or never saw, is used.
    """
