"""Currency conversion to your home currency.

Uses the free open.er-api.com rates (no key needed). If that can't be reached,
falls back to rough built-in rates so the Cheap tab still works.
"""
from __future__ import annotations

import time

import httpx

# Rough rates: 1 unit of the currency = this many AUD. Only used when offline.
FALLBACK_TO_AUD = {
    "AUD": 1.0, "USD": 1.53, "EUR": 1.66, "GBP": 1.95, "CAD": 1.10, "NZD": 0.90,
    "JPY": 0.0100, "ILS": 0.41, "CHF": 1.75, "SEK": 0.145, "NOK": 0.14, "DKK": 0.22,
    "PLN": 0.38, "CZK": 0.066, "HUF": 0.0042, "MXN": 0.080, "BRL": 0.28, "INR": 0.018,
    "ZAR": 0.085, "RUB": 0.016, "UAH": 0.037,
}

_cache: dict[str, tuple[float, dict[str, float]]] = {}


def _fallback(home: str) -> dict[str, float]:
    """Rates as 'units of currency per 1 home' (same shape as the API)."""
    home_in_aud = FALLBACK_TO_AUD.get(home, 1.0)
    return {cur: home_in_aud / aud for cur, aud in FALLBACK_TO_AUD.items()}


async def get_rates(home: str) -> dict[str, float]:
    cached = _cache.get(home)
    if cached and time.time() - cached[0] < 12 * 3600:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"https://open.er-api.com/v6/latest/{home}")
            r.raise_for_status()
            rates = {k.upper(): float(v) for k, v in r.json()["rates"].items()}
    except (httpx.HTTPError, KeyError, ValueError):
        rates = _fallback(home)
    _cache[home] = (time.time(), rates)
    return rates


def convert(amount: float, currency: str, rates: dict[str, float]) -> float | None:
    """Convert `amount` of `currency` into the home currency the rates are based on."""
    per_home = rates.get((currency or "").upper())
    if not per_home:
        return None
    return round(amount / per_home, 2)
