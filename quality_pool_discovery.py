"""Conservative, independent GeckoTerminal Solana pool discovery.

Discovery hints only: execution eligibility is ALWAYS rechecked with DexScreener.
"""
from __future__ import annotations
import math
from typing import Any


def _number(value: Any) -> float:
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def _token_address(rel: dict, included: dict[str, dict]) -> str:
    record = (rel or {}).get("data") or {}
    token = included.get(record.get("id"), {})
    address = (token.get("attributes") or {}).get("address")
    if isinstance(address, str) and address:
        return address
    identifier = record.get("id", "")
    return identifier[len("solana_"):] if isinstance(identifier, str) and identifier.startswith("solana_") else ""


def extract_quality_pool_mints(payload: dict, *, sol_mint: str,
                               supported_dexes: frozenset[str],
                               min_liquidity_usd: float,
                               min_volume_1h_usd: float) -> dict[str, float]:
    """Select SOL-quoted, supported-DEX, priced liquid pools, by base mint.

    Never assume symbols are authoritative; compare the exact SOL mint.
    Some GeckoTerminal DEX ids have a `solana_` prefix. Unknowns fail closed.
    """
    if not isinstance(payload, dict):
        return {}
    included = {i.get("id"): i for i in payload.get("included", [])
                if isinstance(i, dict) and isinstance(i.get("id"), str)}
    results: dict[str, float] = {}
    for pool in payload.get("data", []):
        if not isinstance(pool, dict):
            continue
        attr = pool.get("attributes") or {}
        rel = pool.get("relationships") or {}
        dex_rec = ((rel.get("dex") or {}).get("data") or {})
        dex = str(dex_rec.get("id", "")).lower()
        if dex.startswith("solana_"):
            dex = dex[7:]
        # GeckoTerminal may use e.g. pump_swap; normalize punctuation only.
        dex = dex.replace("_", "").replace("-", "")
        if dex not in supported_dexes:
            continue
        base = _token_address(rel.get("base_token"), included)
        quote = _token_address(rel.get("quote_token"), included)
        if not base or base == sol_mint or quote != sol_mint:
            continue
        liq = _number(attr.get("reserve_in_usd"))
        v1h = _number((attr.get("volume_usd") or {}).get("h1"))
        price = _number(attr.get("base_token_price_usd"))
        if liq < min_liquidity_usd or v1h < min_volume_1h_usd or price <= 0:
            continue
        score = min(liq, 250000.0) + 2.0 * min(v1h, 250000.0)
        results[base] = max(score, results.get(base, 0.0))
    return results
