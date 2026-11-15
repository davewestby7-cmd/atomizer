"""A 'polite' web client: obeys robots.txt and waits between requests to the same site.

Python's built-in robotparser doesn't understand wildcards (*, $) or the
"longest rule wins" convention that sites like Bandcamp rely on, so we use a
small parser of our own.
"""
from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

USER_AGENT = "Atomizer/0.1 (personal free-music finder)"
MIN_DELAY_SECONDS = 1.0


class RobotsDisallowed(Exception):
    pass


@dataclass
class Robots:
    # (allow?, pattern) pairs that apply to us (the "*" group)
    rules: list[tuple[bool, str]] = field(default_factory=list)

    @classmethod
    def parse(cls, text: str, agent: str = "atomizer") -> "Robots":
        groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
        agents: list[str] = []
        rules: list[tuple[bool, str]] = []
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (p.strip() for p in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if not last_was_agent and (agents or rules):
                    groups.append((agents, rules))
                    agents, rules = [], []
                agents.append(value.lower())
                last_was_agent = True
            elif key in ("allow", "disallow"):
                last_was_agent = False
                if value:
                    rules.append((key == "allow", value))
            else:
                last_was_agent = False
        if agents or rules:
            groups.append((agents, rules))

        mine = [r for a, r in groups if any(x != "*" and x in agent.lower() for x in a)]
        chosen = mine or [r for a, r in groups if "*" in a]
        return cls(rules=[rule for g in chosen for rule in g])

    @staticmethod
    def _matches(pattern: str, path: str) -> bool:
        regex = "^" + re.escape(pattern).replace(r"\*", ".*")
        if regex.endswith(r"\$"):
            regex = regex[:-2] + "$"
        return re.match(regex, path) is not None

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query
        best: tuple[int, bool] | None = None
        for allow, pattern in self.rules:
            if self._matches(pattern, path):
                score = (len(pattern), allow)  # longest wins; on a tie, allow wins
                if best is None or score > best:
                    best = score
        return True if best is None else best[1]


class PoliteClient:
    def __init__(self, delay: float = MIN_DELAY_SECONDS):
        self.delay = delay
        self._robots: dict[str, Robots] = {}
        self._last_hit: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self.client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=30
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def _robots_for(self, url: str) -> Robots:
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            try:
                await self._wait(parts.netloc)
                r = await self.client.get(host + "/robots.txt")
                self._robots[host] = Robots.parse(r.text if r.status_code == 200 else "")
            except httpx.HTTPError:
                self._robots[host] = Robots()
        return self._robots[host]

    async def _wait(self, netloc: str) -> None:
        async with self._lock:
            gap = time.monotonic() - self._last_hit.get(netloc, 0)
            if gap < self.delay:
                await asyncio.sleep(self.delay - gap)
            self._last_hit[netloc] = time.monotonic()

    async def request(self, method: str, url: str, **kw) -> httpx.Response:
        if not (await self._robots_for(url)).allowed(url):
            raise RobotsDisallowed(url)
        await self._wait(urlsplit(url).netloc)
        r = await self.client.request(method, url, **kw)
        r.raise_for_status()
        return r

    async def get(self, url: str, **kw) -> httpx.Response:
        return await self.request("GET", url, **kw)

    async def post(self, url: str, **kw) -> httpx.Response:
        return await self.request("POST", url, **kw)
