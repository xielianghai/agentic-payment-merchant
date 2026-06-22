"""USD → SepoliaETH (wei) conversion using a live ETH/USD quote."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

_price_cache: tuple[float, float] | None = None
_CACHE_TTL_SECONDS = 60


def fetch_eth_usd_price(*, force_refresh: bool = False) -> float:
  """Return ETH/USD; cache ~60s; fallback to env or last good price."""
  global _price_cache
  now = time.time()
  if not force_refresh and _price_cache and now - _price_cache[1] < _CACHE_TTL_SECONDS:
    return _price_cache[0]

  fallback = float(os.environ.get("X402_ETH_USD_FALLBACK", "2500"))
  url = os.environ.get(
      "X402_ETH_USD_PRICE_URL",
      "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
  )
  try:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as resp:
      data = json.loads(resp.read().decode("utf-8"))
    price = float(data["ethereum"]["usd"])
    if price <= 0:
      raise ValueError(f"invalid eth/usd price: {price}")
    _price_cache = (price, now)
    return price
  except (urllib.error.URLError, TimeoutError, ValueError, KeyError, TypeError):
    if _price_cache:
      return _price_cache[0]
    return fallback


def usd_cents_to_wei(
    amount_cents: int,
    *,
    eth_usd: float | None = None,
) -> tuple[int, float]:
  """Convert USD cents to wei at the given or fetched ETH/USD rate."""
  cents = int(amount_cents)
  if cents < 0:
    raise ValueError("amount_cents must be non-negative")
  rate = eth_usd if eth_usd is not None else fetch_eth_usd_price()
  if rate <= 0:
    raise ValueError("eth_usd rate must be positive")
  usd = cents / 100.0
  eth = usd / rate
  wei = int(eth * 10**18)
  if wei <= 0 and cents > 0:
    wei = 1
  return wei, rate


def format_eth_from_wei(wei: int, *, max_decimals: int = 8) -> str:
  """Human-readable ETH amount without trailing zeros."""
  if wei <= 0:
    return "0"
  eth = wei / 10**18
  text = f"{eth:.{max_decimals}f}"
  return text.rstrip("0").rstrip(".") or "0"
