"""Local EvidencePackReadPort: obviously fictional assembled packs, reused on identical terms.

The pack's documents enter the SAME admissibility ladder as corpus hits, so reuse gets no
shortcut through the release rules. The seeded pack deliberately carries three documents that are
NOT responsive to the outsourcing question (two of the wrong artefact class, one of a different
topic) so rule A2's over-production control has something real to drop offline.

The two methods keep their different failure semantics: an unknown obligation id is an empty
tuple, because "this obligation has no assembled pack" is a legitimate answer; an unknown pack
reference RAISES, because an item that named a pack which is not there is a caller error and not
a coverage result.
"""

from __future__ import annotations

from datetime import date

from ...config import Settings
from ...domain.kernel import Citation
from ...domain.models import ArtefactClass, EvidenceItem, EvidencePack, RequestTopic, SensitivityTag

_SG = "SG"
_RISK = frozenset({"group:risk"})

#: The pack reference an item names on the wire. A module constant so the fixtures, the demo and
#: the golden set all point at the same obviously fictional pack.
OUTSOURCING_PACK_REF = "PACK-FICTIONAL-OUT-2027-01"
OUTSOURCING_OBLIGATION = "OBL-OUT-001"


def _packed(
    doc_id: str,
    title: str,
    artefact: ArtefactClass,
    topic: RequestTopic,
    as_of: date,
    *,
    tags: tuple[SensitivityTag, ...] = (),
    locator: str = "",
    snippet: str = "",
) -> EvidenceItem:
    return EvidenceItem(
        doc_id=doc_id,
        title=title,
        artefact=artefact,
        topic=topic,
        as_of=as_of,
        owning_jurisdiction=_SG,
        sensitivity=tags,
        acl_labels=_RISK,
        locator=locator,
        snippet=snippet,
        origin="evidence_pack",
    )


_PACK = EvidencePack(
    pack_ref=OUTSOURCING_PACK_REF,
    obligation_id=OUTSOURCING_OBLIGATION,
    title="Outsourcing control evidence pack (FICTIONAL)",
    assembled_on=date(2027, 2, 20),
    items=(
        _packed(
            "pk-out-con-01",
            "Payments processor schedule of services (FICTIONAL)",
            ArtefactClass.THIRD_PARTY_CONTRACT,
            RequestTopic.OUTSOURCING_THIRD_PARTY,
            date(2026, 12, 1),
            locator="schedule 2",
            snippet="Service schedule appended to the master agreement (FICTIONAL).",
        ),
        _packed(
            "pk-out-ctl-01",
            "Provider oversight control test (FICTIONAL)",
            ArtefactClass.CONTROL_TEST_RESULT,
            RequestTopic.OUTSOURCING_THIRD_PARTY,
            date(2027, 2, 1),
            locator="table 1",
            snippet="Oversight control testing for the processor (FICTIONAL).",
        ),
        # Three deliberately NON-RESPONSIVE documents. Rule A2 drops all three and counts them;
        # none of them reaches the index, the schedule, the review payload or the prompt.
        _packed(
            "pk-out-cus-01",
            "Provider staff record (FICTIONAL)",
            ArtefactClass.CUSTOMER_FILE,
            RequestTopic.OUTSOURCING_THIRD_PARTY,
            date(2026, 11, 1),
            snippet="Not responsive to an outsourcing register question (FICTIONAL).",
        ),
        _packed(
            "pk-out-txn-01",
            "Processor settlement sample (FICTIONAL)",
            ArtefactClass.TRANSACTION_SAMPLE,
            RequestTopic.OUTSOURCING_THIRD_PARTY,
            date(2026, 11, 2),
            snippet="Not responsive to an outsourcing register question (FICTIONAL).",
        ),
        _packed(
            "pk-out-off-01",
            "Financial crime policy extract (FICTIONAL)",
            ArtefactClass.POLICY,
            RequestTopic.AML_FINANCIAL_CRIME,
            date(2026, 11, 3),
            snippet="A different topic entirely (FICTIONAL).",
        ),
    ),
    citation=Citation(
        source_id=f"pack:{OUTSOURCING_PACK_REF}",
        title="Outsourcing control evidence pack (FICTIONAL)",
        snippet="Pre-assembled control mapping reused rather than rebuilt.",
    ),
)

_BY_REF: dict[str, EvidencePack] = {OUTSOURCING_PACK_REF: _PACK}
_BY_OBLIGATION: dict[str, tuple[EvidencePack, ...]] = {OUTSOURCING_OBLIGATION: (_PACK,)}


def pack_documents() -> dict[str, EvidenceItem]:
    """Every packed document by id, for the same reason the corpus exposes its own."""
    return {document.doc_id: document for pack in _BY_REF.values() for document in pack.items}


class LocalEvidencePackAdapter:
    """Answer pack lookups from a deterministic fixture (no network, no SDK)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def packs_for(self, obligation_id: str) -> tuple[EvidencePack, ...]:
        return _BY_OBLIGATION.get(obligation_id, ())

    def fetch(self, pack_ref: str) -> EvidencePack:
        pack = _BY_REF.get(pack_ref)
        if pack is None:
            raise LookupError(
                f"no assembled evidence pack {pack_ref!r}. A pack that does not exist is a caller "
                "error, not an empty coverage result."
            )
        return pack
