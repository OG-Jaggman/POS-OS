from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class RepairError(RuntimeError):
    pass


def _run(command: list[str], timeout: int = 300) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RepairError(f"Could not run {' '.join(command)}: {exc}") from exc
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "Command failed").strip()
        raise RepairError(f"{' '.join(command)} failed: {details}")
    return completed.stdout.strip()


def repair_bookworm_sources() -> None:
    os_release = Path("/etc/os-release")
    release_text = os_release.read_text(encoding="utf-8", errors="replace")
    if "VERSION_CODENAME=bookworm" not in release_text and 'VERSION_CODENAME="bookworm"' not in release_text:
        return

    sources = Path("/etc/apt/sources.list")
    backup = Path("/etc/apt/sources.list.posos-backup")
    if sources.exists() and not backup.exists():
        shutil.copy2(sources, backup)
    sources.write_text(
        "deb http://deb.debian.org/debian bookworm main contrib non-free-firmware\n"
        "deb http://deb.debian.org/debian bookworm-updates main contrib non-free-firmware\n"
        "deb http://security.debian.org/debian-security bookworm-security main contrib non-free-firmware\n",
        encoding="utf-8",
    )


def repair_wifi() -> None:
    if os.geteuid() != 0:
        raise RepairError("Wi-Fi repair must run as root through the POS OS repair button.")

    repair_bookworm_sources()
    _run(["apt-get", "update"], timeout=300)
    _run(
        [
            "apt-get",
            "install",
            "-y",
            "network-manager",
            "wpasupplicant",
            "wireless-regdb",
            "rfkill",
            "firmware-iwlwifi",
        ],
        timeout=600,
    )

    rfkill = shutil.which("rfkill") or "/usr/sbin/rfkill"
    if Path(rfkill).exists():
        _run([rfkill, "unblock", "all"], timeout=30)

    _run(["nmcli", "radio", "wifi", "on"], timeout=30)
    _run(["systemctl", "restart", "NetworkManager"], timeout=60)


def main() -> None:
    repair_wifi()
    print("Wi-Fi repair completed successfully.")


if __name__ == "__main__":
    main()
