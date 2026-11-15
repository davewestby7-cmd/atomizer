"""Database tables (SQLite, via SQLModel)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select

from .config import ROOT


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Release(SQLModel, table=True):
    id: str = Field(primary_key=True)          # e.g. "ekto-globular-holobiont" or "bc-4146930237"
    source: str = Field(index=True)            # "ektoplazm" | "bandcamp"
    artist: str = ""
    title: str = ""
    label: str = ""
    tags: str = ""                             # comma separated, lower case
    cover_url: str = ""
    page_url: str = ""
    # "free" (free download), "nyp" (name your price), "cheap", "paid"
    price_kind: str = Field(default="free", index=True)
    price: float = 0.0                         # in the release's own currency
    currency: str = ""
    price_home: Optional[float] = None         # converted to your home currency
    stream_url: str = ""                       # first sample to play
    tracks_json: str = "[]"                    # JSON list of sample URLs
    download_mp3: str = ""
    download_flac: str = ""
    released: str = ""
    fetched_at: datetime = Field(default_factory=utcnow)
    pulled: bool = Field(default=False, index=True)
    local_path: str = ""
    pulled_at: Optional[datetime] = None

    @property
    def can_pull(self) -> bool:
        return bool(self.download_mp3 or self.download_flac)


class Meta(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str = ""


engine = create_engine(
    f"sqlite:///{ROOT / 'psypull.db'}", connect_args={"check_same_thread": False}
)


def init_db(eng=None) -> None:
    SQLModel.metadata.create_all(eng or engine)


def get_meta(session: Session, key: str, default: str = "") -> str:
    row = session.get(Meta, key)
    return row.value if row else default


def set_meta(session: Session, key: str, value: str) -> None:
    row = session.get(Meta, key) or Meta(key=key)
    row.value = value
    session.add(row)
    session.commit()


def upsert_release(session: Session, data: Release) -> None:
    """Insert or update a release, keeping its local 'pulled' state."""
    existing = session.get(Release, data.id)
    if existing is None:
        session.add(data)
        return
    keep = {"pulled", "local_path", "pulled_at"}
    for name in Release.model_fields:
        if name in keep or name == "id":
            continue
        setattr(existing, name, getattr(data, name))
    session.add(existing)


__all__ = ["Release", "Meta", "engine", "init_db", "get_meta", "set_meta",
           "upsert_release", "Session", "select", "utcnow"]
