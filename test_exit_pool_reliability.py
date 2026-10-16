from unittest.mock import Mock
import bot


def test_new_paper_positions_pin_pool():
    s = {"cash_usd": 36, "positions": {}, "seen_tokens": [], "closed_trades": []}
    bot.paper_buy(s, {"address": "mint", "symbol": "T", "name": "Test", "price": 1,
                      "score": 90, "pool_address": "pool-1", "pool_dex": "pumpswap"})
    assert s["positions"]["mint"]["entry_pool_address"] == "pool-1"
    assert s["positions"]["mint"]["entry_pool_dex"] == "pumpswap"


def test_held_pool_fallback_requires_matching_base(monkeypatch):
    bot._pool_fallback_cache.clear()
    pool = "a" * 44
    response = Mock()
    response.json.return_value = {"data": {"relationships": {"base_token": {"data": {"id": "solana_other"}}},
                                             "attributes": {"base_token_price_usd": "1", "reserve_in_usd": "25000"}}}
    monkeypatch.setattr(bot.session, "get", Mock(return_value=response))
    assert bot.held_pool_fallback(pool, "mint") is None


def test_held_pool_fallback_accepts_verified_base_and_quote(monkeypatch):
    bot._pool_fallback_cache.clear()
    pool = "b" * 44
    response = Mock()
    response.json.return_value = {"data": {"relationships": {"base_token": {"data": {"id": "solana_mint"}}},
                                             "attributes": {"base_token_price_usd": "1.5", "reserve_in_usd": "12000"}}}
    monkeypatch.setattr(bot.session, "get", Mock(return_value=response))
    result = bot.held_pool_fallback(pool, "mint")
    assert result["liquidity"] == 12000
    assert result["price"] == 1.5
    assert result["pool_address"] == pool
    assert result["quote_source"] == "geckoterminal_indicative"


def test_held_pool_fallback_rejects_missing_depth(monkeypatch):
    bot._pool_fallback_cache.clear()
    pool = "c" * 44
    response = Mock()
    response.json.return_value = {"data": {"relationships": {"base_token": {"data": {"id": "solana_mint"}}},
                                             "attributes": {"base_token_price_usd": "1.5", "reserve_in_usd": None}}}
    monkeypatch.setattr(bot.session, "get", Mock(return_value=response))
    assert bot.held_pool_fallback(pool, "mint") is None


def test_sniper_liquidity_buffer(monkeypatch):
    monkeypatch.setattr(bot, "SNIPER_MODE", True)
    pair = {"chainId": "solana", "dexId": "pumpswap", "quoteToken": {"address": bot.SOL_MINT},
            "baseToken": {"address": "mint", "symbol": "TEST"}, "priceUsd": "1",
            "pairCreatedAt": 0, "liquidity": {"usd": 5200}, "volume": {"m5": 10000},
            "txns": {"m5": {"buys": 30, "sells": 20}}, "priceChange": {"m5": 10}}
    reasons = __import__('collections').Counter()
    assert bot.analyze_pair(pair, reasons) is None
    assert reasons["sniper_liquidity_buffer"] == 1 or reasons["too_old"] == 1
