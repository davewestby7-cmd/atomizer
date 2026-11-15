"""Bandcamp: browse tag feeds and sort releases into Free / Name-Your-Price / Cheap.

We use Bandcamp's public discover feed (the same one bandcamp.com/discover uses),
which its robots.txt explicitly allows. Each result already includes the price,
currency, a "free download" flag and a 30-second preview stream.

Atomizer never downloads from Bandcamp itself: free and name-your-price downloads
go through Bandcamp's own page (often with an email step), so cards link out.
"""
from __future__ import annotations

import json
import logging
import re

from ..currency import convert
from ..db import Release

DISCOVER_URL = "https://bandcamp.com/api/discover/1/discover_web"
ART_URL = "https://f4.bcbits.com/img/a{art_id}_2.jpg"   # 350x350
PAGE_SIZE = 60
log = logging.getLogger(__name__)


def _clean_url(url: str) -> str:
    return re.sub(r"\?from=discover_page$", "", url or "")


def classify(is_free: bool, price: float, price_home: float | None, threshold: float) -> str:
    if is_free:
        return "free"
    if price <= 0:
        return "nyp"
    if price_home is not None and price_home <= threshold:
        return "cheap"
    return "paid"


def parse_discover(data: dict, tag: str, rates: dict[str, float], threshold: float) -> list[Release]:
    out: list[Release] = []
    for item in data.get("results", []):
        player = item.get("playerData") or {}
        album = player.get("album") or {}
        # album.price.amount is in normal units (6.0 = 6 EUR); the top-level
        # price.amount is in cents, so prefer the album one.
        price_info = album.get("price") or {}
        if "amount" in price_info:
            price = float(price_info["amount"])
        else:
            price = float((item.get("price") or {}).get("amount", 0)) / 100
        currency = (price_info.get("currency")
                    or (item.get("price") or {}).get("currency") or "").upper()
        is_free = bool(item.get("isFreeDownload") or album.get("isFreeDownload"))
        price_home = 0.0 if price <= 0 else convert(price, currency, rates)

        art_id = (item.get("primaryImage") or {}).get("imageId") or player.get("artId")
        stream = "" if player.get("isStreamingDisabled") else (player.get("streamUrl") or "")
        artist = item.get("albumArtist") or item.get("bandName") or player.get("artistName") or ""
        released = (item.get("releaseDate") or "")[:10]

        out.append(Release(
            id=f"bc-{item.get('itemType', 'a')}{item['itemId']}",
            source="bandcamp",
            artist=artist,
            title=item.get("title", ""),
            label=item.get("bandName", "") if item.get("albumArtist") else "",
            tags=tag,
            cover_url=ART_URL.format(art_id=art_id) if art_id else "",
            page_url=_clean_url(item.get("itemUrl") or album.get("url") or ""),
            price_kind=classify(is_free, price, price_home, threshold),
            price=price,
            currency=currency,
            price_home=price_home,
            stream_url=stream,
            tracks_json=json.dumps([stream] if stream else []),
            released=released,
        ))
    return out


async def fetch(client, settings, rates: dict[str, float] | None = None) -> list[Release]:
    from ..currency import get_rates

    cfg = settings.source("bandcamp")
    rates = rates or await get_rates(settings.home_currency)
    per_tag = int(cfg.get("per_tag", 120))
    found: dict[str, Release] = {}
    for tag in cfg.get("tags", []):
        cursor, seen = "*", 0
        while seen < per_tag and cursor:
            body = {
                "category_id": 0, "tag_norm_names": [tag], "geoname_id": 0,
                "slice": "new", "cursor": cursor, "size": min(PAGE_SIZE, per_tag - seen),
                "include_result_types": ["a", "s"],
            }
            try:
                r = await client.post(DISCOVER_URL, json=body)
                data = r.json()
            except Exception as e:
                log.warning("Bandcamp: tag %s failed: %s", tag, e)
                break
            batch = parse_discover(data, tag, rates, settings.cheap_threshold)
            if not batch:
                break
            for rel in batch:
                if rel.id in found:
                    tags = dict.fromkeys(found[rel.id].tags.split(",") + [tag])
                    found[rel.id].tags = ",".join(tags)
                else:
                    found[rel.id] = rel
            seen += len(batch)
            cursor = data.get("cursor")
    # We only keep what's worth showing: free, name-your-price and cheap.
    return [r for r in found.values() if r.price_kind != "paid"]
