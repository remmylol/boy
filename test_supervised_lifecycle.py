import pytest
from order_journal import Journal, JournalError
from supervised_lifecycle import prepare_offline_buy, inspect_offline_order, LifecycleError

SIG = '1' * 65
MINT = 'MintExample'
TX = b'X' * 180

def test_stages_and_blocks_duplicate(tmp_path):
    d = str(tmp_path / 'orders')
    out = prepare_offline_buy(journal_dir=d, mint=MINT, usd=3, approved=True,
                              signature=SIG, synthetic_signed_tx=TX)
    assert out.status == 'uncertain'
    assert Journal(d).entries()[0]['signed_transaction_b64']
    with pytest.raises(JournalError):
        prepare_offline_buy(journal_dir=d, mint=MINT, usd=3, approved=True,
                            signature=SIG, synthetic_signed_tx=TX)
    assert Journal(d).status()['unresolved'] == 1

def test_denies_unapproved_or_oversized(tmp_path):
    d = str(tmp_path / 'orders')
    for usd, approved in [(3, False), (11, True), (float('nan'), True)]:
        with pytest.raises(LifecycleError):
            prepare_offline_buy(journal_dir=d, mint=MINT, usd=usd, approved=approved,
                                signature=SIG, synthetic_signed_tx=TX)
    assert not Journal(d).entries()

def test_missing_status_stays_uncertain(tmp_path):
    d = str(tmp_path / 'orders')
    out = prepare_offline_buy(journal_dir=d, mint=MINT, usd=2, approved=True,
                              signature=SIG, synthetic_signed_tx=TX)
    def fake_rpc(method, params):
        assert method == 'getSignatureStatuses'
        return {'value': [None]}
    result = inspect_offline_order(journal_dir=d, order_id=out.order_id, signature=SIG,
                                   wallet='wallet', mint=MINT, rpc_call=fake_rpc)
    assert result.status == 'uncertain'
    assert Journal(d).status()['unresolved'] == 1

def test_rejects_wrong_signature(tmp_path):
    d = str(tmp_path / 'orders')
    out = prepare_offline_buy(journal_dir=d, mint=MINT, usd=2, approved=True,
                              signature=SIG, synthetic_signed_tx=TX)
    with pytest.raises(LifecycleError):
        inspect_offline_order(journal_dir=d, order_id=out.order_id, signature='2'*65,
                              wallet='wallet', mint=MINT, rpc_call=lambda *_: None)
