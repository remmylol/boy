import time
import bot


def pair(**overrides):
    p = {
        "baseToken": {"address": "testmint", "symbol": "TEST"},
        "priceUsd": "1", "liquidity": {"usd": 80000},
        "volume": {"m5": 20000, "h1": 50000, "h24": 100000},
        "txns": {"m5": {"buys": 50, "sells": 25}},
        "priceChange": {"m5": 7, "h1": 10},
        "pairCreatedAt": int((time.time() - 3600) * 1000),
    }
    p.update(overrides)
    return p


def test_fast_momentum_accepts():
    assert bot.analyze_pair(pair()) is not None


def test_fast_momentum_rejects_low_volume():
    assert bot.analyze_pair(pair(volume={"m5": 1000})) is None


def test_fast_momentum_rejects_flat_price():
    assert bot.analyze_pair(pair(priceChange={"m5": 0})) is None


def test_fast_momentum_rejects_sell_pressure():
    assert bot.analyze_pair(pair(txns={"m5": {"buys": 20, "sells": 40}})) is None


def test_fast_momentum_rejects_extreme_spike():
    assert bot.analyze_pair(pair(priceChange={"m5": 45})) is None


def test_time_limit_closes_stale_position(monkeypatch):
    state = {"cash_usd": 21.0, "positions": {}, "closed_trades": [], "seen_tokens": [], "halted": False}
    bot.paper_buy(state, {"address": "mint", "symbol": "TEST", "name": "Test", "price": 1, "score": 90})
    state["positions"]["mint"]["opened_at"] -= 16 * 60
    bot.manage_positions(state, {"mint": {"price": 1, "liquidity": 100000}})
    assert state["closed_trades"][0]["reason"] == "time_limit"
