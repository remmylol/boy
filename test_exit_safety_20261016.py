from unittest.mock import Mock
import bot


def sample_candidate():
    return {"address": "mint", "pool_address": "p" * 44, "symbol": "T", "name": "Test", "score": 90, "price": 1.0}


def sample_pair():
    return {"pairAddress": "p" * 44, "chainId": "solana", "dexId": "pumpswap", "baseToken": {"address": "mint"}, "quoteToken": {"address": bot.SOL_MINT}, "priceUsd": "1", "liquidity": {"usd": "18000"}}


def test_prebuy_independent_pool_rejects_missing(monkeypatch):
    monkeypatch.setattr(bot, "PAPER_PREBUY_INDEPENDENT_POOL_CHECK", True)
    monkeypatch.setattr(bot, "token_pairs", lambda mint: [sample_pair()])
    monkeypatch.setattr(bot, "held_pool_fallback", lambda pool, mint: None)
    ok, reason = bot.paper_prebuy_sellability(sample_candidate())
    assert (ok, reason) == (False, "independent_same_pool_unavailable")


def test_prebuy_independent_pool_rejects_disagreement(monkeypatch):
    monkeypatch.setattr(bot, "PAPER_PREBUY_INDEPENDENT_POOL_CHECK", True)
    monkeypatch.setattr(bot, "token_pairs", lambda mint: [sample_pair()])
    monkeypatch.setattr(bot, "held_pool_fallback", lambda pool, mint: {"liquidity": 3000, "price": 1})
    assert bot.paper_prebuy_sellability(sample_candidate())[1] == "independent_same_pool_liquidity_disagreement"
    monkeypatch.setattr(bot, "held_pool_fallback", lambda pool, mint: {"liquidity": 18000, "price": 1.5})
    assert bot.paper_prebuy_sellability(sample_candidate())[1] == "independent_same_pool_price_disagreement"


def test_prebuy_independent_pool_accepts_consistent_data(monkeypatch):
    monkeypatch.setattr(bot, "PAPER_PREBUY_INDEPENDENT_POOL_CHECK", True)
    monkeypatch.setattr(bot, "token_pairs", lambda mint: [sample_pair()])
    monkeypatch.setattr(bot, "held_pool_fallback", lambda pool, mint: {"liquidity": 17500, "price": 1.02})
    assert bot.paper_prebuy_sellability(sample_candidate())[0]


def test_exit_diagnostics_distinguish_fallback_and_impact(monkeypatch):
    bot_p = bot.Position(token="mint", symbol="T", name="T", entry_price=1,
                         amount_usd=10, token_units=10, opened_at=0,
                         peak_price=1, last_price=1, score=80)
    monkeypatch.setattr(bot, "PAPER_EXIT_REQUIRE_PRIMARY_QUOTE", True)
    assert bot.paper_exit_failure_reason(bot_p, 1, 10000, "geckoterminal_indicative") == "primary_pool_quote_missing_fallback_valuation_only"
    assert bot.paper_exit_failure_reason(bot_p, 1, 0) == "missing_exit_liquidity"
    assert bot.paper_exit_failure_reason(bot_p, 1, 10000) is None
    assert bot.paper_exit_failure_reason(bot_p, 1000, 1000) == "excessive_estimated_exit_impact"


def test_fallback_quote_never_executes_paper_exit(monkeypatch):
    monkeypatch.setattr(bot, "PAPER_EXIT_REQUIRE_PRIMARY_QUOTE", True)
    s = {"cash_usd": 26, "positions": {}, "seen_tokens": [], "closed_trades": []}
    bot.paper_buy(s, {"address": "mint", "symbol": "T", "name": "T", "price": 1,
                      "score": 90, "pool_address": "pool", "pool_dex": "pumpswap"})
    assert not bot.close_position(s, "mint", 2, "take_profit", 10000, "geckoterminal_indicative")
    assert "mint" in s["positions"] and s["cash_usd"] == 16
    assert s["exit_issues"]["mint"]["reason"] == "primary_pool_quote_missing_fallback_valuation_only"
    assert s["halted"]
