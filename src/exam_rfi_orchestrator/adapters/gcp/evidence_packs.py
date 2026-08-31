"""GCP EvidencePackReadPort: read assembled packs over HTTPS, refusing when unconfigured.

``EXAMRFI_EVIDENCE_PACKS_URL`` is read three-state and this adapter refuses when it is unset or
emptied rather than reaching a default host. An empty pack from a placeholder would silently
reduce coverage, and because completeness drives the release gate it would turn a releasable item
into a blocked one with no visible cause, or assert that the firm holds no control evidence it in
fact holds.
"""

from __future__ import annotations

from ...config import Settings
from ...domain.models import EvidencePack


class CloudEvidencePackAdapter:
    """Read assembled evidence packs, or refuse when the endpoint is unconfigured."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def packs_for(self, obligation_id: str) -> tuple[EvidencePack, ...]:
        url = self._require()
        return self._reach_many(url, obligation_id)

    def fetch(self, pack_ref: str) -> EvidencePack:
        url = self._require()
        return self._reach_one(url, pack_ref)

    def _require(self) -> str:
        url = self._settings.evidence_packs_url
        if not url:
            raise RuntimeError(
                "evidence-pack endpoint is unconfigured: set EXAMRFI_EVIDENCE_PACKS_URL. "
                "There is no default host to fall back to."
            )
        return url

    def _reach_many(
        self, url: str, obligation_id: str
    ) -> tuple[EvidencePack, ...]:  # pragma: no cover - needs the live pack surface
        from google.auth import default as google_auth_default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _project = google_auth_default()
        session = AuthorizedSession(credentials)
        response = session.get(url, params={"obligation_id": obligation_id}, timeout=10.0)
        response.raise_for_status()
        raise NotImplementedError(
            "wire the evidence-pack payload parsing when its live surface is available"
        )

    def _reach_one(
        self, url: str, pack_ref: str
    ) -> EvidencePack:  # pragma: no cover - needs the live pack surface
        from google.auth import default as google_auth_default
        from google.auth.transport.requests import AuthorizedSession

        credentials, _project = google_auth_default()
        session = AuthorizedSession(credentials)
        response = session.get(url, params={"pack_ref": pack_ref}, timeout=10.0)
        response.raise_for_status()
        raise NotImplementedError(
            "wire the evidence-pack payload parsing when its live surface is available"
        )
