"""EvidencePackReadPort: reuse of the risk function's assembled control-evidence packs.

The catalog names reuse of pre-assembled evidence packs, and reuse has to be a read with a name
or it is a claim nobody can check. An exam question about outsourcing controls is often already
answered by a pack mapping the obligation to its controls and their evidence, and rebuilding that
mapping here would create a second, drifting answer to the same question.

TWO METHODS WITH DELIBERATELY DIFFERENT FAILURE SEMANTICS. :meth:`packs_for` is a lookup BY
OBLIGATION where empty is a legitimate answer (this obligation has no assembled pack).
:meth:`fetch` is a lookup BY NAME where absence is an error (the item named a pack that does not
exist). Collapsing them would make "that pack does not exist" indistinguishable from "that pack
is empty", and only one of those is a coverage result.

Kept separate from the knowledge base because it is a different system of record with a different
DTO. A reused pack gets no shortcut: its documents enter the SAME admissibility ladder as corpus
hits, so reuse can never become a route around the release rules.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import EvidencePack


@runtime_checkable
class EvidencePackReadPort(Protocol):
    def packs_for(self, obligation_id: str) -> tuple[EvidencePack, ...]:
        """Every assembled pack mapped to ``obligation_id``, possibly none."""
        ...

    def fetch(self, pack_ref: str) -> EvidencePack:
        """The pack named by ``pack_ref``.

        Raises:
            LookupError: when no such pack exists. An item that names a pack which is not there
                is a caller error worth surfacing, not an empty coverage result.
        """
        ...
