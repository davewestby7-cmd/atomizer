"""Loads config.yaml (falling back to config.example.yaml) into a simple object."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    download_dir: Path
    download_format: str = "mp3"
    home_currency: str = "AUD"
    cheap_threshold: float = 5.0
    refresh_hours: float = 6
    rclone_remote: str = ""
    rclone_mode: str = "copy"
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)

    def source(self, name: str) -> dict[str, Any]:
        return self.sources.get(name) or {}


def load_settings(path: Path | None = None) -> Settings:
    if path is None:
        path = ROOT / "config.yaml"
        if not path.exists():
            path = ROOT / "config.example.yaml"
    raw: dict[str, Any] = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    dl = Path(raw.get("download_dir") or "downloads")
    if not dl.is_absolute():
        dl = ROOT / dl
    return Settings(
        download_dir=dl,
        download_format=str(raw.get("download_format", "mp3")).lower(),
        home_currency=str(raw.get("home_currency", "AUD")).upper(),
        cheap_threshold=float(raw.get("cheap_threshold", 5.0)),
        refresh_hours=float(raw.get("refresh_hours", 6)),
        rclone_remote=str(raw.get("rclone_remote") or ""),
        rclone_mode=str(raw.get("rclone_mode", "copy")).lower(),
        sources=raw.get("sources") or {},
    )
