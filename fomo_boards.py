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


def inspect_fomo_board(payload: Any, *, limit: int = 50) -> tuple[list[str], dict[str, int | str]]:
    """Inspect a FOMO response locally, without network calls or sensitive logging.

    Only explicit Solana-labelled addresses are admitted. Diagnostics contain
    integer counts and fixed-shape labels, never token contents or credentials.
    """
    stats: dict[str, int | str] = {
        "records": 0, "solana_rows": 0, "valid_mints": 0,
        "non_solana": 0, "missing_network": 0,
        "missing_address": 0, "invalid_address": 0, "duplicates": 0,
        "malformed_rows": 0, "status": "ok",
    }
    if not isinstance(payload, dict):
        stats["status"] = "invalid_root"
        return [], stats
    if payload.get("available") is False:
        stats["status"] = "unavailable"
        return [], stats
    if payload.get("stale") is True or payload.get("source") == "captured":
        stats["status"] = "stale_or_captured"
        return [], stats
    rows = payload.get("tokens")
    # Some API gateways wrap the documented board response under `data`.
    if not isinstance(rows, list):
        data = payload.get("data")
        if isinstance(data, dict):
            rows = data.get("tokens")
        elif isinstance(data, list):
            rows = data
    if not isinstance(rows, list):
        stats["status"] = "missing_tokens_list"
        return [], stats
    stats["records"] = len(rows)
    if limit <= 0:
        stats["status"] = "zero_limit"
        return [], stats
    results: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            stats["malformed_rows"] += 1
            continue
        token = row.get("token")
        if not isinstance(token, dict):
            token = row
        network = row.get("network") or row.get("chain") or token.get("network") or token.get("chain")
        if network is None:
            stats["missing_network"] += 1
            continue
        if not isinstance(network, str) or network.strip().lower() not in ("sol", "solana", "solana-mainnet", "solana_mainnet"):
            stats["non_solana"] += 1
            continue
        stats["solana_rows"] += 1
        address = token.get("address") or token.get("mint")
        if not address:
            stats["missing_address"] += 1
        elif not is_solana_mint(address):
            stats["invalid_address"] += 1
        elif address in seen:
            stats["duplicates"] += 1
        else:
            seen.add(address)
            results.append(address)
            if len(results) >= limit:
                break
    stats["valid_mints"] = len(results)
    return results, stats


def extract_fomo_mints(payload: Any, *, limit: int = 50) -> list[str]:
    """Extract verified-format Solana mints from a FOMO token board."""
    return inspect_fomo_board(payload, limit=limit)[0]
