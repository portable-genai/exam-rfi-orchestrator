"""GCP CaseStorePort: Firestore in the residency region, refusing when unconfigured.

The collection is per-deployment configuration (``EXAMRFI_CASE_COLLECTION``), read three-state:
unset and emptied both arrive as ``""`` and this adapter refuses rather than writing to a default
collection. The ``google.cloud.firestore`` import is lazy, inside the method, so the offline
profiles import this module with no cloud SDK installed.

The vertical's Firestore resource is NOT yet in the Terraform posture: its API belongs in
``apis.tf``, its CMEK service-agent binding in ``kms.tf``, its least-privilege role in ``iam.tf``
and its entry in ``vpc_sc.tf``, in one commit. ``docs/practices-audit.md`` records that as an
open gap rather than implying it is done.
"""

from __future__ import annotations

from datetime import date

from ...config import Settings
from ...domain.models import CaseRecord, WaiverRecord


class CloudCaseStoreAdapter:
    """Persist and read the open-item board in Firestore, or refuse when unconfigured."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def record(self, case: CaseRecord) -> str:
        self._require()
        raise NotImplementedError(  # pragma: no cover - needs live Firestore
            "wire the Firestore write when the collection is provisioned in apis.tf, kms.tf, "
            "iam.tf and vpc_sc.tf"
        )

    def open_items(self, tenant: str, entitlements: frozenset[str]) -> tuple[CaseRecord, ...]:
        self._require()
        raise NotImplementedError(  # pragma: no cover - needs live Firestore
            "wire the Firestore query when the collection is provisioned; the ACL filter belongs "
            "in the query, not after it"
        )

    def waiver(self, ref: str, tenant: str) -> WaiverRecord | None:
        self._require()
        raise NotImplementedError(  # pragma: no cover - needs live Firestore
            "wire the Firestore waiver lookup when the collection is provisioned"
        )

    def extension(self, ref: str, tenant: str) -> date | None:
        self._require()
        raise NotImplementedError(  # pragma: no cover - needs live Firestore
            "wire the Firestore extension lookup when the collection is provisioned"
        )

    def _require(self) -> str:
        collection = self._settings.case_collection
        if not collection:
            raise RuntimeError(
                "case-store collection is unconfigured: set EXAMRFI_CASE_COLLECTION. There is no "
                "default collection, because a waiver or an extension resolved from the wrong "
                "place is worse than one that does not resolve at all."
            )
        return collection
