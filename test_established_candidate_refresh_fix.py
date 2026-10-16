"""Verify established markets are discovered, rechecked, but not rescanned on every tick after failures."""
from collections import Counter, OrderedDict
from unittest.mock import patch
from quality_pool_discovery import extract_quality_pool_mints
import bot


def test_momentum_cooldown_survives_renewed_verified_liquidity(monkeypatch):
    monkeypatch.setattr(bot, 'MOMENTUM_SWING_MODE', True)
    monkeypatch.setattr(bot, '_verified_dex_mints', OrderedDict())
    monkeypatch.setattr(bot, '_entry_reject_until', OrderedDict())
    monkeypatch.setattr(bot, '_entry_reject_reason', {})
    monkeypatch.setattr(bot, '_verified_dex_scan_cursor', 0)
    bot.note_verified_dex_mint('A', now=100)
    bot.note_verified_dex_mint('B', now=100)
    bot.note_entry_rejection('A', 'momentum_volume', now=100)
    bot.note_verified_dex_mint('A', now=110)  # refreshed pool should not erase rejection
    assert bot.mint_cooling_down('A', now=111)
    assert bot.verified_dex_due(now=111, limit=2)==['B']
    assert set(bot.verified_dex_due(now=450, limit=2)) == {'A', 'B'}


def test_momentum_quality_pool_shortlisting_skips_explicit_small_cap():
    def row(mint, cap):
        return {'attributes': {'reserve_in_usd':'125000', 'base_token_price_usd':'0.01',
                                'volume_usd':{'h1':'60000'}, 'market_cap_usd':cap,
                                'price_change_percentage':{'m5':1, 'h1':6, 'h6':9, 'h24':12}},
                'relationships':{'dex':{'data':{'id':'solana_raydium'}},
                                 'base_token':{'data':{'id':'solana_'+mint}},
                                 'quote_token':{'data':{'id':'solana_'+bot.SOL_MINT}}}}
    data={'data':[row('small','200000'),row('large','8000000'),row('unknown',None)]}
    rejected=Counter()
    scores=extract_quality_pool_mints(data,sol_mint=bot.SOL_MINT,
        supported_dexes=frozenset({'raydium'}),min_liquidity_usd=15000,
        min_volume_1h_usd=12000,discovery_stage='continuation',
        discovery_min_market_cap_usd=500000,rejection_counts=rejected)
    assert 'small' not in scores and {'large','unknown'} <= set(scores)
    assert rejected['below_established_cap'] == 1


def test_top_pool_discovery_is_additional_and_rate_limited(monkeypatch):
    monkeypatch.setattr(bot, 'MOMENTUM_SWING_MODE', True)
    monkeypatch.setattr(bot, 'SNIPER_MODE', False)
    monkeypatch.setattr(bot, 'MOMENTUM_TRENDING_POOL_PAGES', 5)
    monkeypatch.setattr(bot, 'MOMENTUM_TOP_POOL_PAGES', 2)
    monkeypatch.setattr(bot, 'QUALITY_POOL_DISCOVERY_ENABLED', True)
    monkeypatch.setattr(bot, '_quality_cache', {'until':0,'mints':[],'scores':{}})
    requests=[]
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'data':[]}
    def fake_get(url,**kw):
        requests.append((url,kw['params']))
        return Response()
    with patch.object(bot.session,'get',fake_get):
        bot.quality_pool_candidates()
    assert len(requests)==7
    assert len([x for x,_ in requests if x.endswith('/trending_pools')])==5
    assert len([x for x,_ in requests if x.endswith('/pools')])==2
    assert all(params['order']=='h24_volume_usd_desc' for url,params in requests if url.endswith('/pools'))
