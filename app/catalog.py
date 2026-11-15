"""The catalogue file: every release's details in data/catalog.csv.

Reading thousands of release pages takes a long time, so after each refresh
Atomizer saves everything it knows to this spreadsheet-friendly file (it opens
in Excel or Google Sheets). It is committed to the repo, so a fresh copy of
Atomizer loads it on first start instead of reading every page again; later
refreshes then only read releases that are new.

Your own state (what you pulled, where it's saved) is never written here.

Run by hand:
    python -m app.catalog export      # database -> data/catalog.csv
    python -m app.catalog import      # data/catalog.csv -> database
"""
from __future__ import annotations

import csv
import logging
import sys
from pathlib import Path

from sqlmodel import Session, select

from .config import ROOT
from .db import Release, engine, init_db

CATALOG = ROOT / "data" / "catalog.csv"
# Columns saved, in order. Personal state (pulled, local_path, pulled_at) is left out.
FIELDS = ["id", "source", "artist", "title", "label", "tags", "origin", "kind", "released",
          "price_kind", "price", "currency", "price_home", "cover_url", "page_url",
          "stream_url", "tracks_json", "download_mp3", "download_flac"]
log = logging.getLogger(__name__)


def export_catalog(path: Path = CATALOG, eng=None) -> int:
    """Write every release to the CSV, sorted so changes show up as small diffs."""
    with Session(eng or engine) as s:
        rows = s.exec(select(Release)).all()
    rows.sort(key=lambda r: (r.source, r.id))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(FIELDS)
        for r in rows:
            w.writerow(["" if getattr(r, k) is None else getattr(r, k) for k in FIELDS])
    tmp.replace(path)
    return len(rows)


def _convert(field: str, value: str):
    if field == "price":
        return float(value or 0)
    if field == "price_home":
        return float(value) if value != "" else None
    return value


def import_catalog(path: Path = CATALOG, eng=None) -> int:
    """Add releases from the CSV that the database doesn't have yet. Returns how many."""
    if not path.exists():
        return 0
    added = 0
    with open(path, newline="", encoding="utf-8") as f, Session(eng or engine) as s:
        have = set(s.exec(select(Release.id)).all())
        for row in csv.DictReader(f):
            if not row.get("id") or row["id"] in have:
                continue
            data = {k: _convert(k, row.get(k, "")) for k in FIELDS if k in row}
            s.add(Release(**data))
            have.add(row["id"])
            added += 1
        s.commit()
    return added


if __name__ == "__main__":
    init_db()
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "export":
        print(f"Saved {export_catalog()} releases to {CATALOG}")
    elif cmd == "import":
        print(f"Added {import_catalog()} releases from {CATALOG}")
    else:
        print(__doc__)
