"""Audius (audius.co): an open music platform with a free, key-less public API.

Artists worldwide upload full-length psytrance tracks and DJ sets here. Every
track plays in full (not a 30-second sample). Only tracks the artist has made
freely downloadable (no "follow me first" gate) get a Pull button; the rest
link to Audius.
"""
from __future__ import annotations

import json
import logging

from ..db import Release

API = "https://api.audius.co/v1"
APP = "atomizer"
log = logging.getLogger(__name__)

PSY_WORDS = ("psy", "goa", "darkpsy", "forest", "full on", "full-on", "hi-tech", "hitech",
             "psycore", "twilight", "zenonesque", "trance")


def _looks_psy(t: dict) -> bool:
    text = " ".join([t.get("title") or "", t.get("tags") or "", t.get("genre") or ""]).lower()
    return any(w in text for w in PSY_WORDS)


def parse_tracks(items: list[dict], query: str) -> list[Release]:
    out = []
    for t in items:
        if not _looks_psy(t) or not t.get("is_streamable", True) or t.get("is_stream_gated"):
            continue
        tid = t["id"]
        user = t.get("user") or {}
        art = t.get("artwork") or {}
        stream = f"{API}/tracks/{tid}/stream?app_name={APP}"
        free_dl = bool(t.get("is_downloadable")) and not t.get("is_download_gated")
        tags = [query] + [x.strip().lower() for x in (t.get("tags") or "").split(",") if x.strip()]
        out.append(Release(
            id=f"au-{tid}",
            source="audius",
            artist=user.get("name", ""),
            title=t.get("title", ""),
            label="",
            tags=",".join(dict.fromkeys(tags[:8])),
            cover_url=art.get("480x480") or art.get("150x150") or "",
            page_url=f"https://audius.co{t.get('permalink', '')}",
            price_kind="free",
            price_home=0.0,
            stream_url=stream,
            tracks_json=json.dumps([stream]),
            download_mp3=f"{API}/tracks/{tid}/download?app_name={APP}" if free_dl else "",
            released=(t.get("release_date") or t.get("created_at") or "")[:10],
            origin=(user.get("location") or "").strip(),
            kind="mix" if (t.get("duration") or 0) > 25 * 60 else "release",
        ))
    return out


async def fetch(client, settings, known=None) -> list[Release]:
    cfg = settings.source("audius")
    limit = int(cfg.get("per_query", 50))
    found: dict[str, Release] = {}
    for query in cfg.get("queries", ["psytrance"]):
        try:
            r = await client.get(f"{API}/tracks/search",
                                 params={"query": query, "limit": limit, "app_name": APP})
            items = r.json().get("data") or []
        except Exception as e:
            log.warning("Audius: search %r failed: %s", query, e)
            continue
        for rel in parse_tracks(items, query):
            found.setdefault(rel.id, rel)
    return list(found.values())
