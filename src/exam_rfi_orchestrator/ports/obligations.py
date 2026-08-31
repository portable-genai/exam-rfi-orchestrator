"""ObligationsReadPort: the obligation register, read-only by construction.

The fleet's obligations-and-control-mapping service is the single system of record for the
obligation graph and this repository holds no parallel register. The Protocol returns obligations
and cannot write them, so this service can never grow a second register that drifts.

Rule D3 depends on it: the register, not the question's wording, sets the floor on what must be
produced, which is what stops a badly worded question from decomposing to fewer artefacts than
the obligation demands. Every item's narrative then cites the obligation the regulator is
testing rather than rule text a model composed.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import ObligationRef, RequestTopic


@runtime_checkable
class ObligationsReadPort(Protocol):
    def obligations_for(self, topic: RequestTopic, jurisdiction: str) -> tuple[ObligationRef, ...]:
        """The obligations that bear on ``topic`` in ``jurisdiction``, possibly none.

        An empty tuple is a legitimate answer, and the service records the explicit string "no
        obligation text available" with a citation naming the register rather than guessing a
        rule reference. A failure to REACH the register raises: a silent empty answer would look
        identical to "this topic has no obligations", which would remove every D3 mandatory
        requirement from the completeness denominator and leave a submission with no regulatory
        anchor anywhere in it while the service looked entirely healthy.
        """
        ...
