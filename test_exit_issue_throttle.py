import logging
from unittest.mock import patch
import bot


def state():
    return {"cash_usd": 26.0, "positions": {"mintA": {
        "token": "mintA", "symbol": "Taylor", "name": "Taylor",
        "entry_price": 1.0, "amount_usd": 10.0, "token_units": 10.0,
        "opened_at": 1_000.0, "peak_price": 1.0, "last_price": 1.0,
        "score": 77.0, "last_price_at": 1_000.0,
    }}, "closed_trades": [], "halted": False}


def test_missing_liquidity_preserves_position_and_throttles(caplog):
    s = state()
    with caplog.at_level(logging.ERROR), patch.object(bot.time, 'time', return_value=1100):
        for _ in range(12):
            bot.manage_positions(s, {"mintA": {"price": 1.0, "liquidity": 0.0}})
    assert s['halted'] is True
    assert s['cash_usd'] == 26.0
    assert len(s['positions']) == 1
    assert s['closed_trades'] == []
    assert s['exit_issues']['mintA']['checks'] == 12
    assert s['exit_issues']['mintA']['status'] == 'EXIT_UNAVAILABLE'
    assert sum('PAPER EXIT UNAVAILABLE' in r.message for r in caplog.records) == 1
    with caplog.at_level(logging.ERROR), patch.object(bot.time, 'time', return_value=1161):
        bot.manage_positions(s, {"mintA": {"price": 1.0, "liquidity": 0.0}})
    assert sum('PAPER EXIT UNAVAILABLE' in r.message for r in caplog.records) == 2


def test_price_recovery_clears_issue_but_not_halt():
    s = state()
    with patch.object(bot.time, 'time', return_value=1050):
        bot.manage_positions(s, {"mintA": {"price": 1.0, "liquidity": 0.0}})
    with patch.object(bot.time, 'time', return_value=1051):
        bot.manage_positions(s, {"mintA": {"price": 1.0, "liquidity": 10000.0}})
    assert s['exit_issues'] == {}
    assert s['halted'] is True
    assert 'mintA' in s['positions']


def test_missing_price_after_stale_threshold_records_issue():
    s = state()
    with patch.object(bot.time, 'time', return_value=1100):
        bot.manage_positions(s, {})
    assert s['exit_issues']['mintA']['reason'] == 'stale_or_missing_price'
    assert s['halted'] is True
