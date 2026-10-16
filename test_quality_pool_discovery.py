from quality_pool_discovery import extract_quality_pool_mints

SOL = 'So11111111111111111111111111111111111111112'
MINT = 'SomeValidTokenMint111111111111111111111111111'

def payload(quote=SOL, dex='solana_pump_swap', liq='23000', volume='26000', price='0.02'):
    return {'data': [{'attributes': {'reserve_in_usd': liq, 'volume_usd': {'h1': volume}, 'base_token_price_usd': price},
                      'relationships': {'dex': {'data': {'id': dex}},
                                        'base_token': {'data': {'id': 'solana_' + MINT}},
                                        'quote_token': {'data': {'id': 'solana_' + quote}}}}], 'included': []}

def run(data):
    return extract_quality_pool_mints(data, sol_mint=SOL,
        supported_dexes=frozenset({'pumpfun', 'pumpswap'}),
        min_liquidity_usd=5000, min_volume_1h_usd=10000)

def test_valid_supported_liquid_sol_pool():
    assert MINT in run(payload())

def test_excludes_unsupported_route_even_with_volume():
    assert run(payload(dex='solana_raydium')) == {}

def test_excludes_non_sol_quote():
    assert run(payload(quote='USDC')) == {}

def test_excludes_low_liquidity_or_low_volume_or_missing_price():
    assert not run(payload(liq='3000'))
    assert not run(payload(volume='100'))
    assert not run(payload(price=None))

def test_rejects_wrong_network_dex_and_malformed_input():
    assert not run(payload(dex='ethereum_pumpswap'))
    assert not run(None)
