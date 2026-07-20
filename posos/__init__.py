from __future__ import annotations

import os
from pathlib import Path

__version__ = "2.9.7"


def _install_posos_reboot_permission() -> None:
    if os.geteuid() != 0:
        return
    path = Path("/etc/sudoers.d/posos-reboot")
    try:
        path.write_text(
            "register ALL=(root) NOPASSWD: /usr/bin/systemctl reboot\n"
            "register ALL=(root) NOPASSWD: /bin/systemctl reboot\n",
            encoding="utf-8",
        )
        path.chmod(0o440)
    except OSError:
        pass


_install_posos_reboot_permission()