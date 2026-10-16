"""Regression checks for transient DEX gaps and safe curve observation priorities."""
from collections import OrderedDict
import bot


def test_curve_observation_prioritizes_reserves_and_trade_activity(monkeypatch):
    monkeypatch.setattr(bot, '_curve_verified', OrderedDict())
    monkeypatch.setattr(bot, '_curve_real_sol', {})
    monkeypatch.setattr(bot, '_curve_subscriptions', OrderedDict())
    monkeypatch.setattr(bot, 'RPC_TRADE_MINTS_PER_POLL', 2)
    monkeypatch.setattr(bot, 'CURVE_MIN_REAL_SOL_FOR_OBSERVATION', 1.0)
    bot.note_active_curve('dry', 0.0)
    bot.note_active_curve('deep', 12.0)
    assert bot._curve_poll_mints()[0] == 'deep'


def test_verified_pool_retention_when_index_or_fields_missing(monkeypatch):
    # Verify that the scan doesn't delete an observed verified pool merely
    # because DexScreener briefly returns no indexed pairs or null liquidity.
    monkeypatch.setattr(bot, '_verified_dex_mints', OrderedDict())
    monkeypatch.setattr(bot, '_discovery_priority', {})
    bot.note_verified_dex_mint('verified')
    monkeypatch.setattr(bot, '_entry_scan_next_at', 0.0)
    monkeypatch.setattr(bot, 'latest_candidate_addresses', lambda: ['verified'])
    monkeypatch.setattr(bot, 'fresh_launch_snapshot', lambda: [])
    monkeypatch.setattr(bot, 'due_fresh_launches', lambda **kwargs: [])
    monkeypatch.setattr(bot, 'get_json', lambda url: [])
    monkeypatch.setattr(bot, 'PUMP_CURVE_LOOKUP_ENABLED', False)
    monkeypatch.setattr(bot, 'CURVE_ACTIVITY_ENABLED', False)
    monkeypatch.setattr(bot, 'manage_positions', lambda *_: None)
    monkeypatch.setattr(bot, 'roll_day_if_needed', lambda *_: None)
    monkeypatch.setattr(bot, 'should_halt', lambda *_: True)
    state={'positions': {},'cash_usd': 36, 'seen_tokens': [], 'trades': []}
    bot.scan_once(state)
    assert 'verified' in bot._verified_dex_mints
