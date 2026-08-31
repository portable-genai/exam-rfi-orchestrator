"""GenerationPort: the LLM boundary, kept strictly to narration, classification and normalisation.

The determinism rule of this catalog is that consequential math and verdicts are pure code and
the model only narrates. This port is where the model lives, so its contract is deliberately
narrow: it turns a request (a system instruction, a prompt, the engine facts and the expected
response keys) into raw text, and nothing more.

The adapter never parses, repairs or validates. That would put the grounding rules outside the
pure domain, where the evaluation cannot score them. Rules G1 to G3 sit above this port in
``domain/narration.py`` and discard the output WHOLE on any failure, so binding a real model
cannot change a single number the service produces.

The domain stays pure: this is a Protocol. The adapters (not this module) reach a real model
under the managed profile, answer deterministically offline, and fail fast on-premises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """One generation request. ``facts`` are the engine-owned key/value pairs the text may cite.

    ``facts`` is not decoration: it is the authoritative set of figures the narration contract
    grounds the model's output against. An integer in the model's text that is not derivable
    from these facts is treated as ungrounded and the whole draft is discarded.
    """

    system: str
    prompt: str
    facts: tuple[tuple[str, str], ...] = ()
    response_keys: tuple[str, ...] = ("narrative",)
    max_output_tokens: int = 512


@dataclass(frozen=True, slots=True)
class GenerationResponse:
    """The raw model output. ``text`` is expected to be the structured JSON the prompt asked for."""

    text: str
    model: str = ""
    usage: tuple[tuple[str, int], ...] = field(default_factory=tuple)


@runtime_checkable
class GenerationPort(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Return the model's raw text for ``request`` (expected to be structured JSON).

        Implementations never decide anything: they narrate, classify or normalise. A failure to
        reach the model is a raised error (the managed family) or ``NotImplementedError`` (the
        on-premises placeholder). The caller treats a refusal exactly like a rejected draft:
        an empty narrative plus an ``ungrounded_draft`` blocker, never a silently unnarrated pack.
        """
        ...
