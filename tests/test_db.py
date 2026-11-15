from pathlib import Path

from sqlmodel import Session, create_engine

from app.db import Release, init_db, select, upsert_release
from app.sources.ektoplazm import parse_listing

FIX = Path(__file__).parent / "fixtures"


def test_upsert_keeps_pulled_state():
    eng = create_engine("sqlite://")
    init_db(eng)
    rels = parse_listing((FIX / "ektoplazm_home.html").read_text(encoding="utf-8"))
    first_id = rels[0].id
    with Session(eng) as s:
        for r in rels:
            upsert_release(s, r)
        s.commit()
        first = s.get(Release, first_id)
        first.pulled, first.local_path = True, "downloads/x"
        s.add(first)
        s.commit()

    again = parse_listing((FIX / "ektoplazm_home.html").read_text(encoding="utf-8"))
    with Session(eng) as s:
        for r in again:
            upsert_release(s, r)
        s.commit()
        assert len(s.exec(select(Release)).all()) == 6
        assert s.get(Release, first_id).pulled is True
