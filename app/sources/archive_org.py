"""Internet Archive netlabels (archive.org/details/netlabels).

Hundreds of small netlabels from all over the world publish their releases on
the Internet Archive under Creative Commons licences. We search the "netlabels"
collection for psytrance subjects, then read each item's file list to find
samples and a zip download. Everything here is free and can be pulled.
"""
from __future__ import annotations

import json
import logging
from urllib.parse import quote

from ..db import Release

SEARCH_URL = "https://archive.org/advancedsearch.php"
META_URL = "https://archive.org/metadata/{id}"
log = logging.getLogger(__name__)

DEFAULT_SUBJECTS = ["psytrance", "psy-trance", "psychedelic trance", "goa trance", "goa",
                    "darkpsy", "dark psytrance", "forest psytrance", "psy-prog",
                    "progressive psytrance", "hi-tech", "psychill", "psybient"]
def _is_mp3(fmt: str) -> bool:      # "VBR MP3", "320Kbps MP3", ...
    return "mp3" in (fmt or "").lower()


def _is_lossless(fmt: str) -> bool:  # "Flac", "24bit Flac", "WAVE"
    return any(w in (fmt or "").lower() for w in ("flac", "wave"))


def build_query(subjects: list[str]) -> str:
    terms = " OR ".join(f'"{s}"' for s in subjects)
    return f"collection:netlabels AND mediatype:audio AND subject:({terms})"


def parse_search(data: dict) -> list[dict]:
    return data.get("response", {}).get("docs", [])


def _first(value):
    return value[0] if isinstance(value, list) else (value or "")


def parse_item(doc: dict, meta: dict) -> Release:
    """Turn one search result plus its /metadata into a Release."""
    ident = doc["identifier"]
    files = meta.get("files", [])
    md = meta.get("metadata", {})

    def url(name: str) -> str:
        return f"https://archive.org/download/{ident}/{quote(name)}"

    mp3s = sorted(f["name"] for f in files if _is_mp3(f.get("format")))
    oggs = sorted(f["name"] for f in files if f.get("format") == "Ogg Vorbis")
    lossless = sorted(f["name"] for f in files if _is_lossless(f.get("format")))
    # Browsers can play WAV too, so use it for samples when that's all there is.
    samples = [url(n) for n in (mp3s or oggs or lossless)][:20]

    formats = sorted({f.get("format") or "" for f in files})
    mp3_fmt = next((f for f in formats if _is_mp3(f)), "")
    # Prefer FLAC over WAVE (much smaller)
    lossless_fmt = next((f for f in formats if "flac" in f.lower()), "") or         next((f for f in formats if _is_lossless(f)), "")
    zip_url = "https://archive.org/compress/{id}/formats={fmt}"

    title = _first(doc.get("title")) or ident
    artist = _first(doc.get("creator")) or _first(md.get("creator"))
    if not artist and " - " in title:  # many labels write "[CAT001] Artist - Title"
        head, title = title.split(" - ", 1)
        artist = head.split("]", 1)[-1].strip()
    labels = [c for c in (doc.get("collection") or []) if c != "netlabels"]
    subjects = doc.get("subject") or []
    if isinstance(subjects, str):
        subjects = [s.strip() for s in subjects.replace(";", ",").split(",")]

    return Release(
        id=f"ia-{ident}",
        source="archive",
        artist=artist,
        title=title,
        label=labels[0] if labels else "Netlabel",
        tags=",".join(dict.fromkeys(s.lower() for s in subjects[:8] if s)),
        cover_url=f"https://archive.org/services/img/{ident}",
        page_url=f"https://archive.org/details/{ident}",
        price_kind="free",
        price_home=0.0,
        stream_url=samples[0] if samples else "",
        tracks_json=json.dumps(samples),
        download_mp3=zip_url.format(id=ident, fmt=quote(mp3_fmt)) if mp3_fmt else "",
        download_flac=zip_url.format(id=ident, fmt=quote(lossless_fmt)) if lossless_fmt else "",
        released=(_first(doc.get("date")) or "")[:10],
        origin="",
    )


async def fetch(client, settings, known=None) -> list[Release]:
    cfg = settings.source("archive")
    params = {
        "q": build_query(cfg.get("subjects") or DEFAULT_SUBJECTS),
        "fl[]": ["identifier", "title", "creator", "date", "subject", "collection"],
        "sort[]": "publicdate desc",
        "rows": int(cfg.get("max_items", 80)),
        "output": "json",
    }
    r = await client.get(SEARCH_URL, params=params)
    out = []
    known = known or {}
    for doc in parse_search(r.json()):
        cached = known.get(f"ia-{doc['identifier']}")
        if cached and cached.tracks_json != "[]":  # already read its file list before
            out.append(cached)
            continue
        try:
            meta = (await client.get(META_URL.format(id=doc["identifier"]))).json()
            out.append(parse_item(doc, meta))
        except Exception as e:
            log.warning("archive.org: skipping %s: %s", doc.get("identifier"), e)
    return out
