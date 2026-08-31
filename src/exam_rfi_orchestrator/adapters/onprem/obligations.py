"""On-prem ObligationsReadPort: fail-fast portability placeholder (P-12).

A silent empty answer would look identical to "this topic has no obligations", which would remove
every rule D3 mandatory requirement from the completeness denominator and leave a submission with
no regulatory anchor anywhere in it while the service looked entirely healthy.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ObligationRef, RequestTopic


class OnPremObligationsAdapter:
    """Satisfies the port but refuses: the client binds its own obligation register."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def obligations_for(self, topic: RequestTopic, jurisdiction: str) -> tuple[ObligationRef, ...]:
        raise NotImplementedError(
            "on-prem obligations is a portability placeholder: bind the client's own obligation "
            "register (see docs/onprem-migration.md)."
        )
