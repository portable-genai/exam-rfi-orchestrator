"""Exhibit numbering and the document index: the annex a supervisor actually receives.

Rule E1. Within an item, accepted links are sorted by (artefact declaration index, effective
date, document id) and numbered ``EX-<item_ref>-01`` upward. At pack level the index renumbers
contiguously across items in item order as ``IDX-001`` upward, keeping the exhibit number as a
cross-reference.

The numbering comes out of a SORT rather than out of a model, and that is not a stylistic
preference: two runs over the same inputs have to produce the same annex, or a resubmission
cannot be diffed against the original and a cover letter cannot cross-reference anything. The
sort key's first component is the declaration order of :class:`~.models.ArtefactClass`, which is
why that order is policy and moving a member renumbers historical exhibits.

Withheld documents never reach the index. They are recorded on the withholding schedule instead,
which is a different surface with a different meaning.

Pure stdlib: no ports, no I/O, no model, no clock.
"""

from __future__ import annotations

from collections.abc import Sequence

from .models import ARTEFACT_ORDER, EvidenceLink, Exhibit, ItemAssessment

__all__ = ["number_exhibits", "renumber_document_index"]


def _sort_key(link: EvidenceLink) -> tuple[int, str, str]:
    return (ARTEFACT_ORDER[link.artefact], link.as_of.isoformat(), link.doc_id)


def number_exhibits(item_ref: str, accepted: Sequence[EvidenceLink]) -> tuple[Exhibit, ...]:
    """Number one item's ACCEPTED links deterministically as ``EX-<item_ref>-NN``.

    ``redacted`` is set on every exhibit: the title and locator that leave this service have
    already been through the masking pass, and saying so on the row is what lets a reader tell a
    masked annex from an unmasked one without opening the documents.
    """
    ordered = sorted(accepted, key=_sort_key)
    return tuple(
        Exhibit(
            exhibit_no=f"EX-{item_ref}-{position:02d}",
            doc_id=link.doc_id,
            title=link.title,
            artefact=link.artefact,
            as_of=link.as_of,
            locator=link.locator,
            origin=link.origin,
            redacted=True,
            citation=link.citation,
        )
        for position, link in enumerate(ordered, start=1)
    )


def renumber_document_index(items: Sequence[ItemAssessment]) -> tuple[Exhibit, ...]:
    """Renumber every item's exhibits contiguously across the pack as ``IDX-NNN``.

    The exhibit number survives as a cross-reference, so a per-item narrative citing
    ``EX-2.c-01`` still resolves after the pack-level renumbering.
    """
    out: list[Exhibit] = []
    position = 1
    for item in items:
        for exhibit in item.exhibits:
            out.append(_with_index(exhibit, f"IDX-{position:03d}"))
            position += 1
    return tuple(out)


def _with_index(exhibit: Exhibit, index_no: str) -> Exhibit:
    return Exhibit(
        exhibit_no=exhibit.exhibit_no,
        doc_id=exhibit.doc_id,
        title=exhibit.title,
        artefact=exhibit.artefact,
        as_of=exhibit.as_of,
        locator=exhibit.locator,
        origin=exhibit.origin,
        redacted=exhibit.redacted,
        index_no=index_no,
        citation=exhibit.citation,
    )
