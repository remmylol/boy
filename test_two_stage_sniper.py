"""Stage-1 discovery must not waive Stage-2 sniper entry requirements."""
from datetime import datetime, timedelta, timezone
import bot
from quality_pool_discovery import extract_quality_pool_mints


def payload(age=8, volume=0, change=None, buys=0, sells=0, liq=12000, dex='pump_swap'):
    created=(datetime.now(timezone.utc)-timedelta(minutes=age)).isoformat()
    return {'data': [{'attributes': {
        'pool_created_at': created, 'reserve_in_usd': str(liq),
        'base_token_price_usd': '0.0001',
        'volume_usd': {'h1': '0', 'm5': str(volume)},
        'price_change_percentage': {'m5': change},
        'transactions': {'m5': {'buys': buys,'sells': sells}}},
        'relationships': {'dex': {'data': {'id':'solana_'+dex}},
        'base_token': {'data': {'id':'solana_MINTX'}},
        'quote_token': {'data': {'id':'solana_'+bot.SOL_MINT}}}}]}


def discover(p, stage='watch'):
    return extract_quality_pool_mints(p,sol_mint=bot.SOL_MINT,
        supported_dexes=frozenset({'pumpswap'}),min_liquidity_usd=5000,
        min_volume_1h_usd=0,sniper_max_age_minutes=30,
        sniper_min_volume_5m_usd=5000,sniper_min_change_5m_pct=5,
        sniper_min_buy_sell_ratio=1.3,sniper_min_txns_5m=12,
        discovery_stage=stage)


def test_stage1_admits_young_liquid_pool_before_momentum():
    p=payload()
    assert 'MINTX' in discover(p)
    assert 'MINTX' not in discover(p,'strict')


def test_stage1_never_admits_old_illiquid_or_unsupported_pool():
    assert discover(payload(age=31)) == {}
    assert discover(payload(liq=4999)) == {}
    assert discover(payload(dex='raydium')) == {}


def test_watchlist_rotates_and_expires(monkeypatch):
    monkeypatch.setattr(bot,'_sniper_watchlist',bot.OrderedDict())
    monkeypatch.setattr(bot,'_sniper_watch_cursor',0)
    monkeypatch.setattr(bot,'_entry_reject_until',bot.OrderedDict())
    monkeypatch.setattr(bot,'_entry_reject_reason',{})
    monkeypatch.setattr(bot,'SNIPER_WATCHLIST_TTL_SECONDS',60)
    bot.update_sniper_watchlist({'a':1,'b':2,'c':3},now=100)
    assert bot.sniper_watchlist_due(now=101,limit=2)==['a','b']
    assert bot.sniper_watchlist_due(now=102,limit=2)==['c','a']
    assert bot.sniper_watchlist_due(now=161,limit=2)==[]


def test_watchlist_respects_cooldowns(monkeypatch):
    monkeypatch.setattr(bot,'_sniper_watchlist',bot.OrderedDict())
    monkeypatch.setattr(bot,'_entry_reject_until',bot.OrderedDict())
    monkeypatch.setattr(bot,'_entry_reject_reason',{})
    bot.update_sniper_watchlist({'a':1,'b':2},now=100)
    bot.note_entry_rejection('a','supported_pair_missing_price',now=100)
    assert bot.sniper_watchlist_due(now=101,limit=2)==['b']


def test_stage2_never_approves_missing_momentum(monkeypatch):
    monkeypatch.setattr(bot,'SNIPER_MODE',True)
    pair={'baseToken':{'address':'MINTX','symbol':'X'},
          'quoteToken':{'address':bot.SOL_MINT},'chainId':'solana',
          'dexId':'pumpswap','priceUsd':'0.0001','liquidity':{'usd':12000},
          'volume':{'m5':0},'txns':{'m5':{'buys':0,'sells':0}},
          'priceChange':{'m5':0},
          'pairCreatedAt':int((datetime.now(timezone.utc)-timedelta(minutes=8)).timestamp()*1000)}
    assert bot.analyze_pair(pair) is None
