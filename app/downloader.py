"""Downloads a release zip and unpacks it into downloads/<Artist> - <Title>/."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from .polite import USER_AGENT

_BAD_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(text: str) -> str:
    """Make a folder name that works on Windows, macOS and Linux."""
    name = _BAD_CHARS.sub("_", text).strip().rstrip(". ")
    return name[:120] or "Untitled"


def release_folder(download_dir: Path, artist: str, title: str) -> Path:
    label = f"{artist} - {title}" if artist else title
    return download_dir / safe_name(label)


def _long(path: Path) -> str:
    """On Windows, allow paths longer than 260 characters."""
    s = str(path.resolve())
    prefix = "\\\\?\\"   # i.e. \\?\
    if os.name == "nt" and not s.startswith(prefix):
        s = prefix + s
    return s


def _extract(zip_path: Path, dest: Path) -> int:
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    count = 0
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            # Flatten, and never let a zip write outside its folder.
            target = (dest / safe_name(Path(info.filename).name)).resolve()
            if root not in target.parents:
                continue
            with z.open(info) as src, open(_long(target), "wb") as out:
                shutil.copyfileobj(src, out)
            count += 1
    return count


async def pull(url: str, dest: Path) -> AsyncIterator[dict]:
    """Download `url` into `dest`, yielding progress events as dicts."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / (dest.name + ".part")
    yield {"stage": "start", "url": url}
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT},
                                 follow_redirects=True, timeout=60) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or 0)
            done = 0
            last_pct = -1
            with open(tmp, "wb") as f:
                async for chunk in r.aiter_bytes(256 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    pct = int(done * 100 / total) if total else -1
                    if pct != last_pct:
                        last_pct = pct
                        yield {"stage": "download", "bytes": done, "total": total, "percent": pct}

    yield {"stage": "unzip"}
    try:
        if zipfile.is_zipfile(tmp):
            files = await asyncio.to_thread(_extract, tmp, dest)
            tmp.unlink(missing_ok=True)
        else:  # not a zip (e.g. a .rar): keep the archive as-is
            dest.mkdir(parents=True, exist_ok=True)
            tmp.replace(dest / safe_name(url.rsplit("/", 1)[-1].replace("%20", " ")))
            files = 1
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    yield {"stage": "done", "files": files, "path": str(dest)}


def folder_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for folder, _dirs, files in os.walk(_long(path)):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(folder, f))
            except OSError:
                pass
    return total
