"""CaseStorePort: the open-item board, and the only correct home for a waiver or an extension.

Workflow and case is this vertical's archetype, and the catalog says the system TRACKS deadlines,
owners, SLA clocks and completeness. Without a store the clock is a calculation rather than a
clock: nobody can see the open request list and the exam lead has no board. It is written on
every item assembly and read back in the reviewer-queue beat, so it is not a seam nobody
exercises.

IT IS ALSO WHAT STOPS A WIRE FIELD FROM BEING A GRANT. The request carries ``waiver_ref`` and
``extension_ref``, and both are LOOKUP KEYS. Making the resolution a store read is what makes a
client-asserted waiver unlock nothing and a client-asserted extension move no regulatory
deadline. A reference that resolves to nothing leaves the document withheld and the date where it
was.

:meth:`open_items` takes the reader's entitlements and filters on the row's ACL labels IN THE
QUERY rather than after it, which is where object-level authorisation from data tags lands.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from ..domain.models import CaseRecord, WaiverRecord


@runtime_checkable
class CaseStorePort(Protocol):
    def record(self, case: CaseRecord) -> str:
        """Upsert one case row and return its reference."""
        ...

    def open_items(self, tenant: str, entitlements: frozenset[str]) -> tuple[CaseRecord, ...]:
        """The tenant's open items this reader is entitled to see, in a deterministic order."""
        ...

    def waiver(self, ref: str, tenant: str) -> WaiverRecord | None:
        """The stored privilege waiver ``ref`` for ``tenant``, or ``None`` when none exists.

        ``None`` means "no such record exists", which leaves the document withheld. The
        on-premises placeholder RAISES instead of returning ``None``, because an unwired store
        must say it is unwired rather than silently withholding.
        """
        ...

    def extension(self, ref: str, tenant: str) -> date | None:
        """The stored extended due date for ``ref`` and ``tenant``, or ``None``.

        ``None`` means the reference resolves to nothing and the date does not move. The
        on-premises placeholder RAISES for the same reason :meth:`waiver` does.
        """
        ...
