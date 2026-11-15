"""Atomizer web app. Run with:  uvicorn app.main:app"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import col, or_

from . import downloader
from .config import ROOT, load_settings
from .db import Release, Session, engine, get_meta, init_db, select, set_meta, upsert_release, utcnow
from .polite import PoliteClient
from .sources import SOURCES
from .sync import run_sync, sync_state

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("atomizer")

settings = load_settings()
state = {"refreshing": False, "last_errors": {}, "pulling": set()}
scheduler = AsyncIOScheduler()


# ---------------------------------------------------------------- refresh

async def refresh(force: bool = False) -> None:
    if state["refreshing"]:
        return
    with Session(engine) as s:
        last = get_meta(s, "last_refresh")
    if not force and last:
        age = utcnow() - datetime.fromisoformat(last)
        if age < timedelta(hours=settings.refresh_hours):
            log.info("Sources were checked %s ago; using the cache.", age)
            return

    state["refreshing"] = True
    state["last_errors"] = {}
    client = PoliteClient()
    try:
        for name, module in SOURCES.items():
            if not settings.source(name).get("enabled", True):
                continue
            started = utcnow()
            try:
                releases = await module.fetch(client, settings)
                log.info("%s: %d releases", name, len(releases))
                _save(name, releases, started)
            except Exception as e:  # one broken source shouldn't stop the others
                log.exception("Source %s failed", name)
                state["last_errors"][name] = str(e)
        with Session(engine) as s:
            set_meta(s, "last_refresh", utcnow().isoformat())
    except Exception:
        log.exception("Refresh failed")
    finally:
        await client.close()
        state["refreshing"] = False


def _save(source: str, releases: list[Release], started) -> None:
    with Session(engine) as s:
        for rel in releases:
            rel.fetched_at = utcnow()
            upsert_release(s, rel)
        s.commit()
        if releases:  # forget old, un-pulled releases that have dropped off the source
            stale = s.exec(select(Release).where(
                Release.source == source, Release.pulled == False,  # noqa: E712
                Release.fetched_at < started)).all()
            for r in stale:
                s.delete(r)
            s.commit()


# ---------------------------------------------------------------- app

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    scheduler.add_job(refresh, "interval", hours=settings.refresh_hours, id="refresh")
    scheduler.start()
    task = asyncio.create_task(refresh())  # uses the cache if it's fresh
    yield
    scheduler.shutdown(wait=False)
    task.cancel()


app = FastAPI(title="Atomizer", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT / "static" / "index.html")


def _to_json(r: Release) -> dict:
    d = r.model_dump()
    d["tracks"] = json.loads(r.tracks_json or "[]")
    d["tags"] = [t for t in r.tags.split(",") if t]
    d["can_pull"] = r.can_pull
    d["pulling"] = r.id in state["pulling"]
    del d["tracks_json"]
    return d


@app.get("/api/releases")
def releases(bucket: str = "free", q: str = "", tag: str = "", source: str = ""):
    stmt = select(Release)
    if bucket == "pulled":
        stmt = stmt.where(Release.pulled == True).order_by(col(Release.pulled_at).desc())  # noqa: E712
    elif bucket == "cheap":
        stmt = stmt.where(Release.price_kind == "cheap").order_by(col(Release.price_home))
    else:
        stmt = stmt.where(col(Release.price_kind).in_(["free", "nyp"])) \
                   .order_by(col(Release.released).desc())
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(col(Release.artist).ilike(like), col(Release.title).ilike(like),
                              col(Release.label).ilike(like)))
    if tag:
        stmt = stmt.where(col(Release.tags).ilike(f"%{tag}%"))
    if source:
        stmt = stmt.where(Release.source == source)
    with Session(engine) as s:
        return [_to_json(r) for r in s.exec(stmt.limit(600)).all()]


@app.get("/api/status")
def status():
    with Session(engine) as s:
        rows = s.exec(select(Release)).all()
        last_refresh = get_meta(s, "last_refresh")
        last_sync = get_meta(s, "last_sync")
        last_sync_ok = get_meta(s, "last_sync_ok")
    counts = Counter()
    tags = Counter()
    for r in rows:
        counts["pulled"] += r.pulled
        counts["cheap" if r.price_kind == "cheap" else "free"] += r.price_kind != "paid"
        tags.update(t for t in r.tags.split(",") if t)
    return {
        "refreshing": state["refreshing"],
        "errors": state["last_errors"],
        "last_refresh": last_refresh,
        "last_sync": last_sync,
        "last_sync_ok": last_sync_ok == "1",
        "sync_state": sync_state(settings),
        "rclone_remote": settings.rclone_remote,
        "download_dir": str(settings.download_dir),
        "download_bytes": downloader.folder_size(settings.download_dir),
        "counts": counts,
        "tags": [t for t, _ in tags.most_common(16)],
        "home_currency": settings.home_currency,
        "cheap_threshold": settings.cheap_threshold,
    }


@app.post("/api/refresh")
async def refresh_now():
    if not state["refreshing"]:
        asyncio.create_task(refresh(force=True))
    return {"started": True}


@app.post("/api/sync")
async def sync_now():
    ok, output = await run_sync(settings)
    if ok or output not in ("no-rclone", "no-remote"):
        with Session(engine) as s:
            set_meta(s, "last_sync", utcnow().isoformat())
            set_meta(s, "last_sync_ok", "1" if ok else "0")
    return {"ok": ok, "output": output}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/api/pull/{release_id}")
async def pull(release_id: str):
    with Session(engine) as s:
        rel = s.get(Release, release_id)
    if rel is None:
        raise HTTPException(404, "Release not found")
    fmt = settings.download_format
    url = (rel.download_flac if fmt == "flac" else rel.download_mp3) \
        or rel.download_mp3 or rel.download_flac
    if not url:
        raise HTTPException(400, "This release can't be pulled directly; open its page instead.")
    if release_id in state["pulling"]:
        raise HTTPException(409, "Already pulling this one")

    dest = downloader.release_folder(settings.download_dir, rel.artist, rel.title)

    async def events():
        state["pulling"].add(release_id)
        try:
            async for ev in downloader.pull(url, dest):
                if ev["stage"] == "done":
                    with Session(engine) as s:
                        r = s.get(Release, release_id)
                        r.pulled, r.local_path, r.pulled_at = True, str(dest), utcnow()
                        s.add(r)
                        s.commit()
                yield _sse(ev)
        except Exception as e:
            log.exception("Pull failed")
            yield _sse({"stage": "error", "message": str(e)})
        finally:
            state["pulling"].discard(release_id)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache"})


def _inside_downloads(path: Path) -> bool:
    root = settings.download_dir.resolve()
    return root in path.resolve().parents


@app.delete("/api/pulled/{release_id}")
def delete_pulled(release_id: str):
    with Session(engine) as s:
        rel = s.get(Release, release_id)
        if rel is None:
            raise HTTPException(404, "Release not found")
        if rel.local_path:
            p = Path(rel.local_path)
            if p.exists() and _inside_downloads(p):
                shutil.rmtree(downloader._long(p))
        rel.pulled, rel.local_path, rel.pulled_at = False, "", None
        s.add(rel)
        s.commit()
    return {"ok": True}


@app.post("/api/open-folder")
def open_folder(release_id: str = ""):
    """Open the downloads folder (or one release's folder) in Explorer/Finder."""
    path = settings.download_dir
    if release_id:
        with Session(engine) as s:
            rel = s.get(Release, release_id)
        if rel and rel.local_path and Path(rel.local_path).exists() \
                and _inside_downloads(Path(rel.local_path)):
            path = Path(rel.local_path)
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
    return {"ok": True, "path": str(path)}
