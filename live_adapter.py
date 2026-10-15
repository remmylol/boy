"""Fail-closed PumpPortal Local Transaction adapter.

This module is an execution layer, NOT yet wired into bot.py's strategy loop.
No trade is sent unless LIVE_TRADING_ENABLED=true and execute_trade() is called.
Wallet secrets must be base58 private keys stored only in Railway Variables.
"""
from __future__ import annotations

import argparse
import base64
import os
import time
from typing import Any

import requests

PUMPPORTAL_LOCAL_URL = "https://pumpportal.fun/api/trade-local"
DEFAULT_RPC_TIMEOUT = 12


class LiveAdapterError(RuntimeError):
    pass


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _require_https_url(name: str, value: str) -> str:
    value = value.strip()
    if not value.startswith("https://"):
        raise LiveAdapterError(f"{name} must be an HTTPS URL")
    return value


def validate_trade(action: str, mint: str, amount: float | str,
                   denominated_in_sol: bool, slippage_pct: float,
                   priority_fee_sol: float, max_buy_sol: float) -> None:
    if action not in {"buy", "sell"}:
        raise LiveAdapterError("action must be 'buy' or 'sell'")
    if not isinstance(mint, str) or not mint.strip() or len(mint.strip()) > 64:
        raise LiveAdapterError("mint must be a non-empty token mint address")
    if not (0.1 <= float(slippage_pct) <= 5.0):
        raise LiveAdapterError("slippage must be between 0.1% and 5.0%")
    if not (0 <= float(priority_fee_sol) <= 0.0001):
        raise LiveAdapterError("priority fee must be between 0 and 0.0001 SOL")
    if action == "buy":
        try:
            value = float(amount)
        except (TypeError, ValueError) as exc:
            raise LiveAdapterError("buy amount must be SOL") from exc
        if not denominated_in_sol:
            raise LiveAdapterError("buys must be denominated in SOL")
        if value < 0.001 or value > max_buy_sol:
            raise LiveAdapterError(f"buy size must be between 0.001 and {max_buy_sol:g} SOL")
    else:
        if denominated_in_sol:
            raise LiveAdapterError("sells must be denominated in tokens, not SOL")
        if str(amount).strip() != "100%":
            raise LiveAdapterError("this adapter only supports selling 100% of the dedicated wallet's token balance")
    try:
        from solders.pubkey import Pubkey
        Pubkey.from_string(mint.strip())
    except Exception as exc:
        raise LiveAdapterError("mint is not a valid Solana public key") from exc


def _keypair():
    secret = os.getenv("BOT_PRIVATE_KEY", "").strip()
    if not secret:
        raise LiveAdapterError("BOT_PRIVATE_KEY is missing from environment")
    # Accept base58-encoded private key only; never print or log this value.
    try:
        from solders.keypair import Keypair
        return Keypair.from_base58_string(secret)
    except Exception as exc:
        raise LiveAdapterError("BOT_PRIVATE_KEY must be a valid base58 Solana private key") from exc


def _rpc_url() -> str:
    value = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com/").strip()
    return _require_https_url("SOLANA_RPC_URL", value)


def _rpc(method: str, params: list[Any], timeout: int = DEFAULT_RPC_TIMEOUT) -> Any:
    url = _rpc_url()
    try:
        response = requests.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        body = response.json()
    except Exception as exc:
        raise LiveAdapterError(f"RPC request failed for {method}: {type(exc).__name__}") from exc
    if body.get("error"):
        # Do not print the full RPC URL; it may contain a private provider token.
        raise LiveAdapterError(f"RPC {method} returned an error: {body['error'].get('message', 'unknown error')}")
    if "result" not in body:
        raise LiveAdapterError(f"RPC {method} returned no result")
    return body["result"]


def check_wallet() -> dict[str, Any]:
    """Read-only check: loads signer and reads its SOL balance; never sends a tx."""
    keypair = _keypair()
    pubkey = str(keypair.pubkey())
    result = _rpc("getBalance", [pubkey, {"commitment": "confirmed"}])
    lamports = int(result["value"])
    return {"public_key": pubkey, "balance_sol": lamports / 1_000_000_000}


def execute_trade(action: str, mint: str, amount: float | str,
                  denominated_in_sol: bool, slippage_pct: float | None = None,
                  priority_fee_sol: float | None = None, pool: str = "auto") -> str:
    """Submit one explicitly requested trade and return its confirmed signature.

    This is not connected to the bot's scanner/position manager yet. A caller must
    reconcile token balances and position state before calling it from a strategy.
    """
    if not _env_bool("LIVE_TRADING_ENABLED", False):
        raise LiveAdapterError("LIVE_TRADING_ENABLED is not true; refusing to submit a transaction")
    keypair = _keypair()
    rpc_url = _rpc_url()  # validate configuration before requesting a transaction
    max_buy_sol = float(os.getenv("MAX_BUY_SOL", "0.15"))
    slippage = float(slippage_pct if slippage_pct is not None else os.getenv("LIVE_SLIPPAGE_PCT", "3.0"))
    priority = float(priority_fee_sol if priority_fee_sol is not None else os.getenv("LIVE_PRIORITY_FEE_SOL", "0.00005"))
    validate_trade(action, mint, amount, denominated_in_sol, slippage, priority, max_buy_sol)
    allowed_pools = {"auto", "pump", "pump-amm", "raydium", "raydium-cpmm", "launchlab", "bonk"}
    if pool not in allowed_pools:
        raise LiveAdapterError("unsupported pool")

    payload = {
        "publicKey": str(keypair.pubkey()),
        "action": action,
        "mint": mint.strip(),
        "amount": amount,
        "denominatedInSol": "true" if denominated_in_sol else "false",
        "slippage": slippage,
        "priorityFee": priority,
        "pool": pool,
    }
    try:
        response = requests.post(PUMPPORTAL_LOCAL_URL, data=payload, timeout=20)
    except Exception as exc:
        raise LiveAdapterError(f"PumpPortal transaction request failed: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise LiveAdapterError(f"PumpPortal rejected transaction request (HTTP {response.status_code})")
    raw_tx = response.content
    if not raw_tx or raw_tx.lstrip().startswith(b"{"):
        raise LiveAdapterError("PumpPortal did not return a serialized transaction")

    try:
        from solders.transaction import VersionedTransaction
        unsigned = VersionedTransaction.from_bytes(raw_tx)
        message = unsigned.message
        signer_count = int(message.header.num_required_signatures)
        required_signers = list(message.account_keys[:signer_count])
        if not required_signers or required_signers[0] != keypair.pubkey():
            raise LiveAdapterError("transaction fee payer is not the configured bot wallet")
        if keypair.pubkey() not in required_signers:
            raise LiveAdapterError("configured bot wallet is not a required transaction signer")
        signed = VersionedTransaction(message, [keypair])
        encoded = base64.b64encode(bytes(signed)).decode("ascii")
    except LiveAdapterError:
        raise
    except Exception as exc:
        raise LiveAdapterError(f"could not validate/sign transaction: {type(exc).__name__}") from exc

    # A send timeout is ambiguous. Never auto-retry; a retry could duplicate a buy.
    try:
        response = requests.post(
            rpc_url,
            json={"jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
                  "params": [encoded, {"encoding": "base64", "skipPreflight": False,
                                        "preflightCommitment": "confirmed", "maxRetries": 0}]},
            timeout=20,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        body = response.json()
    except Exception as exc:
        raise LiveAdapterError(
            "RPC send result is uncertain; check wallet and signature history before any retry. "
            f"Error type: {type(exc).__name__}"
        ) from exc
    if body.get("error"):
        raise LiveAdapterError(f"RPC rejected transaction: {body['error'].get('message', 'unknown error')}")
    signature = body.get("result")
    if not isinstance(signature, str) or not signature:
        raise LiveAdapterError("RPC returned no transaction signature; do not retry blindly")

    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        statuses = _rpc("getSignatureStatuses", [[signature], {"searchTransactionHistory": True}])
        status = (statuses.get("value") or [None])[0]
        if status:
            if status.get("err") is not None:
                raise LiveAdapterError(f"transaction failed on-chain; signature={signature}")
            if status.get("confirmationStatus") in {"confirmed", "finalized"}:
                return signature
        time.sleep(2)
    raise LiveAdapterError(
        f"transaction submitted but confirmation timed out; signature={signature}. "
        "Check explorer/wallet and do not submit the same trade again blindly."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only wallet check for the PumpPortal local adapter")
    parser.add_argument("--check-wallet", action="store_true", help="read wallet public address and SOL balance; sends no transaction")
    args = parser.parse_args()
    if not args.check_wallet:
        parser.error("only --check-wallet is exposed as a CLI command; trade execution must be explicitly integrated and reviewed")
    try:
        result = check_wallet()
    except LiveAdapterError as exc:
        print(f"CHECK FAILED: {exc}")
        return 1
    print(f"Wallet: {result['public_key']}")
    print(f"SOL balance: {result['balance_sol']:.6f}")
    print("Read-only check passed; no transaction was sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
