"""Regression tests for active-but-not-vertical older Solana momentum markets."""
from collections import Counter, OrderedDict
import time
from unittest.mock import patch
import pytest
import bot


def older_pool(**kwargs):
    data = {
        'chainId': 'solana', 'dexId': 'raydium', 'pairAddress': 'X'*44,
        'baseToken': {'address': 'Y'*44, 'symbol': 'OLDER', 'name': 'Established'},
        'quoteToken': {'address': bot.SOL_MINT, 'symbol': 'SOL'},
        'priceUsd': '0.01', 'marketCap': 90000000,
        'liquidity': {'usd': 120000},
        'pairCreatedAt': int((time.time()-86400*185)*1000),
        'volume': {'m5': 1650, 'h1': 40000, 'h6': 120000, 'h24': 500000},
        'priceChange': {'m5': 0.6, 'h1': 3.0, 'h6': 5.5, 'h24': 9.1},
        'txns': {'m5': {'buys': 17, 'sells': 12}},
    }
    data.update(kwargs)
    return data


@pytest.fixture(autouse=True)
def current_continuation(monkeypatch):
    monkeypatch.setattr(bot, 'MOMENTUM_SWING_MODE', True)
    monkeypatch.setattr(bot, 'SNIPER_MODE', False)
    monkeypatch.setattr(bot, 'FAST_MOMENTUM_ENABLED', True)
    monkeypatch.setattr(bot, 'MIN_VOLUME_5M_USD', 1000)  # old Railway setting
    monkeypatch.setattr(bot, 'MOMENTUM_MIN_LIQUIDITY_USD', 15000)
    monkeypatch.setattr(bot, 'MOMENTUM_MIN_VOLUME_5M_USD', 800)
    monkeypatch.setattr(bot, 'MOMENTUM_MIN_VOLUME_1H_USD', 12000)
    monkeypatch.setattr(bot, 'MOMENTUM_MARKET_CAP_MIN_USD', 500000)
    monkeypatch.setattr(bot, 'MOMENTUM_MARKET_CAP_MAX_USD', 250000000)
    monkeypatch.setattr(bot, 'MOMENTUM_MIN_PAIR_AGE_MINUTES', 60)
    monkeypatch.setattr(bot, 'MOMENTUM_MAX_PAIR_AGE_HOURS', 0)
    monkeypatch.setattr(bot, 'MOMENTUM_MIN_CHANGE_5M_PCT', 0.2)
    monkeypatch.setattr(bot, 'MOMENTUM_MAX_CHANGE_5M_PCT', 18)
    monkeypatch.setattr(bot, 'MOMENTUM_MIN_CHANGE_1H_PCT', 2)
    monkeypatch.setattr(bot, 'MOMENTUM_MIN_CHANGE_6H_PCT', 0.5)
    monkeypatch.setattr(bot, 'MOMENTUM_MIN_CHANGE_24H_PCT', 0)
    monkeypatch.setattr(bot, 'MOMENTUM_MIN_TXNS_5M', 8)
    monkeypatch.setattr(bot, 'MOMENTUM_MIN_BUY_SELL_RATIO', 1.05)
    monkeypatch.setattr(bot, 'MOMENTUM_MIN_VOLUME_LIQUIDITY_RATIO', 0.005)


def test_established_90m_old_market_moderate_five_minute_lift():
    c = bot.analyze_pair(older_pool())
    assert c and c['change_m5'] == 0.6 and c['market_cap_usd'] == 90000000
    assert c['age_hours'] > 185*23
    assert c['score'] >= 62


def test_swing_volume_floor_overrides_legacy_min_volume():
    p=older_pool(volume={'m5': 900, 'h1': 30000})
    assert bot.analyze_pair(p) is not None
    reasons=Counter()
    p['volume']['m5']=790
    assert bot.analyze_pair(p,reasons) is None
    assert reasons['momentum_volume'] == 1
    assert reasons['minimum_volume'] == 0


@pytest.mark.parametrize('changes', [
    {'m5': -.5, 'h1': 5, 'h6': 7, 'h24': 10},
    {'m5': 2, 'h1': -1, 'h6': 7, 'h24': 10},
    {'m5': 2, 'h1': 5, 'h6': -3, 'h24': 10},
    {'m5': 2, 'h1': 5, 'h6': 7, 'h24': -5},
    {'m5': 27, 'h1': 20, 'h6': 30, 'h24': 50},
])
def test_no_downtrend_or_mania(changes):
    assert bot.analyze_pair(older_pool(priceChange=changes)) is None


def test_liquidity_and_cap_safety_still_apply():
    assert bot.analyze_pair(older_pool(marketCap=260000000)) is None
    assert bot.analyze_pair(older_pool(liquidity={'usd': 14999})) is None
    assert bot.analyze_pair(older_pool(liquidity={'usd': 0})) is None


def test_verified_watchlist_rechecks_rotate(monkeypatch):
    monkeypatch.setattr(bot, '_verified_dex_mints', OrderedDict())
    monkeypatch.setattr(bot, '_verified_dex_scan_cursor', 0)
    for i in range(8):
        bot.note_verified_dex_mint('mint'+str(i), now=100)
    assert bot.verified_dex_due(now=101, limit=3)==['mint0','mint1','mint2']
    assert bot.verified_dex_due(now=101, limit=3)==['mint3','mint4','mint5']
    assert bot.verified_dex_due(now=101, limit=3)==['mint6','mint7','mint0']


def test_price_confirmation_not_disabled():
    with patch.object(bot,'ENTRY_TREND_CONFIRM_ENABLED',True),patch.object(bot,'ENTRY_TREND_MIN_CHANGE_PCT',0.2):
        mint='continuation-regression'
        bot._candidate_price_history.pop(mint,None)
        assert bot.candidate_momentum_confirm(mint,1,now=1000)[0] is False
        assert bot.candidate_momentum_confirm(mint,0.99,now=1016)[0] is False
        assert bot.candidate_momentum_confirm(mint,1.005,now=1030)[0] is True
