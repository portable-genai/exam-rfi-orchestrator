"""KnowledgeBaseReadPort: ACL-aware retrieval against the governed enterprise corpus.

The catalog contract names ACL-aware retrieval reaching the shared enterprise knowledge base as a
PORT, and this repository builds no retrieval backend of its own. The seam is what makes empty
retrieval a hard blocker (rule G1) rather than an ungrounded answer.

WHY THIS PORT RETURNS A RESULT OBJECT RATHER THAN THE BARE TUPLE THE SIBLING REPOS USE. This is
the one deliberate deviation from the fleet's retrieval shape, and it is load-bearing.
:class:`~..domain.models.RetrievalResult` carries ``suppressed_by_entitlement``, the COUNT of
responsive documents the store refused to serve this principal, and ``suppressed_by_artefact``,
that count split by artefact class. The count is what turns "nothing came back" into "responsive
documents exist that you may not read", and a regulator told the first when the second is true
has been given a materially false statement. The split is what keeps that sentence attached to
the class it is true of: an item-level total alone makes it about every class the item asked
for, including classes the firm genuinely holds nothing of. Both are only counts: no title, no
id, nothing that leaks what was withheld. An adapter that cannot attribute leaves the split
empty and the engine keeps the over-broad reading rather than understating a denial.

The query and result DTOs live in ``domain/models.py`` next to the engine that consumes them, so
the port imports the domain and the domain imports no port.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import RetrievalQuery, RetrievalResult


@runtime_checkable
class KnowledgeBaseReadPort(Protocol):
    def search(self, query: RetrievalQuery) -> RetrievalResult:
        """Retrieve the entitled candidate documents for ``query``, possibly none.

        An empty ``items`` tuple with ``corpus_reached`` true is a LEGITIMATE answer that rule G1
        turns into "no draft". A failure to REACH the store is a raised error (the managed
        family) or ``NotImplementedError`` (the on-premises placeholder), never a silent empty
        success: an empty success here would not look broken, it would look like a firm that
        holds no responsive evidence, and that is what would go to the supervisor over somebody's
        signature.
        """
        ...
