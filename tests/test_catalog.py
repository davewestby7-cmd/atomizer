import csv
import json

from sqlmodel import Session, create_engine, select

from app.catalog import FIELDS, export_catalog, import_catalog
from app.db import Release, init_db, utcnow


def engine_with(*releases):
    eng = create_engine("sqlite://")
    init_db(eng)
    with Session(eng) as s:
        for r in releases:
            s.add(r)
        s.commit()
    return eng


def sample(**kw):
    base = dict(id="ekto-x", source="ektoplazm", artist="Artcore", title="Tea Party Valley",
                label="Ektoplazm", tags="full-on,israel", origin="Israel", released="2017-03-01",
                price_kind="free", price=0.0, price_home=0.0,
                tracks_json=json.dumps(["https://ektoplazm.com/audio/a.mp3"]),
                download_mp3="https://ektoplazm.com/files/a.zip")
    base.update(kw)
    return Release(**base)


def test_round_trip_keeps_details_but_not_personal_state(tmp_path):
    path = tmp_path / "catalog.csv"
    src = engine_with(
        sample(pulled=True, local_path="C:/Music/x", pulled_at=utcnow()),
        sample(id="bcl-z-a1", source="bclabels", title="Paid one", price_kind="paid",
               price=6.0, currency="EUR", price_home=10.0, download_mp3=""),
        sample(id="bc-a2", source="bandcamp", price_home=None, price_kind="paid"),
    )
    assert export_catalog(path, src) == 3

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0].keys()) == FIELDS
    assert "local_path" not in rows[0] and "pulled" not in rows[0]
    assert [r["id"] for r in rows] == ["bc-a2", "bcl-z-a1", "ekto-x"]   # sorted

    fresh = engine_with()
    assert import_catalog(path, fresh) == 3
    with Session(fresh) as s:
        got = {r.id: r for r in s.exec(select(Release)).all()}
    e = got["ekto-x"]
    assert (e.artist, e.title, e.origin, e.tags) == ("Artcore", "Tea Party Valley", "Israel",
                                                    "full-on,israel")
    assert json.loads(e.tracks_json) == ["https://ektoplazm.com/audio/a.mp3"]
    assert e.can_pull and e.pulled is False and e.local_path == ""
    assert got["bcl-z-a1"].price == 6.0 and got["bcl-z-a1"].price_home == 10.0
    assert got["bc-a2"].price_home is None


def test_import_never_overwrites_existing_rows(tmp_path):
    path = tmp_path / "catalog.csv"
    export_catalog(path, engine_with(sample(title="From file")))
    db = engine_with(sample(title="Already here", pulled=True))
    assert import_catalog(path, db) == 0
    with Session(db) as s:
        r = s.get(Release, "ekto-x")
        assert r.title == "Already here" and r.pulled is True


def test_missing_file_is_fine(tmp_path):
    assert import_catalog(tmp_path / "nope.csv", engine_with()) == 0
