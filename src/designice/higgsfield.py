"""Higgsfield image generation.

Deliberately key-optional. Without credentials this module still does the
useful half of the job - it hands back the art-directed prompts so they can be
pasted into any image tool - and only the network call is skipped. A design
pipeline that refuses to produce anything because a key is missing is worse
than one that degrades.

API shape (docs.higgsfield.ai):
    POST https://api.higgsfield.ai/<model-path>   -> {status, request_id, status_url}
    GET  https://api.higgsfield.ai/requests/<id>/status
    terminal statuses: completed | failed | nsfw | canceled
    a completed image request carries {"images": [{"url": ...}]}
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from .config import higgsfield_credentials

API_BASE = "https://api.higgsfield.ai"
TERMINAL = {"completed", "failed", "nsfw", "canceled"}

# Model paths that suit website imagery. `soul` is Higgsfield's photographic
# model and is the right default for hero and editorial shots.
MODELS = {
    "soul": "higgsfield-ai/soul/v2/standard",
    "soul-hd": "higgsfield-ai/soul/v2/hd",
    "flux-kontext": "flux-pro/kontext/max/text-to-image",
}
DEFAULT_MODEL = "soul"


class HiggsfieldError(RuntimeError):
    pass


class NoCredentials(HiggsfieldError):
    pass


def available() -> bool:
    return higgsfield_credentials() is not None


def _auth_header() -> str:
    creds = higgsfield_credentials()
    if not creds:
        raise NoCredentials(
            "Higgsfield credentials are not set. Export HF_API_KEY_ID and HF_API_KEY_SECRET "
            "(create them at https://cloud.higgsfield.ai/), or use the prompts as-is in any image tool."
        )
    return "Key {}:{}".format(*creds)


def _request(url: str, payload: dict | None = None, timeout: int = 60) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Authorization", _auth_header())
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:600]
        if exc.code == 401:
            raise HiggsfieldError(f"Higgsfield rejected the credentials (401): {body}") from exc
        raise HiggsfieldError(f"Higgsfield {exc.code} on {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise HiggsfieldError(f"could not reach Higgsfield: {exc.reason}") from exc


def submit(prompt: str, *, model: str = DEFAULT_MODEL, **params: Any) -> dict:
    path = MODELS.get(model, model)
    payload: dict[str, Any] = {"prompt": prompt}
    payload.update({k: v for k, v in params.items() if v is not None})
    return _request(f"{API_BASE}/{path.lstrip('/')}", payload)


def poll(request_id: str, *, timeout: float = 300.0) -> dict:
    """Poll to a terminal state with the backoff Higgsfield's docs recommend."""
    url = f"{API_BASE}/requests/{request_id}/status"
    deadline = time.monotonic() + timeout
    delay = 2.0
    while True:
        result = _request(url)
        if result.get("status") in TERMINAL:
            return result
        if time.monotonic() > deadline:
            raise HiggsfieldError(f"request {request_id} did not finish within {timeout:.0f}s")
        time.sleep(delay + random.uniform(0, 0.5))
        delay = min(delay * 1.5, 10.0)


def generate(prompt: str, *, model: str = DEFAULT_MODEL, timeout: float = 300.0, **params: Any) -> dict:
    submitted = submit(prompt, model=model, **params)
    request_id = submitted.get("request_id")
    if not request_id:
        raise HiggsfieldError(f"unexpected submit response: {submitted}")
    result = poll(request_id, timeout=timeout)
    if result.get("status") != "completed":
        raise HiggsfieldError(f"generation ended as {result.get('status')}: {result}")
    return result


def download(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        destination.write_bytes(resp.read())
    return destination


def generate_set(
    prompts: Iterable[dict[str, str]],
    out_dir: Path,
    *,
    model: str = DEFAULT_MODEL,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Run a brief's image_prompts and save the results next to the project.

    Outputs are kept for at least seven days on Higgsfield's side, so anything
    worth keeping gets downloaded here immediately rather than referenced by URL.
    """
    results: list[dict[str, Any]] = []
    have_keys = available()
    for spec in prompts:
        slot = spec.get("slot", "image")
        record: dict[str, Any] = {"slot": slot, "prompt": spec["prompt"],
                                  "aspect_ratio": spec.get("aspect_ratio", "16:9")}
        if dry_run or not have_keys:
            record["status"] = "prompt-only"
            record["reason"] = "dry run" if dry_run else "no Higgsfield credentials set"
            results.append(record)
            continue
        try:
            result = generate(spec["prompt"], model=model,
                              aspect_ratio=spec.get("aspect_ratio"))
            urls = [img["url"] for img in result.get("images", []) if img.get("url")]
            saved = []
            for i, url in enumerate(urls):
                name = f"{slot}.png" if i == 0 else f"{slot}-{i + 1}.png"
                saved.append(str(download(url, out_dir / name)))
            record.update(status="completed", urls=urls, files=saved)
        except HiggsfieldError as exc:
            record.update(status="failed", error=str(exc))
        results.append(record)
    return results
