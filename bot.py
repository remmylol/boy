import json
import re
import logging
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any
from collections import Counter
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
STOP_LOSS = float(os.getenv("STOP_LOSS_PCT", "0.35"))
TRAILING_STOP_ENABLED = os.getenv("TRAILING_STOP_ENABLED", "false").lower() == "true"
TRAILING_STOP = float(os.getenv("TRAILING_STOP_PCT", "0.15"))
MIN_SCORE = float(os.getenv("MIN_SCORE", "75"))
MIN_LIQUIDITY_USD = float(os.getenv("MIN_LIQUIDITY_USD", "5000"))
MIN_SOL_PAIR_LIQUIDITY_USD = max(10000.0, float(os.getenv("MIN_SOL_PAIR_LIQUIDITY_USD", "10000")))
MIN_VOLUME_5M_USD = float(os.getenv("MIN_VOLUME_5M_USD", "1000"))
MAX_PAIR_AGE_HOURS = float(os.getenv("MAX_PAIR_AGE_HOURS", "6"))
MIN_PAIR_AGE_MINUTES = float(os.getenv("MIN_PAIR_AGE_MINUTES", "5"))
FAST_MOMENTUM_ENABLED = os.getenv("FAST_MOMENTUM_ENABLED", "true").lower() == "true"
MOMENTUM_MIN_VOLUME_5M_USD = float(os.getenv("MOMENTUM_MIN_VOLUME_5M_USD", "15000"))
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

DISCOVERY_SEARCH_TERMS = tuple(x.strip() for x in os.getenv("DISCOVERY_SEARCH_TERMS", "pump,solana,meme,cat,dog").split(",") if x.strip())
DISCOVERY_SEARCHES_PER_SCAN = max(0, min(3, int(os.getenv("DISCOVERY_SEARCHES_PER_SCAN", "2"))))
DISCOVERY_CACHE_SECONDS = max(10, int(os.getenv("DISCOVERY_CACHE_SECONDS", "30")))
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


def get_json(url: str, timeout: int = 12) -> Any:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


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
            addresses.extend(matches)
            sources[url.rsplit('/', 3)[-3]] = len(matches)
        except Exception as exc:
            log.warning("Discovery endpoint failed (%s): %s", url, exc)

    if DISCOVERY_SEARCH_TERMS:
        for offset in range(min(DISCOVERY_SEARCHES_PER_SCAN, len(DISCOVERY_SEARCH_TERMS))):
            term = DISCOVERY_SEARCH_TERMS[(_discovery_round + offset) % len(DISCOVERY_SEARCH_TERMS)]
            try:
                response = session.get(f"{BASE}/latest/dex/search", params={"q": term}, timeout=12)
                response.raise_for_status()
                pairs = response.json().get("pairs") or []
                matches = [(pair.get("baseToken") or {}).get("address") for pair in pairs
                           if isinstance(pair, dict) and pair.get("chainId") == "solana"]
                addresses.extend(mint for mint in matches if mint)
                sources[f"search:{term}"] = len(matches)
            except Exception as exc:
                log.warning("Discovery search failed (%s): %s", term, exc)
        _discovery_round = (_discovery_round + DISCOVERY_SEARCHES_PER_SCAN) % len(DISCOVERY_SEARCH_TERMS)

    unique = list(dict.fromkeys(addresses))
    fresh = sum(mint not in _discovery_seen for mint in unique)
    _discovery_seen.update(unique)
    log.info("DISCOVERY sources=%s raw=%d unique=%d new_since_start=%d", sources, len(addresses), len(unique), fresh)
    _discovery_cache.update(until=now + DISCOVERY_CACHE_SECONDS, addresses=unique)
    return unique


def token_pairs(address: str) -> list[dict]:
    try:
        data = get_json(f"{BASE}/token-pairs/v1/solana/{address}")
        return data if isinstance(data, list) else []
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


def scan_once(state: dict) -> None:
    addresses = latest_candidate_addresses()
    market: dict[str, dict] = {}
    rejection_counts: Counter = Counter()
    route_rejections: Counter = Counter()
    evaluated = 0
    for start in range(0, len(addresses), 30):
        batch = addresses[start:start + 30]
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
            for mint, mint_pairs in grouped.items():
                evaluated += 1
                pair = best_entry_pair(mint_pairs)
                if pair is None:
                    # Log a useful reason for the deepest pool rather than scoring it.
                    representative = best_pair(mint_pairs)
                    if representative:
                        reason = entry_pair_reason(representative) or "no eligible SOL trading pool"
                        route_rejections[reason.split(" ")[0]] += 1
                        log.info("REJECT %s: %s", (representative.get("baseToken") or {}).get("symbol", mint), reason)
                    continue
                c = analyze_pair(pair, rejection_counts)
                if c:
                    c["pumpportal_pool"] = SUPPORTED_SOL_ROUTES[pair["dexId"].lower()]
                    market[mint] = c
        except Exception as exc:
            log.warning("Batch token lookup failed: %s", exc)

    log.info("FILTER SUMMARY evaluated=%d eligible=%d route_rejections=%s momentum_rejections=%s",
             evaluated, len(market), dict(route_rejections), dict(rejection_counts))

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
