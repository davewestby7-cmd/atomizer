import copy
import json
from pathlib import Path

from app.sources.bandcamp import classify, parse_discover

FIX = Path(__file__).parent / "fixtures"
# Fixed test rates: how many of each currency 1 AUD buys.
RATES = {"AUD": 1.0, "USD": 0.65, "EUR": 0.60, "ILS": 2.40}


def load():
    return json.loads((FIX / "bandcamp_discover_psytrance.json").read_text(encoding="utf-8"))


def by_title(rels):
    return {r.title: r for r in rels}


def test_parses_all_results():
    rels = parse_discover(load(), "psytrance", RATES, threshold=5.0)
    assert len(rels) == 10
    for r in rels:
        assert r.source == "bandcamp"
        assert r.id.startswith("bc-a")
        assert r.page_url.startswith("https://") and "from=discover_page" not in r.page_url
        assert r.cover_url.startswith("https://f4.bcbits.com/img/a")
        assert r.stream_url.startswith("https://t4.bcbits.com/stream/")
        assert r.tags == "psytrance"


def test_price_buckets():
    rels = by_title(parse_discover(load(), "psytrance", RATES, threshold=5.0))
    nyp = rels["The Soft Focus"]
    assert nyp.price_kind == "nyp" and nyp.price == 0

    cheap = rels["Shizukeza"]          # USD 2.00 ~= AUD 3.08
    assert cheap.price_kind == "cheap"
    assert cheap.currency == "USD" and cheap.price == 2.0
    assert cheap.price_home == 3.08

    assert rels["Yami"].price_kind == "paid"                      # USD 9
    assert rels["In The Future (Remixes)"].price_kind == "paid"   # ILS 36 = AUD 15
    assert rels["Art Of Camouflage"].price_kind == "paid"         # EUR 6 = AUD 10


def test_threshold_is_configurable():
    rels = by_title(parse_discover(load(), "psytrance", RATES, threshold=12.0))
    assert rels["Art Of Camouflage"].price_kind == "cheap"


def test_free_download_flag_wins():
    data = load()
    item = copy.deepcopy(data["results"][3])  # a USD 9 album
    item["isFreeDownload"] = True
    rel = parse_discover({"results": [item]}, "goa-trance", RATES, 5.0)[0]
    assert rel.price_kind == "free"


def test_classify_unknown_currency_is_not_cheap():
    assert classify(False, 3.0, None, 5.0) == "paid"
