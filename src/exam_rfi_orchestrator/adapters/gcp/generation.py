"""GCP GenerationPort: managed narration, classification and normalisation (SDK imports are lazy).

The model narrates, classifies and normalises; every consequential number is computed by the
deterministic engine. The response is returned RAW: this adapter never parses, repairs or
validates, because that would put the grounding rules outside the pure domain where the
evaluation cannot score them.

The model id is per-deployment configuration, read three-state through ``Settings``: unset or
emptied both arrive as ``""`` and this adapter REFUSES rather than picking a default model.
"""

from __future__ import annotations

from ...config import Settings
from ...ports.generation import GenerationRequest, GenerationResponse


class CloudGenerationAdapter:
    """Narrate through a managed model, or refuse when no model is configured."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        model = self._settings.generation_model
        if not model:
            raise RuntimeError(
                "no generation model is configured: set EXAMRFI_GENERATION_MODEL. There is no "
                "default model, because a banner naming one the deployment never calls is worse "
                "than a refusal."
            )
        return self._reach(model, request)

    def _reach(
        self, model: str, request: GenerationRequest
    ) -> GenerationResponse:  # pragma: no cover - needs a live managed model
        # Lazy import: absent in the offline profiles and in CI.
        from google import genai
        from google.genai import types

        client = genai.Client()
        completion = client.models.generate_content(
            model=model,
            contents=request.prompt,
            config=types.GenerateContentConfig(
                system_instruction=request.system,
                response_mime_type="application/json",
                max_output_tokens=request.max_output_tokens,
                temperature=0.2,
            ),
        )
        return GenerationResponse(text=completion.text or "", model=model)
