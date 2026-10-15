import pytest
from wallet_reconciliation import inspect_transaction, ReconciliationError

def sample():
    return {'meta': {'err': None, 'fee': 5000, 'preBalances': [300000000], 'postBalances': [269995000],
                     'preTokenBalances': [], 'postTokenBalances': [{'owner':'wallet','mint':'mint','uiTokenAmount': {'amount':'1234567','decimals':6}}]},
            'transaction': {'message': {'accountKeys': [{'pubkey':'wallet','signer':True}]}}}

def test_reconciles_finalized_balance_deltas():
    x = inspect_transaction('sig','wallet','mint',lambda method, args: sample())
    assert x['sol_delta'] == '-0.030005'
    assert x['token_delta'] == '1.234567'
    assert x['network_fee_sol'] == '0.000005'

def test_unknown_transaction_fails_closed():
    with pytest.raises(ReconciliationError):
        inspect_transaction('sig','wallet','mint',lambda *_: None)

def test_unrelated_wallet_fails_closed():
    with pytest.raises(ReconciliationError):
        inspect_transaction('sig','other','mint',lambda *_: sample())

def test_failed_transaction_fails_closed():
    tx=sample(); tx['meta']['err']={'InstructionError':[0,'Custom']}
    with pytest.raises(ReconciliationError):
        inspect_transaction('sig','wallet','mint',lambda *_: tx)
