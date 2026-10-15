import bot

MINT = '7BGgw7k7WteUgdvgM3yZ7HQ3yRvzajFSG4H8ZhaYpump'

def pair(dex='pumpfun', quote=None, liquidity=None, price='0.00001'):
    return {'chainId': 'solana', 'dexId': dex, 'baseToken': {'address': MINT},
            'quoteToken': {'address': quote or bot.SOL_MINT},
            'priceUsd': price, 'liquidity': {} if liquidity is None else {'usd': liquidity}}

def test_no_sol_pair_not_misreported_as_zero_liquidity():
    status, _ = bot.entry_pair_diagnostic([pair(quote='USDC', liquidity=100000)])
    assert status == 'no_sol_quoted_pair'

def test_unavailable_liquidity_not_treated_as_zero():
    status, _ = bot.entry_pair_diagnostic([pair()])
    assert status == 'supported_pair_liquidity_unavailable'

def test_actual_low_liquidity():
    status, _ = bot.entry_pair_diagnostic([pair(liquidity=200)])
    assert status == 'supported_pair_low_liquidity'

def test_supported_pair_wins_over_deep_unsupported_pool():
    status, selected = bot.entry_pair_diagnostic([pair(dex='raydium', liquidity=100000), pair(liquidity=10000)])
    assert status == 'eligible_route_liquidity'
    assert selected['dexId'] == 'pumpfun'

def test_unsupported_route_not_low_liquidity():
    status, _ = bot.entry_pair_diagnostic([pair(dex='raydium', liquidity=100000)])
    assert status == 'unsupported_sol_route'
