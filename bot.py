import json
import re
import logging
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any
from collections import Counter, OrderedDict
import threading
from pump_curve_market import lookup_curve
from curve_paper import buy_quote, sell_quote
from curve_activity import CurveActivity
from curve_rpc_activity import RpcCurveTradeTracker, ReadOnlySolanaRPC
from live_execution import execute_buy, execute_sell
print("EXECUTION BRIDGE LOADED - preview only, live trading disabled", flush=True)

import requests
from dotenv import load_dotenv

load_dotenv()

# ---- Configuration ----
STARTING_CAPITAL = float(os.getenv("STARTING_CAPITAL_USD", "36"))
PAPER_MODE = os.getenv("PAPER_MODE", "true").lower() == "true"
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL_SECONDS", "5"))
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "2"))
POSITION_SIZE_USD = float(os.getenv("POSITION_SIZE_USD", "15"))  # Fixed paper position size in USD
MAX_DAILY_LOSS_FRACTION = float(os.getenv("MAX_DAILY_LOSS_FRACTION", "0.5"))
TAKE_PROFIT = float(os.getenv("TAKE_PROFIT_PCT", "0.20"))
STOP_LOSS = float(os.getenv("STOP_LOSS_PCT", "0.30"))
TRAILING_STOP_ENABLED = os.getenv("TRAILING_STOP_ENABLED", "false").lower() == "true"
TRAILING_STOP = float(os.getenv("TRAILING_STOP_PCT", "0.15"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "75"))
MIN_LIQUIDITY_USD = float(os.getenv("MIN_LIQUIDITY_USD", "5000"))
MIN_SOL_PAIR_LIQUIDITY_USD = max(5000.0, float(os.getenv("MIN_SOL_PAIR_LIQUIDITY_USD", "5000")))
MIN_VOLUME_5M_USD = float(os.getenv("MIN_VOLUME_5M_USD", "1000"))
MAX_PAIR_AGE_HOURS = float(os.getenv("MAX_PAIR_AGE_HOURS", "6"))
MIN_PAIR_AGE_MINUTES = float(os.getenv("MIN_PAIR_AGE_MINUTES", "5"))
FAST_MOMENTUM_ENABLED = os.getenv("FAST_MOMENTUM_ENABLED", "true").lower() == "true"
MOMENTUM_MIN_VOLUME_5M_USD = float(os.getenv("MOMENTUM_MIN_VOLUME_5M_USD", "5000"))
MOMENTUM_MIN_CHANGE_5M_PCT = float(os.getenv("MOMENTUM_MIN_CHANGE_5M_PCT", "3"))
MOMENTUM_MAX_CHANGE_5M_PCT = float(os.getenv("MOMENTUM_MAX_CHANGE_5M_PCT", "15"))
MOMENTUM_MIN_TXNS_5M = int(os.getenv("MOMENTUM_MIN_TXNS_5M", "40"))
MOMENTUM_MIN_BUY_SELL_RATIO = float(os.getenv("MOMENTUM_MIN_BUY_SELL_RATIO", "1.5"))
MOMENTUM_MIN_VOLUME_LIQUIDITY_RATIO = float(os.getenv("MOMENTUM_MIN_VOLUME_LIQUIDITY_RATIO", "0.15"))
MAX_HOLD_MINUTES = float(os.getenv("MAX_HOLD_MINUTES", "5"))
MAX_SLIPPAGE_BPS = int(os.getenv("MAX_SLIPPAGE_BPS", "150"))
MAX_STALE_PRICE_SECONDS = int(os.getenv("MAX_STALE_PRICE_SECONDS", "60"))
# Fee/slippage haircut used for paper-trade estimates. Actual costs vary.
ESTIMATED_ROUND_TRIP_COST = float(os.getenv("ESTIMATED_ROUND_TRIP_COST", "0.04"))
PAPER_MAX_EXIT_IMPACT = float(os.getenv("PAPER_MAX_EXIT_IMPACT", "0.10"))
PAPER_EXIT_LIQUIDITY_FRACTION = float(os.getenv("PAPER_EXIT_LIQUIDITY_FRACTION", "0.5"))

PUMP_CURVE_LOOKUP_ENABLED = os.getenv("PUMP_CURVE_LOOKUP_ENABLED", "true").lower() == "true"
PUMP_CURVE_LOOKUPS_PER_SCAN = max(0, min(10, int(os.getenv("PUMP_CURVE_LOOKUPS_PER_SCAN", "4"))))
FRESH_LAUNCH_FEED_ENABLED = os.getenv("FRESH_LAUNCH_FEED_ENABLED", "true").lower() == "true"
FRESH_LAUNCH_TTL_SECONDS = max(300, int(os.getenv("FRESH_LAUNCH_TTL_SECONDS", "3600")))
FRESH_LAUNCH_POOL_LIMIT = max(100, int(os.getenv("FRESH_LAUNCH_POOL_LIMIT", "1500")))
FRESH_LAUNCH_SCAN_QUOTA = max(0, int(os.getenv("FRESH_LAUNCH_SCAN_QUOTA", "24")))
VERIFIED_DEX_RECHECK_QUOTA = max(0, int(os.getenv("VERIFIED_DEX_RECHECK_QUOTA", "18")))
VERIFIED_DEX_TTL_SECONDS = max(60, int(os.getenv("VERIFIED_DEX_TTL_SECONDS", "900")))
CURVE_MIN_REAL_SOL_FOR_OBSERVATION = max(0.0, float(os.getenv("CURVE_MIN_REAL_SOL_FOR_OBSERVATION", "1.0")))
FRESH_RECHECK_BASE_SECONDS = max(60, int(os.getenv("FRESH_RECHECK_BASE_SECONDS", "60")))
FRESH_RECHECK_MAX_SECONDS = max(FRESH_RECHECK_BASE_SECONDS, int(os.getenv("FRESH_RECHECK_MAX_SECONDS", "300")))
DISCOVERY_SEARCH_TERMS = tuple(x.strip() for x in os.getenv("DISCOVERY_SEARCH_TERMS", "pump").split(",") if x.strip())
DISCOVERY_SEARCHES_PER_SCAN = max(0, min(3, int(os.getenv("DISCOVERY_SEARCHES_PER_SCAN", "2"))))
DISCOVERY_CACHE_SECONDS = max(60, int(os.getenv("DISCOVERY_CACHE_SECONDS", "60")))
ENTRY_SCAN_INTERVAL_SECONDS = max(60, int(os.getenv("ENTRY_SCAN_INTERVAL_SECONDS", "60")))
ENTRY_BATCH_SIZE = max(1, min(30, int(os.getenv("ENTRY_BATCH_SIZE", "30"))))
MAX_ENTRY_TOKENS_PER_SCAN = max(1, int(os.getenv("MAX_ENTRY_TOKENS_PER_SCAN", "60")))
MARKET_REQUEST_SPACING_SECONDS = max(0.0, float(os.getenv("MARKET_REQUEST_SPACING_SECONDS", "1.5")))
RATE_LIMIT_COOLDOWN_SECONDS = max(30, int(os.getenv("RATE_LIMIT_COOLDOWN_SECONDS", "120")))
BASE = "https://api.dexscreener.com"
SOL_MINT = "So11111111111111111111111111111111111111112"
STATE_FILE = Path(os.getenv("STATE_FILE", "bot_state_36.json"))
PUBLIC_WALLET_ADDRESS = os.getenv("SOLANA_WALLET_ADDRESS", "").strip()
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "").strip()
LOG_FILE = Path("bot.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE, encoding="utf-8")]
)
log = logging.getLogger("meme-bot")
session = requests.Session()
session.headers.update({"User-Agent": "SolanaMemeRiskBot/0.1"})


@dataclass
class Position:
    token: str
    symbol: str
    name: str
    entry_price: float
    amount_usd: float
    token_units: float
    opened_at: float
    peak_price: float
    last_price: float
    score: float
    last_price_at: float = 0.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_api_cooldown_until = 0.0
_last_market_request_at = 0.0


class DexRateLimited(RuntimeError):
    pass


def api_cooldown_remaining() -> float:
    return max(0.0, _api_cooldown_until - time.monotonic())


def dex_request(url: str, *, params: dict | None = None, timeout: int = 12) -> Any:
    """Shared DexScreener budget; a 429 pauses ALL DexScreener calls."""
    global _api_cooldown_until, _last_market_request_at
    if api_cooldown_remaining() > 0:
        raise DexRateLimited(f"cooldown {api_cooldown_remaining():.0f}s")
    wait = MARKET_REQUEST_SPACING_SECONDS - (time.monotonic() - _last_market_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_market_request_at = time.monotonic()
    response = session.get(url, params=params, timeout=timeout)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "")
        try:
            delay = float(retry_after)
        except (ValueError, TypeError):
            delay = RATE_LIMIT_COOLDOWN_SECONDS
        delay = max(RATE_LIMIT_COOLDOWN_SECONDS, min(delay, 900))
        _api_cooldown_until = time.monotonic() + delay
        log.warning("DexScreener HTTP 429: pausing API requests for %.0fs", delay)
        raise DexRateLimited(f"HTTP 429; cooldown {delay:.0f}s")
    response.raise_for_status()
    return response.json()


def get_json(url: str, timeout: int = 12) -> Any:
    return dex_request(url, timeout=timeout)


def log_real_wallet_balance() -> None:
    """Read-only Solana balance; never loads a secret or signs a transaction."""
    if not PUBLIC_WALLET_ADDRESS or not SOLANA_RPC_URL:
        log.warning("REAL WALLET: unavailable; set SOLANA_WALLET_ADDRESS (public) and SOLANA_RPC_URL in Railway Variables.")
        return
    if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", PUBLIC_WALLET_ADDRESS):
        log.error("REAL WALLET: invalid public address format; no RPC request made.")
        return
    if not SOLANA_RPC_URL.startswith("https://"):
        log.error("REAL WALLET: SOLANA_RPC_URL must use HTTPS.")
        return
    try:
        response = session.post(SOLANA_RPC_URL, json={
            "jsonrpc": "2.0", "id": 1, "method": "getBalance",
            "params": [PUBLIC_WALLET_ADDRESS, {"commitment": "confirmed"}],
        }, timeout=12)
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise ValueError("RPC returned an error")
        lamports = payload["result"]["value"]
        if not isinstance(lamports, int) or lamports < 0:
            raise ValueError("RPC returned invalid balance")
        sol = lamports / 1_000_000_000
        try:
            price_response = session.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "solana", "vs_currencies": "usd"}, timeout=10)
            price_response.raise_for_status()
            usd_price = float(price_response.json()["solana"]["usd"])
            if usd_price <= 0:
                raise ValueError("Invalid SOL/USD price")
            log.info("REAL WALLET (read-only): %.6f SOL (~$%.2f USD); PAPER portfolio is separate.", sol, sol * usd_price)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            log.warning("REAL WALLET (read-only): %.6f SOL; USD estimate unavailable (price feed error).", sol)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        log.exception("REAL WALLET: unable to fetch balance; paper trading continues independently.")


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            log.exception("State file is unreadable; refusing to overwrite it.")
            raise
    return {
        "cash_usd": STARTING_CAPITAL,
        "positions": {},
        "closed_trades": [],
        "day": str(date.today()),
        "day_start_equity": STARTING_CAPITAL,
        "halted": False,
        "seen_tokens": []
    }


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


_discovery_cache: dict[str, Any] = {"until": 0.0, "addresses": []}
_discovery_round = 0
_discovery_seen: set[str] = set()
_discovery_priority: dict[str, float] = {}

# PumpPortal's public subscribeNewToken feed is discovery-only. Every mint must
# still pass DexScreener's SOL-pool, liquidity, age and momentum checks.
_fresh_launches: OrderedDict[str, float] = OrderedDict()
# Mint -> (next check monotonic timestamp, attempts, last outcome).
# Entries are bounded by the feed TTL and pool size.
_fresh_checks: dict[str, tuple[float, int, str]] = {}
_fresh_lock = threading.Lock()
_feed_started = False
_feed_connected = False
_feed_messages = 0
_feed_reconnects = 0
_curve_activity = CurveActivity()
_curve_subscriptions: OrderedDict[str, float] = OrderedDict()
_curve_verified: OrderedDict[str, float] = OrderedDict()
_curve_sub_lock = threading.Lock()
_curve_rpc_tracker: RpcCurveTradeTracker | None = None
_curve_poll_worker_running = False
_curve_poll_cursor = 0
# Last validated on-chain curve reserves; diagnostics and prioritization only.
_curve_real_sol: dict[str, tuple[float, float]] = {}
CURVE_ACTIVITY_ENABLED = os.getenv("CURVE_ACTIVITY_ENABLED", "true").lower() == "true"
CURVE_ACTIVITY_MAX_SUBSCRIPTIONS = max(1, min(100, int(os.getenv("CURVE_ACTIVITY_MAX_SUBSCRIPTIONS", "40"))))
CURVE_ACTIVITY_MIN_TRADES = max(1, int(os.getenv("CURVE_ACTIVITY_MIN_TRADES", "20")))
CURVE_ACTIVITY_MIN_VOLUME_SOL = max(0., float(os.getenv("CURVE_ACTIVITY_MIN_VOLUME_SOL", "2")))
RPC_TRADE_POLL_INTERVAL_SECONDS = max(15, int(os.getenv("RPC_TRADE_POLL_INTERVAL_SECONDS", "30")))
RPC_TRADE_MINTS_PER_POLL = max(1, min(12, int(os.getenv("RPC_TRADE_MINTS_PER_POLL", "4"))))
RPC_TRADE_SIGNATURE_LIMIT = max(2, min(50, int(os.getenv("RPC_TRADE_SIGNATURE_LIMIT", "12"))))
RPC_TRADE_TRANSACTIONS_PER_POLL = max(1, min(20, int(os.getenv("RPC_TRADE_TRANSACTIONS_PER_POLL", "5"))))


def _curve_poll_mints() -> list[str]:
    """Prioritize confirmed active curves, while rotating across fresh launches.

    The feed can arrive faster than an affordable RPC polling rate, so the
    observed 5-minute volume is a *lower bound*, not a complete trade tape.
    """
    global _curve_poll_cursor
    with _curve_sub_lock:
        threshold = time.monotonic() - 900
        for mint, when in list(_curve_verified.items()):
            if when < threshold:
                del _curve_verified[mint]
                _curve_real_sol.pop(mint, None)
        # Prefer recently observed, reserve-backed curves, and rotate the rest.
        # This only prioritizes read-only trade observations; it never enables entries.
        verified = sorted(_curve_verified, key=lambda mint: (
            _curve_real_sol.get(mint, (0.0, 0.0))[0] >= CURVE_MIN_REAL_SOL_FOR_OBSERVATION,
            _curve_activity.summary(mint)['trades'],
            _curve_verified[mint]), reverse=True)[:max(1, RPC_TRADE_MINTS_PER_POLL // 2)]
        others = [mint for mint in _curve_subscriptions if mint not in verified]
        slots = max(0, RPC_TRADE_MINTS_PER_POLL - len(verified))
        rotating = []
        if others and slots:
            start = _curve_poll_cursor % len(others)
            rotating = [others[(start + i) % len(others)] for i in range(min(slots, len(others)))]
            _curve_poll_cursor += len(rotating)
        return verified + rotating


def _curve_rpc_worker() -> None:
    global _curve_rpc_tracker, _curve_poll_worker_running
    if not SOLANA_RPC_URL:
        log.warning("CURVE RPC activity unavailable: SOLANA_RPC_URL not configured")
        return
    try:
        tracker = RpcCurveTradeTracker(ReadOnlySolanaRPC(SOLANA_RPC_URL), _curve_activity,
                                       signature_limit=RPC_TRADE_SIGNATURE_LIMIT,
                                       transaction_limit=RPC_TRADE_TRANSACTIONS_PER_POLL)
    except ValueError as exc:
        log.warning("CURVE RPC activity unavailable: %s", type(exc).__name__)
        return
    _curve_rpc_tracker = tracker
    _curve_poll_worker_running = True
    log.info("CURVE RPC ACTIVITY started (read-only Solana RPC; no paid trade subscription) poll=%ds mints=%d tx_limit=%d",
             RPC_TRADE_POLL_INTERVAL_SECONDS, RPC_TRADE_MINTS_PER_POLL,
             RPC_TRADE_TRANSACTIONS_PER_POLL)
    try:
        while True:
            started = time.monotonic()
            mints = _curve_poll_mints()
            try:
                tracker.poll(mints)
            except Exception as exc:
                log.warning("CURVE RPC ACTIVITY worker error=%s", type(exc).__name__)
            diag = tracker.diagnostics()
            if mints and (diag['poll_cycles'] <= 3 or diag['poll_cycles'] % 5 == 0):
                log.info("CURVE RPC ACTIVITY watched=%d polled=%d signature_scans=%d tx_fetched=%d valid_trades=%d rpc_errors=%d history_gaps=%d pending=%d",
                         len(_curve_subscriptions), len(mints), diag['signature_scans'],
                         diag['tx_fetched'], diag['valid_trades'], diag['rpc_errors'],
                         diag['history_gaps'], diag['pending_signatures'])
            time.sleep(max(1, RPC_TRADE_POLL_INTERVAL_SECONDS - (time.monotonic() - started)))
    finally:
        _curve_poll_worker_running = False


def start_curve_activity() -> None:
    if CURVE_ACTIVITY_ENABLED:
        threading.Thread(target=_curve_rpc_worker, daemon=True, name="curve-rpc-activity").start()


def update_curve_subscriptions(mints: list[str]) -> None:
    """Keep a bounded launch watchlist for read-only RPC polling.

    This no longer sends any paid PumpPortal subscribeTokenTrade requests.
    """
    if not CURVE_ACTIVITY_ENABLED:
        return
    now = time.monotonic()
    with _curve_sub_lock:
        for mint in mints:
            if not isinstance(mint, str) or not _MINT_RE.fullmatch(mint):
                continue
            if mint not in _curve_subscriptions:
                _curve_subscriptions[mint] = now
        cutoff = now - min(FRESH_LAUNCH_TTL_SECONDS, 1800)
        for mint, timestamp in list(_curve_subscriptions.items()):
            if timestamp < cutoff:
                del _curve_subscriptions[mint]
        while len(_curve_subscriptions) > CURVE_ACTIVITY_MAX_SUBSCRIPTIONS:
            _curve_subscriptions.popitem(last=False)


def note_active_curve(mint: str, real_sol: float | None = None) -> None:
    """Prioritize mints with verified curve accounts for RPC activity polls."""
    if not CURVE_ACTIVITY_ENABLED:
        return
    with _curve_sub_lock:
        timestamp = time.monotonic()
        _curve_verified[mint] = timestamp
        if real_sol is not None:
            _curve_real_sol[mint] = (max(0.0, real_sol), timestamp)
        _curve_verified.move_to_end(mint)
        while len(_curve_verified) > 20:
            old, _ = _curve_verified.popitem(last=False)
            _curve_real_sol.pop(old, None)


def curve_activity_diagnostics() -> dict[str, Any]:
    with _curve_sub_lock:
        watched = len(_curve_subscriptions)
        verified = len(_curve_verified)
    tracker = _curve_rpc_tracker
    details = tracker.diagnostics() if tracker else {"source": "solana_rpc", "valid_trades": 0,
                                                     "signature_scans": 0, "tx_fetched": 0}
    return {"watched": watched, "verified_curves": verified, "worker_running": _curve_poll_worker_running,
            **details}

_MINT_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def record_fresh_launch(mint: str, *, seen_at: float | None = None) -> bool:
    if not isinstance(mint, str) or not _MINT_RE.fullmatch(mint) or mint == SOL_MINT:
        return False
    timestamp = time.monotonic() if seen_at is None else seen_at
    with _fresh_lock:
        _fresh_launches.pop(mint, None)
        _fresh_launches[mint] = timestamp
        _fresh_checks.setdefault(mint, (timestamp, 0, "new"))
        while len(_fresh_launches) > FRESH_LAUNCH_POOL_LIMIT:
            old_mint, _ = _fresh_launches.popitem(last=False)
            _fresh_checks.pop(old_mint, None)
    update_curve_subscriptions([mint])
    return True


def fresh_launch_snapshot() -> list[str]:
    cutoff = time.monotonic() - FRESH_LAUNCH_TTL_SECONDS
    with _fresh_lock:
        for mint, timestamp in list(_fresh_launches.items()):
            if timestamp < cutoff:
                _fresh_launches.pop(mint, None)
                _fresh_checks.pop(mint, None)
        return list(reversed(_fresh_launches))



def due_fresh_launches(*, now: float | None = None, limit: int | None = None) -> list[str]:
    """Oldest-due first: avoid permanently starving launches behind newer ones."""
    current = time.monotonic() if now is None else now
    with _fresh_lock:
        due = [(checks[0], _fresh_launches[mint], mint)
               for mint, checks in _fresh_checks.items()
               if mint in _fresh_launches and checks[0] <= current]
    due.sort()
    return [mint for _, _, mint in due[:limit]]


def mark_fresh_checked(mint: str, outcome: str, *, now: float | None = None) -> None:
    current = time.monotonic() if now is None else now
    with _fresh_lock:
        if mint not in _fresh_launches:
            return
        _, attempts, _ = _fresh_checks.get(mint, (current, 0, "new"))
        attempts += 1
        # Missing market data is rechecked regularly as the token matures.
        # Longer intervals prevent hammering DexScreener for unindexed launches.
        delay = min(FRESH_RECHECK_MAX_SECONDS, FRESH_RECHECK_BASE_SECONDS * (2 ** min(attempts - 1, 8)))
        _fresh_checks[mint] = (current + delay, attempts, outcome)


def fresh_check_counts() -> dict[str, int]:
    with _fresh_lock:
        counts = Counter(outcome for _, _, outcome in _fresh_checks.values())
    return dict(counts)


def _fresh_launch_worker() -> None:
    global _feed_connected, _feed_messages, _feed_reconnects
    try:
        import websocket
    except ImportError:
        log.warning("Fresh-launch feed unavailable: install websocket-client")
        return
    backoff = 3
    while True:
        ws = None
        try:
            ws = websocket.create_connection("wss://pumpportal.fun/api/data", timeout=20)
            ws.settimeout(30)
            ws.send(json.dumps({"method": "subscribeNewToken"}))
            _feed_connected = True
            log.info("FRESH FEED connected (PumpPortal new-token stream)")
            backoff = 3
            while True:
                message = json.loads(ws.recv())
                if not isinstance(message, dict):
                    continue
                mint = message.get("mint")
                if record_fresh_launch(mint):
                    _feed_messages += 1
        except Exception as exc:
            _feed_reconnects += 1
            log.warning("FRESH FEED disconnected (%s); retry in %ds", exc, backoff)
        finally:
            _feed_connected = False
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass
        time.sleep(backoff)
        backoff = min(60, backoff * 2)


def start_fresh_launch_feed() -> None:
    global _feed_started
    if not FRESH_LAUNCH_FEED_ENABLED or _feed_started:
        return
    _feed_started = True
    threading.Thread(target=_fresh_launch_worker, daemon=True, name="fresh-launch-feed").start()



def latest_candidate_addresses() -> list[str]:
    """Discover Solana mints from profiles, boosts and rotating DEX search queries.

    Discovery data is cached briefly to avoid hammering public APIs every five seconds.
    Pair quotes are still refreshed on each scan. Search results are *not* trusted
    as executable routes: entry_pair_reason validates the actual SOL pool.
    """
    global _discovery_round
    now = time.monotonic()
    if now < _discovery_cache["until"]:
        return list(_discovery_cache["addresses"])

    addresses: list[str] = []
    priority: dict[str, float] = {}
    sources: dict[str, int] = {}
    endpoints = [
        f"{BASE}/token-profiles/latest/v1",
        f"{BASE}/token-boosts/latest/v1",
        f"{BASE}/token-boosts/top/v1",
    ]
    for url in endpoints:
        try:
            data = get_json(url)
            matches = [item["tokenAddress"] for item in data
                       if isinstance(item, dict) and item.get("chainId") == "solana"
                       and item.get("tokenAddress")] if isinstance(data, list) else []
            addresses.extend(mint for mint in matches if mint != SOL_MINT)
            sources[url.rsplit('/', 3)[-3]] = len(matches)
        except DexRateLimited:
            break
        except Exception as exc:
            log.warning("Discovery endpoint failed (%s): %s", url, exc)

    if DISCOVERY_SEARCH_TERMS:
        for offset in range(min(DISCOVERY_SEARCHES_PER_SCAN, len(DISCOVERY_SEARCH_TERMS))):
            term = DISCOVERY_SEARCH_TERMS[(_discovery_round + offset) % len(DISCOVERY_SEARCH_TERMS)]
            try:
                pairs = dex_request(f"{BASE}/latest/dex/search", params={"q": term}).get("pairs") or []
                matches = []
                for pair in pairs:
                    if not isinstance(pair, dict) or pair.get("chainId") != "solana":
                        continue
                    mint = (pair.get("baseToken") or {}).get("address")
                    # Search returns unrelated symbols, SOL/USDC pools, and repeated
                    # pairs. Only use search hits with a supported SOL route.
                    if not mint or mint == SOL_MINT:
                        continue
                    if (pair.get("quoteToken") or {}).get("address") != SOL_MINT:
                        continue
                    if (pair.get("dexId") or "").lower() not in SUPPORTED_SOL_ROUTES:
                        continue
                    matches.append(mint)
                    liquidity = as_float((pair.get("liquidity") or {}).get("usd"))
                    if liquidity >= MIN_SOL_PAIR_LIQUIDITY_USD:
                        priority[mint] = max(priority.get(mint, 0), liquidity)
                addresses.extend(matches)
                sources[f"search:{term}"] = len(set(matches))
            except DexRateLimited:
                break
            except Exception as exc:
                log.warning("Discovery search failed (%s): %s", term, exc)
        _discovery_round = (_discovery_round + DISCOVERY_SEARCHES_PER_SCAN) % len(DISCOVERY_SEARCH_TERMS)

    # Feed mints are added even when DexScreener profiles/boosts are unchanged.
    # A newly launched token may have no indexed SOL pair yet; that is normal.
    stream_mints = fresh_launch_snapshot()
    sources["fresh_launch_feed"] = len(stream_mints)
    unique = [mint for mint in dict.fromkeys(stream_mints + addresses) if mint != SOL_MINT]
    # Preserve rotating coverage of all addresses; prioritize known viable search
    # hits, but do not permanently starve the remainder of the pool.
    _discovery_priority.clear()
    _discovery_priority.update(priority)
    fresh = sum(mint not in _discovery_seen for mint in unique)
    _discovery_seen.update(unique)
    log.info("DISCOVERY sources=%s raw=%d unique=%d new_since_start=%d supported_liquid_search_mints=%d", sources, len(addresses), len(unique), fresh, len(priority))
    # Keep the last successful token list during rate limits or temporary outages.
    if unique:
        _discovery_cache.update(until=time.monotonic() + DISCOVERY_CACHE_SECONDS, addresses=unique)
        return unique
    _discovery_cache["until"] = time.monotonic() + DISCOVERY_CACHE_SECONDS
    return list(_discovery_cache["addresses"])


def token_pairs(address: str) -> list[dict]:
    try:
        data = get_json(f"{BASE}/token-pairs/v1/solana/{address}")
        return data if isinstance(data, list) else []
    except DexRateLimited:
        return []
    except Exception as exc:
        log.debug("Pair lookup failed for %s: %s", address, exc)
        return []


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def age_hours(pair: dict) -> float:
    created = pair.get("pairCreatedAt")
    if not created:
        return 1e9
    return max(0.0, (time.time() * 1000 - float(created)) / 3_600_000)


def best_pair(pairs: list[dict]) -> dict | None:
    # Pick the pair with the deepest liquidity, not necessarily the highest FDV.
    sol_pairs = [p for p in pairs if p.get("chainId") == "solana" and p.get("priceUsd")]
    if not sol_pairs:
        return None
    return max(sol_pairs, key=lambda p: as_float((p.get("liquidity") or {}).get("usd")))


# Entry eligibility is distinct from price discovery for held positions.
# Only these pool identifiers have an explicit PumpPortal route in our staging flow.
SUPPORTED_SOL_ROUTES = {"pumpfun": "pump", "pumpswap": "pump-amm"}


def entry_pair_reason(pair: dict) -> str | None:
    if pair.get("chainId") != "solana":
        return "not a Solana pair"
    quote = pair.get("quoteToken") or {}
    if quote.get("address") != SOL_MINT:
        return f"unsupported quote mint {quote.get('symbol') or quote.get('address') or 'unknown'}"
    dex = (pair.get("dexId") or "").lower()
    if dex not in SUPPORTED_SOL_ROUTES:
        return f"unsupported PumpPortal route {dex or 'unknown'}"
    liq = as_float((pair.get("liquidity") or {}).get("usd"))
    if liq < MIN_SOL_PAIR_LIQUIDITY_USD:
        return f"SOL-pair liquidity ${liq:.0f} below ${MIN_SOL_PAIR_LIQUIDITY_USD:.0f}"
    return None


def entry_pair_diagnostic(pairs: list[dict]) -> tuple[str, dict | None]:
    """Report the actual blocking stage, without treating absent liquidity as zero.

    A token may have a liquid USDC/Raydium pool and an unindexed Pump.fun
    bonding curve. Reporting the deepest unrelated pool as a SOL liquidity
    failure obscures that distinction.
    """
    solana = [p for p in pairs if p.get("chainId") == "solana"]
    sol_quoted = [p for p in solana if (p.get("quoteToken") or {}).get("address") == SOL_MINT]
    supported = [p for p in sol_quoted if (p.get("dexId") or "").lower() in SUPPORTED_SOL_ROUTES]
    priced = [p for p in supported if as_float(p.get("priceUsd")) > 0]
    if not solana:
        return "no_solana_pair", None
    if not sol_quoted:
        return "no_sol_quoted_pair", max(solana, key=lambda p: as_float((p.get("liquidity") or {}).get("usd")))
    if not supported:
        return "unsupported_sol_route", max(sol_quoted, key=lambda p: as_float((p.get("liquidity") or {}).get("usd")))
    if not priced:
        return "supported_pair_missing_price", supported[0]
    with_liquidity = [p for p in priced if (p.get("liquidity") or {}).get("usd") is not None]
    if not with_liquidity:
        return "supported_pair_liquidity_unavailable", priced[0]
    deepest = max(with_liquidity, key=lambda p: as_float((p.get("liquidity") or {}).get("usd")))
    if as_float((deepest.get("liquidity") or {}).get("usd")) < MIN_SOL_PAIR_LIQUIDITY_USD:
        return "supported_pair_low_liquidity", deepest
    return "eligible_route_liquidity", deepest


def best_entry_pair(pairs: list[dict]) -> dict | None:
    eligible = [p for p in pairs if entry_pair_reason(p) is None and p.get("priceUsd")]
    return max(eligible, key=lambda p: as_float((p.get("liquidity") or {}).get("usd")), default=None)


def analyze_pair(pair: dict, reject_reasons: Counter | None = None) -> dict | None:
    token = pair.get("baseToken") or {}
    address = token.get("address")
    price = as_float(pair.get("priceUsd"))
    liquidity = as_float((pair.get("liquidity") or {}).get("usd"))
    volume = pair.get("volume") or {}
    txns = pair.get("txns") or {}
    change = pair.get("priceChange") or {}
    m5_volume = as_float(volume.get("m5"))
    h1_volume = as_float(volume.get("h1"))
    h24_volume = as_float(volume.get("h24"))
    m5_buys = as_float((txns.get("m5") or {}).get("buys"))
    m5_sells = as_float((txns.get("m5") or {}).get("sells"))
    ch5 = as_float(change.get("m5"))
    ch1 = as_float(change.get("h1"))
    age = age_hours(pair)

    def reject(reason: str) -> None:
        if reject_reasons is not None:
            reject_reasons[reason] += 1

    if not address or price <= 0:
        reject("missing_price_or_mint")
        return None

    # Hard safety/liquidity filters. Public DEX data is not a honeypot audit.
    if liquidity < MIN_LIQUIDITY_USD:
        reject("minimum_liquidity")
        return None
    if m5_volume < MIN_VOLUME_5M_USD:
        reject("minimum_volume")
        return None
    if age > MAX_PAIR_AGE_HOURS:
        reject("too_old")
        return None
    if FAST_MOMENTUM_ENABLED:
        if age * 60 < MIN_PAIR_AGE_MINUTES:
            reject("too_new")
            return None
        if m5_volume < MOMENTUM_MIN_VOLUME_5M_USD:
            reject("momentum_volume")
            return None
        if not MOMENTUM_MIN_CHANGE_5M_PCT <= ch5 <= MOMENTUM_MAX_CHANGE_5M_PCT:
            reject("momentum_price_change")
            return None
        if m5_buys + m5_sells < MOMENTUM_MIN_TXNS_5M:
            reject("momentum_transactions")
            return None
        if m5_sells <= 0 or m5_buys / m5_sells < MOMENTUM_MIN_BUY_SELL_RATIO:
            reject("momentum_buy_sell_ratio")
            return None
        if m5_volume / max(liquidity, 1) < MOMENTUM_MIN_VOLUME_LIQUIDITY_RATIO:
            reject("momentum_volume_liquidity_ratio")
            return None
    if m5_sells == 0 and m5_buys >= 8:
        # One-sided flow is often suspicious; avoid rather than assume it's bullish.
        reject("one_sided_flow")
        return None
    if m5_buys + m5_sells < 8:
        reject("insufficient_transactions")
        return None
    if ch5 > 80 or ch1 > 250:
        # Avoid chasing extreme vertical moves.
        reject("extreme_price_spike")
        return None
    if ch5 < -25 or ch1 < -45:
        reject("price_collapse")
        return None

    # Heuristic score, not a predictive model. Each component is capped.
    liquidity_score = min(25.0, liquidity / 2000.0)
    volume_score = min(20.0, (m5_volume / 1000.0) * 5.0)
    activity_score = min(15.0, (m5_buys + m5_sells) / 2.0)
    buy_pressure = m5_buys / max(1.0, m5_buys + m5_sells)
    flow_score = max(0.0, min(15.0, (buy_pressure - 0.45) * 50.0 + 7.5))
    momentum_score = 0.0
    if 0 < ch5 <= 15:
        momentum_score += 8
    elif -5 <= ch5 <= 0:
        momentum_score += 4
    if 0 < ch1 <= 35:
        momentum_score += 7
    elif -10 <= ch1 <= 0:
        momentum_score += 3
    age_score = 10.0 if 0.25 <= age <= 24 else (6.0 if age <= 72 else 2.0)
    score = min(100.0, liquidity_score + volume_score + activity_score +
                flow_score + momentum_score + age_score)

    return {
        "address": address,
        "symbol": str(token.get("symbol") or "???")[:20],
        "name": str(token.get("name") or "Unknown")[:50],
        "price": price,
        "liquidity": liquidity,
        "m5_volume": m5_volume,
        "h1_volume": h1_volume,
        "h24_volume": h24_volume,
        "m5_buys": int(m5_buys),
        "m5_sells": int(m5_sells),
        "change_m5": ch5,
        "change_h1": ch1,
        "age_hours": age,
        "score": score,
        "url": pair.get("url", ""),
    }


def equity(state: dict, current_prices: dict[str, float] | None = None) -> float:
    current_prices = current_prices or {}
    value = as_float(state["cash_usd"])
    for mint, raw in state["positions"].items():
        pos = Position(**raw)
        p = current_prices.get(mint, pos.last_price)
        value += pos.token_units * p
    return value


def roll_day_if_needed(state: dict) -> None:
    today = str(date.today())
    if state.get("day") != today:
        state["day"] = today
        state["day_start_equity"] = equity(state)
        state["halted"] = False
        log.info("New day. Daily equity baseline reset to $%.2f", state["day_start_equity"])


def should_halt(state: dict) -> bool:
    baseline = as_float(state.get("day_start_equity"), STARTING_CAPITAL)
    current = equity(state)
    loss_fraction = (baseline - current) / max(1.0, baseline)
    if loss_fraction >= MAX_DAILY_LOSS_FRACTION:
        state["halted"] = True
        log.error("DAILY LOSS LIMIT HIT: %.2f%%. New entries halted.", loss_fraction * 100)
    return bool(state.get("halted"))


def paper_buy(state: dict, c: dict) -> None:
    if c["address"] in state["positions"]:
        return
    if len(state["positions"]) >= MAX_POSITIONS:
        return
    # Fixed position allocation, capped by available cash. This is position size,
    # not the amount guaranteed to be lost; stop-losses can slip in volatile markets.
    size = min(state["cash_usd"], POSITION_SIZE_USD)
    if size < 5:
        return
    # Conservative paper entry haircut for spread/impact. Live costs can be worse.
    entry = c["price"] * (1 + ESTIMATED_ROUND_TRIP_COST / 2)
    units = size / entry
    state["cash_usd"] -= size
    state["positions"][c["address"]] = asdict(Position(
        token=c["address"], symbol=c["symbol"], name=c["name"],
        entry_price=entry, amount_usd=size, token_units=units,
        opened_at=time.time(), peak_price=entry, last_price=entry, score=c["score"],
        last_price_at=time.time()
    ))
    state["seen_tokens"] = (state.get("seen_tokens", []) + [c["address"]])[-2000:]
    log.info("PAPER BUY %s ($%.2f) score=%.1f price=%g", c["symbol"], size, c["score"], entry)


def paper_exit_quote(pos: Position, price: float, liquidity_usd: float) -> dict | None:
    """Conservative indicative proceeds, NOT a DEX executable quote.

    A constant-product-style impact approximation assumes half of reported
    pool USD liquidity is quote-side depth. Reject unknown/insufficient depth.
    """
    if price <= 0 or liquidity_usd <= 0 or pos.token_units <= 0:
        return None
    gross = pos.token_units * price
    quote_depth = liquidity_usd * PAPER_EXIT_LIQUIDITY_FRACTION
    if quote_depth <= 0:
        return None
    impact = gross / (quote_depth + gross)
    if impact > PAPER_MAX_EXIT_IMPACT:
        return None
    cost = max(0.0, min(0.99, ESTIMATED_ROUND_TRIP_COST / 2))
    proceeds = gross * (1 - impact) * (1 - cost)
    return {"proceeds_usd": proceeds, "impact_pct": impact * 100,
            "exit_price": proceeds / pos.token_units, "liquidity_usd": liquidity_usd}


def close_position(state: dict, mint: str, price: float, reason: str, liquidity_usd: float | None = None) -> bool:
    raw = state["positions"].get(mint)
    if not raw:
        return False
    pos = Position(**raw)
    quote = paper_exit_quote(pos, price, liquidity_usd or 0)
    if quote is None:
        log.warning("PAPER EXIT BLOCKED %s: missing liquidity or estimated price impact too high", pos.symbol)
        state["halted"] = True
        return False
    exit_price = quote["exit_price"]
    proceeds = quote["proceeds_usd"]
    pnl = proceeds - pos.amount_usd
    state["cash_usd"] += proceeds
    state["closed_trades"].append({
        "closed_at": now_iso(), "token": mint, "symbol": pos.symbol,
        "entry_price": pos.entry_price, "exit_price": exit_price,
        "invested_usd": pos.amount_usd, "proceeds_usd": proceeds,
        "pnl_usd": pnl, "pnl_pct": pnl / max(1.0, pos.amount_usd) * 100,
        "reason": reason, "estimated_impact_pct": quote["impact_pct"],
        "pool_liquidity_usd": quote["liquidity_usd"], "execution": "paper_estimate_only"
    })
    state["closed_trades"] = state["closed_trades"][-1000:]
    del state["positions"][mint]
    log.info("PAPER SELL %s reason=%s PnL=$%.2f (%.1f%%) impact≈%.2f%% [estimate only]", pos.symbol, reason, pnl,
             pnl / max(1.0, pos.amount_usd) * 100, quote["impact_pct"])
    return True


def manage_positions(state: dict, market: dict[str, dict]) -> None:
    for mint in list(state["positions"].keys()):
        raw = state["positions"][mint]
        pos = Position(**raw)
        c = market.get(mint)
        if not c or as_float(c.get("price")) <= 0:
            # Never invent a price. Halt new entries if a held position has no
            # usable quote for too long; its mark-to-market value is uncertain.
            last_valid = pos.last_price_at or pos.opened_at
            stale_for = max(0.0, time.time() - last_valid)
            log.warning("No fresh price for held token %s; last valid quote %.0fs ago",
                        pos.symbol, stale_for)
            if stale_for >= MAX_STALE_PRICE_SECONDS:
                state["halted"] = True
                log.error("STALE PRICE SAFETY HALT: %s has no usable quote for %.0fs. "
                          "New entries halted; check the position manually.", pos.symbol, stale_for)
            continue
        price = c["price"]
        pos.last_price = price
        pos.last_price_at = time.time()
        pos.peak_price = max(pos.peak_price, price)
        raw.update(asdict(pos))
        # Evaluate TP/SL against estimated net proceeds, including the paper
        # execution haircut, rather than the raw market-price change alone.
        liquidity = as_float(c.get("liquidity"))
        quote = paper_exit_quote(pos, price, liquidity)
        if quote is None:
            state["halted"] = True
            log.error("PAPER EXIT UNAVAILABLE %s: liquidity missing or impact over limit; halt entries", pos.symbol)
            continue
        net_return = quote["proceeds_usd"] / max(pos.amount_usd, 1e-15) - 1
        peak_return = price / max(pos.peak_price, 1e-15) - 1
        if net_return >= TAKE_PROFIT:
            close_position(state, mint, price, "take_profit", liquidity)
        elif net_return <= -STOP_LOSS:
            close_position(state, mint, price, "stop_loss", liquidity)
        elif MAX_HOLD_MINUTES > 0 and time.time() - pos.opened_at >= MAX_HOLD_MINUTES * 60:
            close_position(state, mint, price, "time_limit", liquidity)
        elif TRAILING_STOP_ENABLED and pos.peak_price > pos.entry_price and peak_return <= -TRAILING_STOP:
            close_position(state, mint, price, "trailing_stop", liquidity)
        elif c["liquidity"] < MIN_LIQUIDITY_USD * 0.65:
            close_position(state, mint, price, "liquidity_deterioration", liquidity)


_entry_scan_next_at = 0.0
_entry_scan_cursor = 0
# Revisit previously confirmed SOL-quoted, supported, sufficiently liquid DEX
# markets. These are candidates for momentum re-evaluation, NOT auto-buys.
_verified_dex_mints: OrderedDict[str, float] = OrderedDict()


def note_verified_dex_mint(mint: str, *, now: float | None = None) -> None:
    if not mint or mint == SOL_MINT:
        return
    stamp = time.monotonic() if now is None else now
    _verified_dex_mints[mint] = stamp + VERIFIED_DEX_TTL_SECONDS
    _verified_dex_mints.move_to_end(mint)
    while len(_verified_dex_mints) > 250:
        _verified_dex_mints.popitem(last=False)


def verified_dex_due(*, now: float | None = None, limit: int | None = None) -> list[str]:
    stamp = time.monotonic() if now is None else now
    for mint, expires_at in list(_verified_dex_mints.items()):
        if expires_at <= stamp:
            _verified_dex_mints.pop(mint, None)
    cap = VERIFIED_DEX_RECHECK_QUOTA if limit is None else limit
    return list(reversed(_verified_dex_mints))[:max(0, cap)]


def select_entry_mints(addresses: list[str], fresh_due: list[str], *, count: int, cursor: int) -> tuple[list[str], int, int]:
    """Reserve slots for verified pools; share the rest with fresh and rotating discovery.

    This only selects mints for new API lookups. No cached price, liquidity or
    momentum score is trusted for an actual trade.
    """
    cap = max(0, count)
    selected = list(dict.fromkeys(verified_dex_due(limit=min(VERIFIED_DEX_RECHECK_QUOTA, cap))))
    selected = selected[:cap]
    fresh_cap = min(FRESH_LAUNCH_SCAN_QUOTA, cap - len(selected))
    prioritized_fresh = []
    for mint in fresh_due:
        if mint not in selected and len(prioritized_fresh) < fresh_cap:
            prioritized_fresh.append(mint)
    selected.extend(prioritized_fresh)
    # Older indexed pools discovered through search are also valuable.
    search = sorted((m for m in addresses if m in _discovery_priority and m not in selected),
                    key=lambda m: _discovery_priority[m], reverse=True)
    for mint in search[:max(0, (cap - len(selected)) // 2)]:
        selected.append(mint)
    rotating = [m for m in dict.fromkeys(addresses) if m not in selected]
    remaining = cap - len(selected)
    chosen = [rotating[(cursor + i) % len(rotating)] for i in range(min(remaining, len(rotating)))] if rotating else []
    selected.extend(chosen)
    return selected, (cursor + len(chosen)) % max(1, len(rotating)), len(prioritized_fresh)



def scan_once(state: dict) -> None:
    global _entry_scan_next_at, _entry_scan_cursor
    # Always manage existing positions; discovery is a separate, slower job.
    now = time.monotonic()
    scan_entries = now >= _entry_scan_next_at and api_cooldown_remaining() <= 0
    if scan_entries:
        _entry_scan_next_at = now + ENTRY_SCAN_INTERVAL_SECONDS
    addresses = latest_candidate_addresses() if scan_entries else []
    if addresses:
        count = min(MAX_ENTRY_TOKENS_PER_SCAN, max(len(addresses), len(_verified_dex_mints)))
        stream_set = set(fresh_launch_snapshot())
        stream_priority = due_fresh_launches(limit=min(count, FRESH_LAUNCH_SCAN_QUOTA))
        addresses, _entry_scan_cursor, fresh_selected = select_entry_mints(
            addresses, stream_priority, count=count, cursor=_entry_scan_cursor)
        log.info("ENTRY SCAN tokens=%d fresh_due=%d verified_dex_selected=%d verified_dex_watched=%d feed_connected=%s feed_messages=%d feed_reconnects=%d next_in=%ds",
                 len(addresses), fresh_selected, len([m for m in addresses if m in _verified_dex_mints]),
                 len(_verified_dex_mints), _feed_connected, _feed_messages, _feed_reconnects, ENTRY_SCAN_INTERVAL_SECONDS)
    elif api_cooldown_remaining() > 0:
        log.info("ENTRY SCAN paused: DexScreener cooldown %.0fs", api_cooldown_remaining())
    market: dict[str, dict] = {}
    rejection_counts: Counter = Counter()
    route_rejections: Counter = Counter()
    evaluated = 0
    missing_pairs = 0
    market_data_rejections: Counter = Counter()
    checked_mints: set[str] = set()
    curve_checks = 0
    curve_outcomes: Counter = Counter()
    curve_pending: list[str] = []
    curve_quote_ready = 0
    curve_activity_ready = 0
    curve_activity_observed_threshold_met = 0
    curve_reserve_observation_ready = 0
    for start in range(0, len(addresses), ENTRY_BATCH_SIZE):
        batch = addresses[start:start + ENTRY_BATCH_SIZE]
        if not batch:
            continue
        try:
            data = get_json(f"{BASE}/tokens/v1/solana/{','.join(batch)}")
            pairs = data if isinstance(data, list) else []
            # Select eligible SOL-quoted PumpPortal routes for new entries only.
            grouped: dict[str, list[dict]] = {}
            for p in pairs:
                mint = (p.get("baseToken") or {}).get("address")
                if mint:
                    grouped.setdefault(mint, []).append(p)
            for mint in batch:
                checked_mints.add(mint)
                if mint not in grouped:
                    missing_pairs += 1
                    market_data_rejections["pair_not_indexed"] += 1
                    # A missing index response is not evidence that yesterday's
                    # verified pool disappeared. Retain it until its TTL expires.
                    mark_fresh_checked(mint, "pair_not_indexed")
                    if mint in stream_set:
                        curve_pending.append(mint)
            for mint, mint_pairs in grouped.items():
                evaluated += 1
                pair = best_entry_pair(mint_pairs)
                if pair is None:
                    # Log a useful reason for the deepest pool rather than scoring it.
                    diagnostic, representative = entry_pair_diagnostic(mint_pairs)
                    market_data_rejections[diagnostic] += 1
                    if representative:
                        reason = entry_pair_reason(representative) or diagnostic
                        route_rejections[reason.split(" ")[0]] += 1
                        log.info("REJECT %s: %s (market_data=%s)", (representative.get("baseToken") or {}).get("symbol", mint), reason, diagnostic)
                    else:
                        log.info("REJECT %s: %s", mint, diagnostic)
                    if diagnostic not in ("supported_pair_liquidity_unavailable", "supported_pair_missing_price"):
                        # Confirmed low liquidity / unsupported route invalidates
                        # the verified entry, unlike transient missing data.
                        _verified_dex_mints.pop(mint, None)
                    mark_fresh_checked(mint, diagnostic)
                    if mint in stream_set and diagnostic in ("supported_pair_liquidity_unavailable", "supported_pair_missing_price", "no_sol_quoted_pair"):
                        curve_pending.append(mint)
                    continue
                # Record only markets re-verified from fresh pair data.
                note_verified_dex_mint(mint)
                c = analyze_pair(pair, rejection_counts)
                mark_fresh_checked(mint, "eligible" if c else "momentum_rejected")
                if c:
                    c["pumpportal_pool"] = SUPPORTED_SOL_ROUTES[pair["dexId"].lower()]
                    market[mint] = c
        except DexRateLimited:
            break
        except Exception as exc:
            log.warning("Batch token lookup failed: %s", exc)

    # Read-only on-chain fallback for fresh launches. This supplies genuine
    # bonding-curve status/reserves, NOT a substitute DEX liquidity number.
    if scan_entries and PUMP_CURVE_LOOKUP_ENABLED and SOLANA_RPC_URL:
        for mint in dict.fromkeys(curve_pending):
            if curve_checks >= PUMP_CURVE_LOOKUPS_PER_SCAN:
                break
            curve_checks += 1
            try:
                info = lookup_curve(mint, SOLANA_RPC_URL)
                status = info["status"]
                curve_outcomes[status] += 1
                if status in ("active_bonding_curve", "graduated"):
                    if status == "active_bonding_curve":
                        note_active_curve(mint, info.get("real_sol_reserve"))
                    # A 0.1 SOL quote checks reserve arithmetic without treating
                    # virtual reserves as verified liquidity or enabling entries.
                    indicative = buy_quote(info, 0.1)
                    if indicative:
                        curve_quote_ready += 1
                        activity = _curve_activity.summary(mint)
                        # Trade activity is diagnostic only; for modern quote-token
                        # curves the event's quote amount isn't necessarily SOL.
                        # Never make entry eligibility depend on assumed quote units.
                        reserve_observation_ready = info["real_sol_reserve"] >= CURVE_MIN_REAL_SOL_FOR_OBSERVATION
                        curve_reserve_observation_ready += int(reserve_observation_ready)
                        observed_threshold = activity['trades'] >= CURVE_ACTIVITY_MIN_TRADES
                        curve_activity_observed_threshold_met += int(observed_threshold)
                        ready = False  # quote-mint/fee/exits not yet validated for curve entries
                        curve_activity_ready += int(ready)
                        log.info("CURVE ACTIVITY mint=%s source=solana_rpc trades5m=%d buys=%d sells=%d unverified_quote_amount_as_sol=%.4f observed_trade_threshold=%s reserve_observation_ready=%s activity_ready=%s entry=blocked_pending_execution_validation",
                                 mint, activity['trades'], activity['buys'], activity['sells'], activity['volume_sol'], observed_threshold, reserve_observation_ready, ready)
                        log.info("CURVE QUOTE mint=%s buy_sol=0.1 token_raw=%.0f impact=%.3f%% real_sol=%.4f entry=blocked_pending_execution_validation",
                                 mint, indicative["token_raw"], indicative["impact"] * 100, info["real_sol_reserve"])
                    else:
                        log.info("CURVE DATA mint=%s status=%s real_sol=%.4f quote=unavailable entry=blocked",
                                 mint, status, info["real_sol_reserve"])
                else:
                    log.info("CURVE DATA mint=%s status=%s entry=blocked", mint, status)
            except Exception as exc:
                curve_outcomes["lookup_error"] += 1
                log.warning("CURVE LOOKUP failed mint=%s error=%s", mint, type(exc).__name__)

    if scan_entries and CURVE_ACTIVITY_ENABLED:
        # Subscribe to a rotating bounded selection of fresh launches, including
        # mints awaiting their first DexScreener pair. This is observation only.
        # Watchlist is populated on launch arrival; never replace it with scan subset.
        pass
    if scan_entries:
        log.info("FILTER SUMMARY evaluated=%d eligible=%d pair_not_indexed=%d route_rejections=%s momentum_rejections=%s market_data_rejections=%s fresh_check_outcomes=%s curve_checks=%d curve_outcomes=%s curve_quote_ready=%d curve_reserve_observation_ready=%d curve_activity_observed_threshold_met=%d curve_activity_ready=%d curve_activity_source=solana_rpc curve_trade_diagnostics=%s",
                 evaluated, len(market), missing_pairs, dict(route_rejections), dict(rejection_counts), dict(market_data_rejections), fresh_check_counts(), curve_checks, dict(curve_outcomes), curve_quote_ready, curve_reserve_observation_ready, curve_activity_observed_threshold_met, curve_activity_ready, curve_activity_diagnostics())

    # Fetch quotes for held positions separately from candidate screening.
    # A held token may fail entry filters (e.g. momentum/volume) but still need
    # to be priced so exits and portfolio valuation can be managed.
    for mint in list(state["positions"].keys()):
        if mint in market:
            continue
        pairs = token_pairs(mint)
        eligible_quote_pairs = [p for p in pairs if p.get("chainId") == "solana"
                                and (p.get("quoteToken") or {}).get("address") == SOL_MINT
                                and (p.get("dexId") or "").lower() in SUPPORTED_SOL_ROUTES]
        pair = best_pair(eligible_quote_pairs)
        if pair:
            price = as_float(pair.get("priceUsd"))
            liquidity = as_float((pair.get("liquidity") or {}).get("usd"))
            if price > 0:
                market[mint] = {"price": price, "liquidity": liquidity}

    manage_positions(state, market)
    roll_day_if_needed(state)
    if should_halt(state):
        save_state(state)
        return

    # Price-only quotes for held positions have no score and are not entry candidates.
    candidates = sorted(
        (c for c in market.values()
         if isinstance(c.get("score"), (int, float))
         and isinstance(c.get("address"), str)),
        key=lambda c: c["score"],
        reverse=True,
    )
    for c in candidates:
        if c["score"] < MIN_SCORE:
            continue
        if c["address"] in state["positions"]:
            continue
        # Avoid repeatedly re-entering tokens after a completed trade.
        if c["address"] in state.get("seen_tokens", []):
            continue
        log.info("CANDIDATE %s score=%.1f liq=$%.0f vol5m=$%.0f age=%.1fh %s",
                 c["symbol"], c["score"], c["liquidity"], c["m5_volume"], c["age_hours"], c["url"])
        if PAPER_MODE:
            paper_buy(state, c)
        else:
            # Live execution is deliberately fail-closed until a tested swap adapter
            # is installed. Never silently pretend a live order was sent.
            log.error("LIVE MODE REQUESTED BUT NO VERIFIED EXECUTION ADAPTER IS CONFIGURED. No order sent.")
            state["halted"] = True
            break
        if len(state["positions"]) >= MAX_POSITIONS:
            break
    save_state(state)
    log.info("Equity≈$%.2f cash=$%.2f positions=%d candidates=%d",
             equity(state), state["cash_usd"], len(state["positions"]), len(market))


def main() -> None:
    # Explicit import verifies the strategy and execution bridge are deployed together.
    # Live transaction calls remain disabled until recovery and reconciliation are reviewed.
    from live_execution import execute_buy, execute_sell  # noqa: F401
    if os.getenv("LIVE_TRADING_ENABLED", "false").lower() == "true":
        log.critical("LIVE_TRADING_ENABLED must remain false for this staged strategy release. Refusing to start.")
        raise SystemExit(2)
    if not PAPER_MODE:
        log.critical("PAPER_MODE=false, but this release has no live swap signer. Refusing to trade live.")
        log.critical("Set PAPER_MODE=true. Live mode requires a separately reviewed Jupiter swap adapter.")
        raise SystemExit(2)
    state = load_state()
    start_fresh_launch_feed()
    start_curve_activity()
    log.info("Paper state file: %s (existing state, if present, takes precedence over starting capital)", STATE_FILE)
    log_real_wallet_balance()
    log.info("Starting in PAPER MODE. Capital=$%.2f; position size=$%.2f; max positions=%d; stop-loss=%.0f%%; take-profit=%.0f%%; trailing stop=%s; min score=%.1f",
             STARTING_CAPITAL, POSITION_SIZE_USD, MAX_POSITIONS, STOP_LOSS * 100, TAKE_PROFIT * 100,
             (f"enabled ({TRAILING_STOP:.0%})" if TRAILING_STOP_ENABLED else "disabled"), MIN_SCORE)
    log.info("This is not a live trading bot. No wallet key is read and no transaction is signed.")
    last_wallet_check = time.monotonic()
    while True:
        try:
            if time.monotonic() - last_wallet_check >= 300:
                log_real_wallet_balance()
                last_wallet_check = time.monotonic()
            scan_once(state)
        except KeyboardInterrupt:
            log.info("Stopped by user.")
            save_state(state)
            break
        except Exception:
            log.exception("Unexpected scan error; will retry next cycle.")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
