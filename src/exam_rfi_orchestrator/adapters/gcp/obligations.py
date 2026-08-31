"""GCP ObligationsReadPort: read the obligation register over HTTPS, refusing when unconfigured.

``EXAMRFI_OBLIGATIONS_URL`` is read three-state: UNSET and SET-AND-EMPTY both arrive as ``""``
and this adapter refuses rather than reaching a default host. The ``google.auth`` import is lazy,
inside the method, so the offline profiles import this module with no cloud SDK present.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import ObligationRef, RequestTopic


class CloudObligationsAdapter:
    """Read the obligation register, or refuse when the endpoint is unconfigured."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def obligations_for(self, topic: RequestTopic, jurisdiction: str) -> tuple[ObligationRef, ...]:
        url = self._settings.obligations_url
        if not url:
            raise RuntimeError(
                "obligation register endpoint is unconfigured: set EXAMRFI_OBLIGATIONS_URL. "
                "There is no default host, because an empty register looks exactly like a topic "
                "with no obligations and would leave a submission with no regulatory anchor."
            )
        return self._reach(url, topic, jurisdiction)

    def _reach(
        self, url: str, topic: RequestTopic, jurisdiction: str
    ) -> tuple[ObligationRef, ...]:  # pragma: no cover - needs the live register
        from google.auth import default as google_auth_default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _project = google_auth_default()
        session = AuthorizedSession(credentials)
        response = session.get(
            url, params={"topic": topic.value, "jurisdiction": jurisdiction}, timeout=10.0
        )
        response.raise_for_status()
        return self._parse(response.json())

    @staticmethod
    def _parse(
        payload: object,
    ) -> tuple[ObligationRef, ...]:  # pragma: no cover - needs the live register
        raise NotImplementedError(
            "wire the obligation register's payload parsing when its live surface is available"
        )
