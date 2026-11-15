"""Ektoplazm (ektoplazm.com): a free, Creative Commons psytrance netlabel.

We read the home page, one page per style (e.g. /style/goa) and one page per
country (e.g. /region/israel). Every release there is a free download, so they
all land on the Free tab.

Country pages only list thumbnails, so each new release's own page is read once
(at most `max_new_per_refresh` per refresh) and then remembered.
Note: Ektoplazm's robots.txt blocks /page/N pagination, so we only read the
first page of each style or country. The polite client enforces that for us.
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


def parse_region(html: str) -> tuple[str, list[dict]]:
    """A country page: returns (country name, [{id, page_url, cover_url, artist, title}])."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.select_one("h1")
    name = h1.get_text(strip=True) if h1 else ""
    items, seen = [], set()
    for cap in soup.select("div.wp-caption"):
        a = cap.select_one("a[href*='/free-music/']")
        if not a:
            continue
        page_url = urljoin(BASE, a["href"])
        slug = page_url.rstrip("/").rsplit("/", 1)[-1]
        if slug in seen:
            continue
        seen.add(slug)
        img = cap.select_one("img")
        text = cap.select_one(".wp-caption-text")
        artist, title = _split_artist_title(text.get_text(" ", strip=True) if text else slug)
        items.append({"id": f"ekto-{slug}", "page_url": page_url, "artist": artist, "title": title,
                      "cover_url": urljoin(BASE, img["src"]) if img and img.get("src") else ""})
    return name, items


async def _read_release(client, url: str, rel_id: str) -> Release | None:
    try:
        r = await client.get(url)
    except Exception as e:
        log.warning("Ektoplazm: could not read %s: %s", url, e)
        return None
    return next((full for full in parse_listing(r.text) if full.id == rel_id), None)


async def fetch(client, settings, known=None) -> list[Release]:
    cfg = settings.source("ektoplazm")
    known = known or {}
    budget = int(cfg.get("max_new_per_refresh", 150))   # release pages we may read this time
    found: dict[str, Release] = {}

    # 1. Home page + style pages (these list full releases with samples).
    for url in [BASE + "/"] + [f"{BASE}/style/{s}" for s in cfg.get("styles", [])]:
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

    # Short-format posts (home page) have no samples; read their own page.
    for rel in [r for r in found.values() if not r.stream_url][:10]:
        cached = known.get(rel.id)
        full = cached if cached and cached.stream_url else await _read_release(client, rel.page_url, rel.id)
        if full:
            full.tags = _merge_tags(rel.tags, full.tags)
            found[rel.id] = full

    # 2. Country pages: thumbnails only, so reuse what we know and read new ones.
    for region in cfg.get("regions", []):
        try:
            r = await client.get(f"{BASE}/region/{region}")
        except Exception as e:
            log.warning("Ektoplazm: could not read region %s: %s", region, e)
            continue
        country, items = parse_region(r.text)
        country = country or region.replace("-", " ").title()
        for item in items:
            rel = found.get(item["id"])
            if rel is None:
                cached = known.get(item["id"])
                if cached and (cached.download_mp3 or cached.download_flac):
                    rel = cached
                elif budget > 0:
                    budget -= 1
                    rel = await _read_release(client, item["page_url"], item["id"])
                if rel is None:
                    continue   # over this refresh's budget: picked up next time
                found[rel.id] = rel
            if not rel.origin:
                rel.origin = country
            rel.tags = _merge_tags(rel.tags, country.lower())
    return list(found.values())
