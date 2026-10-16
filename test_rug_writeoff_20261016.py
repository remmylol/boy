"""Offline regression tests for zero-recovery rug accounting and halt release."""
from datetime import date
from unittest.mock import patch

import bot


MINT = 'r' * 44
POOL = 'p' * 44


def state():
    return {
        'cash_usd': 26.0, 'positions': {MINT: {
            'token': MINT, 'symbol': 'RUG', 'name': 'RUG', 'entry_price': 1.0,
            'amount_usd': 10.0, 'token_units': 10.0, 'opened_at': 1000.,
            'peak_price': 1.0, 'last_price': 1.0, 'score': 80.,
            'last_price_at': 1000., 'entry_pool_address': POOL, 'entry_pool_dex': 'pumpswap',
        }}, 'closed_trades': [], 'day': str(date.today()), 'day_start_equity': 36.0,
        'seen_tokens': [MINT], 'halted': False, 'exit_issues': {}, 'paper_trade_metrics': {},
    }


def evidence():
    return {'verified': True, 'reason': 'pinned_pool_missing_no_liquid_alternative'}


def test_writeoff_requires_successful_primary_checks_and_time(monkeypatch):
    s = state()
    monkeypatch.setattr(bot, 'PAPER_RUG_WRITEOFF_ENABLED', True)
    monkeypatch.setattr(bot, 'PAPER_RUG_WRITEOFF_AFTER_SECONDS', 300)
    monkeypatch.setattr(bot, 'PAPER_RUG_WRITEOFF_MIN_CHECKS', 3)
    # No evidence: missing data is not a rug.
    with patch.object(bot.time, 'time', return_value=1000):
        bot.manage_positions(s, {MINT: {'price': 1, 'liquidity': 0}})
    assert MINT in s['positions']
    assert s['exit_issues'][MINT]['checks'] == 1
    for instant in (1100, 1200):
        with patch.object(bot.time, 'time', return_value=instant):
            bot.manage_positions(s, {MINT: {'price': 1, 'liquidity': 0}}, {MINT: evidence()})
    assert MINT in s['positions']
    # Healthy confirmed observations are required even after 5 minutes.
    with patch.object(bot.time, 'time', return_value=1300):
        bot.manage_positions(s, {MINT: {'price': 1, 'liquidity': 0}}, {MINT: evidence()})
    assert MINT not in s['positions']
    record = s['closed_trades'][0]
    assert record['pnl_usd'] == -10.0 and record['pnl_pct'] == -100.0
    assert record['proceeds_usd'] == 0.0 and record['exit_price'] == 0.0
    assert record['execution'] == 'paper_writeoff_no_sale'
    assert record['status'] == 'closed_writeoff'
    assert MINT in s['rugged_mints']
    assert s['cash_usd'] == 26.0
    assert bot.equity(s) == 26.0
    assert not s['exit_issues'] and not s['halted']
    assert bot.paper_reentry_decision(s, MINT, now=10000)[1] == 'rug_writeoff_blacklisted'
    # A direct buy attempt cannot bypass the blacklist either.
    bot.paper_buy(s, {'address': MINT, 'symbol': 'RUG', 'name': 'RUG',
                      'price': 1.0, 'score': 95., 'pool_address': POOL})
    assert s['positions'] == {}


def test_no_writeoff_if_api_unhealthy_or_alternative_depth_exists(monkeypatch):
    p = bot.Position(**state()['positions'][MINT])
    assert not bot.pinned_pool_liquidity_evidence(p, [], primary_healthy=False)['verified']
    other = {'chainId': 'solana', 'dexId': 'pumpswap', 'pairAddress': 'q' * 44,
             'baseToken': {'address': MINT}, 'quoteToken': {'address': bot.SOL_MINT},
             'priceUsd': '1', 'liquidity': {'usd': '20000'}}
    assert bot.pinned_pool_liquidity_evidence(p, [other], primary_healthy=True)['reason'] == 'alternative_liquid_sol_pool_found'
    assert bot.pinned_pool_liquidity_evidence(p, [{'chainId': 'solana', 'dexId': 'pumpswap',
        'pairAddress': POOL, 'baseToken': {'address': MINT},
        'quoteToken': {'address': bot.SOL_MINT}, 'priceUsd': '1',
        'liquidity': {'usd': None}}], primary_healthy=True)['verified'] is False
    s = state()
    with patch.object(bot.time, 'time', return_value=1000):
        bot.note_unavailable_exit(s, MINT, 'RUG', 'stale_or_missing_price')
    with patch.object(bot.time, 'time', return_value=2000):
        assert not bot.maybe_write_off_rugged_position(s, MINT, {'verified': False})
    assert MINT in s['positions']


def test_rug_writeoff_does_not_clear_unrelated_manual_or_daily_halt(monkeypatch):
    monkeypatch.setattr(bot, 'PAPER_RUG_WRITEOFF_ENABLED', True)
    monkeypatch.setattr(bot, 'PAPER_RUG_WRITEOFF_MIN_CHECKS', 2)
    monkeypatch.setattr(bot, 'PAPER_RUG_WRITEOFF_AFTER_SECONDS', 60)
    for mode in ('manual', 'daily'):
        s = state()
        if mode == 'manual':
            s['halted'] = True
        else:
            s['day_start_equity'] = 60.0  # 34/60 lost after writeoff > 50% threshold
        with patch.object(bot.time, 'time', return_value=1000):
            bot.manage_positions(s, {MINT: {'price': 1, 'liquidity': 0}}, {MINT: evidence()})
        with patch.object(bot.time, 'time', return_value=1100):
            bot.manage_positions(s, {MINT: {'price': 1, 'liquidity': 0}}, {MINT: evidence()})
        assert s['closed_trades'][0]['execution'] == 'paper_writeoff_no_sale'
        assert s['halted']


def test_legacy_exit_issue_with_checks_120_is_recovered_from_saved_state(monkeypatch):
    monkeypatch.setattr(bot, 'PAPER_RUG_WRITEOFF_ENABLED', True)
    monkeypatch.setattr(bot, 'PAPER_RUG_WRITEOFF_MIN_CHECKS', 2)
    monkeypatch.setattr(bot, 'PAPER_RUG_WRITEOFF_AFTER_SECONDS', 300)
    s = state()
    s['halted'] = True
    s['exit_issues'] = {MINT: {'status': 'IMPAIRED_EXIT_UNAVAILABLE',
                              'reason': 'primary_pool_quote_missing_fallback_valuation_only',
                              'checks': 120, 'first_seen_at': 1000., 'last_logged_at': 1000.}}
    with patch.object(bot.time, 'time', return_value=1400):
        bot.manage_positions(s, {MINT: {'price': 1.0, 'liquidity': 2000.,
                                       'quote_source': 'geckoterminal_indicative'}},
                             {MINT: evidence()})
    assert MINT in s['positions']
    with patch.object(bot.time, 'time', return_value=1405):
        bot.manage_positions(s, {MINT: {'price': 1.0, 'liquidity': 2000.,
                                       'quote_source': 'geckoterminal_indicative'}},
                             {MINT: evidence()})
    assert MINT not in s['positions']
    assert s['closed_trades'][0]['rug_evidence']['healthy_pool_checks'] == 2
    assert not s['halted']


def test_quote_recovery_still_requires_review():
    s = state()
    with patch.object(bot.time, 'time', return_value=1100):
        bot.manage_positions(s, {MINT: {'price': 1, 'liquidity': 0}})
    with patch.object(bot.time, 'time', return_value=1105):
        bot.manage_positions(s, {MINT: {'price': 1, 'liquidity': 20000}})
    assert s['exit_recovery_review_required'] and s['halted']
    assert MINT in s['positions'] and not s['closed_trades']


def test_pinned_pool_zero_depth_qualifies_but_small_nonzero_does_not():
    pos = bot.Position(**state()['positions'][MINT])
    pair = {'chainId': 'solana', 'dexId': 'pumpswap', 'pairAddress': POOL,
            'baseToken': {'address': MINT}, 'quoteToken': {'address': bot.SOL_MINT},
            'priceUsd': '1', 'liquidity': {'usd': 0}}
    assert bot.pinned_pool_liquidity_evidence(pos, [pair], primary_healthy=True)['verified']
    pair['liquidity']['usd'] = 100
    assert not bot.pinned_pool_liquidity_evidence(pos, [pair], primary_healthy=True)['verified']


def test_full_scan_retires_stuck_fallback_only_rug_and_resumes(monkeypatch):
    """Run actual scanning code with mocked fresh Dex responses; no HTTP calls."""
    s = state()
    s['halted'] = True
    s['exit_issues'] = {MINT: {'status': 'IMPAIRED_EXIT_UNAVAILABLE',
                              'first_seen_at': 1000., 'checks': 120,
                              'reason': 'primary_pool_quote_missing_fallback_valuation_only',
                              'last_logged_at': 1000.}}
    monkeypatch.setattr(bot, 'PAPER_RUG_WRITEOFF_ENABLED', True)
    monkeypatch.setattr(bot, 'PAPER_RUG_WRITEOFF_AFTER_SECONDS', 300)
    monkeypatch.setattr(bot, 'PAPER_RUG_WRITEOFF_MIN_CHECKS', 3)
    monkeypatch.setattr(bot, '_entry_scan_next_at', bot.time.monotonic() + 100000)
    monkeypatch.setattr(bot, 'get_json', lambda url, timeout=12: [])
    monkeypatch.setattr(bot, 'held_pool_fallback', lambda *args: {
        'price': 1.0, 'liquidity': 5000,
        'pool_address': POOL, 'quote_source': 'geckoterminal_indicative'})
    saves = []
    monkeypatch.setattr(bot, 'save_state', lambda state: saves.append(len(state['positions'])))
    for now in (1400, 1405, 1410):
        with patch.object(bot.time, 'time', return_value=now):
            bot.scan_once(s)
    assert len(s['closed_trades']) == 1
    assert s['closed_trades'][0]['pnl_usd'] == -10.0
    assert s['closed_trades'][0]['execution'] == 'paper_writeoff_no_sale'
    assert saves == [1, 1, 0]
    assert s['halted'] is False
