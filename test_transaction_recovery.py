import base64
import pytest
from order_journal import Journal, JournalError
from transaction_recovery import (RecoveryError, stage_signed_transaction,
                                  inspect_signature_status, inspect_pending_orders)
MINT = 'So11111111111111111111111111111111111111112'
SIG = '2' * 88

def test_stage_blocks_followup_and_does_not_broadcast(tmp_path):
    journal = Journal(str(tmp_path))
    order = journal.create_intent(action='buy', mint=MINT, usd=2)
    staged = stage_signed_transaction(journal, order['id'], signature=SIG, signed_transaction=b'X'*200)
    assert staged['status'] == 'uncertain'
    entry = journal.entries()[0]
    assert base64.b64decode(entry['signed_transaction_b64']) == b'X'*200
    assert journal.status()['unresolved'] == 1
    with pytest.raises(JournalError): journal.create_intent(action='buy', mint=MINT, usd=2)
    with pytest.raises(RecoveryError): stage_signed_transaction(journal, order['id'], signature=SIG, signed_transaction=b'X'*200)

def test_read_only_statuses():
    assert inspect_signature_status(SIG, lambda *_: {'value':[None]})['status'] == 'uncertain'
    assert inspect_signature_status(SIG, lambda *_: {'value':[{'err':None, 'confirmationStatus':'finalized'}]})['status'] == 'finalized'
    assert inspect_signature_status(SIG, lambda *_: {'value':[{'err':{'InstructionError':[1,'Custom']}}]})['status'] == 'failed_on_chain'
    with pytest.raises(RecoveryError): inspect_signature_status(SIG, lambda *_: (_ for _ in ()).throw(TimeoutError()))

def test_unsigned_intent_requires_manual_review(tmp_path):
    journal = Journal(str(tmp_path))
    journal.create_intent(action='buy', mint=MINT, usd=2)
    assert inspect_pending_orders(journal, lambda *_: (_ for _ in ()).throw(AssertionError()))[0]['status'] == 'uncertain'

def test_invalid_inputs(tmp_path):
    journal = Journal(str(tmp_path))
    order = journal.create_intent(action='buy', mint=MINT, usd=2)
    with pytest.raises(RecoveryError): stage_signed_transaction(journal, order['id'], signature='bad', signed_transaction=b'X'*200)
    with pytest.raises(RecoveryError): stage_signed_transaction(journal, '../oops', signature=SIG, signed_transaction=b'X'*200)
