"""Tests for `designice snapshot`, the capture step behind the design-critic agent.
The browser is faked: what matters is the file naming, the manifest shape, and
that a missing Playwright is a one-line hint rather than a traceback."""

import json

import pytest

from designice import snapshot
from designice.cli import build_parser, main

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class FakeLocator:
    def __init__(self, page):
        self.page = page
        self.first = self

    def scroll_into_view_if_needed(self):
        pass

    def screenshot(self, path):
        self.page.shots.append(path)
        open(path, "wb").write(PNG)


class FakePage:
    inventory = [
        {"id": "hero", "tag": "section", "selector": '[data-snap-index="0"]', "top": 0, "height": 820,
         "width": 1440, "background": "rgb(255,255,255)", "padding": ["80px", "96px"], "columns": 2,
         "headings": ["h1 56px: Tired of shoppers leaving"], "buttons": 2, "links": 3, "images": 1,
         "icons": 4, "inputs": 0, "words": 60},
        {"id": "", "tag": "footer", "selector": '[data-snap-index="1"]', "top": 820, "height": 240,
         "width": 1440, "background": "rgb(17,17,17)", "padding": ["48px", "48px"], "columns": 4,
         "headings": [], "buttons": 0, "links": 12, "images": 0, "icons": 3, "inputs": 1, "words": 80},
        {"id": "hero", "tag": "section", "selector": '[data-snap-index="2"]', "top": 1060, "height": 0,
         "width": 1440, "background": "rgb(255,255,255)", "padding": ["0px", "0px"], "columns": 1,
         "headings": [], "buttons": 0, "links": 0, "images": 0, "icons": 0, "inputs": 0, "words": 0},
    ]

    def __init__(self, ctx):
        self.ctx = ctx
        self.shots = []
        self.handlers = {}

    def on(self, event, handler):
        self.handlers[event] = handler

    def goto(self, url, **kw):
        self.ctx.browser.visited.append((url, self.ctx.kw["viewport"]))

    def add_style_tag(self, content):
        assert "nextjs-portal" in content

    def evaluate(self, script):
        if "data-snap-index" in script:
            return [dict(s) for s in self.inventory]
        if "scrollHeight" in script:
            return 1060
        if "scrollWidth" in script:
            return self.ctx.kw["viewport"]["width"] < 400  # the fake mobile page overflows
        return True

    def wait_for_timeout(self, ms):
        pass

    def wait_for_function(self, script, timeout=None):
        assert "data-reveal" in script

    def screenshot(self, path, full_page=False):
        self.shots.append(path)
        open(path, "wb").write(PNG)

    def locator(self, selector):
        return FakeLocator(self)


class FakeContext:
    def __init__(self, browser, **kw):
        self.browser = browser
        self.kw = kw

    def new_page(self):
        return FakePage(self)

    def close(self):
        pass


class FakeBrowser:
    def __init__(self):
        self.visited = []
        self.contexts = []
        self.closed = False

    def new_context(self, **kw):
        ctx = FakeContext(self, **kw)
        self.contexts.append(ctx)
        return ctx

    def close(self):
        self.closed = True


class FakePlaywright:
    browser = FakeBrowser()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    class chromium:
        @staticmethod
        def launch():
            return FakePlaywright.browser


@pytest.fixture
def fake_pw():
    FakePlaywright.browser = FakeBrowser()
    return FakePlaywright


def test_parse_size_accepts_wxh_and_rejects_noise():
    assert snapshot.parse_size("1440x900") == (1440, 900)
    assert snapshot.parse_size(" 390 X 844 ") == (390, 844)
    with pytest.raises(ValueError):
        snapshot.parse_size("wide")
    with pytest.raises(ValueError):
        snapshot.parse_size("")


def test_capture_writes_named_images_and_a_manifest(tmp_path, fake_pw):
    manifest = snapshot.capture("http://localhost:3000", tmp_path, _playwright=fake_pw)

    names = sorted(p.name for p in tmp_path.iterdir())
    assert "desktop-viewport.png" in names and "desktop-full.png" in names
    assert "mobile-viewport.png" in names and "mobile-full.png" in names
    assert "desktop-hero.png" in names and "desktop-footer.png" in names
    assert "desktop-hero-2.png" not in names, "a zero-height region is listed but not captured"
    assert json.loads((tmp_path / "manifest.json").read_text()) == manifest

    desktop, mobile = manifest["screens"]
    assert (desktop["width"], desktop["height"]) == (1440, 900)
    assert (mobile["width"], mobile["height"]) == (390, 844)
    assert desktop["overflow_x"] is False and mobile["overflow_x"] is True
    slugs = [s["slug"] for s in desktop["sections"]]
    assert slugs == ["hero", "footer", "hero-2"], "id-less regions use their tag; duplicates get a suffix"
    assert desktop["sections"][0]["file"] == "desktop-hero.png"
    assert desktop["sections"][2]["file"] is None
    assert desktop["sections"][0]["columns"] == 2 and desktop["sections"][0]["headings"]
    assert fake_pw.browser.closed


def test_capture_can_limit_to_one_viewport(tmp_path, fake_pw):
    manifest = snapshot.capture("http://x", tmp_path, only="mobile", sections=False, _playwright=fake_pw)
    assert [s["viewport"] for s in manifest["screens"]] == ["mobile"]
    assert fake_pw.browser.contexts[0].kw["is_mobile"] is True
    assert not any(s["file"] for s in manifest["screens"][0]["sections"])
    with pytest.raises(ValueError):
        snapshot.capture("http://x", tmp_path, desktop=None, mobile=None, _playwright=fake_pw)


def test_cli_parser_has_sensible_defaults():
    args = build_parser().parse_args(["snapshot", "http://localhost:3000"])
    assert args.out == "verify/critique"
    assert (args.desktop, args.mobile) == ("1440x900", "390x844")
    assert args.only is None and args.no_sections is False


def test_cli_explains_how_to_install_playwright(tmp_path, monkeypatch, capsys):
    def missing():
        raise snapshot.SnapshotUnavailable(snapshot.INSTALL_HINT)

    monkeypatch.setattr(snapshot, "_load_playwright", missing)
    code = main(["snapshot", "http://localhost:3000", "--out", str(tmp_path)])
    assert code == 2
    err = capsys.readouterr().err
    assert "playwright install chromium" in err and "Traceback" not in err


def test_cli_prints_a_region_table(tmp_path, monkeypatch, capsys, fake_pw):
    monkeypatch.setattr(snapshot, "_load_playwright", lambda: fake_pw)
    assert main(["snapshot", "http://localhost:3000", "--out", str(tmp_path), "--only", "desktop"]) == 0
    out = capsys.readouterr().out
    assert "desktop  1440x900" in out and "hero" in out and "cols 2" in out
    assert "manifest.json" in out
