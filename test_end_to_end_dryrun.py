import json
import pytest
from end_to_end_dryrun import run_offline_rehearsal
from order_journal import Journal, JournalError

WALLET = 'ExampleWallet'
MINT = 'ExampleMint'

def fake_rpc(method, params):
    if method == 'getSignatureStatuses':
        return {'value': [{'err': None, 'confirmationStatus': 'finalized'}]}
    if method == 'getTransaction':
        return {'meta': {'err': None, 'preBalances': [1_000_000_000],
                         'postBalances': [990_000_000], 'fee': 5000,
                         'preTokenBalances': [],
                         'postTokenBalances': [{'owner': WALLET, 'mint': MINT,
                           'uiTokenAmount': {'amount': '500', 'decimals': 2}}]},
                'transaction': {'message': {'accountKeys': [WALLET]}}}
    raise AssertionError(method)

def test_full_rehearsal_blocks_after_finalized(tmp_path):
    sent = []
    path = str(tmp_path / 'orders')
    result = run_offline_rehearsal(journal_dir=path, mint=MINT, wallet=WALLET,
        rpc_call=fake_rpc, simulated_broadcast=lambda tx: sent.append(tx))
    assert result.staged and result.broadcast_simulated and result.pending_blocked
    assert result.signature_status == 'finalized'
    assert result.reconciliation_status == 'observed_finalized'
    assert result.journal_unresolved == 1
    assert sent[0].startswith(b'OFFLINE_FAKE')
    with pytest.raises(JournalError):
        Journal(path).create_intent(action='buy', mint=MINT, usd=2)

def test_rpc_absence_keeps_order_blocked(tmp_path):
    def absent(method, params):
        if method == 'getSignatureStatuses': return {'value': [None]}
        if method == 'getTransaction': return None
    result = run_offline_rehearsal(journal_dir=str(tmp_path / 'orders'),
        mint=MINT, wallet=WALLET, rpc_call=absent, simulated_broadcast=lambda tx: None)
    assert result.signature_status == 'uncertain'
    assert result.reconciliation_status == 'unavailable_keep_blocked'
    assert result.journal_unresolved == 1

def test_broadcast_timeout_keeps_durable_blocker(tmp_path):
    path = str(tmp_path / 'orders')
    def timeout(_): raise TimeoutError('simulated ambiguous network timeout')
    with pytest.raises(TimeoutError):
        run_offline_rehearsal(journal_dir=path, mint=MINT, wallet=WALLET,
                             rpc_call=fake_rpc, simulated_broadcast=timeout)
    assert Journal(path).status()['unresolved'] == 1
    with pytest.raises(JournalError): Journal(path).assert_no_unresolved()

def test_duplicate_rehearsal_refused(tmp_path):
    path = str(tmp_path / 'orders')
    args = dict(journal_dir=path, mint=MINT, wallet=WALLET,
                rpc_call=fake_rpc, simulated_broadcast=lambda tx: None)
    run_offline_rehearsal(**args)
    with pytest.raises(JournalError): run_offline_rehearsal(**args)
