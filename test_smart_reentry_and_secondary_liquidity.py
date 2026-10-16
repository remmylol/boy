"""Deterministic tests for safe paper reentry and same-pool liquidity recovery."""
import time
from collections import OrderedDict
from datetime import datetime, timezone
from unittest.mock import Mock

import bot
import pytest


MINT = "C" * 44
POOL = "D" * 44


def new_state():
    return {"cash_usd": 36.0, "positions": {}, "seen_tokens": [], "closed_trades": [],
            "paper_trade_metrics": {}, "exit_issues": {}, "halted": False}


def closed(mint=MINT, at=1000., reason="immediate_reversal", pnl=-0.5, reentry=False):
    return {"token": mint, "closed_at": datetime.fromtimestamp(at, timezone.utc).isoformat(),
            "reason": reason, "pnl_usd": pnl, "paper_metrics": {"is_reentry": reentry}}


def pair(liq=None, quote=None, dex="pumpswap", price="0.01", age_min=10):
    return {"chainId": "solana", "dexId": dex, "pairAddress": POOL,
            "baseToken": {"address": MINT, "symbol": "TEST"},
            "quoteToken": {"address": quote or bot.SOL_MINT},
            "priceUsd": price, "liquidity": {"usd": liq},
            "pairCreatedAt": (time.time() - age_min * 60) * 1000,
            "volume": {"m5": 10000, "h1": 30000, "h24": 100000},
            "txns": {"m5": {"buys": 50, "sells": 25}},
            "priceChange": {"m5": 10, "h1": 16}, "url": "https://example.invalid/test"}


def gecko_resp(reserve="20000", price="0.01", base=MINT, quote=None, pool=POOL):
    response = Mock(status_code=200)
    response.json.return_value = {"data": {"id": "solana_" + pool,
        "attributes": {"address": pool, "reserve_in_usd": reserve, "base_token_price_usd": price},
        "relationships": {
            "base_token": {"data": {"id": "solana_" + base}},
            "quote_token": {"data": {"id": "solana_" + (quote or bot.SOL_MINT)}}}}}
    return response


def reset_secondary(monkeypatch):
    monkeypatch.setattr(bot, "_secondary_liquidity_cache", {})
    monkeypatch.setattr(bot, "_secondary_request_times", [])
    monkeypatch.setattr(bot, "_secondary_paused_until", 0.0)
    monkeypatch.setattr(bot, "PAPER_SECONDARY_LIQUIDITY_ENABLED", True)
    monkeypatch.setattr(bot, "PAPER_SECONDARY_LIQUIDITY_MAX_PER_MINUTE", 4)


def test_reversal_reentry_exactly_five_minutes_and_persistent_state():
    state = new_state()
    state["seen_tokens"] = [MINT]
    state["closed_trades"] = [closed()]
    assert not bot.paper_reentry_decision(state, MINT, now=1299)[0]
    allowed, reason, was_reentry = bot.paper_reentry_decision(state, MINT, now=1300)
    assert (allowed, reason, was_reentry) == (True, "reentry_approved", True)
    # Reconciling the same JSON dictionary after a restart yields the same result.
    assert bot.paper_reentry_decision(dict(state), MINT, now=1300)[0]


def test_other_exit_three_minutes_and_liquidity_exit_longer():
    state = new_state()
    state["closed_trades"] = [closed(reason="take_profit")]
    assert not bot.paper_reentry_decision(state, MINT, now=1179)[0]
    assert bot.paper_reentry_decision(state, MINT, now=1180)[0]
    state["closed_trades"] = [closed(reason="liquidity_deterioration")]
    assert not bot.paper_reentry_decision(state, MINT, now=1300)[0]
    assert bot.paper_reentry_decision(state, MINT, now=4600)[0]


def test_reentry_does_not_bypass_already_held_unresolved_issue_or_missing_history():
    state = new_state()
    state["seen_tokens"] = [MINT]
    assert bot.paper_reentry_decision(state, MINT, now=2000)[1] == "legacy_trade_no_exit_history"
    state["closed_trades"] = [closed()]
    state["exit_issues"] = {MINT: {"status": "IMPAIRED_EXIT_UNAVAILABLE"}}
    assert bot.paper_reentry_decision(state, MINT, now=2000)[1] == "unresolved_exit_issue"
    state["exit_issues"] = {}
    state["positions"] = {MINT: {}}
    assert bot.paper_reentry_decision(state, MINT, now=2000)[1] == "already_held"


def test_reentry_loss_budget_and_max_2_closed_reentries_per_hour():
    state = new_state()
    state["closed_trades"] = [closed(at=1000, pnl=-2.1)]
    assert bot.paper_reentry_decision(state, MINT, now=1500)[1].startswith("reentry_loss_budget")
    state["closed_trades"] = [closed(at=1000, pnl=-0.1),
                              closed(at=1300, reason="take_profit", pnl=0.3, reentry=True),
                              closed(at=1600, reason="take_profit", pnl=0.2, reentry=True)]
    assert bot.paper_reentry_decision(state, MINT, now=1900)[1] == "reentry_hourly_limit"
    assert bot.paper_reentry_decision(state, MINT, now=5400)[0]


def test_recent_sold_token_returns_to_scanner_after_cooldown(monkeypatch):
    state = new_state()
    state["closed_trades"] = [closed(at=time.time() - 301)]
    monkeypatch.setattr(bot, "_entry_reject_until", OrderedDict())
    assert bot.paper_reentry_watch_mints(state) == [MINT]
    picked, _, _ = bot.select_entry_mints([], [], count=10, cursor=0,
                                           reentry_due=bot.paper_reentry_watch_mints(state))
    assert MINT in picked


def test_reentry_bounded_old_pair_passes_same_momentum_checks(monkeypatch):
    monkeypatch.setattr(bot, "SNIPER_MODE", True)
    monkeypatch.setattr(bot, "PAPER_REENTRY_MAX_POOL_AGE_MINUTES", 180)
    stale = pair(liq=22000, age_min=90)
    counts = bot.Counter()
    assert bot.analyze_pair(stale, counts) is None
    assert counts["too_old"] == 1
    assert bot.analyze_pair(stale, allow_reentry_age=True) is not None
    too_old = pair(liq=22000, age_min=181)
    assert bot.analyze_pair(too_old, allow_reentry_age=True) is None


def test_reentry_price_confirmation_forced_even_if_generic_switch_off(monkeypatch):
    monkeypatch.setattr(bot, "ENTRY_TREND_CONFIRM_ENABLED", False)
    monkeypatch.setattr(bot, "ENTRY_TREND_MIN_OBSERVATION_SECONDS", 10)
    mint = "z" * 44
    bot._candidate_price_history.pop(mint, None)
    assert bot.candidate_momentum_confirm(mint, .01, now=100, force_confirmation=True)[0] is False
    assert bot.candidate_momentum_confirm(mint, .0101, now=115, force_confirmation=True)[0] is True
    bot._candidate_price_history.pop(mint, None)


def test_missing_liquidity_recovers_from_pinned_sol_pool(monkeypatch):
    reset_secondary(monkeypatch)
    mock_get = Mock(return_value=gecko_resp())
    monkeypatch.setattr(bot.session, "get", mock_get)
    recovered, outcome = bot.independently_verify_missing_liquidity(pair())
    assert outcome == "verified_indicative_only"
    assert recovered["liquidity"]["usd"] == 20000
    assert recovered["liquidity_data_source"] == "geckoterminal_indicative"
    # Per-pool cached evidence still needs to match fresh primary token price.
    again, _ = bot.independently_verify_missing_liquidity(pair(price="0.03"))
    assert again is None
    assert mock_get.call_count == 1
    # Prebuy independently rechecks exact token pool and quote identity.
    c = bot.analyze_pair(recovered)
    assert c is not None
    c["liquidity_data_source"] = recovered["liquidity_data_source"]
    valid, why = bot.paper_prebuy_sellability(c, pairs=[pair()])
    assert valid, why


@pytest.mark.parametrize("response,why", [
    (gecko_resp(reserve="200"), "secondary_insufficient_depth_or_price"),
    (gecko_resp(base="wrong"), "secondary_wrong_token_or_quote"),
    (gecko_resp(quote="USDC"), "secondary_wrong_token_or_quote"),
    (gecko_resp(pool="F" * 44), "secondary_wrong_pool"),
    (gecko_resp(price="0.02"), "secondary_price_disagreement"),
])
def test_secondary_fails_closed_for_bad_data(monkeypatch, response, why):
    reset_secondary(monkeypatch)
    monkeypatch.setattr(bot.session, "get", Mock(return_value=response))
    assert bot.independently_verify_missing_liquidity(pair())[1] == why


def test_secondary_never_overrides_reported_zero_or_unsupported_routes(monkeypatch):
    reset_secondary(monkeypatch)
    mocked = Mock()
    monkeypatch.setattr(bot.session, "get", mocked)
    assert bot.independently_verify_missing_liquidity(pair(liq=0))[1] == "primary_liquidity_present"
    assert bot.independently_verify_missing_liquidity(pair(dex="raydium"))[1] == "unsupported_route"
    assert bot.independently_verify_missing_liquidity(pair(quote="USDC"))[1] == "unsupported_pair_orientation_or_id"
    mocked.assert_not_called()


def test_secondary_rate_limited_and_paper_exit_still_requires_verified_price(monkeypatch):
    reset_secondary(monkeypatch)
    resp = Mock(status_code=429)
    monkeypatch.setattr(bot.session, "get", Mock(return_value=resp))
    assert bot.independently_verify_missing_liquidity(pair())[1] == "secondary_rate_limited"
    assert bot.independently_verify_missing_liquidity(pair())[1] == "rate_limit_cooldown"
    pos = bot.Position(token=MINT, symbol="T", name="T", entry_price=.01, amount_usd=10,
                       token_units=1000, opened_at=0, peak_price=.01, last_price=.01, score=80)
    assert bot.paper_exit_failure_reason(pos, .02, 20000, "geckoterminal_indicative") is not None
    assert bot.paper_exit_failure_reason(pos, .02, 20000, "dexscreener_price_geckoterminal_depth_indicative") is None


def test_full_entry_scan_rebuys_previous_mint_if_reconfirmed(monkeypatch):
    """Integrates closed-trade history with discovery -> screening -> paper buy."""
    state = new_state()
    state["seen_tokens"] = [MINT]
    state["closed_trades"] = [closed(at=time.time() - 301)]
    monkeypatch.setattr(bot, "_entry_scan_next_at", 0.0)
    monkeypatch.setattr(bot, "_entry_reject_until", OrderedDict())
    monkeypatch.setattr(bot, "_verified_dex_mints", OrderedDict())
    monkeypatch.setattr(bot, "_sniper_watchlist", OrderedDict())
    monkeypatch.setattr(bot, "_quality_pool_mints", [])
    monkeypatch.setattr(bot, "PUMP_CURVE_LOOKUP_ENABLED", False)
    monkeypatch.setattr(bot, "SOLANA_RPC_URL", "")
    monkeypatch.setattr(bot, "latest_candidate_addresses", lambda: [])
    monkeypatch.setattr(bot, "get_json", lambda *args, **kw: [pair(liq=20000)])
    monkeypatch.setattr(bot, "candidate_momentum_confirm", lambda *args, **kw: (True, "confirmed"))
    monkeypatch.setattr(bot, "paper_prebuy_sellability", lambda *args, **kw: (True, "confirmed"))
    monkeypatch.setattr(bot, "save_state", lambda state: None)
    bot.scan_once(state)
    assert MINT in state["positions"]
    assert state["paper_trade_metrics"][MINT]["is_reentry"]
    assert state["cash_usd"] < 36.0


def test_full_entry_scan_secondary_liquidity_requires_prebuy_sellability(monkeypatch):
    state = new_state()
    reset_secondary(monkeypatch)
    monkeypatch.setattr(bot, "_entry_scan_next_at", 0.0)
    monkeypatch.setattr(bot, "_entry_reject_until", OrderedDict())
    monkeypatch.setattr(bot, "_verified_dex_mints", OrderedDict())
    monkeypatch.setattr(bot, "_sniper_watchlist", OrderedDict())
    monkeypatch.setattr(bot, "_quality_pool_mints", [])
    monkeypatch.setattr(bot, "PUMP_CURVE_LOOKUP_ENABLED", False)
    monkeypatch.setattr(bot, "SOLANA_RPC_URL", "")
    # A fresh Stage-1 Gecko pool is prioritized; raw discovery alone is not.
    monkeypatch.setattr(bot, "_quality_pool_mints", [MINT])
    monkeypatch.setattr(bot, "latest_candidate_addresses", lambda: [MINT])
    monkeypatch.setattr(bot, "get_json", lambda *args, **kw: [pair()])
    monkeypatch.setattr(bot, "candidate_momentum_confirm", lambda *args, **kw: (True, "confirmed"))
    monkeypatch.setattr(bot, "save_state", lambda state: None)
    monkeypatch.setattr(bot.session, "get", Mock(return_value=gecko_resp()))
    bot.scan_once(state)
    assert MINT in state["positions"], "Secondary same-pool depth + Dex price should permit paper buy"
    assert state["positions"][MINT]["entry_pool_address"] == POOL


def test_reentry_watch_ignores_unrelated_stale_scanner_cooldown(monkeypatch):
    state = new_state()
    state["closed_trades"] = [closed(at=time.time()-301)]
    monkeypatch.setattr(bot, "_entry_reject_until", OrderedDict())
    bot.note_entry_rejection(MINT, "too_old")  # 30min scanner delay, not a trade exit
    assert bot.mint_cooling_down(MINT)
    assert MINT in bot.paper_reentry_watch_mints(state)
    # The market gate still rejects old pools unless they pass the separate
    # bounded reentry-age rule; bypassing the scanner queue is not bypassing risk.
    very_old = pair(liq=20000, age_min=bot.PAPER_REENTRY_MAX_POOL_AGE_MINUTES+1)
    assert bot.analyze_pair(very_old, allow_reentry_age=True) is None
