"""ReviewRouterPort: the boundary that routes a reviewable outcome to human review (rule R8).

Rule R8 is the reason this port exists. A producer that sets ``requires_human_review`` MUST hand
the item to the Human-Review and Maker-Checker Console; terminating the escalation in a per-repo
boolean is the failure this port removes, because a flag nobody reads is auto-execution with
extra steps. Setting the flag and calling :meth:`route` is one act, not two optional ones.

It is typed on :class:`~..domain.models.ReviewableOutcome`, the Protocol both a per-item
assessment and a whole response pack satisfy, so R8 has ONE routing path for two artifact shapes
rather than two payload builders that drift apart. The pack routes unconditionally, including
when every item in it is clean, because the contract is that a regulator response is approved
before it leaves the firm.

The domain stays pure. This port names the hand-off; the adapters (not this module) depend on the
shared review kit and perform the service-to-service submission.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import ReviewableOutcome


@runtime_checkable
class ReviewRouterPort(Protocol):
    def route(self, result: ReviewableOutcome, *, maker: str, tenant: str = "") -> str:
        """Route one reviewable outcome to human review and return the routing reference.

        ``maker`` is the VERIFIED principal that originated the underlying decision, never a
        client-asserted actor. The return value is the console's review id where the console
        answered, or a local queue reference where the submission was buffered; it is never
        empty, so a caller can record what happened to the escalation.
        """
        ...
