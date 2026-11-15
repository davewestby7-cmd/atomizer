import json
from pathlib import Path

from app.main import country_of
from app.sources.archive_org import build_query, parse_item, parse_search
from app.sources.bandcamp import parse_discover
from app.sources.hearthis import parse_tracks

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def docs():
    return {d["identifier"]: d for d in parse_search(load("archive_search.json"))}


def test_archive_query_targets_netlabels():
    q = build_query(["psytrance", "goa trance"])
    assert q.startswith("collection:netlabels") and '"goa trance"' in q


def test_archive_mp3_release():
    rel = parse_item(docs()["pn242"], load("archive_meta_pn242.json"))
    assert rel.id == "ia-pn242" and rel.source == "archive" and rel.price_kind == "free"
    assert rel.page_url == "https://archive.org/details/pn242"
    assert rel.stream_url.startswith("https://archive.org/download/pn242/")
    assert rel.stream_url.lower().endswith(".mp3")
    assert rel.download_mp3 == "https://archive.org/compress/pn242/formats=320Kbps%20MP3"
    assert rel.can_pull


def test_archive_wav_only_release():
    rel = parse_item(docs()["digital-diamonds-117"], load("archive_meta_digital-diamonds-117.json"))
    assert rel.artist == "L-maghreb"
    assert rel.title == "Desert Heartbeat EP"
    assert rel.label == "digital-diamonds"
    assert not rel.download_mp3
    assert rel.download_flac.endswith("formats=WAVE")
    assert rel.stream_url.endswith(".wav")
    assert "psytrance" in rel.tags


def test_hearthis_keeps_only_free_downloads():
    items = load("hearthis_psytrance.json")
    rels = parse_tracks(items, "psytrance")
    free = [i for i in items if str(i["downloadable"]) == "1"]
    assert len(rels) == len(free) > 0
    for r in rels:
        assert r.source == "hearthis" and r.price_kind == "free"
        assert r.page_url.startswith("https://hearthis.at/")
        assert not r.can_pull            # robots.txt: downloads happen on their page
        assert r.kind in ("mix", "release")
    assert any(r.origin for r in rels)
    assert any(r.kind == "mix" for r in rels)


def test_bandcamp_keeps_artist_location():
    rels = parse_discover(load("bandcamp_discover_psytrance.json"), "psytrance", {"USD": 0.65}, 5.0)
    assert rels[0].origin == "Portland, Oregon"


def test_country_tag():
    assert country_of("Tel Aviv Yafo, Israel") == "israel"
    assert country_of("Israel") == "israel"
    assert country_of("") == ""
