"""Sniper discovery must not waste slots on unverified generic profile/boost hits."""
from datetime import datetime, timedelta, timezone
import bot
from quality_pool_discovery import extract_quality_pool_mints

SOL = bot.SOL_MINT

def pool(*, buys=18, sells=12, volume=9000, age=10, change=8):
    created = (datetime.now(timezone.utc) - timedelta(minutes=age)).isoformat()
    return {'data': [{'attributes': {'pool_created_at': created, 'reserve_in_usd': '16000',
                 'volume_usd': {'h1': '20000', 'm5': str(volume)},
                 'transactions': {'m5': {'buys': buys, 'sells': sells}},
                 'price_change_percentage': {'m5': str(change)}, 'base_token_price_usd': '0.002'},
                 'relationships': {'dex': {'data': {'id': 'solana_pump_swap'}},
                 'base_token': {'data': {'id': 'solana_SNIPER1'}},
                 'quote_token': {'data': {'id': 'solana_'+SOL}}}}]}

def parse(payload):
    return extract_quality_pool_mints(payload, sol_mint=SOL,
             supported_dexes=frozenset({'pumpswap'}), min_liquidity_usd=5000,
             min_volume_1h_usd=0, sniper_max_age_minutes=30,
             sniper_min_volume_5m_usd=5000, sniper_min_change_5m_pct=5,
             sniper_min_buy_sell_ratio=1.3, sniper_min_txns_5m=12,
             sniper_max_change_5m_pct=80, sniper_min_age_minutes=1)

def test_sniper_source_rejects_weak_trade_flow():
    assert 'SNIPER1' in parse(pool())
    assert not parse(pool(buys=12, sells=12))
    assert not parse(pool(buys=4, sells=2))
    assert not parse(pool(buys=12, sells=0))
    assert not parse(pool(buys=18, sells=12, volume=4999))

def test_sniper_source_age_and_spike_limits():
    assert not parse(pool(age=31))
    assert not parse(pool(age=0.5))
    assert not parse(pool(change=81))

def test_sniper_source_missing_transaction_metadata_fails_closed():
    p=pool()
    p['data'][0]['attributes'].pop('transactions')
    assert not parse(p)

def test_sniper_scan_selects_only_prequalified_verified_and_fresh(monkeypatch):
    monkeypatch.setattr(bot,'SNIPER_MODE',True)
    monkeypatch.setattr(bot,'_quality_pool_mints',['quality1','quality2'])
    monkeypatch.setattr(bot,'_verified_dex_mints',bot.OrderedDict())
    monkeypatch.setattr(bot,'_entry_reject_until',bot.OrderedDict())
    monkeypatch.setattr(bot,'_entry_reject_reason',{})
    monkeypatch.setattr(bot,'SNIPER_LAUNCH_PROBE_QUOTA',2)
    monkeypatch.setattr(bot,'FRESH_LAUNCH_SCAN_QUOTA',24)
    monkeypatch.setattr(bot.time,'monotonic',lambda:100)
    bot.note_verified_dex_mint('verified',now=100)
    got, _, fresh = bot.select_entry_mints(['garbageA','garbageB','quality1','verified'],
                   ['newA','newB','newC'], count=20,cursor=0)
    assert got == ['quality1','quality2','verified','newA','newB']
    assert fresh == 2

def test_sniper_scan_cooldown_never_makes_unverified_eligible(monkeypatch):
    monkeypatch.setattr(bot,'SNIPER_MODE',True)
    monkeypatch.setattr(bot,'_quality_pool_mints',['qualified'])
    monkeypatch.setattr(bot,'_verified_dex_mints',bot.OrderedDict())
    monkeypatch.setattr(bot,'_entry_reject_until',bot.OrderedDict())
    monkeypatch.setattr(bot,'_entry_reject_reason',{})
    monkeypatch.setattr(bot.time,'monotonic',lambda:100)
    bot.note_entry_rejection('qualified','supported_pair_liquidity_unavailable',now=100)
    got, _, _ = bot.select_entry_mints(['qualified','garbage'],[],count=20,cursor=0)
    assert got == []
