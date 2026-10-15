import bot

MINT = 'ExampleMint'
def pair(dex='pumpswap', quote=bot.SOL_MINT, liquidity=30000):
    return {'chainId':'solana', 'dexId':dex, 'priceUsd':'0.001',
            'baseToken':{'address':MINT, 'symbol':'TEST'},
            'quoteToken':{'address':quote, 'symbol':'SOL' if quote == bot.SOL_MINT else 'TTWO'},
            'liquidity':{'usd':liquidity}}

def test_rejects_ttwo_even_if_liquid():
    assert 'unsupported quote' in bot.entry_pair_reason(pair(quote='TTWO', liquidity=100000))

def test_rejects_meteora_even_if_sol():
    assert 'unsupported PumpPortal route' in bot.entry_pair_reason(pair(dex='meteora'))

def test_rejects_low_sol_liquidity():
    assert 'liquidity' in bot.entry_pair_reason(pair(liquidity=1718))

def test_prefers_supported_sol_pool_not_largest_ttwo():
    eligible = pair(liquidity=25000)
    assert bot.best_entry_pair([pair(quote='TTWO',liquidity=100000),eligible]) == eligible

def test_no_eligible_pair_fails_closed():
    assert bot.best_entry_pair([pair(dex='meteora'), pair(quote='TTWO')]) is None

def test_existing_best_pair_remains_available_for_held_position_prices():
    assert bot.best_pair([pair(dex='meteora')]) is not None
