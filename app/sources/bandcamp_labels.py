"""Bandcamp labels you follow: Zenon, Looney Moon, Deepnotic, HOMmega, Blue Tunes...

For each label (e.g. zenonrecords.bandcamp.com) we read its /music page, which
lists its whole catalogue, then each album's page once for the price,
free-download flag, artwork, style tags and per-track previews. Unlike the
other sources, paid releases are kept too: they show on the Labels tab.
Free and cheap ones also appear on the Free and Cheap tabs.

Bandcamp's preview links expire after about a day, so pressing Play asks the
server for fresh ones (see refresh_tracks below).
Downloads and purchases happen on Bandcamp (its robots.txt forbids automated
downloads), so cards link out.
"""
from __future__ import annotations

import html as htmllib
import json
import logging
import re
import time
from datetime import datetime

from ..currency import convert, get_rates
from ..db import Release
from .bandcamp import classify

log = logging.getLogger(__name__)


def _label_cfg(entry, default_max: int) -> tuple[str, int]:
    """Config entries are 'zenonrecords' or {name: zenonrecords, max_albums: 0}.

    max_albums: newest N releases to read; 0 means the whole catalogue.
    """
    if isinstance(entry, dict):
        return str(entry["name"]), int(entry.get("max_albums", default_max))
    return str(entry), default_max


_RELEASE = r'(?:https://[a-z0-9-]+\.bandcamp\.com)?/(?:album|track)/[^"?#&]+'


def _full_url(link: str, base: str) -> str:
    """Labels often list releases that live on the artist's own Bandcamp page."""
    link = htmllib.unescape(link).split("?", 1)[0]
    return link if link.startswith("http") else base + link


def parse_music_page(html: str, base: str) -> tuple[str, list[str]]:
    """A label's /music page -> (label name, release URLs newest first)."""
    name = ""
    m = re.search(r'<meta property="og:site_name" content="([^"]+)"', html) or \
        re.search(r"<title>[^|<]*\|\s*([^<]+)</title>", html)
    if m:
        name = htmllib.unescape(m.group(1)).strip()
    # The newest releases are in the page itself; only look inside the music grid.
    start = html.find('id="music-grid"')
    grid = html[start:html.find("</ol>", start)] if start >= 0 else html
    links = re.findall(r'href="(' + _RELEASE + r')[^"]*"', grid)
    m = re.search(r'data-client-items="([^"]*)"', html)
    if m:  # the rest of the catalogue, loaded by Bandcamp's own page script
        try:
            links += [i["page_url"] for i in json.loads(htmllib.unescape(m.group(1)))
                      if i.get("page_url")]
        except ValueError:
            pass
    return name, list(dict.fromkeys(_full_url(link, base) for link in links))


def _tralbum(html: str) -> dict:
    m = re.search(r'data-tralbum="([^"]*)"', html)
    return json.loads(htmllib.unescape(m.group(1))) if m else {}


def preview_urls(html: str) -> list[str]:
    tracks = _tralbum(html).get("trackinfo") or []
    return [t["file"]["mp3-128"] for t in tracks if (t.get("file") or {}).get("mp3-128")]


def _iso(date_text: str) -> str:
    try:
        return datetime.strptime(date_text, "%d %b %Y %H:%M:%S %Z").date().isoformat()
    except (TypeError, ValueError):
        return ""


def parse_album(html: str, url: str, label: str, sub: str,
                rates: dict[str, float], threshold: float) -> Release | None:
    data = _tralbum(html)
    if not data:
        return None
    cur = data.get("current") or {}
    price = float(cur.get("minimum_price") or 0)
    currency = ""
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        c = re.search(r'"priceCurrency"\s*:\s*"(\w+)"', m.group(1))
        if c:
            currency = c.group(1).upper()
            break
    is_free = data.get("freeDownloadPage") is not None
    price_home = 0.0 if price <= 0 else convert(price, currency, rates)

    og = re.search(r'<meta property="og:image" content="([^"]+)"', html)
    loc = re.search(r'<span class="location secondaryText">([^<]+)', html)
    origin = htmllib.unescape(loc.group(1)).strip() if loc else ""
    tags = [htmllib.unescape(t).strip().lower()
            for t in re.findall(r'<a class="tag"[^>]*>([^<]+)', html)]
    tags = [t for t in tags if t != origin.lower()][:8]
    samples = preview_urls(html)
    kind = data.get("item_type") or "album"

    return Release(
        id=f"bcl-{sub}-{kind[0]}{data.get('id')}",
        source="bclabels",
        artist=data.get("artist") or label,
        title=cur.get("title") or "",
        label=label,
        tags=",".join(dict.fromkeys(tags)),
        cover_url=og.group(1) if og else "",
        page_url=url,
        price_kind=classify(is_free, price, price_home, threshold),
        price=price,
        currency=currency,
        price_home=price_home,
        stream_url=samples[0] if samples else "",
        tracks_json=json.dumps(samples),
        released=_iso(cur.get("release_date") or data.get("album_release_date") or ""),
        origin=origin,
    )


def previews_expired(tracks: list[str], margin: int = 600) -> bool:
    """Bandcamp preview links carry ts=<expiry unix time>."""
    for url in tracks:
        m = re.search(r"[?&]ts=(\d+)", url)
        if m and int(m.group(1)) < time.time() + margin:
            return True
    return False


async def refresh_tracks(client, rel: Release) -> list[str]:
    """Fresh preview links for one release (called when you press Play)."""
    r = await client.get(rel.page_url)
    return preview_urls(r.text)


async def fetch(client, settings, known=None) -> list[Release]:
    cfg = settings.source("bclabels")
    known = known or {}
    budget = int(cfg.get("max_new_per_refresh", 300))   # album pages we may read this time
    default_max = int(cfg.get("max_albums", 60))          # newest N per label (0 = all)
    rates = await get_rates(settings.home_currency)
    out: dict[str, Release] = {}
    by_url = {k.page_url: k for k in known.values()}

    for entry in cfg.get("labels", []):
        sub, max_albums = _label_cfg(entry, default_max)
        base = f"https://{sub}.bandcamp.com"
        try:
            r = await client.get(f"{base}/music")
        except Exception as e:
            log.warning("Bandcamp label %s: %s", sub, e)
            continue
        label, urls = parse_music_page(r.text, base)
        if max_albums > 0:
            urls = urls[:max_albums]
        for url in urls:
            cached = by_url.get(url)
            if cached:
                out[cached.id] = cached
                continue
            if budget <= 0:
                continue   # picked up on the next refresh
            budget -= 1
            try:
                page = await client.get(url)
            except Exception as e:
                log.warning("Bandcamp label %s: could not read %s: %s", sub, url, e)
                continue
            rel = parse_album(page.text, url, label or sub, sub, rates, settings.cheap_threshold)
            if rel:
                out[rel.id] = rel
    return list(out.values())
