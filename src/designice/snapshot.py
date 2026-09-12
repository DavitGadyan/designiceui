"""Screenshot a running build so the critique stage can compare it with the
template it was reproduced from.

Zero required dependencies, like the rest of the package: Playwright is imported
lazily and its absence is reported as a one-line install hint rather than a
traceback. Everything the critic needs to reason with numbers - section order,
heights, padding, grid column counts, headings with their sizes, button / link /
image counts, console errors, horizontal overflow - lands in ``manifest.json``
next to the images, so a critique can say "the hero is 62% of the viewport"
instead of "the hero feels short".
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

DEFAULT_DESKTOP = "1440x900"
DEFAULT_MOBILE = "390x844"

INSTALL_HINT = (
    "playwright is not installed. It is only needed for `designice snapshot`:\n"
    "  python3 -m pip install playwright && python3 -m playwright install chromium"
)

# Next.js dev-mode chrome that must never appear in a capture.
HIDE_DEV_CSS = (
    "nextjs-portal, #__next-build-watcher, [data-nextjs-toast], [data-next-badge-root]"
    " { display: none !important; }"
)
# Reveal-on-scroll elements that never entered the viewport would otherwise be
# captured invisible and read as "missing content".
REVEAL_JS = (
    "document.querySelectorAll('[data-reveal]')"
    ".forEach(n => n.setAttribute('data-reveal', 'shown'))"
)
# Sticky navs overlap element screenshots taken further down the page.
UNSTICK_JS = """() => {
  for (const el of document.querySelectorAll('body *')) {
    const p = getComputedStyle(el).position;
    if (p === 'sticky' || p === 'fixed') el.style.position = 'static';
  }
}"""
# One record per top-level region, in document order, with the numbers a critic
# needs. Tags each region with data-snap-index so it can be screenshotted alone.
INVENTORY_JS = """() => {
  const picked = [...document.querySelectorAll('header, nav, main > section, section[id], [data-section], footer')];
  const outer = picked.filter(el => !picked.some(o => o !== el && o.contains(el)));
  outer.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
  return outer.map((el, i) => {
    el.setAttribute('data-snap-index', String(i));
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    let columns = 1;
    for (const d of [el, ...el.querySelectorAll('*')]) {
      const s = getComputedStyle(d);
      if (s.display === 'grid') {
        const n = s.gridTemplateColumns.split(' ').filter(Boolean).length;
        if (n > columns) columns = n;
      } else if (s.display === 'flex' && s.flexDirection.startsWith('row') && d.children.length > 1 && d.children.length <= 8) {
        const kids = [...d.children];
        if (kids.every(k => k.getBoundingClientRect().width >= 120) && kids.length > columns) columns = kids.length;
      }
    }
    const text = (el.innerText || '').trim();
    return {
      id: el.id || el.dataset.section || '',
      tag: el.tagName.toLowerCase(),
      selector: `[data-snap-index="${i}"]`,
      top: Math.round(r.top + scrollY),
      height: Math.round(r.height),
      width: Math.round(r.width),
      background: cs.backgroundColor,
      padding: [cs.paddingTop, cs.paddingBottom],
      columns,
      headings: [...el.querySelectorAll('h1, h2, h3')].slice(0, 8).map(h =>
        `${h.tagName.toLowerCase()} ${Math.round(parseFloat(getComputedStyle(h).fontSize))}px: ${h.textContent.trim().replace(/\\s+/g, ' ').slice(0, 90)}`),
      buttons: el.querySelectorAll('button, a[class*="btn"], [role="button"]').length,
      links: el.querySelectorAll('a[href]').length,
      images: el.querySelectorAll('img, picture, video, canvas').length,
      icons: el.querySelectorAll('svg').length,
      inputs: el.querySelectorAll('input, textarea, select').length,
      words: text ? text.split(/\\s+/).length : 0,
    };
  });
}"""


class SnapshotUnavailable(RuntimeError):
    """The browser automation layer is missing; the message says how to get it."""


def parse_size(text: str) -> tuple[int, int]:
    m = re.fullmatch(r"\s*(\d{3,5})\s*[xX×]\s*(\d{3,5})\s*", text or "")
    if not m:
        raise ValueError(f"size must look like 1440x900, got {text!r}")
    return int(m.group(1)), int(m.group(2))


def _load_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - exercised through the CLI test
        raise SnapshotUnavailable(INSTALL_HINT) from exc
    return sync_playwright


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "section"


def capture(
    url: str,
    out: str | pathlib.Path,
    *,
    desktop: str | None = DEFAULT_DESKTOP,
    mobile: str | None = DEFAULT_MOBILE,
    only: str | None = None,
    sections: bool = True,
    settle_ms: int = 600,
    timeout_ms: int = 30000,
    _playwright=None,
) -> dict[str, Any]:
    """Capture ``url`` at the desktop and/or mobile viewport into ``out``.

    Returns the manifest that was also written to ``out/manifest.json``.
    """
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    viewports: list[tuple[str, tuple[int, int], bool]] = []
    if only in (None, "desktop") and desktop:
        viewports.append(("desktop", parse_size(desktop), False))
    if only in (None, "mobile") and mobile:
        viewports.append(("mobile", parse_size(mobile), True))
    if not viewports:
        raise ValueError("nothing to capture: both viewports are disabled")

    sync_playwright = _playwright or _load_playwright()
    manifest: dict[str, Any] = {"url": url, "screens": [], "errors": []}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for name, (w, h), is_mobile in viewports:
                manifest["screens"].append(
                    _capture_viewport(browser, url, out, name, w, h, is_mobile,
                                      sections, settle_ms, timeout_ms, manifest["errors"])
                )
        finally:
            browser.close()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def _capture_viewport(browser, url, out, name, w, h, is_mobile, sections, settle_ms, timeout_ms, errors):
    ctx = browser.new_context(
        viewport={"width": w, "height": h}, device_scale_factor=2,
        is_mobile=is_mobile, has_touch=is_mobile, reduced_motion="reduce",
    )
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(f"{name} console.{m.type}: {m.text}")
            if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: errors.append(f"{name} pageerror: {e}"))
    page.goto(url, wait_until="networkidle", timeout=timeout_ms)
    page.add_style_tag(content=HIDE_DEV_CSS)
    page.evaluate("document.fonts ? document.fonts.ready : true")
    page.evaluate(REVEAL_JS)
    page.wait_for_timeout(settle_ms)

    screen: dict[str, Any] = {"viewport": name, "width": w, "height": h, "files": {}, "sections": []}
    path = out / f"{name}-viewport.png"
    page.screenshot(path=str(path))
    screen["files"]["viewport"] = path.name

    page.evaluate(UNSTICK_JS)
    page.wait_for_timeout(150)
    path = out / f"{name}-full.png"
    page.screenshot(path=str(path), full_page=True)
    screen["files"]["full"] = path.name
    screen["page_height"] = page.evaluate("document.documentElement.scrollHeight")
    screen["overflow_x"] = bool(page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth"))

    seen: set[str] = set()
    for i, sec in enumerate(page.evaluate(INVENTORY_JS) or []):
        base = _slug(sec.get("id") or sec.get("tag") or f"section-{i}")
        slug, n = base, 2
        while slug in seen:
            slug, n = f"{base}-{n}", n + 1
        seen.add(slug)
        sec["slug"] = slug
        sec["file"] = None
        if sections and 0 < sec.get("height", 0) <= 6000:
            try:
                loc = page.locator(sec["selector"]).first
                loc.scroll_into_view_if_needed()
                page.wait_for_timeout(120)
                path = out / f"{name}-{slug}.png"
                loc.screenshot(path=str(path))
                sec["file"] = path.name
            except Exception as exc:  # a region that cannot be captured is a note, not a crash
                errors.append(f"{name} section {slug}: {exc}")
        screen["sections"].append(sec)
    ctx.close()
    return screen
