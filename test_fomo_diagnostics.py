from fomo_boards import inspect_fomo_board

M='A'*32

def test_counts_exclusions_and_keeps_only_explicit_sol():
    got, d = inspect_fomo_board({'tokens': [
        {'network':'solana','token':{'address':M}},
        {'network':'sol','token':{'address':M}},
        {'network':'ethereum','token':{'address':'B'*32}},
        {'token':{'address':'B'*32}},
        {'network':'solana','token':{'address':'not-a-mint'}},
        {'network':'solana','token':{}},
        None,
    ]})
    assert got == [M]
    assert d['records'] == 7 and d['solana_rows'] == 4
    assert d['valid_mints'] == 1 and d['duplicates'] == 1
    assert d['non_solana'] == 1 and d['missing_network'] == 1
    assert d['invalid_address'] == 1 and d['missing_address'] == 1
    assert d['malformed_rows'] == 1

def test_wrapped_documented_response_and_mint_alias():
    got, d = inspect_fomo_board({'data': {'tokens':[{'network':'solana','token':{'mint':M}}]}})
    assert got == [M] and d['status'] == 'ok'

def test_schema_problem_explicit_and_fail_closed():
    assert inspect_fomo_board({'count':30})[1]['status'] == 'missing_tokens_list'
    assert inspect_fomo_board({'tokens':[{'token':{'address':M}}]})[0] == []
    assert inspect_fomo_board({'available':False,'tokens':[{'network':'solana','token':{'address':M}}]})[0] == []
    assert inspect_fomo_board({'stale':True,'tokens':[{'network':'solana','token':{'address':M}}]})[0] == []

def test_no_broad_assumption_about_network():
    got, d = inspect_fomo_board({'tokens':[{'network':'base','address':M}, {'network':101,'address':M}]})
    assert got == [] and d['non_solana'] == 2
