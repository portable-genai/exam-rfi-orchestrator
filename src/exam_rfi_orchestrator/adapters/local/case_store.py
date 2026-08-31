"""Local CaseStorePort: a tenant-partitioned SQLite board, with the ACL filter IN THE QUERY.

The store is the difference between an SLA calculation and an SLA clock: without it nobody can
see the open request list and the exam lead has no board. It is written on every item assembly
and read back in the reviewer-queue beat, so it is not a seam nobody exercises.

TWO PROPERTIES ARE LOAD-BEARING AND BOTH ARE IN THE SQL.

* **The tenant partition and the ACL filter are predicates, not a post-filter.** A row is invisible
  to a reader who lacks any one of its labels because the query says so. Filtering after the read
  is a filter somebody eventually forgets to apply on a new call path.
* **A waiver and an extension are STORED RECORDS resolved by reference.** The request carries a
  lookup key and nothing else, so a client-asserted waiver unlocks no privileged document and a
  client-asserted extension moves no regulatory deadline. A key that resolves to nothing, an
  expired record and a record filed under another tenant are all the same answer.

The seeded waiver and extension are obviously fictional and exist so BOTH the resolves and the
does-not-resolve paths run offline. No SDK, no network.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime

from ...config import Settings
from ...domain.kernel import Citation, Severity
from ...domain.models import CaseRecord, Disposition, WaiverRecord

#: The seeded, obviously fictional records. The demo, the fixtures and the golden set all point
#: at these two references, and at one reference that resolves to nothing.
SEEDED_WAIVER_REF = "WVR-FICTIONAL-2027-11"
SEEDED_EXTENSION_REF = "EXT-FICTIONAL-2027-52"
SEEDED_TENANT = "demo-bank"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS case_row (
    tenant TEXT NOT NULL,
    request_id TEXT NOT NULL,
    item_ref TEXT NOT NULL,
    owner TEXT NOT NULL,
    disposition TEXT NOT NULL,
    band TEXT NOT NULL,
    due_on TEXT NOT NULL,
    internal_due_on TEXT NOT NULL,
    business_days_remaining INTEGER NOT NULL,
    completeness_pct INTEGER NOT NULL,
    review_ref TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (tenant, request_id, item_ref)
);
CREATE TABLE IF NOT EXISTS case_acl (
    tenant TEXT NOT NULL,
    request_id TEXT NOT NULL,
    item_ref TEXT NOT NULL,
    label TEXT NOT NULL,
    PRIMARY KEY (tenant, request_id, item_ref, label)
);
CREATE TABLE IF NOT EXISTS waiver (
    ref TEXT NOT NULL,
    tenant TEXT NOT NULL,
    scope TEXT NOT NULL,
    granted_by TEXT NOT NULL,
    expires_on TEXT NOT NULL,
    PRIMARY KEY (ref, tenant)
);
CREATE TABLE IF NOT EXISTS extension (
    ref TEXT NOT NULL,
    tenant TEXT NOT NULL,
    extended_to TEXT NOT NULL,
    PRIMARY KEY (ref, tenant)
);
"""


class LocalCaseStoreAdapter:
    """A SQLite open-item board, ephemeral by default and durable when a path is configured."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # ``check_same_thread=False`` plus an explicit lock, because the click-through demo
        # server is threaded and a connection bound to its creating thread raises there rather
        # than in the gate. The lock is what makes the relaxation safe: sqlite3 documents the
        # flag as requiring the application to serialise access, so the application does.
        self._conn = sqlite3.connect(
            settings.case_store_path or ":memory:", check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
        self._seed()

    def _seed(self) -> None:
        with self._lock:
            self._seed_locked()

    def _seed_locked(self) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO waiver VALUES (?, ?, ?, ?, ?)",
            (
                SEEDED_WAIVER_REF,
                SEEDED_TENANT,
                "data_privacy",
                "general.counsel@bank.example",
                date(2027, 12, 31).isoformat(),
            ),
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO extension VALUES (?, ?, ?)",
            (SEEDED_EXTENSION_REF, SEEDED_TENANT, date(2027, 6, 30).isoformat()),
        )
        self._conn.commit()

    def record(self, case: CaseRecord) -> str:
        with self._lock:
            return self._record_locked(case)

    def _record_locked(self, case: CaseRecord) -> str:
        key = (case.tenant, case.request_id, case.item_ref)
        self._conn.execute(
            "INSERT OR REPLACE INTO case_row VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                case.tenant,
                case.request_id,
                case.item_ref,
                case.owner,
                case.disposition.value,
                case.band.value,
                case.due_on.isoformat(),
                case.internal_due_on.isoformat(),
                case.business_days_remaining,
                case.completeness_pct,
                case.review_ref,
                case.updated_at.isoformat(),
            ),
        )
        self._conn.execute(
            "DELETE FROM case_acl WHERE tenant = ? AND request_id = ? AND item_ref = ?", key
        )
        self._conn.executemany(
            "INSERT OR REPLACE INTO case_acl VALUES (?, ?, ?, ?)",
            [(*key, label) for label in sorted(case.acl_labels)],
        )
        self._conn.commit()
        return f"case:{case.tenant}:{case.request_id}:{case.item_ref}"

    def open_items(self, tenant: str, entitlements: frozenset[str]) -> tuple[CaseRecord, ...]:
        """Rows for this tenant that carry NO label the reader lacks.

        The ``NOT EXISTS`` is the whole authorisation decision, and it lives in the query. An
        empty entitlement set therefore sees untagged rows and nothing else, which is the
        fail-closed reading.
        """
        labels = sorted(entitlements)
        placeholders = ", ".join("?" for _ in labels) or "NULL"
        sql = (
            "SELECT c.*, ("
            "  SELECT group_concat(a2.label) FROM case_acl AS a2 WHERE a2.tenant = c.tenant "
            "  AND a2.request_id = c.request_id AND a2.item_ref = c.item_ref"
            ") AS labels "
            "FROM case_row AS c WHERE c.tenant = ? AND NOT EXISTS ("
            "  SELECT 1 FROM case_acl AS a WHERE a.tenant = c.tenant "
            "  AND a.request_id = c.request_id AND a.item_ref = c.item_ref "
            f"  AND a.label NOT IN ({placeholders})"
            ") ORDER BY c.request_id, c.item_ref"
        )
        with self._lock:
            rows = self._conn.execute(sql, (tenant, *labels)).fetchall()
        return tuple(_to_case(row) for row in rows)

    def waiver(self, ref: str, tenant: str) -> WaiverRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM waiver WHERE ref = ? AND tenant = ?", (ref, tenant)
            ).fetchone()
        if row is None:
            return None
        return WaiverRecord(
            ref=str(row["ref"]),
            tenant=str(row["tenant"]),
            scope=str(row["scope"]),
            granted_by=str(row["granted_by"]),
            expires_on=date.fromisoformat(str(row["expires_on"])),
            citation=Citation(
                source_id=f"waiver:{row['ref']}",
                title="Recorded privilege waiver (FICTIONAL)",
                snippet=f"Waiver of scope {row['scope']} recorded for this tenant.",
            ),
        )

    def extension(self, ref: str, tenant: str) -> date | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT extended_to FROM extension WHERE ref = ? AND tenant = ?", (ref, tenant)
            ).fetchone()
        return None if row is None else date.fromisoformat(str(row["extended_to"]))


def _to_case(row: sqlite3.Row) -> CaseRecord:
    return CaseRecord(
        request_id=str(row["request_id"]),
        item_ref=str(row["item_ref"]),
        tenant=str(row["tenant"]),
        owner=str(row["owner"]),
        disposition=Disposition(str(row["disposition"])),
        band=Severity(str(row["band"])),
        due_on=date.fromisoformat(str(row["due_on"])),
        internal_due_on=date.fromisoformat(str(row["internal_due_on"])),
        business_days_remaining=int(row["business_days_remaining"]),
        completeness_pct=int(row["completeness_pct"]),
        review_ref=str(row["review_ref"]),
        acl_labels=frozenset(str(row["labels"] or "").split(",")) - {""},
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )
