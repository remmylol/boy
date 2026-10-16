from curve_paper import buy_quote, sell_quote

CURVE = dict(virtual_token_raw=1_000_000_000_000_000, virtual_sol_lamports=30_000_000_000,
             real_token_raw=800_000_000_000_000, real_sol_lamports=15_000_000_000, complete=False)

def test_round_trip_loses_fees_and_impact():
    buy = buy_quote(CURVE, .1)
    assert buy and buy['token_raw'] > 0
    after = dict(CURVE, virtual_token_raw=CURVE['virtual_token_raw']-buy['token_raw'],
                 virtual_sol_lamports=CURVE['virtual_sol_lamports']+.1e9*.99,
                 real_token_raw=CURVE['real_token_raw']-buy['token_raw'],
                 real_sol_lamports=CURVE['real_sol_lamports']+.1e9*.99)
    sell = sell_quote(after, buy['token_raw'])
    assert sell and 0 < sell['sol_out'] < .1

def test_rejects_insufficient_real_reserves():
    assert buy_quote(dict(CURVE, real_token_raw=1), .1) is None
    assert sell_quote(dict(CURVE, real_sol_lamports=1), 1e12) is None

def test_rejects_graduated_and_invalid():
    assert buy_quote(dict(CURVE, complete=True), .1) is None
    assert sell_quote(dict(CURVE, complete=True), 1e12) is None
    assert buy_quote(CURVE, 0) is None
