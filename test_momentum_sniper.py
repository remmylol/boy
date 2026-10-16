"""Regression checks for conservative DEX-only momentum-sniping eligibility."""
import time
from datetime import datetime, timedelta, timezone

import pytest
import bot
from quality_pool_discovery import extract_quality_pool_mints

SOL = bot.SOL_MINT
MINT = "TESTSniperToken11111111111111111111111111111"

@pytest.fixture(autouse=True)
def sniper_defaults(monkeypatch):
    monkeypatch.setattr(bot, 'SNIPER_MODE', True)
    monkeypatch.setattr(bot, 'SNIPER_MAX_AGE_MINUTES', 30)
    monkeypatch.setattr(bot, 'SNIPER_MIN_VOLUME_5M_USD', 5000)
    monkeypatch.setattr(bot, 'SNIPER_MIN_BUY_SELL_RATIO', 1.3)
    monkeypatch.setattr(bot, 'SNIPER_MIN_PRICE_CHANGE_5M_PCT', 5)
    monkeypatch.setattr(bot, 'SNIPER_MAX_ENTRY_IMPACT_PCT', 2)
    monkeypatch.setattr(bot, 'POSITION_SIZE_USD', 10)
    monkeypatch.setattr(bot, 'MIN_PAIR_AGE_MINUTES', 1)
    monkeypatch.setattr(bot, 'SNIPER_MIN_TXNS_5M', 12)

def pair(**overrides):
    p = {'chainId': 'solana', 'dexId': 'pumpswap',
         'quoteToken': {'address': SOL},
         'baseToken': {'address': MINT, 'symbol': 'SNIP'},
         'priceUsd': '0.002', 'liquidity': {'usd': 20000},
         'volume': {'m5': 9000, 'h1': 25000},
         'txns': {'m5': {'buys': 18, 'sells': 12}},
         'priceChange': {'m5': 6, 'h1': 8},
         'pairCreatedAt': int((time.time() - 10 * 60) * 1000)}
    p.update(overrides)
    return p

def test_sniper_accepts_matching_market():
    result = bot.analyze_pair(pair())
    assert result and result['estimated_entry_impact_pct'] < 2

def test_sniper_age_max():
    assert bot.analyze_pair(pair(pairCreatedAt=int((time.time()-31*60)*1000))) is None

def test_sniper_volume_minimum():
    assert bot.analyze_pair(pair(volume={'m5': 4999})) is None

def test_sniper_buy_sell_ratio():
    assert bot.analyze_pair(pair(txns={'m5': {'buys': 12, 'sells': 10}})) is None

def test_sniper_min_price_increase():
    assert bot.analyze_pair(pair(priceChange={'m5': 4.99, 'h1': 10})) is None

def test_sniper_impact_limit(monkeypatch):
    monkeypatch.setattr(bot, 'POSITION_SIZE_USD', 250)
    assert bot.analyze_pair(pair()) is None

def test_sniper_requires_supported_sol_pool():
    assert bot.analyze_pair(pair(dexId='raydium')) is None
    assert bot.analyze_pair(pair(quoteToken={'address':'USDC'})) is None

def test_sniper_requires_dex_liquidity():
    assert bot.analyze_pair(pair(liquidity={'usd': 4999})) is None

def test_sniper_quality_discovery_requires_age_volume_and_momentum():
    now = datetime.now(timezone.utc)
    def raw(created, volume='9000', change='6'):
        return {'data': [{'attributes': {
            'pool_created_at': created, 'reserve_in_usd': '20000',
            'volume_usd': {'h1': '25000', 'm5': volume},
            'price_change_percentage': {'m5': change},
            'base_token_price_usd': '0.02'},
            'relationships': {
                'dex': {'data': {'id': 'solana_pump_swap'}},
                'base_token': {'data': {'id': 'solana_'+MINT}},
                'quote_token': {'data': {'id': 'solana_'+SOL}}}}], 'included': []}
    def run(payload):
        return extract_quality_pool_mints(payload, sol_mint=SOL,
            supported_dexes=frozenset({'pumpswap'}),
            min_liquidity_usd=5000, min_volume_1h_usd=10000,
            sniper_max_age_minutes=30, sniper_min_volume_5m_usd=5000,
            sniper_min_change_5m_pct=5)
    assert MINT in run(raw((now-timedelta(minutes=12)).isoformat()))
    assert not run(raw((now-timedelta(minutes=31)).isoformat()))
    assert not run(raw((now-timedelta(minutes=12)).isoformat(), volume='4000'))
    assert not run(raw((now-timedelta(minutes=12)).isoformat(), change='2'))
    assert not run(raw('unavailable'))

def test_paper_only_no_curve_entry(monkeypatch):
    assert bot.SNIPER_MODE
    assert bot.PAPER_MODE
