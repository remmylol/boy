import bot

MINT = '7BGgw7k7WteUgdvgM3yZ7HQ3yRvzajFSG4H8ZhaYpump'

def pair(liquidity=None):
    return {'chainId':'solana','dexId':'pumpfun',
            'baseToken':{'address':MINT},
            'quoteToken':{'address':bot.SOL_MINT},
            'priceUsd':'0.00001',
            'liquidity': {} if liquidity is None else {'usd':liquidity}}

def test_missing_liquidity_remains_untradeable():
    assert bot.best_entry_pair([pair()]) is None

def test_detail_with_verified_liquidity_can_be_used():
    detail = pair(bot.MIN_SOL_PAIR_LIQUIDITY_USD + 1000)
    assert bot.best_entry_pair([detail]) is detail

def test_detail_below_minimum_stays_untradeable():
    assert bot.best_entry_pair([pair(bot.MIN_SOL_PAIR_LIQUIDITY_USD - 1)]) is None
