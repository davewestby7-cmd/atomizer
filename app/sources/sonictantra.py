"""Sonic Tantra (sonictantra.com): an Indian dark/hi-tech/psycore label.

Its "free compilations" page lists free albums from Sonic Tantra and friendly
labels around the world. Newer album pages have direct MP3/WAV zip links, so
Atomizer can pull them; older ones are on mega.nz, so those cards open the page.
There are no sample files (only SoundCloud embeds), so the Play button is off
for these; open the page to listen.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..db import Release

LIST_URL = "https://sonictantra.com/free-psychedelic-trance-music-compilations/"
log = logging.getLogger(__name__)

STYLE_WORDS = {
    "darkpsy": "darkpsy", "dark psy": "darkpsy", "psycore": "psycore", "hi-tech": "hi-tech",
    "hitech": "hi-tech", "goa": "goa", "forest": "forest", "horrordelic": "horrordelic",
    "full-on": "full-on", "full on": "full-on", "twilight": "twilight", "psytrance": "psytrance",
}


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items, seen = [], set()
    for a in soup.select("a[href*='/download-release/']"):
        url = urljoin(LIST_URL, a["href"])
        if url in seen:
            continue
        seen.add(url)
        img = a.select_one("img")
        items.append({"page_url": url, "cover_url": img.get("src", "") if img else ""})
    return items


def _styles(text: str) -> list[str]:
    low = text.lower().replace("_", " ")
    return list(dict.fromkeys(tag for word, tag in STYLE_WORDS.items() if word in low)) or ["psytrance"]


def parse_release(html: str, page_url: str, cover_hint: str = "") -> Release | None:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.select_one("h1.product_title") or soup.select_one("h1")
    full_title = h1.get_text(" ", strip=True) if h1 else ""

    zips = [urljoin(page_url, a["href"]) for a in soup.select("a[href]")
            if a["href"].lower().endswith(".zip") and "/wp-content/uploads/" in a["href"]]
    mp3 = next((z for z in zips if "mp3" in z.lower()), "")
    lossless = next((z for z in zips if "flac" in z.lower()), "") or \
        next((z for z in zips if "wav" in z.lower()), "")
    hosted_elsewhere = any(h in a["href"] for a in soup.select("a[href]")
                           for h in ("mega.nz", "drive.google", "mediafire", "bandcamp.com/album"))
    if not (mp3 or lossless or hosted_elsewhere):
        return None  # no download offered at all
    # Many older albums are on mega.nz: those can't be pulled automatically,
    # so they show "Get" and open the album page instead.

    # "Hanuman's Goa Friends Vol. 3 (2026, PsyWorld Records)"
    title, year, label = full_title, "", "Sonic Tantra"
    m = re.match(r"^(.*?)\s*\((\d{4}),\s*([^)]+)\)\s*$", full_title)
    if m:
        title, year, label = m.group(1), m.group(2), m.group(3).strip()
    artist = "Various Artists"
    if " - " in title and not title.lower().startswith("va "):
        artist, title = (s.strip() for s in title.split(" - ", 1))
    elif title.lower().startswith(("va - ", "va ")):
        title = title.split(" ", 1)[1].lstrip("- ").strip()

    og = soup.select_one("meta[property='og:image']")
    published = soup.find(string=re.compile(r'"datePublished"'))
    date = ""
    if published:
        d = re.search(r'"datePublished":"(\d{4}-\d{2}-\d{2})', published)
        date = d.group(1) if d else ""

    slug = page_url.rstrip("/").rsplit("/", 1)[-1]
    return Release(
        id=f"st-{slug}",
        source="sonictantra",
        artist=artist,
        title=title,
        label=label,
        tags=",".join(_styles(full_title + " " + slug)),
        cover_url=(og.get("content") if og else "") or cover_hint,
        page_url=page_url,
        price_kind="free",
        price_home=0.0,
        download_mp3=mp3,
        download_flac=lossless,
        released=date or year,
    )


async def fetch(client, settings, known=None) -> list[Release]:
    cfg = settings.source("sonictantra")
    known = known or {}
    budget = int(cfg.get("max_new_per_refresh", 60))
    r = await client.get(LIST_URL)
    out = []
    for item in parse_list(r.text):
        slug = item["page_url"].rstrip("/").rsplit("/", 1)[-1]
        cached = known.get(f"st-{slug}")
        if cached:
            out.append(cached)
            continue
        if budget <= 0:
            continue
        budget -= 1
        try:
            page = await client.get(item["page_url"])
        except Exception as e:
            log.warning("Sonic Tantra: could not read %s: %s", item["page_url"], e)
            continue
        rel = parse_release(page.text, item["page_url"], item["cover_url"])
        if rel:
            out.append(rel)
    return out
