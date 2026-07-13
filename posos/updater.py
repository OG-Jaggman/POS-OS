from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
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


# Add the Internet manager page without tying the networking code to the main
# register screen. The POS app creates its manager tabs dynamically, so this
# hook inserts the Internet tab when the System tab is added.
_original_notebook_add = ttk.Notebook.add


def _posos_notebook_add(self, child, **kwargs):
    result = _original_notebook_add(self, child, **kwargs)
    if kwargs.get("text") == "System" and not getattr(self, "_posos_internet_added", False):
        self._posos_internet_added = True
        internet_tab = ttk.Frame(self, padding=8)
        _original_notebook_add(self, internet_tab, text="Internet")
        try:
            from .internet import build_internet_tab

            build_internet_tab(self.winfo_toplevel(), internet_tab)
        except Exception as exc:
            ttk.Label(
                internet_tab,
                text=f"Internet settings could not start:\n{exc}",
                wraplength=800,
                justify="center",
            ).pack(fill="both", expand=True, padx=20, pady=20)
    return result


if not getattr(ttk.Notebook, "_posos_internet_hook", False):
    ttk.Notebook.add = _posos_notebook_add
    ttk.Notebook._posos_internet_hook = True


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
    """Convert versions such as v2.6.1 into comparable integer tuples."""
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


def _restart_into_current_version() -> None:
    current = Path("/opt/posos/current").resolve()
    python = current / "venv/bin/python"
    if not python.exists():
        raise UpdateError("The new POS OS Python environment was not found")

    # The launcher starts POS OS with its working directory inside the old
    # version folder. Without changing directories, Python can import the old
    # package again even after /opt/posos/current points to the new version.
    os.chdir(current)
    os.environ["PYTHONPATH"] = str(current)
    os.execve(
        str(python),
        [str(python), "-m", "posos"],
        os.environ.copy(),
    )


def install_main_update(repo: str, branch: str, expected_version: str) -> None:
    """Install the current GitHub branch through the restricted root helper."""
    helper = Path("/usr/local/sbin/posos-install-update")
    if not helper.exists():
        raise UpdateError(
            "This POS OS installation does not contain the in-place update helper. "
            "Install the v2.5.0 ISO once; later POS updates will not need new ISOs."
        )

    try:
        completed = subprocess.run(
            ["sudo", "-n", str(helper), repo, branch, expected_version],
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError(f"Could not start the update installer: {exc}") from exc

    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "Unknown updater error").strip()
        raise UpdateError(f"Update installation failed: {details}")

    _restart_into_current_version()


def check_latest(repo: str, current: str, branch: str = "main") -> dict:
    """
    Check GitHub main. When a newer version exists on an installed POS kiosk,
    install it, preserve /var/lib/posos, and immediately restart into it.
    """
    latest = github_main_version(repo, branch)
    available = _version_tuple(latest) > _version_tuple(current)

    if available and Path("/opt/posos/current").exists():
        install_main_update(repo, branch, latest)

    return {
        "available": available,
        "version": latest,
        "current": current,
        "source": f"{branch} branch",
        "notes": (
            "A newer POS OS version is available. On an installed kiosk, pressing "
            "Check for updates installs it automatically and restarts POS OS."
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
