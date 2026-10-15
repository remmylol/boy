import pytest
pytest.importorskip("solders", reason="solders not installed in local test environment")
from solders.keypair import Keypair
from solders.instruction import Instruction, AccountMeta
from solders.message import Message
from solders.transaction import Transaction
from pumpportal_unsigned_inspector import inspect_bytes, InspectionError


def sample_tx(wallet):
    # This is an unsigned legacy transaction with a system transfer instruction;
    # it is intentionally not a real PumpPortal swap.
    from solders.system_program import transfer, TransferParams
    ix = transfer(TransferParams(from_pubkey=wallet.pubkey(), to_pubkey=Keypair().pubkey(), lamports=10))
    from solders.hash import Hash
    tx = Transaction.new_unsigned(Message.new_with_blockhash([ix], wallet.pubkey(), Hash.default()))
    return bytes(tx)


def test_reports_not_approved():
    wallet = Keypair()
    mint = str(Keypair().pubkey())
    report = inspect_bytes(sample_tx(wallet), wallet=str(wallet.pubkey()), mint=mint)
    assert report['approved_for_execution'] is False
    assert report['instructions'][0]['data_hex']
    assert report['fee_payer'] == str(wallet.pubkey())


def test_rejects_wrong_wallet():
    wallet = Keypair()
    with pytest.raises(InspectionError, match='Fee payer'):
        inspect_bytes(sample_tx(wallet), wallet=str(Keypair().pubkey()), mint=str(Keypair().pubkey()))


def test_rejects_invalid_bytes():
    with pytest.raises(InspectionError):
        inspect_bytes(b'broken', wallet=str(Keypair().pubkey()), mint=str(Keypair().pubkey()))


def test_rejects_empty():
    with pytest.raises(InspectionError):
        inspect_bytes(b'', wallet='x', mint='y')
