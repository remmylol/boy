"""Regression checks for 2026-10-16 no-trades diagnosis (paper only)."""
from collections import Counter, OrderedDict
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import bot
from quality_pool_discovery import extract_quality_pool_mints


def pair(mint, age_minutes, liquidity=18000, dex='pumpswap', quote=None):
    return {
        'chainId': 'solana', 'dexId': dex,
        'baseToken': {'address': mint, 'symbol': 'TEST'},
        'quoteToken': {'address': quote or bot.SOL_MINT},
        'priceUsd': '0.01', 'liquidity': {'usd': liquidity},
        'pairAddress': mint+'-pool',
        'pairCreatedAt': (bot.time.time() - age_minutes * 60) * 1000,
        'volume': {'m5': 7000, 'h1': 20000},
        'txns': {'m5': {'buys': 20, 'sells': 10}},
        'priceChange': {'m5': 10, 'h1': 14}
    }


def test_fresh_pool_wins_over_older_deeper_pool():
    mint='fresh-mint'
    with patch.object(bot, 'SNIPER_MODE', True), patch.object(bot, 'SNIPER_MAX_AGE_MINUTES', 45):
        latest=pair(mint, 7, liquidity=10000)
        old=pair(mint, 120, liquidity=200000)
        assert bot.best_entry_pair([old, latest]) is latest
        assert bot.analyze_pair(bot.best_entry_pair([old, latest])) is not None


def test_liquidity_and_routes_remain_hard_blockers():
    with patch.object(bot, 'SNIPER_MODE', True):
        assert bot.best_entry_pair([pair('mint', 5, liquidity=1000)]) is None
        assert bot.best_entry_pair([pair('mint', 5, dex='raydium')]) is None
        assert bot.best_entry_pair([pair('mint', 5, quote='usdc')]) is None


def test_old_verified_mint_is_retired_and_cools_down():
    with patch.object(bot, 'SNIPER_MODE', True), \
         patch.object(bot, '_verified_dex_mints', OrderedDict()), \
         patch.object(bot, '_sniper_watchlist', OrderedDict()), \
         patch.object(bot, '_entry_reject_until', OrderedDict()), \
         patch.object(bot, '_entry_reject_reason', {}), \
         patch.object(bot, 'SNIPER_MAX_AGE_MINUTES', 45):
        bot.note_verified_dex_mint('stale')
        bot.update_sniper_watchlist({'stale': 1})
        assert not bot.retain_fresh_verified_pool('stale', pair('stale', 80))
        assert 'stale' not in bot._verified_dex_mints
        assert 'stale' not in bot._sniper_watchlist
        assert bot.mint_cooling_down('stale')
        assert 'stale' not in bot.verified_dex_due()
        assert 'stale' not in bot.sniper_watchlist_due()


def test_quality_sources_prioritized_over_wide_stale_board():
    with patch.object(bot, 'SNIPER_MODE', True), \
         patch.object(bot, '_quality_pool_mints', ['new-quality']), \
         patch.object(bot, '_sniper_watchlist', OrderedDict()), \
         patch.object(bot, '_verified_dex_mints', OrderedDict()), \
         patch.object(bot, '_entry_reject_until', OrderedDict()), \
         patch.object(bot, '_entry_reject_reason', {}):
        bot.update_sniper_watchlist({f'old-{i}': 1 for i in range(35)})
        bot.update_sniper_watchlist({'new-quality': 100})
        got, _, _ = bot.select_entry_mints([], [], count=10, cursor=0)
        assert got[0] == 'new-quality'
        assert len(got) == len(set(got)) == 10


def test_missing_key_never_attempts_websocket():
    with patch.object(bot, 'PUMPPORTAL_API_KEY', ''), \
         patch.object(bot, '_feed_status', 'not_started'), \
         patch.object(bot.time, 'sleep', side_effect=AssertionError('unnecessary reconnect')), \
         patch.object(bot, '_feed_reconnects', 0):
        bot._fresh_launch_worker()
        assert bot._feed_status == 'missing_api_key'
        assert bot._feed_reconnects == 0


def test_missing_age_rejected_not_misidentified_as_old():
    p = pair('mint', 4)
    p.pop('pairCreatedAt')
    with patch.object(bot, 'SNIPER_MODE', True):
        rejected=Counter()
        assert bot.analyze_pair(p, rejected) is None
        assert rejected['missing_pair_age'] == 1


def test_quality_source_reasons_visible_without_loosening():
    created=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
    payload={'data':[{'attributes':{'pool_created_at':created,'reserve_in_usd':'100','base_token_price_usd':'0.01', 'volume_usd':{'m5':'5000','h1':'8000'}},
                      'relationships':{'dex':{'data':{'id':'solana_pump_swap'}},
                                       'base_token':{'data':{'id':'solana_test'}},
                                       'quote_token':{'data':{'id':'solana_'+bot.SOL_MINT}}}}]}
    reasons=Counter()
    found=extract_quality_pool_mints(payload, sol_mint=bot.SOL_MINT,
                    supported_dexes=frozenset({'pumpswap'}),
                    min_liquidity_usd=5000, min_volume_1h_usd=0,
                    sniper_max_age_minutes=45, discovery_stage='watch',
                    rejection_counts=reasons)
    assert not found
    assert reasons['below_minimum_liquidity'] == 1
