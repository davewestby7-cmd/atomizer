import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.sources import bandcamp_labels as bcl

FIX = Path(__file__).parent / "fixtures"
RATES = {"AUD": 1.0, "EUR": 0.60, "USD": 0.65}


def text(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_music_page_lists_whole_catalogue():
    base = "https://zenonrecords.bandcamp.com"
    name, paths = bcl.parse_music_page(text("bclabel_zenon_music.html"), base)
    assert name == "Zenon Records"
    assert len(paths) > 400                       # grid + the rest of the catalogue
    assert paths[:2] == [base + "/album/remember", base + "/album/unresolved"]  # newest first
    assert base + "/album/an-appeal-to-geometry" in paths                        # older ones follow
    assert len(paths) == len(set(paths))


def test_paid_album():
    url = "https://zenonrecords.bandcamp.com/album/an-appeal-to-geometry"
    rel = bcl.parse_album(text("bclabel_zenon_album.html"), url, "Zenon Records",
                          "zenonrecords", RATES, threshold=5.0)
    assert rel.source == "bclabels" and rel.label == "Zenon Records"
    assert rel.artist == "Redshift" and rel.title == "An Appeal to Geometry"
    assert rel.price == 6.0 and rel.currency == "EUR"
    assert rel.price_home == 10.0 and rel.price_kind == "paid"
    assert rel.released == "2026-04-02"
    assert rel.origin == "Australia"
    assert "zenonesque" in rel.tags and "australia" not in rel.tags
    assert len(json.loads(rel.tracks_json)) == 5
    assert not rel.can_pull                       # bought on Bandcamp


def test_free_album():
    url = "https://looneymoonrecords.bandcamp.com/album/free-earth-looney-moon-present-earth-alchemy"
    rel = bcl.parse_album(text("bclabel_looneymoon_album.html"), url, "Looney Moon Records",
                          "looneymoonrecords", RATES, threshold=5.0)
    assert rel.price_kind == "free"
    assert rel.label == "Looney Moon Records" and rel.origin == "Italy"
    assert len(json.loads(rel.tracks_json)) == 17


def test_preview_expiry():
    soon = int(time.time()) + 60
    later = int(time.time()) + 86400
    assert bcl.previews_expired([f"https://t4.bcbits.com/stream/x?p=0&ts={soon}&t=y"])
    assert not bcl.previews_expired([f"https://t4.bcbits.com/stream/x?p=0&ts={later}&t=y"])
    assert not bcl.previews_expired(["https://ektoplazm.com/audio/a.mp3"])


class FakeClient:
    def __init__(self, pages):
        self.pages, self.requests = pages, []

    async def get(self, url, **kw):
        self.requests.append(url)
        return SimpleNamespace(text=self.pages.get(url, "<html></html>"))


def test_fetch_limits_and_reuses(monkeypatch):
    async def rates(home):
        return RATES
    monkeypatch.setattr(bcl, "get_rates", rates)
    base = "https://zenonrecords.bandcamp.com"
    pages = {base + "/music": text("bclabel_zenon_music.html"),
             # serve a saved album page as the newest release
             base + "/album/remember": text("bclabel_zenon_album.html")}
    s = Settings(download_dir=Path("dl"), sources={"bclabels": {
        "labels": [{"name": "zenonrecords", "max_albums": 3}], "max_new_per_refresh": 2}})
    client = FakeClient(pages)
    rels = asyncio.run(bcl.fetch(client, s))
    album_reads = [u for u in client.requests if "/music" not in u]
    assert len(album_reads) == 2                    # budget of 2 new pages
    assert len(rels) == 1 and rels[0].page_url == base + "/album/remember"

    # next refresh: the known one is reused, not re-read
    known = {r.id: r for r in rels}
    client2 = FakeClient(pages)
    asyncio.run(bcl.fetch(client2, s, known=known))
    assert base + "/album/remember" not in client2.requests


def test_releases_on_artist_pages_keep_their_own_address():
    html = ('<ol id="music-grid"><li><a href="https://jimigreenlooneymoon.bandcamp.com/album/'
            'catch-a-buzz?label=1&amp;tab=music">x</a></li><li><a href="/album/own">y</a></li></ol>'
            '<ol data-client-items="[{&quot;page_url&quot;:&quot;https://dustlooneymoon.bandcamp.com'
            '/album/thirteen?label=1&amp;tab=music&quot;}]"></ol>')
    _, urls = bcl.parse_music_page(html, "https://looneymoonrecords.bandcamp.com")
    assert urls == ["https://jimigreenlooneymoon.bandcamp.com/album/catch-a-buzz",
                    "https://looneymoonrecords.bandcamp.com/album/own",
                    "https://dustlooneymoon.bandcamp.com/album/thirteen"]


def test_whole_catalogue_setting():
    assert bcl._label_cfg({"name": "zenonrecords", "max_albums": 0}, 60) == ("zenonrecords", 0)
    assert bcl._label_cfg("hommega", 60) == ("hommega", 60)
