"""Google Drive sync by running rclone (https://rclone.org)."""
from __future__ import annotations

import asyncio
import shutil
import subprocess

from .config import Settings


def rclone_path() -> str | None:
    return shutil.which("rclone")


def sync_state(settings: Settings) -> str:
    """'ready', 'no-rclone' (not installed) or 'no-remote' (not set in config)."""
    if not rclone_path():
        return "no-rclone"
    if not settings.rclone_remote:
        return "no-remote"
    return "ready"


async def run_sync(settings: Settings) -> tuple[bool, str]:
    state = sync_state(settings)
    if state != "ready":
        return False, state
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    mode = "sync" if settings.rclone_mode == "sync" else "copy"
    cmd = [rclone_path(), mode, str(settings.download_dir), settings.rclone_remote,
           "--exclude", "*.part"]
    # A thread + subprocess.run works on every OS/event loop (incl. Windows).
    proc = await asyncio.to_thread(
        subprocess.run, cmd, capture_output=True, text=True, errors="replace"
    )
    text = (proc.stdout + proc.stderr).strip()
    return proc.returncode == 0, text[-2000:]
