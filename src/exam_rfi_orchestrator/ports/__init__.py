"""The hexagon's boundaries, re-exported once so there is a single import site.

Every port is a ``@runtime_checkable`` Protocol and every port has a binding in every profile
(``config.DEFAULT_BINDINGS``); ``tests/contract/test_port_parity.py`` asserts both, plus set
equality in the reverse direction so a port added here without a binding fails the build.

``IdentityPort``, ``ObservabilityTracerPort`` and ``EvaluationGatePort`` are not redeclared:
they come from the shared commons packages and are re-exported here so consumers still have
one import site for the boundary set. Copies of these had already drifted apart across the
fleet before they were shared, which is the whole reason they are imported rather than typed
out. See :mod:`.observability`. What an identity
adapter DECLARES about the authentication it provides is this service's own vocabulary, not the
commons', and lives in :mod:`.identity` next to the re-export.
"""

from __future__ import annotations

from hex_service_kit.identity import IdentityPort

from .audit import AuditSinkPort
from .case_store import CaseStorePort
from .evidence_packs import EvidencePackReadPort
from .generation import GenerationPort, GenerationRequest, GenerationResponse
from .identity import (
    CLIENT_ASSERTED,
    END_USER_AUTH_ATTR,
    END_USER_AUTH_KINDS,
    UNIMPLEMENTED,
    VERIFIED,
    EndUserAuthUnavailableError,
    declared_end_user_auth,
)
from .knowledge_base import KnowledgeBaseReadPort
from .obligations import ObligationsReadPort
from .observability import (
    EvaluationGatePort,
    ObservabilityTracerPort,
    TokenUsage,
)
from .review_router import ReviewRouterPort

#: port name (the key in the settings ``adapters:`` block) -> the Protocol it must satisfy.
PORT_PROTOCOLS: dict[str, type] = {
    "audit": AuditSinkPort,
    "identity": IdentityPort,
    "review_router": ReviewRouterPort,
    "tracer": ObservabilityTracerPort,
    "evaluation": EvaluationGatePort,
    "knowledge_base": KnowledgeBaseReadPort,
    "obligations": ObligationsReadPort,
    "evidence_packs": EvidencePackReadPort,
    "generation": GenerationPort,
    "case_store": CaseStorePort,
}

__all__ = [
    "TokenUsage",
    "ObservabilityTracerPort",
    "EvaluationGatePort",
    "CLIENT_ASSERTED",
    "END_USER_AUTH_ATTR",
    "END_USER_AUTH_KINDS",
    "PORT_PROTOCOLS",
    "UNIMPLEMENTED",
    "VERIFIED",
    "AuditSinkPort",
    "CaseStorePort",
    "EndUserAuthUnavailableError",
    "EvidencePackReadPort",
    "GenerationPort",
    "GenerationRequest",
    "GenerationResponse",
    "IdentityPort",
    "KnowledgeBaseReadPort",
    "ObligationsReadPort",
    "ReviewRouterPort",
    "declared_end_user_auth",
]
