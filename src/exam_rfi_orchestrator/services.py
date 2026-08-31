"""One place that wires the container's ports into the domain service.

Every surface (the API, the CLI, the agent tools, the demo and the evaluation) needs the same
service built from the same bindings. Writing that assembly out five times is how one surface
ends up on a different set of ports, which is exactly the drift the settings file exists to
prevent, so it is written once here.

This module sits OUTSIDE ``domain/``: it imports the container, and the domain must not. The
domain service takes ports and a frozen policy, and knows nothing about profiles or settings.
"""

from __future__ import annotations

from .config import Container, Settings, build_container
from .domain.response_pack_service import ResponsePackService

__all__ = ["build_service"]


def build_service(container: Container | Settings | None = None) -> ResponsePackService:
    """Build the response-pack service from a container, some settings, or the environment."""
    resolved = container if isinstance(container, Container) else build_container(container)
    return ResponsePackService(
        resolved.audit,
        resolved.tracer,
        knowledge_base=resolved.knowledge_base,
        obligations=resolved.obligations,
        evidence_packs=resolved.evidence_packs,
        generation=resolved.generation,
        case_store=resolved.case_store,
        policy=resolved.settings.policy,
    )
