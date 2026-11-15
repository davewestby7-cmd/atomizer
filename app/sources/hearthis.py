"""hearthis.at: a Berlin-based sound platform used by psytrance DJs worldwide.

We read its public API by genre and keep only mixes/tracks the uploader has
marked as free to download. hearthis's robots.txt doesn't allow automated
downloads, so cards play a preview and link to the page where you download it.
"""
from __future__ import annotations

import json
import logging

from ..db import Release

API = "https://api-v2.hearthis.at/categories/{genre}/"
log = logging.getLogger(__name__)


def _is_mix(item: dict) -> bool:
    try:
        long = int(item.get("duration") or 0) > 25 * 60
    except ValueError:
        long = False
    text = (item.get("title", "") + " " + item.get("tags", "")).lower()
    return long or any(w in text for w in ("mix", "set", "podcast", "live @", "radio"))


def parse_tracks(items: list[dict], genre: str) -> list[Release]:
    out = []
    for it in items:
        if str(it.get("downloadable")) != "1" or str(it.get("private", "0")) == "1":
            continue
        user = it.get("user") or {}
        sample = it.get("preview_url") or ""
        tags = [genre] + [t.strip().lower() for t in (it.get("tags") or "").split(",") if t.strip()]
        title = it.get("title", "")
        artist = user.get("username", "")
        if title.lower().startswith(artist.lower() + " - "):
            title = title[len(artist) + 3:]
        out.append(Release(
            id=f"ht-{it['id']}",
            source="hearthis",
            artist=artist,
            title=title,
            label="",
            tags=",".join(dict.fromkeys(tags)),
            cover_url=it.get("artwork_url") or it.get("thumb") or "",
            page_url=it.get("permalink_url", ""),
            price_kind="free",
            price_home=0.0,
            stream_url=sample,
            tracks_json=json.dumps([sample] if sample else []),
            released=(it.get("release_date") or it.get("created_at") or "")[:10],
            origin=it.get("geo") or "",
            kind="mix" if _is_mix(it) else "release",
        ))
    return out


async def fetch(client, settings, known=None) -> list[Release]:
    cfg = settings.source("hearthis")
    pages = int(cfg.get("pages", 2))
    found: dict[str, Release] = {}
    for genre in cfg.get("genres", ["psytrance"]):
        for page in range(1, pages + 1):
            try:
                r = await client.get(API.format(genre=genre),
                                     params={"page": page, "count": 50})
                items = r.json()
            except Exception as e:
                log.warning("hearthis: %s page %d failed: %s", genre, page, e)
                break
            if not isinstance(items, list) or not items:
                break
            for rel in parse_tracks(items, genre):
                found.setdefault(rel.id, rel)
    return list(found.values())
