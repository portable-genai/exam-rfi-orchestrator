"""On-prem KnowledgeBaseReadPort: fail-fast portability placeholder (P-12).

This is the seam whose silent success would be worst in the repository. A placeholder returning
an empty tuple would not look broken: it would look like a firm that holds no responsive
evidence, and that is what would go to the supervisor over somebody's signature. So it raises,
and the portability tour asserts the refusal by name.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RetrievalQuery, RetrievalResult


class OnPremKnowledgeBaseAdapter:
    """Satisfies the port but refuses at call time: the client binds its own retrieval link."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search(self, query: RetrievalQuery) -> RetrievalResult:
        raise NotImplementedError(
            "on-prem knowledge_base is a portability placeholder: bind the client's own governed "
            "retrieval store (see docs/onprem-migration.md). An empty success here would be a "
            "false statement to a regulator about what the firm holds."
        )
