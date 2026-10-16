from quality_pool_discovery import extract_quality_pool_mints
import bot


def packet(changes):
    data=[]
    included=[]
    for i,(h1,h6) in enumerate(changes):
        mint = f'mint{i}'
        data.append({'attributes': {'reserve_in_usd':'100000', 'base_token_price_usd':'0.01',
            'volume_usd':{'h1':'25000'}, 'price_change_percentage': {'h1': h1, 'h6': h6}},
            'relationships': {
                'dex': {'data': {'id': 'solana_raydium'}},
                'base_token': {'data':{'id':'solana_'+mint}},
                'quote_token': {'data':{'id': 'solana_'+bot.SOL_MINT}}}})
        included += [{'id': 'solana_'+mint, 'attributes':{'address':mint}},
                     {'id':'solana_'+bot.SOL_MINT,'attributes':{'address':bot.SOL_MINT}}]
    return {'data': data, 'included':included}


def test_positive_multi_hour_movement_prioritized_for_discovery():
    scores=extract_quality_pool_mints(packet([(-3,-5),(5,12)]),
        sol_mint=bot.SOL_MINT, supported_dexes=frozenset({'raydium'}),
        min_liquidity_usd=15000,min_volume_1h_usd=12000,discovery_stage='continuation')
    assert scores['mint1'] > scores['mint0']


def test_discovery_ranking_cannot_authorize_a_trade():
    # This is only a shortlisting hint; an unsupported quote is never picked.
    p=packet([(8,12)])
    p['data'][0]['relationships']['quote_token']['data']['id']='solana_USDC'
    scores=extract_quality_pool_mints(p,
        sol_mint=bot.SOL_MINT, supported_dexes=frozenset({'raydium'}),
        min_liquidity_usd=15000,min_volume_1h_usd=12000,discovery_stage='continuation')
    assert not scores
