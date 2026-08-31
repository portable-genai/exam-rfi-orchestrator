"""On-prem EvidencePackReadPort: fail-fast portability placeholder (P-12).

An empty pack from a placeholder would silently reduce coverage, and because completeness drives
the release gate it would turn a releasable item into a blocked one with no visible cause, or
assert that the firm holds no control evidence it in fact holds. Both methods refuse.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import EvidencePack


class OnPremEvidencePackAdapter:
    """Satisfies the port but refuses: the client binds its own assembled-pack source."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def packs_for(self, obligation_id: str) -> tuple[EvidencePack, ...]:
        raise NotImplementedError(
            "on-prem evidence_packs is a portability placeholder: bind the client's own "
            "assembled-pack source (see docs/onprem-migration.md)."
        )

    def fetch(self, pack_ref: str) -> EvidencePack:
        raise NotImplementedError(
            "on-prem evidence_packs is a portability placeholder: bind the client's own "
            "assembled-pack source (see docs/onprem-migration.md)."
        )
