"""On-prem CaseStorePort: fail-fast portability placeholder (P-12).

All four methods raise, and for :meth:`waiver` and :meth:`extension` that is load-bearing:
returning ``None`` means "no such record exists", which would silently withhold a waived document
and silently refuse to move a granted deadline. An unwired store must say it is unwired.
"""

from __future__ import annotations

from datetime import date

from ...config import Settings
from ...domain.models import CaseRecord, WaiverRecord

_MESSAGE = (
    "on-prem case_store is a portability placeholder: bind the client's own case store "
    "(see docs/onprem-migration.md)."
)


class OnPremCaseStoreAdapter:
    """Satisfies the port but refuses: the client binds its own case store."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def record(self, case: CaseRecord) -> str:
        raise NotImplementedError(_MESSAGE)

    def open_items(self, tenant: str, entitlements: frozenset[str]) -> tuple[CaseRecord, ...]:
        raise NotImplementedError(_MESSAGE)

    def waiver(self, ref: str, tenant: str) -> WaiverRecord | None:
        raise NotImplementedError(
            _MESSAGE + " Returning None would silently withhold a waived document."
        )

    def extension(self, ref: str, tenant: str) -> date | None:
        raise NotImplementedError(
            _MESSAGE + " Returning None would silently refuse to move a granted deadline."
        )
