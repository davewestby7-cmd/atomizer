"""Downloads a release zip and unpacks it into downloads/<Artist> - <Title>/."""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import unquote, urlsplit

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


def _filename(url: str, headers, fallback: str) -> str:
    """Best name for a single (non-zip) file: server's name, else the URL's, else fallback."""
    cd = headers.get("content-disposition") or ""
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)"?', cd)
    if m:
        return safe_name(unquote(m.group(1)))
    last = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    if "." in last:
        return safe_name(last)
    ext = {"audio/mpeg": ".mp3", "audio/flac": ".flac", "audio/wav": ".wav",
           "audio/x-wav": ".wav", "audio/ogg": ".ogg"}.get(
        (headers.get("content-type") or "").split(";")[0].strip(), "")
    return safe_name(fallback) + ext


async def pull(url: str, dest: Path, name_hint: str = "") -> AsyncIterator[dict]:
    """Download `url` into `dest`, yielding progress events as dicts.

    Zips are unpacked into `dest`; anything else (a single track, a .rar) is saved as one file.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / (dest.name + ".part")
    yield {"stage": "start", "url": url}
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT},
                                 follow_redirects=True, timeout=60) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            headers = r.headers
            total = int(headers.get("content-length") or 0)
            done = 0
            last = -1
            with open(_long(tmp), "wb") as f:
                async for chunk in r.aiter_bytes(256 * 1024):
                    f.write(chunk)
                    done += len(chunk)
                    # percent when the size is known, otherwise every ~2 MB
                    mark = int(done * 100 / total) if total else done // (2 * 1024 * 1024)
                    if mark != last:
                        last = mark
                        yield {"stage": "download", "bytes": done, "total": total,
                               "percent": mark if total else -1}

    yield {"stage": "unzip"}
    try:
        if zipfile.is_zipfile(tmp):
            files = await asyncio.to_thread(_extract, tmp, dest)
            tmp.unlink(missing_ok=True)
        else:  # a single track or a .rar: keep it as one file
            dest.mkdir(parents=True, exist_ok=True)
            os.replace(_long(tmp), _long(dest / _filename(url, headers, name_hint or dest.name)))
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
