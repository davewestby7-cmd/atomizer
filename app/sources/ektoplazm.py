"""Ektoplazm (ektoplazm.com): a free, Creative Commons psytrance netlabel.

We read the home page plus one page per style (e.g. /style/goa). Every release
there is a free download, so they all land on the Free tab.
Note: Ektoplazm's robots.txt blocks /page/N pagination, so we only read the
first page of each style. The polite client enforces that for us.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..db import Release

BASE = "https://ektoplazm.com"
log = logging.getLogger(__name__)


def _split_artist_title(text: str) -> tuple[str, str]:
    for sep in (" – ", " - ", " — "):
        if sep in text:
            artist, title = text.split(sep, 1)
            return artist.strip(), title.strip()
    return "", text.strip()


def _iso_date(text: str) -> str:
    """'December 29, 2018' -> '2018-12-29' (so releases sort properly)."""
    try:
        return datetime.strptime(text.strip(), "%B %d, %Y").date().isoformat()
    except ValueError:
        return text.strip()


def _merge_tags(*tag_strings: str) -> str:
    tags = [t for s in tag_strings for t in s.split(",") if t]
    return ",".join(dict.fromkeys(tags))


def parse_listing(html: str) -> list[Release]:
    """Parse any Ektoplazm page containing release posts (home, style or release page)."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, Release] = {}
    for post in soup.select("div.post"):
        link = post.select_one("h1 a[href]")
        if not link or "/free-music/" not in link["href"]:
            continue
        page_url = urljoin(BASE, link["href"])
        slug = page_url.rstrip("/").rsplit("/", 1)[-1]
        artist, title = _split_artist_title(link.get_text(" ", strip=True))

        img = post.select_one("img.cover") or post.select_one("img.alignleft")
        cover = urljoin(BASE, img["src"]) if img and img.get("src") else ""

        tags = [a.get_text(strip=True).lower() for a in post.select("span.style a")]
        date = post.select_one("span.d")

        downloads = {a.get("data-download-format"): a["href"]
                     for a in post.select("a[data-download-format][href]")}

        if not artist and any("/VA%20-%20" in u for u in downloads.values()):
            artist = "Various Artists"

        tracks: list[str] = []
        player = post.select_one("[data-tracks]")
        if player:
            try:
                tracks = [t for t in json.loads(player["data-tracks"]) if isinstance(t, str)]
            except ValueError:
                pass

        out[slug] = Release(
            id=f"ekto-{slug}",
            source="ektoplazm",
            artist=artist,
            title=title,
            label="Ektoplazm",
            tags=",".join(dict.fromkeys(tags)),
            cover_url=cover,
            page_url=page_url,
            price_kind="free",
            price=0.0,
            currency="",
            price_home=0.0,
            stream_url=tracks[0] if tracks else "",
            tracks_json=json.dumps(tracks),
            download_mp3=downloads.get("mp3", ""),
            download_flac=downloads.get("flac", ""),
            released=_iso_date(date.get_text(strip=True)) if date else "",
        )
    return list(out.values())


async def fetch(client, settings) -> list[Release]:
    cfg = settings.source("ektoplazm")
    pages = [BASE + "/"] + [f"{BASE}/style/{s}" for s in cfg.get("styles", [])]
    found: dict[str, Release] = {}
    for url in pages:
        try:
            r = await client.get(url)
        except Exception as e:  # keep going if one page fails
            log.warning("Ektoplazm: could not read %s: %s", url, e)
            continue
        for rel in parse_listing(r.text):
            prev = found.get(rel.id)
            if prev:  # seen on another page: keep the version with samples, merge tags
                best = rel if rel.stream_url or not prev.stream_url else prev
                best.tags = _merge_tags(prev.tags, rel.tags)
                found[rel.id] = best
            else:
                found[rel.id] = rel

    # Short-format posts (home page) have no samples; read their own page (max 10).
    missing = [r for r in found.values() if not r.stream_url][:10]
    for rel in missing:
        try:
            r = await client.get(rel.page_url)
        except Exception as e:
            log.warning("Ektoplazm: could not read %s: %s", rel.page_url, e)
            continue
        for full in parse_listing(r.text):
            if full.id == rel.id:
                full.tags = _merge_tags(rel.tags, full.tags)
                found[rel.id] = full
    return list(found.values())
