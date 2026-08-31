"""GCP KnowledgeBaseReadPort: reach the governed store over HTTPS, refusing when unconfigured.

The endpoint is per-deployment configuration (``EXAMRFI_KNOWLEDGE_BASE_URL``), read three-state:
UNSET and SET-AND-EMPTY both arrive as ``""`` and this adapter REFUSES every call rather than
reaching a default host. That refusal is the managed-family behaviour the parity suite asserts
offline.

The caller's entitlements are forwarded so filtering happens IN the store, and the response is
re-checked by rule A1 anyway, which is defence in depth rather than duplication.

The ``google.*`` auth imports stay INSIDE the method so ``local`` and ``onprem`` import this
module with no cloud SDK installed (the portability proof).
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import RetrievalQuery, RetrievalResult


class CloudKnowledgeBaseAdapter:
    """Reach the governed corpus over HTTPS, or refuse when the endpoint is unconfigured."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def search(self, query: RetrievalQuery) -> RetrievalResult:
        url = self._settings.knowledge_base_url
        if not url:
            raise RuntimeError(
                "knowledge-base endpoint is unconfigured: set EXAMRFI_KNOWLEDGE_BASE_URL to the "
                "governed store's URL. There is no default host to fall back to, because an "
                "empty answer from the wrong host is a false statement about what the firm holds."
            )
        return self._reach(url, query)

    def _reach(
        self, url: str, query: RetrievalQuery
    ) -> RetrievalResult:  # pragma: no cover - needs the live governed store
        # Lazy import: absent offline and in CI, so a managed run without the SDK raises here.
        from google.auth import default as google_auth_default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _project = google_auth_default()
        session = AuthorizedSession(credentials)
        response = session.get(
            url,
            params={
                "topic": query.topic.value,
                "artefacts": ",".join(a.value for a in query.artefacts),
                "period_start": query.period_start.isoformat(),
                "period_end": query.period_end.isoformat(),
                "principals": ",".join(sorted(query.entitlements)),
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return self._parse(response.json())

    @staticmethod
    def _parse(
        payload: object,
    ) -> RetrievalResult:  # pragma: no cover - needs the live governed store
        raise NotImplementedError(
            "wire the governed store's payload parsing when its live surface is available, and "
            "report what entitlement filtering suppressed as BOTH a total and a per-artefact "
            "split: an unattributed total makes the engine say 'you are not entitled to read "
            "this' about every class the item asked for"
        )
