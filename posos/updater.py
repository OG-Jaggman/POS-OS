from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path
from tkinter import ttk


# Tk's themed buttons have a fairly large default requested width. A row of
# ten single-character touchscreen keys can therefore overflow a 1024px kiosk
# display even when pack(expand=True) is used. Keep one-character keys compact
# while leaving normal application buttons unchanged.
_original_button_init = ttk.Button.__init__


def _compact_touch_button_init(self, master=None, **kwargs):
    text = str(kwargs.get("text", ""))
    if len(text) == 1 or text in {"⌫", "←", "→"}:
        kwargs.setdefault("width", 2)
        kwargs.setdefault("padding", (1, 6))
    _original_button_init(self, master, **kwargs)


if not getattr(ttk.Button, "_posos_compact_keys", False):
    ttk.Button.__init__ = _compact_touch_button_init
    ttk.Button._posos_compact_keys = True


class UpdateError(RuntimeError):
    pass


def _request_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "POSOS-Updater",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode("utf-8").strip()


def _version_tuple(version: str) -> tuple[int, ...]:
    """Convert versions such as v2.4.0 into comparable integer tuples."""
    cleaned = version.strip().lower().lstrip("v")
    numbers = re.findall(r"\d+", cleaned)
    if not numbers:
        return (0,)
    values = tuple(int(number) for number in numbers[:4])
    return values + (0,) * (4 - len(values))


def github_main_version(repo: str, branch: str = "main") -> str:
    url = f"https://raw.githubusercontent.com/{repo}/{branch}/VERSION"
    version = _request_text(url).lstrip("v")
    if not version:
        raise UpdateError("The GitHub VERSION file was empty")
    return version


def github_latest_release(repo: str) -> dict:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "POSOS-Updater",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def check_latest(repo: str, current: str, branch: str = "main") -> dict:
    """Check the current POS-OS main branch instead of stale GitHub Releases."""
    latest = github_main_version(repo, branch)
    available = _version_tuple(latest) > _version_tuple(current)
    return {
        "available": available,
        "version": latest,
        "current": current,
        "source": f"{branch} branch",
        "notes": (
            "This version is available from the current POS-OS GitHub main branch. "
            "The installed updater currently reports availability; automatic installation is handled separately."
            if available
            else ""
        ),
        "assets": {},
    }


def download_and_verify(url: str, sha_url: str, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, destination)
    expected = _request_text(sha_url).split()[0]
    actual = hashlib.sha256(destination.read_bytes()).hexdigest()
    if actual.lower() != expected.lower():
        destination.unlink(missing_ok=True)
        raise UpdateError("Update checksum did not match")
    return actual
