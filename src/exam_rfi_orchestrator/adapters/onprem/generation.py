"""On-prem GenerationPort: fail-fast portability placeholder (P-12).

Deliberately NOT absent-and-degrading like the tracer. An on-premises operator must bind their
own model explicitly, and a placeholder returning empty text would produce a pack with no cover
note that still looked complete. ``Settings.generator_model`` reports ``onprem-not-implemented``
so the provenance banner says so too.
"""

from __future__ import annotations

from ...config import Settings
from ...ports.generation import GenerationRequest, GenerationResponse


class OnPremGenerationAdapter:
    """Satisfies the port but refuses: the client binds its own model."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise NotImplementedError(
            "on-prem generation is a portability placeholder: bind the client's own model "
            "(see docs/onprem-migration.md). An empty narration would look like a complete pack."
        )
