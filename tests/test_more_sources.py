import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from app.config import Settings
from app.db import Release
from app.downloader import _filename
from app.sources import ektoplazm
from app.sources.audius import parse_tracks
from app.sources.ektoplazm import parse_region
from app.sources.sonictantra import parse_list, parse_release

FIX = Path(__file__).parent / "fixtures"


def text(name):
    return (FIX / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------- Ektoplazm countries

def test_region_page_lists_israeli_releases():
    country, items = parse_region(text("ektoplazm_region_israel.html"))
    assert country == "Israel"
    assert len(items) == 90
    first = items[0]
    assert first["id"] == "ekto-mascalito-the-twilight-zone"
    assert first["artist"] == "Mascalito" and first["title"] == "The Twilight Zone"
    assert first["cover_url"].endswith("-120x120.jpg")


class FakeClient:
    """Serves saved pages instead of the internet, and counts requests."""
    def __init__(self, pages):
        self.pages, self.requests = pages, []

    async def get(self, url, **kw):
        self.requests.append(url)
        return SimpleNamespace(text=self.pages.get(url, "<html></html>"))


def settings(**ekto):
    return Settings(download_dir=Path("dl"), sources={"ektoplazm": ekto})


def test_region_reuses_known_releases_and_respects_budget():
    pages = {"https://ektoplazm.com/region/israel": text("ektoplazm_region_israel.html")}
    known = {"ekto-mascalito-the-twilight-zone": Release(
        id="ekto-mascalito-the-twilight-zone", source="ektoplazm", artist="Mascalito",
        title="The Twilight Zone", download_mp3="https://ektoplazm.com/files/x.zip")}
    client = FakeClient(pages)
    rels = asyncio.run(ektoplazm.fetch(
        client, settings(regions=["israel"], max_new_per_refresh=3), known=known))

    # the known release is reused without reading its page; 3 new pages are read
    release_reads = [u for u in client.requests if "/free-music/" in u]
    assert len(release_reads) == 3
    assert "https://ektoplazm.com/free-music/mascalito-the-twilight-zone" not in release_reads
    reused = next(r for r in rels if r.id == "ekto-mascalito-the-twilight-zone")
    assert reused.origin == "Israel" and "israel" in reused.tags


# ---------------------------------------------------------------- Sonic Tantra

def test_sonictantra_list():
    items = parse_list(text("sonictantra_list.html"))
    assert len(items) == 41
    assert all("/download-release/" in i["page_url"] for i in items)


def test_sonictantra_release():
    url = "https://sonictantra.com/download-release/hanumans-goa-friends-vol-3-2026-psy-world/"
    rel = parse_release(text("sonictantra_release.html"), url)
    assert rel.id == "st-hanumans-goa-friends-vol-3-2026-psy-world"
    assert rel.title == "Hanuman’s Goa Friends Vol. 3"
    assert rel.label == "PsyWorld Records"
    assert rel.artist == "Various Artists"
    assert rel.released == "2026-08-12"
    assert rel.download_mp3.endswith("MP3.zip") and rel.download_flac.endswith("WAV.zip")
    assert "goa" in rel.tags
    assert rel.can_pull and rel.price_kind == "free"


# ---------------------------------------------------------------- Audius

def test_audius_tracks():
    data = json.loads(text("audius_search_darkpsy.json"))["data"]
    rels = parse_tracks(data, "darkpsy")
    assert len(rels) > 10
    for r in rels:
        assert r.source == "audius" and r.price_kind == "free"
        assert r.stream_url.startswith("https://api.audius.co/v1/tracks/")
        assert r.page_url.startswith("https://audius.co/")
    # Only tracks that are downloadable AND not gated ("follow me first") can be pulled.
    by_id = {f"au-{t['id']}": t for t in data}
    for r in rels:
        t = by_id[r.id]
        assert r.can_pull == (bool(t["is_downloadable"]) and not t["is_download_gated"])
    pullable = [r for r in rels if r.can_pull]
    assert 0 < len(pullable) < len(rels)
    assert all(r.download_mp3.endswith("/download?app_name=atomizer") for r in pullable)
    assert any(r.kind == "mix" for r in rels)


def test_single_file_names():
    h = {"content-disposition": 'attachment; filename="OM Primordial [144] - [KaLiu].mp3"'}
    assert _filename("https://x/download?a=1", h, "x") == "OM Primordial [144] - [KaLiu].mp3"
    assert _filename("https://x/files/Some%20Album.rar", {}, "x") == "Some Album.rar"
    assert _filename("https://x/stream", {"content-type": "audio/mpeg"}, "A - B") == "A - B.mp3"
