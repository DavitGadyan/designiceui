#!/usr/bin/env python3
"""Record the README walkthrough GIFs from the showcase builds.

Needs the builds running first (any ports; pass the URLs):
  cd output/buyme  && npm run build && npx next start -p 3127          # production, no dev overlay
  cd output/justdo && npx expo export --platform web && \
      python3 -c "import http.server,functools;h=http.server.SimpleHTTPRequestHandler;http.server.ThreadingHTTPServer(('',3126),functools.partial(h,directory='dist')).serve_forever()"
  python3.12 scripts/record-showcase.py docs/showcase http://localhost:3127 http://localhost:3126

Playwright (python) and ffmpeg must be installed. ONLY=buyme|justdo records one app.
JustDo's static export lacks clean-URL routing; serve it with a handler that maps
/week -> week.html (see the critic's notes) or record against `npx expo start --web`.
"""
import subprocess, sys, pathlib, shutil, time
READY = {"t": 0.6}
T0 = time.time()
def log(msg): print(f"[{time.time()-T0:6.2f}s] {msg}", flush=True)
def tap(loc, wait=800, what=""):
    try:
        loc.click(timeout=6000); log(f"tap {what or loc}")
    except Exception as e:
        log(f"SKIP {what or loc}: {str(e).splitlines()[0][:90]}")
from playwright.sync_api import sync_playwright

OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BUYME = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:3127"
JUSTDO = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:3126"
HIDE = "nextjs-portal,#__next-build-watcher,[data-nextjs-toast],[data-next-badge-root]{display:none!important}"

def scroll_to(page, y, ms):
    """Animate window scroll to y over ms with ease-in-out - smooth on video, no per-event overhead."""
    page.evaluate("""([y, ms]) => new Promise(res => {
      const y0 = scrollY, d = y - y0, t0 = performance.now();
      const step = t => { const k = Math.min(1, (t - t0) / ms); const e = k < .5 ? 2*k*k : -1 + (4 - 2*k)*k;
        scrollTo(0, y0 + d*e); if (k < 1) requestAnimationFrame(step); else res(); };
      requestAnimationFrame(step); })""", [y, ms])

def smooth_scroll(page, total, step=90, pause=45):
    done = 0
    while done < total:
        page.mouse.wheel(0, step); done += step; page.wait_for_timeout(pause)

def to_gif(webm, gif, width, fps=10, colors=128, trim=0.6):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(trim), "-i", str(webm),
        "-vf", f"fps={fps},scale={width}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors={colors}:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
        "-loop", "0", str(gif)], check=True)
    print(gif.name, round(gif.stat().st_size / 1024), "KB")

def record(p, name, w, h, mobile, run):
    tmp = OUT / f"_{name}"; shutil.rmtree(tmp, ignore_errors=True)
    browser = p.chromium.launch()
    READY["t0"] = time.time()
    ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1,
        is_mobile=mobile, has_touch=mobile, record_video_dir=str(tmp), record_video_size={"width": w, "height": h})
    page = ctx.new_page()
    run(page)
    log("run done"); video = page.video.path(); ctx.close(); log("closed")
    dst = OUT / f"{name}.webm"; shutil.move(video, dst); shutil.rmtree(tmp, ignore_errors=True)
    return dst

def ready(page):
    """Call once the first screen is on; the GIF is trimmed to start here."""
    READY["t"] = max(0.0, time.time() - READY["t0"] - 0.25)

def buyme(page):
    log("goto"); page.goto(BUYME, wait_until="load"); page.add_style_tag(content=HIDE); page.wait_for_timeout(600); ready(page); log("ready")
    page.get_by_role("link", name="Install on Shopify").first.hover(); page.wait_for_timeout(450)
    page.get_by_role("link", name="Try it for free").first.hover(); page.wait_for_timeout(450)
    page.mouse.move(640, 500)
    top = lambda sel: page.locator(sel).evaluate("el => el.getBoundingClientRect().top + scrollY")
    log("hero done"); scroll_to(page, top("#agent-features") - 60, 1100); page.wait_for_timeout(500); log("features")
    scroll_to(page, top("#shopify") - 60, 1100); page.wait_for_timeout(500)
    scroll_to(page, top("#install") - 60, 1000); page.wait_for_timeout(450)
    scroll_to(page, top("#faq") - 40, 1300); page.wait_for_timeout(350); log("faq")
    summaries = page.locator("#faq summary")
    summaries.nth(1).click(); page.wait_for_timeout(700)
    summaries.nth(3).click(); page.wait_for_timeout(700)
    page.mouse.move(640, 400)
    scroll_to(page, page.evaluate("document.documentElement.scrollHeight"), 1200)
    page.get_by_role("link", name="Install on Shopify").last.hover(); page.wait_for_timeout(900); log("end")

def tap_text(page, text, wait=900):
    tap(page.get_by_text(text, exact=True).locator("visible=true").last, what=text); page.wait_for_timeout(wait); return True

def justdo(page):
    page.goto(JUSTDO + "/onboarding/event", wait_until="load"); page.wait_for_timeout(900); ready(page)
    tap_text(page, "Yes", 500); tap_text(page, "Cycling", 500); tap_text(page, "Next", 1000)
    tap_text(page, "Reach peak performance", 500); tap_text(page, "Next", 1000)
    # drag the first rating slider
    box = None
    try:
        box = page.get_by_role("slider").locator("visible=true").first.bounding_box(timeout=4000)
    except Exception as e:
        log(f"SKIP slider: {str(e).splitlines()[0][:80]}")
    if box:
        y = box["y"] + box["height"] / 2
        page.mouse.move(box["x"] + box["width"] * 0.3, y); page.mouse.down()
        for i in range(12): page.mouse.move(box["x"] + box["width"] * (0.3 + 0.5 * i / 11), y); page.wait_for_timeout(40)
        page.mouse.up(); page.wait_for_timeout(500)
    tap_text(page, "Build my plan", 1100)
    page.mouse.move(195, 400)
    tap(page.get_by_label("Open training calendar").locator("visible=true").last, what="calendar"); page.wait_for_timeout(1300)
    page.mouse.click(195, 120); page.wait_for_timeout(600)
    tap_text(page, "Week 1", 1000)
    tap_text(page, "Types of Goals", 1100)
    page.go_back(); page.wait_for_timeout(600); page.go_back(); page.wait_for_timeout(700)
    tab = page.locator('a[href="/progress"]').locator("visible=true").first
    tap(tab, what="progress tab"); page.wait_for_timeout(900)
    tap(page.get_by_label("Focus session stats").locator("visible=true").last, what="stats"); page.wait_for_timeout(1200)
    tap(page.get_by_label("Next skill").locator("visible=true").last, what="next skill"); page.wait_for_timeout(900)
    page.mouse.click(195, 120); page.wait_for_timeout(500)
    page.mouse.move(195, 500); smooth_scroll(page, 700, step=50, pause=40); page.wait_for_timeout(1000)

import os
ONLY = os.environ.get("ONLY")
with sync_playwright() as p:
    if ONLY in (None, "buyme"):
        v = record(p, "buyme-walkthrough", 1280, 800, False, buyme); to_gif(v, OUT / "buyme-walkthrough.gif", 640, fps=10, colors=96, trim=READY["t"])
    if ONLY in (None, "justdo"):
        v = record(p, "justdo-walkthrough", 390, 844, True, justdo); to_gif(v, OUT / "justdo-walkthrough.gif", 300, fps=10, colors=96, trim=READY["t"])
