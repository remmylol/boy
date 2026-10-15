import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os
import pytest
import live_adapter


def test_live_trading_defaults_off(monkeypatch):
    monkeypatch.delenv("LIVE_TRADING_ENABLED", raising=False)
    with pytest.raises(live_adapter.LiveAdapterError, match="LIVE_TRADING_ENABLED"):
        live_adapter.execute_trade("buy", "11111111111111111111111111111111", 0.01, True)


def test_rejects_bad_action():
    with pytest.raises(live_adapter.LiveAdapterError, match="action"):
        live_adapter.validate_trade("swap", "11111111111111111111111111111111", 0.01, True, 3.0, 0.00005, 0.15)


def test_rejects_buy_over_cap():
    with pytest.raises(live_adapter.LiveAdapterError, match="buy size"):
        live_adapter.validate_trade("buy", "11111111111111111111111111111111", 0.151, True, 3.0, 0.00005, 0.15)


def test_rejects_high_slippage():
    with pytest.raises(live_adapter.LiveAdapterError, match="slippage"):
        live_adapter.validate_trade("buy", "11111111111111111111111111111111", 0.01, True, 6.0, 0.00005, 0.15)


def test_rejects_buy_not_in_sol():
    with pytest.raises(live_adapter.LiveAdapterError, match="buys must"):
        live_adapter.validate_trade("buy", "11111111111111111111111111111111", 0.01, False, 3.0, 0.00005, 0.15)


def test_rejects_partial_sell():
    with pytest.raises(live_adapter.LiveAdapterError, match="100%"):
        live_adapter.validate_trade("sell", "11111111111111111111111111111111", "50%", False, 3.0, 0.00005, 0.15)


def test_rejects_invalid_mint(monkeypatch):
    pytest.importorskip("solders")
    with pytest.raises(live_adapter.LiveAdapterError, match="valid Solana"):
        live_adapter.validate_trade("buy", "not-a-mint", 0.01, True, 3.0, 0.00005, 0.15)
