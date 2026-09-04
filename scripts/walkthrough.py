"""Presenter-paced walkthrough of the live demo, with a hard assertion behind every step.

This is the script you run in front of somebody. It starts the demo server itself (and stops it
on exit), narrates each step on THIS terminal, waits for you, then performs the step and checks
that the service really reached the state the narration just claimed. The audience sees only the
clean output view; the narration never appears on the page.

It drives the server over plain HTTP with the stdlib, deliberately. A walkthrough that needed a
browser engine could not be installed offline, could not run in CI, and would rot the first time
the engine moved. Because it needs none, ``--auto`` turns the same script into the demo's
self-test (practices check F2): the demo cannot rot silently, because the same steps run
unattended on every push and fail the build when a claim stops being true.

    make demo             # presenter-paced, opens the page in a browser
    make demo-selftest    # unattended and headless, asserts every step, non-zero on failure

At a prompt: Enter runs the step, a number jumps to that step, ``r`` restarts, ``q`` quits.

Environment overrides: ``DEMO_URL`` (attach to a running server instead of spawning one),
``DEMO_PORT``, ``HEADLESS=1`` (never open a browser), ``DEMO_AUTO=1`` (do not wait for input).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

import demo

HERE = Path(__file__).resolve().parent
_TTY = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    """Colour for a real terminal, plain text when the output is captured (CI logs)."""
    return "\033[" + code + "m" + text + "\033[0m" if _TTY else text


# --------------------------------------------------------------------------------------- #
# What each step must have actually done. The demo's narration is a claim; this is the check.
# --------------------------------------------------------------------------------------- #

Check = Callable[[dict[str, Any]], list[str]]


def _facts(state: dict[str, Any]) -> dict[str, Any]:
    facts = state["steps"][-1]["facts"]
    return dict(facts) if isinstance(facts, dict) else {}


def _check_opened(state: dict[str, Any]) -> list[str]:
    """The stack is bound offline AND the policy it will decide with was actually configured.

    The second half is the point. A demo that opened over an empty policy block would run every
    later beat on module defaults nobody chose, and would look identical to one that did not.
    """
    facts = _facts(state)
    problems: list[str] = []
    if state["profile"] != "local":
        problems.append("expected the local profile, got " + str(state["profile"]))
    if facts.get("sdk_modules"):
        problems.append("a cloud SDK was imported: " + str(facts["sdk_modules"]))
    if len(facts.get("profiles", [])) < 3:
        problems.append("fewer than three profiles are bound for every port")
    if not facts.get("response_windows"):
        problems.append("the policy block carries no response windows")
    if not facts.get("band_ceilings"):
        problems.append("the policy block carries no SLA band ceilings")
    if not facts.get("hard_withhold_tags"):
        problems.append("the policy block names no tag that is never produced")
    if not facts.get("silent_withhold_tags"):
        problems.append("the policy block names no silent-withhold tag")
    for regime in demo.REQUIRED_REGIMES:
        if regime not in facts.get("regimes", []):
            problems.append("the regime register is missing " + regime)
    for jurisdiction in demo.REQUIRED_CALENDARS:
        if jurisdiction not in facts.get("calendars", []):
            problems.append("no business calendar is configured for " + jurisdiction)
    if any(not version for version in facts.get("calendar_versions", [])):
        problems.append("a business calendar carries no version, so no deadline can be pinned")
    if facts.get("generator_model") in ("", "no-model"):
        problems.append(
            "a generative port is bound but the banner reports no model; a reviewer is "
            "entitled to know which of the two they are reading"
        )
    return problems


def _check_routine(state: dict[str, Any]) -> list[str]:
    facts = _facts(state)
    problems: list[str] = []
    if facts.get("requires_human_review"):
        problems.append("a fully evidenced item escalated")
    if facts.get("review_ref"):
        problems.append("a review was manufactured for an item with no blocker")
    if state["totals"]["escalated"] != 0:
        problems.append("escalation count moved on a routine item")
    if facts.get("completeness_pct") != 100:
        problems.append(
            "the fully evidenced item is not complete: " + str(facts.get("completeness_pct"))
        )
    if facts.get("disposition") != "on_track":
        problems.append(
            "the fully evidenced item is not on track: " + str(facts.get("disposition"))
        )
    if not facts.get("exhibits"):
        problems.append("a fully evidenced item indexed no exhibit")
    if not facts.get("exhibits_reproduce"):
        problems.append(
            "the exhibit numbers did not reproduce on a second run over the same inputs"
        )
    if not facts.get("narrative_grounded"):
        problems.append("the draft cited an exhibit outside this item's index, or cited none")
    if facts.get("release_state") != "held_for_checker":
        problems.append("an outcome did not come back held for a checker")
    return problems


def _check_escalation(state: dict[str, Any]) -> list[str]:
    facts = _facts(state)
    problems: list[str] = []
    if not facts.get("requires_human_review"):
        problems.append("a critical item did not escalate")
    if not facts.get("review_ref"):
        problems.append("rule R8: an escalation was flagged but not routed")
    totals = state["totals"]
    if totals["routed"] != totals["escalated"]:
        problems.append("routed and escalated counts disagree")
    if not facts.get("release_blockers_named"):
        problems.append("a release blocker is free text rather than a named BlockerKind")
    if not facts.get("prior_answer_conflict"):
        problems.append("the contradiction with the prior submission was not detected")
    if facts.get("release_state") != "held_for_checker":
        problems.append("an escalated outcome was not held for a checker")
    return problems


def _check_redaction(state: dict[str, Any]) -> list[str]:
    facts = _facts(state)
    problems: list[str] = []
    if facts.get("planted_identifier_leaked"):
        problems.append("the planted identifier reached the immutable record or the outcome")
    if facts.get("privileged_snippet_leaked"):
        problems.append("a withheld document's snippet reached a citation, a draft or the record")
    if not facts.get("review_ref"):
        problems.append("rule R8: the item with withheld evidence was not routed")
    withheld = facts.get("withheld", [])
    if len(withheld) < 3:
        problems.append("the withholding schedule does not carry every non-produced document")
    known_bases = {"A1", "A4", "A5", "A6"}
    for record in withheld:
        if str(record.get("basis_rule")) not in known_bases:
            problems.append("a withhold row carries no known basis rule: " + str(record))
    if facts.get("silent_withhold_titled"):
        problems.append(
            "a silent-withhold row carried a title, which is the fact it must not state"
        )
    return problems


def _check_review_queue(state: dict[str, Any]) -> list[str]:
    facts = _facts(state)
    problems: list[str] = []
    if facts.get("wire_leak"):
        problems.append("personal data or a withheld snippet reached the outbound review payload")
    # The pack routes on top of every item escalation, so the queue holds one more than the
    # escalated count. Asserting the two separately is what stops a console integration that
    # merged item exceptions and pack approvals into one list from looking correct here.
    if int(facts.get("pending", 0)) != int(state["totals"]["escalated"]) + 1:
        problems.append("the queue does not hold every item escalation plus exactly one pack")
    if not facts.get("pack_review_ref"):
        problems.append("rule P2: the pack was assembled but not routed for approval")
    if not facts.get("approvals_match"):
        problems.append("a queued review's approval count disagrees with the engine's number")
    if not facts.get("dual_control_without_escalation"):
        problems.append(
            "the skilled-person item did not demand two approvals without escalating, so dual "
            "control and escalation are not being answered separately"
        )
    if facts.get("pack_release_state") != "held_for_checker":
        problems.append("the pack did not come back held for a checker")
    if int(facts.get("board_rows", 0)) < 1:
        problems.append("the open-item board is empty, so the SLA clock is not a clock")
    return problems


def _check_audit(state: dict[str, Any]) -> list[str]:
    facts = _facts(state)
    problems: list[str] = []
    if not facts.get("chain_ok"):
        problems.append("the audit chain did not verify: " + str(facts))
    if not facts.get("anchored"):
        problems.append("no external head anchor was written")
    if not facts.get("round_trip_ok"):
        problems.append("the exported trail did not reload with its chain intact")
    if int(facts.get("entries", 0)) < 3:
        problems.append("fewer audit records than items assessed")
    if not facts.get("due_basis_recorded"):
        problems.append("an audit record does not name the rule that set its deadline")
    if not facts.get("calendar_version_recorded"):
        problems.append("an audit record does not pin the calendar version it computed against")
    if not facts.get("withhold_bases_recorded"):
        problems.append("the withholding bases did not survive into the exported trail")
    return problems


def _check_tamper(state: dict[str, Any]) -> list[str]:
    facts = _facts(state)
    problems: list[str] = []
    if facts.get("chain_ok"):
        problems.append("a rewritten record still verified: the chain is not tamper-evident")
    if not facts.get("detected"):
        problems.append("the report did not name the rewritten record")
    return problems


def _check_portability(state: dict[str, Any]) -> list[str]:
    facts = _facts(state)
    # Two expectations, not one. Every control seam must REFUSE, and every seam documented as a
    # diagnostic must be ABSENT. Checking only the first would let a tracer that started raising
    # pass, and checking only the union would let a control seam quietly move into the exempt set.
    expected_refused = sorted(set(demo.EXIT_CALLS) - demo.EXIT_ABSENT)
    expected_absent = sorted(demo.EXIT_ABSENT)
    refused = sorted(facts.get("refused", []))
    absent = sorted(facts.get("absent", []))
    problems: list[str] = []
    if refused != expected_refused:
        problems.append("the exit profile did not refuse every control seam: " + str(refused))
    if absent != expected_absent:
        problems.append("a seam meant to be absent on-prem was not: " + str(absent))
    return problems


#: One entry per step key, in the demo's order. A step added to ``demo.STEPS`` without a check
#: here fails the walkthrough immediately, so the arc and its assertions cannot drift.
CHECKS: dict[str, Check] = {
    "opened": _check_opened,
    "routine": _check_routine,
    "escalation": _check_escalation,
    "redaction": _check_redaction,
    "review_queue": _check_review_queue,
    "audit": _check_audit,
    "tamper": _check_tamper,
    "portability": _check_portability,
}


# --------------------------------------------------------------------------------------- #
# Driving the server
# --------------------------------------------------------------------------------------- #


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _get(url: str, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(url + path, timeout=10) as response:  # noqa: S310 - loopback
        payload = json.loads(response.read().decode("utf-8"))
    return dict(payload)


def _post(url: str, path: str) -> None:
    request = urllib.request.Request(url + path, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - loopback
        response.read()


def _wait_for(url: str, process: subprocess.Popen[bytes] | None, seconds: float = 30.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise SystemExit("the demo server exited before it was ready")
        try:
            _get(url, "/healthz")
            return
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            time.sleep(0.1)
    raise SystemExit("the demo server never became ready at " + url)


def _print_step(state: dict[str, Any]) -> None:
    step = state["steps"][-1]
    number = str(int(state["step_index"]) + 1) + "/" + str(state["step_count"])
    print("")
    print(_c("1;36", "  step " + number + ": " + str(step["label"])))
    for panel in step["panels"]:
        print(_c("1", "    " + panel["title"]))
        for row in panel["rows"]:
            print("      " + str(row["label"]) + ": " + str(row["value"]))


def _prompt(state: dict[str, Any], auto: bool) -> str:
    """Return the presenter's instruction: ``next``, ``restart``, ``quit`` or a step number."""
    upcoming = state["next"] or "finish"
    print("")
    print(_c("0;33", "  next: " + str(upcoming)))
    if auto:
        return "next"
    try:
        answer = input("  [Enter] run  [number] jump  [r] restart  [q] quit > ").strip().lower()
    except EOFError:
        return "quit"
    if answer in ("q", "quit"):
        return "quit"
    if answer in ("r", "restart"):
        return "restart"
    if answer.isdigit():
        return answer
    return "next"


def run(url: str, *, auto: bool, headless: bool, process: subprocess.Popen[bytes] | None) -> int:
    _wait_for(url, process)
    state = _get(url, "/state")
    if not headless:
        webbrowser.open(url)

    print(_c("1", state["repository"] + " ( walkthrough"))
    print("  " + url + "  profile=" + str(state["profile"]) + " region=" + str(state["region"]))

    failures: list[str] = []
    seen: list[str] = []
    while True:
        key = str(state["step"])
        if key not in CHECKS:
            failures.append("step '" + key + "' has no expectation in walkthrough.CHECKS")
            break
        problems = CHECKS[key](state)
        _print_step(state)
        print("")
        print("  " + _c("0;37", demo.STEPS[int(state["step_index"])].narration))
        if problems:
            for problem in problems:
                print("  " + _c("1;31", "FAIL: " + problem))
            failures.extend(key + ": " + problem for problem in problems)
        else:
            print("  " + _c("1;32", "checks passed"))
        seen.append(key)

        if state["done"]:
            break
        instruction = _prompt(state, auto)
        if instruction == "quit":
            print("  quit before the end; nothing was asserted about the remaining steps")
            return 1 if failures else 0
        if instruction == "restart":
            _post(url, "/restart")
            state = _get(url, "/state")
            seen = []
            continue
        if instruction.isdigit():
            target = max(1, min(int(instruction), int(state["step_count"])))
            while int(state["step_index"]) + 1 < target and not state["done"]:
                _post(url, "/next")
                state = _get(url, "/state")
            continue
        _post(url, "/next")
        state = _get(url, "/state")

    missing = [key for key in demo.STEP_KEYS if key not in seen]
    if missing:
        failures.append("steps never reached: " + ", ".join(missing))

    print("")
    if failures:
        print(_c("1;31", "DEMO WALKTHROUGH: FAILED"))
        for failure in failures:
            print("  - " + failure)
        return 1
    print(_c("1;32", "DEMO WALKTHROUGH: PASS (" + str(len(seen)) + " steps asserted)"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Presenter-paced walkthrough of the live demo.")
    parser.add_argument("--url", default=os.environ.get("DEMO_URL", ""))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DEMO_PORT", "0")))
    parser.add_argument(
        "--auto",
        action="store_true",
        default=os.environ.get("DEMO_AUTO") == "1",
        help="advance without waiting for the presenter (the self-test)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=os.environ.get("HEADLESS") == "1",
        help="never open a browser window",
    )
    args = parser.parse_args(argv)

    if args.url:
        return run(args.url.rstrip("/"), auto=args.auto, headless=args.headless, process=None)

    port = args.port or _free_port()
    command = [sys.executable, str(HERE / "demo_server.py"), "--port", str(port)]
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        return run(
            "http://127.0.0.1:" + str(port),
            auto=args.auto,
            headless=args.headless,
            process=process,
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - a wedged child
            process.kill()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
