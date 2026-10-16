"""Run historical sniper regression tests against their original strategy preset.

New tests in test_established_momentum.py opt into the changed default explicitly.
The deployed bot still defaults to MOMENTUM_SWING_MODE=true.
"""
import pytest
import bot


@pytest.fixture(autouse=True)
def _legacy_strategy_compatibility(request, monkeypatch):
    if request.module.__name__ == "test_established_momentum":
        return
    monkeypatch.setattr(bot, "MOMENTUM_SWING_MODE", False)
    monkeypatch.setattr(bot, "SNIPER_MODE", True)
    monkeypatch.setattr(bot, "MAX_HOLD_MINUTES", 5)
    monkeypatch.setattr(bot, "CURVE_ACTIVITY_ENABLED", True)
