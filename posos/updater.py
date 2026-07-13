from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path
from tkinter import messagebox, ttk


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


def _repair_bookworm_apt_sources_when_root() -> None:
    if os.geteuid() != 0:
        return

    marker = Path("/var/lib/posos/.apt-sources-repaired-v271")
    if marker.exists():
        return

    os_release = Path("/etc/os-release")
    try:
        release_text = os_release.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    if "VERSION_CODENAME=bookworm" not in release_text and 'VERSION_CODENAME="bookworm"' not in release_text:
        return

    sources = Path("/etc/apt/sources.list")
    backup = Path("/etc/apt/sources.list.posos-backup")
    try:
        if sources.exists() and not backup.exists():
            backup.write_bytes(sources.read_bytes())
        sources.write_text(
            "deb http://deb.debian.org/debian bookworm main contrib non-free-firmware\n"
            "deb http://deb.debian.org/debian bookworm-updates main contrib non-free-firmware\n"
            "deb http://security.debian.org/debian-security bookworm-security main contrib non-free-firmware\n",
            encoding="utf-8",
        )
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("2.7.1\n", encoding="utf-8")
    except OSError:
        return


def _install_repair_sudoers_when_root() -> None:
    if os.geteuid() != 0:
        return
    sudoers = Path("/etc/sudoers.d/posos-network-repair")
    try:
        sudoers.write_text(
            "register ALL=(root) NOPASSWD: /opt/posos/current/venv/bin/python -m posos.repair\n",
            encoding="utf-8",
        )
        sudoers.chmod(0o440)
    except OSError:
        return


_repair_bookworm_apt_sources_when_root()
_install_repair_sudoers_when_root()


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


def _reboot_system() -> None:
    commands = (
        ["systemctl", "reboot"],
        ["loginctl", "reboot"],
        ["sudo", "-n", "systemctl", "reboot"],
    )
    errors: list[str] = []
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{' '.join(command)}: {exc}")
            continue
        if completed.returncode == 0:
            return
        details = (completed.stderr or completed.stdout or "permission denied").strip()
        errors.append(f"{' '.join(command)}: {details}")
    raise UpdateError("Linux could not reboot automatically. " + " | ".join(errors))


def install_main_update(repo: str, branch: str, expected_version: str) -> None:
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


def check_latest(repo: str, current: str, branch: str = "main") -> dict:
    latest = github_main_version(repo, branch)
    available = _version_tuple(latest) > _version_tuple(current)
    installed = False

    if available and Path("/opt/posos/current").exists():
        install_main_update(repo, branch, latest)
        installed = True
        reboot_now = messagebox.askyesno(
            "POS OS Update Installed",
            f"POS OS v{latest} was installed successfully.\n\n"
            "Reboot the entire Linux system now to finish the update?",
        )
        if reboot_now:
            try:
                _reboot_system()
            except UpdateError as exc:
                messagebox.showerror("Reboot failed", str(exc))

    return {
        "available": available,
        "installed": installed,
        "version": latest,
        "current": current,
        "source": f"{branch} branch",
        "notes": (
            "The update was installed. Reboot Linux to begin using the new version."
            if installed
            else (
                "A newer POS OS version is available. On an installed kiosk, pressing "
                "Check for updates installs it automatically."
                if available
                else ""
            )
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
