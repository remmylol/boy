import json
import pytest
from order_journal import Journal, _atomic_write
from live_position_ledger import observe_finalized_order, PositionLedgerError

SIG = '1' * 65
WALLET = 'wallet-test'
MINT = 'mint-test'


def setup_order(tmp_path):
    journal = Journal(str(tmp_path / 'orders'))
    order = journal.create_intent(action='buy', mint=MINT, usd=3)
    _atomic_write(journal.directory / (order['id'] + '.json'), dict(order, status='uncertain', signature=SIG))
    return journal, order['id']


def rpc(method, params):
    if method == 'getSignatureStatuses':
        return {'value': [{'err': None, 'confirmationStatus': 'finalized'}]}
    if method == 'getTransaction':
        return {'transaction': {'message': {'accountKeys': [WALLET]}},
                'meta': {'err': None, 'preBalances': [1000000000], 'postBalances': [970000000],
                         'fee': 5000, 'preTokenBalances': [], 'postTokenBalances': [
                             {'owner': WALLET, 'mint': MINT, 'uiTokenAmount': {'amount': '1000000', 'decimals': 6}}]}}
    raise AssertionError(method)


def test_records_once_and_preserves_blocker(tmp_path):
    journal, order_id = setup_order(tmp_path)
    ledger_path = str(tmp_path / 'positions.json')
    first = observe_finalized_order(journal_dir=str(journal.directory), ledger_path=ledger_path,
                                    order_id=order_id, wallet=WALLET, rpc_call=rpc)
    assert first['token_delta'] == '1'
    second = observe_finalized_order(journal_dir=str(journal.directory), ledger_path=ledger_path,
                                     order_id=order_id, wallet=WALLET, rpc_call=lambda *_: 1/0)
    assert first == second
    assert journal.status()['unresolved'] == 1
    assert len(json.loads((tmp_path / 'positions.json').read_text())['observations']) == 1


def test_unfinalized_blocks(tmp_path):
    journal, order_id = setup_order(tmp_path)
    def pending(method, params):
        return {'value': [None]}
    with pytest.raises(PositionLedgerError, match='not finalized'):
        observe_finalized_order(journal_dir=str(journal.directory), ledger_path=str(tmp_path / 'positions.json'),
                                order_id=order_id, wallet=WALLET, rpc_call=pending)


def test_wallet_mismatch_blocks(tmp_path):
    journal, order_id = setup_order(tmp_path)
    ledger = tmp_path / 'positions.json'
    ledger.write_text(json.dumps({'schema': 1, 'wallet': 'other', 'observations': {}}))
    with pytest.raises(PositionLedgerError, match='wallet mismatch'):
        observe_finalized_order(journal_dir=str(journal.directory), ledger_path=str(ledger),
                                order_id=order_id, wallet=WALLET, rpc_call=rpc)


def test_no_double_signature(tmp_path):
    journal, order_id = setup_order(tmp_path)
    ledger = tmp_path / 'positions.json'
    ledger.write_text(json.dumps({'schema': 1, 'wallet': WALLET, 'observations': {'another': {'signature': SIG}}}))
    with pytest.raises(PositionLedgerError, match='already recorded'):
        observe_finalized_order(journal_dir=str(journal.directory), ledger_path=str(ledger),
                                order_id=order_id, wallet=WALLET, rpc_call=rpc)
