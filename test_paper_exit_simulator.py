import bot


def make_state():
    return {"cash_usd": 21.0, "positions": {}, "closed_trades": [], "seen_tokens": [], "halted": False}


def candidate():
    return {"address": "mint", "symbol": "TEST", "name": "Test", "price": 1.0, "score": 90.0}


def test_paper_buy_and_take_profit_sell_without_network(monkeypatch):
    state = make_state()
    bot.paper_buy(state, candidate())
    assert "mint" in state["positions"]
    bot.manage_positions(state, {"mint": {"price": 1.8, "liquidity": 100000}})
    assert "mint" not in state["positions"]
    assert state["closed_trades"][0]["reason"] == "take_profit"
    assert state["closed_trades"][0]["execution"] == "paper_estimate_only"
    assert state["cash_usd"] > 21


def test_stop_loss():
    state = make_state()
    bot.paper_buy(state, candidate())
    bot.manage_positions(state, {"mint": {"price": .5, "liquidity": 100000}})
    assert state["closed_trades"][0]["reason"] == "stop_loss"


def test_missing_liquidity_blocks_exit_and_halts_entries():
    state = make_state()
    bot.paper_buy(state, candidate())
    bot.manage_positions(state, {"mint": {"price": 2, "liquidity": 0}})
    assert "mint" in state["positions"]
    assert state["halted"] is True


def test_low_liquidity_blocks_exit():
    state = make_state()
    bot.paper_buy(state, candidate())
    bot.manage_positions(state, {"mint": {"price": 2, "liquidity": 20}})
    assert "mint" in state["positions"]
    assert state["halted"] is True


def test_paper_quote_includes_impact():
    state = make_state()
    bot.paper_buy(state, candidate())
    pos = bot.Position(**state["positions"]["mint"])
    quote = bot.paper_exit_quote(pos, 1, 10000)
    assert quote["proceeds_usd"] < pos.token_units
    assert quote["impact_pct"] > 0
