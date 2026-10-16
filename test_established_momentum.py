"""Regression tests for the established-cap, positive-trend paper strategy."""
import time
from collections import Counter, OrderedDict
from datetime import datetime, timezone, timedelta

import bot
import pytest


@pytest.fixture(autouse=True)
def established(monkeypatch):
    monkeypatch.setattr(bot, "MOMENTUM_SWING_MODE", True)
    monkeypatch.setattr(bot, "SNIPER_MODE", False)
    monkeypatch.setattr(bot, "PAPER_MODE", True)
    monkeypatch.setattr(bot, "MIN_SCORE", 68)
    monkeypatch.setattr(bot, "MIN_VOLUME_5M_USD", 1000)
    monkeypatch.setattr(bot, "MIN_SOL_PAIR_LIQUIDITY_USD", 5000)
    monkeypatch.setattr(bot, "MOMENTUM_MIN_LIQUIDITY_USD", 20000)
    monkeypatch.setattr(bot, "MOMENTUM_MARKET_CAP_MIN_USD", 500000)
    monkeypatch.setattr(bot, "MOMENTUM_MARKET_CAP_MAX_USD", 50000000)
    monkeypatch.setattr(bot, "MOMENTUM_MIN_PAIR_AGE_MINUTES", 60)
    monkeypatch.setattr(bot, "MOMENTUM_MAX_PAIR_AGE_HOURS", 0)
    monkeypatch.setattr(bot, "MOMENTUM_ALLOW_FDV_FALLBACK", True)
    monkeypatch.setattr(bot, "MOMENTUM_MIN_VOLUME_5M_USD", 2000)
    monkeypatch.setattr(bot, "MOMENTUM_MIN_VOLUME_1H_USD", 20000)
    monkeypatch.setattr(bot, "MOMENTUM_MIN_CHANGE_5M_PCT", 1.5)
    monkeypatch.setattr(bot, "MOMENTUM_MAX_CHANGE_5M_PCT", 25)
    monkeypatch.setattr(bot, "MOMENTUM_MIN_CHANGE_1H_PCT", 3)
    monkeypatch.setattr(bot, "MOMENTUM_MIN_CHANGE_6H_PCT", 1)
    monkeypatch.setattr(bot, "MOMENTUM_MIN_CHANGE_24H_PCT", 0)
    monkeypatch.setattr(bot, "MOMENTUM_MIN_VOLUME_LIQUIDITY_RATIO", 0.01)
    monkeypatch.setattr(bot, "MOMENTUM_MIN_TXNS_5M", 10)
    monkeypatch.setattr(bot, "MOMENTUM_MIN_BUY_SELL_RATIO", 1.1)


def pool(*, mint="C" * 44, dex="raydium", cap=2_000_000, days=160, liq=125000,
         change=None, fdv=None, price=0.01, pool_address="R" * 44):
    return {"chainId": "solana", "dexId": dex, "pairAddress": pool_address,
            "baseToken": {"address": mint, "symbol": "OLDER", "name": "Older Coin"},
            "quoteToken": {"address": bot.SOL_MINT, "symbol": "SOL"},
            "priceUsd": str(price), "marketCap": cap, "fdv": fdv,
            "liquidity": {"usd": liq},
            "pairCreatedAt": int((time.time() - 86400 * days) * 1000),
            "volume": {"m5": 6500, "h1": 100000, "h6": 400000, "h24": 2000000},
            "priceChange": change or {"m5": 3.8, "h1": 12.0, "h6": 24.0, "h24": 49.0},
            "txns": {"m5": {"buys": 35, "sells": 20}}}


def test_old_pool_without_max_age_eligible():
    p=pool(days=700)
    result=bot.analyze_pair(p)
    assert result is not None
    assert result["age_hours"] > 24*690
    assert result["market_cap_usd"] == 2_000_000
    assert result["market_cap_source"] == "marketCap"
    assert result["change_h6"] == 24
    assert result["score"] >= 68


def test_market_cap_window_limits():
    assert bot.analyze_pair(pool(cap=499999)) is None
    assert bot.analyze_pair(pool(cap=500000)) is not None
    assert bot.analyze_pair(pool(cap=50000000)) is not None
    assert bot.analyze_pair(pool(cap=50000001)) is None


def test_missing_cap_or_fdv_are_not_guessed(monkeypatch):
    assert bot.analyze_pair(pool(cap=None, fdv=None)) is None
    fallback=bot.analyze_pair(pool(cap=None, fdv=3_000_000))
    assert fallback and fallback["market_cap_source"] == "fdv_proxy"
    monkeypatch.setattr(bot, "MOMENTUM_ALLOW_FDV_FALLBACK", False)
    assert bot.analyze_pair(pool(cap=None, fdv=3_000_000)) is None


@pytest.mark.parametrize("changes", [
    {"m5": 4, "h1": -1, "h6": 24, "h24": 30},
    {"m5": 4, "h1": 12, "h6": -4, "h24": 30},
    {"m5": 4, "h1": 12, "h6": 24, "h24": -10},
    {"m5": -3, "h1": 12, "h6": 24, "h24": 30},
    {"m5": 4, "h1": 12, "h24": 30},
])
def test_downtrends_missing_windows_rejected(changes):
    assert bot.analyze_pair(pool(change=changes)) is None


def test_zero_or_sparse_liquidity_rejected():
    assert bot.analyze_pair(pool(liq=5000)) is None
    assert bot.best_entry_pair([pool(liq=5000)]) is None
    assert bot.analyze_pair(pool(liq=0)) is None


def test_paper_dex_expanded_but_old_sniper_still_restricted(monkeypatch):
    assert bot.entry_pair_reason(pool(dex="raydium")) is None
    assert bot.entry_pair_reason(pool(dex="meteora")) is None
    assert bot.entry_pair_reason(pool(dex="orca")) is None
    assert bot.entry_pair_reason(pool(dex="unknown-dex")) is not None
    monkeypatch.setattr(bot, "MOMENTUM_SWING_MODE", False)
    monkeypatch.setattr(bot, "SNIPER_MODE", True)
    assert "unsupported" in bot.entry_pair_reason(pool(dex="meteora"))


def test_too_new_and_optional_max_age(monkeypatch):
    assert bot.analyze_pair(pool(days=0.01)) is None
    monkeypatch.setattr(bot, "MOMENTUM_MAX_PAIR_AGE_HOURS", 72)
    assert bot.analyze_pair(pool(days=160)) is None
    assert bot.analyze_pair(pool(days=2)) is not None


def test_choose_trending_pool_over_deeper_downtrend_pool():
    falling=pool(liq=2000000, change={"m5": -10, "h1": -14, "h6": -25, "h24": -40}, pool_address="D"*44)
    rising=pool(liq=125000, pool_address="U"*44)
    assert bot.best_entry_pair([falling, rising])["pairAddress"] == "U"*44


def test_trending_gecko_source_multiple_pages_and_no_new_pools(monkeypatch):
    monkeypatch.setattr(bot, "MOMENTUM_TRENDING_POOL_PAGES", 3)
    monkeypatch.setattr(bot, "MOMENTUM_TOP_POOL_PAGES", 0)
    monkeypatch.setattr(bot, "QUALITY_POOL_DISCOVERY_ENABLED", True)
    monkeypatch.setattr(bot, "_quality_cache", {"until": 0, "mints": [], "scores": {}})
    calls=[]
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"data": []}
    def fake_get(url, **kwargs):
        calls.append((url, kwargs.get("params", {}).get("page")))
        return Response()
    monkeypatch.setattr(bot.session, "get", fake_get)
    bot.quality_pool_candidates()
    assert len(calls) == 3
    assert [p for _,p in calls] == [1,2,3]
    assert all("trending_pools" in url for url,_ in calls)


def test_end_to_end_scan_places_paper_entry(monkeypatch):
    p=pool()
    mint=p["baseToken"]["address"]
    state={"cash_usd":36.0,"positions":{},"closed_trades":[],"seen_tokens":[],"halted":False,"rugged_mints":[],"exit_issues":{},"day_start_equity":36.0,"date":datetime.now(timezone.utc).date().isoformat()}
    monkeypatch.setattr(bot, "_entry_scan_next_at", 0)
    monkeypatch.setattr(bot, "_entry_scan_cursor", 0)
    monkeypatch.setattr(bot, "_verified_dex_mints", OrderedDict())
    monkeypatch.setattr(bot, "_entry_reject_until", OrderedDict())
    monkeypatch.setattr(bot, "_quality_pool_mints", [mint])
    monkeypatch.setattr(bot, "_discovery_priority", {})
    monkeypatch.setattr(bot, "latest_candidate_addresses", lambda:[mint])
    monkeypatch.setattr(bot, "get_json", lambda *a, **kw:[p])
    monkeypatch.setattr(bot, "candidate_momentum_confirm", lambda *a,**kw:(True,"confirmed"))
    monkeypatch.setattr(bot, "paper_prebuy_sellability", lambda *a,**kw:(True,"same_pool_indicative"))
    monkeypatch.setattr(bot, "save_state", lambda *a:None)
    monkeypatch.setattr(bot, "PAPER_EXPLORATION_ENABLED", False)
    monkeypatch.setattr(bot, "PUMP_CURVE_LOOKUP_ENABLED", False)
    monkeypatch.setattr(bot, "SOLANA_RPC_URL", "")
    monkeypatch.setattr(bot, "FRESH_LAUNCH_FEED_ENABLED", False)
    bot.scan_once(state)
    assert mint in state["positions"]
    assert state["paper_trade_metrics"][mint]["strategy"] == "established_momentum"
    assert state["paper_trade_metrics"][mint]["entry_market_cap_usd"] == 2_000_000
    assert state["positions"][mint]["entry_pool_dex"] == "raydium"



def test_momentum_paper_prebuy_rechecks_exact_raydium_pool(monkeypatch):
    p=pool()
    candidate=bot.analyze_pair(p)
    assert candidate
    monkeypatch.setattr(bot,"token_pairs",lambda mint:[p])
    monkeypatch.setattr(bot,"PAPER_PREBUY_INDEPENDENT_POOL_CHECK",True)
    monkeypatch.setattr(bot,"held_pool_fallback",lambda pool, mint: {
        "pool_address":p["pairAddress"],"price":0.01,"liquidity":125000,
        "quote_source":"geckoterminal_indicative"})
    ok,why=bot.paper_prebuy_sellability(candidate)
    assert ok and why=="indicative_same_pool_sell_depth_verified"
    monkeypatch.setattr(bot,"held_pool_fallback",lambda pool,mint:None)
    assert bot.paper_prebuy_sellability(candidate)[0] is False


def test_missing_invalid_age_is_rejected_even_when_age_max_unlimited():
    p=pool()
    p["pairCreatedAt"]=-1
    reasons=Counter()
    assert bot.analyze_pair(p,reasons) is None
    assert reasons["invalid_pair_age"]==1
