#!/usr/bin/env python3
"""The half a predicate cannot score: is the RESPONSE NARRATIVE any good, judged, against a floor.

`run_eval.py` scores eight metrics and every one is deterministic. The closest thing to a
quality measure there is `citation_grounding`, and it is a predicate: a paragraph passes by
citing only exhibits it was given and writing only numbers it was handed. That is a floor on
honesty. It is not a floor on usefulness, and the two are not the same thing.

A regulator reads this paragraph, with the firm's name on it, inside a statutory clock. It can
be perfectly grounded and still fail to say which item it answers, hedge the completeness figure
until it means nothing, omit the deadline the examiner is counting, or promise a document the
firm never agreed to produce. None of those is ungrounded. All four are wrong, and the only
thing that catches them is a judgement against written criteria.

The whole run is `agent_eval_kit.narrative_main`. This file supplies only what is specific to
this service. The judge is chosen HERE, on the command line, and never from the environment: a
judge selected by a variable is a judge a deployment can change without a diff.

    make eval-narrative     # offline, no model, no credentials, no network
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_eval_kit import narrative_main

_REPO_ROOT = Path(__file__).resolve().parent.parent
DATASET = _REPO_ROOT / "eval" / "datasets" / "narrative_golden.jsonl"
FLOORS = _REPO_ROOT / "config" / "quality-floors.toml"

#: The ways each narrative is written. PROFILES rather than adjectives: they say which
#: deployment produced the paragraph, which is what a portability claim is about. `regressed`
#: is the deliberate defect and must be UNFIT everywhere, or it is not a control.
PROFILES = ("managed", "reduced", "regressed")
CONTROL = "regressed"


if __name__ == "__main__":
    raise SystemExit(
        narrative_main(
            dataset=DATASET,
            floors=FLOORS,
            profiles=PROFILES,
            control=CONTROL,
            description="Response-narrative quality, judged against the model-risk floors.",
            argv=sys.argv[1:],
        )
    )
