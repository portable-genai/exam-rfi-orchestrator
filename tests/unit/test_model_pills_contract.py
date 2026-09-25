"""The half of the model-pills contract that lives in the BROWSER.

Every served console names, at the top right of every page, the model that ANSWERED and whether
it searched (owner decision, 2026-09-23; the pills replaced the full-width provenance banner of
2026-08-30). The SERVICE half -- ``/healthz`` carries ``runtime`` and ``generator_model``, and a
model-backed response carries ``X-Answered-By`` / ``X-Search-Used`` -- is pinned in
``tests/unit/test_api.py`` and ``tests/unit/test_answer_provenance.py`` and is not restated here.

This file pins the other half, and the other half is the one that broke before. On 2026-09-04
eight consoles were found to have been rendering NOTHING on every page load since the banner
landed: the component named ``/api/agent`` in trees that ship no such handler, the health call
reached nothing, and the failure branch renders nothing by design. In the same eight trees a
negative margin hoisted the strip above the viewport. Every service-side assertion was green
throughout, which is why these live in their own file.
"""

from __future__ import annotations

import re
from pathlib import Path

UI = Path("ui")
PILLS = UI / "app" / "ModelPills.tsx"


def test_the_pills_are_mounted_in_the_layout_rather_than_in_a_page() -> None:
    """Being at the top of EVERY page is a property of the console, not of any page."""
    layout = UI / "app" / "layout.tsx"
    assert layout.is_file(), "this console has no root layout, so nothing can be mounted for it"
    assert "<ModelPills />" in layout.read_text(encoding="utf-8"), (
        "the root layout does not mount the pills, so they reach only the pages that remember to"
    )
    for source in sorted(UI.glob("app/**/*.tsx")) + sorted(UI.glob("components/**/*.tsx")):
        text = source.read_text(encoding="utf-8")
        assert "ProvenanceBanner" not in text, f"{source} still references the banner"
        assert "running on GCP · model" not in text, f"{source} still renders the banner sentence"


def test_the_pills_call_a_base_this_console_actually_serves() -> None:
    """The defect that shipped, stated as an assertion: naming a proxy the tree does not have.

    Both architectures are legitimate, so this pins AGREEMENT rather than a literal. A tree with
    ``ui/app/api/agent`` proxies through its own origin, the pills name that path, and the route
    must forward both answer headers or the pills stay "configured" forever.
    """
    pills = PILLS.read_text(encoding="utf-8")
    proxies_through_own_origin = Path("ui/app/api/agent").is_dir()
    assert ('"/api/agent"' in pills) == proxies_through_own_origin, (
        f"{PILLS} names /api/agent but this console has no route handler at ui/app/api/agent"
        if not proxies_through_own_origin
        else f"this console ships a /api/agent route handler but {PILLS} does not use it"
    )
    if proxies_through_own_origin:
        route = (UI / "app" / "api" / "agent" / "[...path]" / "route.ts").read_text(
            encoding="utf-8"
        )
        for header in ('"x-answered-by"', '"x-search-used"'):
            assert header in route, "the proxy drops " + header + " from the service's response"


def _rule(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    return css[start : css.index("}", start)]


def test_the_pills_sit_fixed_at_the_top_right() -> None:
    """Fixed, so no page content can push them off screen; never hoisted above the viewport.

    The banner these replace once rendered 32px ABOVE the viewport: a negative margin written
    for a ``body`` with padding, carried into one without. So the geometry is asserted, not the
    presence: fixed, anchored at a non-negative top and right, and no margin to hoist it.
    """
    css = (UI / "app" / "globals.css").read_text(encoding="utf-8")
    assert ".provenance-banner" not in css, "the banner's rule survived its component"
    block = _rule(css, ".model-pills")
    assert "position: fixed;" in block
    for edge in ("top", "right"):
        match = re.search(rf"^\s*{edge}:\s*(\d+)px;", block, re.MULTILINE)
        assert match, f".model-pills is not anchored at a non-negative {edge} in px"
    assert "margin" not in block, "a margin on a fixed strip is how it left the viewport before"
