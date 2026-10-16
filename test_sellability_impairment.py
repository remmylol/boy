from unittest.mock import patch
import bot


def pair(liq=20000, addr='pool1', quote=None):
    return {'pairAddress': addr, 'chainId': 'solana', 'dexId': 'pumpswap',
            'baseToken': {'address': 'mint'}, 'quoteToken': {'address': quote or bot.SOL_MINT},
            'priceUsd': '1', 'liquidity': {'usd': liq}}


def candidate():
    return {'address': 'mint', 'pool_address': 'pool1', 'symbol': 'TEST',
            'name': 'Test', 'price': 1, 'score': 90}


def test_prebuy_quote_matching_pool():
    assert bot.paper_prebuy_sellability(candidate(), [pair()])[0]


def test_prebuy_rejects_other_pool_and_unsupported_quote():
    assert not bot.paper_prebuy_sellability(candidate(), [pair(addr='other')])[0]
    assert not bot.paper_prebuy_sellability(candidate(), [pair(quote='notSOL')])[0]


def test_prebuy_rejects_low_liquidity_and_stale_price():
    assert not bot.paper_prebuy_sellability(candidate(), [pair(liq=5100)])[0]
    changed = pair(); changed['priceUsd'] = '1.5'
    assert not bot.paper_prebuy_sellability(candidate(), [changed])[0]


def test_prebuy_fails_closed_on_api_error():
    with patch.object(bot, 'token_pairs', side_effect=ConnectionError('offline')):
        assert not bot.paper_prebuy_sellability(candidate())[0]


def test_impairment_does_not_erase_open_position_or_fabricate_sell():
    s = {'cash_usd': 26, 'positions': {'mint': {
        'token': 'mint', 'symbol': 'Atomcrn', 'name': 'Atomcrn',
        'entry_price': 1, 'amount_usd': 10, 'token_units': 10,
        'opened_at': 1000, 'peak_price': 1, 'last_price': 2, 'score': 80,
        'last_price_at': 1000}}, 'closed_trades': [], 'halted': False}
    with patch.object(bot.time, 'time', return_value=1100):
        bot.note_unavailable_exit(s, 'mint', 'Atomcrn', 'no_liquidity')
    with patch.object(bot.time, 'time', return_value=1170):
        bot.note_unavailable_exit(s, 'mint', 'Atomcrn', 'no_liquidity')
        bot.note_unavailable_exit(s, 'mint', 'Atomcrn', 'no_liquidity')
    assert s['exit_issues']['mint']['status'] == 'IMPAIRED_EXIT_UNAVAILABLE'
    assert bot.equity(s) == 26
    assert s['cash_usd'] == 26 and 'mint' in s['positions'] and not s['closed_trades']
    assert s['halted']
    with patch.object(bot.time, 'time', return_value=1171):
        bot.clear_exit_issue(s, 'mint', 'Atomcrn')
    assert bot.equity(s) == 46
    assert s['halted']
