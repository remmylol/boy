"""Optional, read-only FOMO Family token board discovery.

Unaffiliated API: https://fomoapi.io/docs. Responses are hints, never trusted
as pool/route/liquidity or sell-execution evidence.
"""
from __future__ import annotations

from typing import Any

BASE_URL = "https://api.fomoapi.io"
BOARDS = ("graduated", "trending")
_BASE58 = frozenset("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")


def is_solana_mint(address: object) -> bool:
    return isinstance(address, str) and 32 <= len(address) <= 44 and all(c in _BASE58 for c in address)


def extract_fomo_mints(payload: Any, *, limit: int = 50) -> list[str]:
    """Accept only explicitly Solana-identified token rows from FOMO token boards.

    The response is {board,capturedAt,count,tokens:[{token:{address},network,...}]}.
    Missing/unknown network information must fail closed, not silently admit EVM.
    """
    if not isinstance(payload, dict) or payload.get("available") is False or payload.get("stale") is True:
        return []
    rows = payload.get("tokens")
    if not isinstance(rows, list) or limit <= 0:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        token = row.get("token")
        if not isinstance(token, dict):
            continue
        network = row.get("network", token.get("network"))
        if not isinstance(network, str) or network.lower() not in ("sol", "solana"):
            continue
        address = token.get("address")
        if not is_solana_mint(address) or address in seen:
            continue
        seen.add(address)
        result.append(address)
        if len(result) >= limit:
            break
    return result
