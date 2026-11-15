import json
from pathlib import Path

from app.sources.ektoplazm import parse_listing

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_home_page_finds_releases_not_blog_posts():
    rels = parse_listing(load("ektoplazm_home.html"))
    assert len(rels) == 6
    assert all(r.page_url.startswith("https://ektoplazm.com/free-music/") for r in rels)
    assert all(r.price_kind == "free" and r.source == "ektoplazm" for r in rels)


def test_full_post_has_everything():
    rel = parse_listing(load("ektoplazm_home.html"))[0]
    assert rel.id == "ekto-globular-entangled-everything"
    assert rel.artist == "Globular"
    assert rel.title == "Entangled Everything"
    assert rel.tags == "downtempo,psy dub"
    assert rel.released == "2018-12-29"
    assert rel.cover_url.endswith("globular-entangled-everything-300x300.jpg")
    assert rel.download_mp3.endswith("MP3.zip")
    assert rel.download_flac.endswith("FLAC.zip")
    tracks = json.loads(rel.tracks_json)
    assert len(tracks) == 10
    assert rel.stream_url == tracks[0] == "https://ektoplazm.com/audio/globular-popping-out.mp3"


def test_short_post_has_downloads_but_no_samples():
    rels = {r.id: r for r in parse_listing(load("ektoplazm_home.html"))}
    z = rels["ekto-zoungla-there-will-be-dub"]
    assert z.artist == "Zoungla" and z.title == "There Will Be Dub"
    assert z.download_mp3 and not z.stream_url
    assert z.cover_url.endswith("-120x120.jpg")


def test_style_page():
    rels = parse_listing(load("ektoplazm_style_goa.html"))
    assert len(rels) == 5
    assert all(r.stream_url for r in rels)
    first = rels[0]
    assert first.artist == "Sab Kuch Milegator"
    assert first.title == "Surrounded By Surreality"
    assert "goa" in first.tags and "forest" in first.tags
