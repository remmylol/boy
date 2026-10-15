import pytest
from transaction_inspector import Inspection, InspectionError, inspect_serialized_transaction, require_execution_approval

def test_rejects_empty_and_oversized_bytes():
    for raw in (b'', b'x'*1233):
        with pytest.raises(InspectionError):
            inspect_serialized_transaction(raw, expected_wallet='wallet', expected_mint='mint')

def test_rejects_same_accounts():
    with pytest.raises(InspectionError):
        inspect_serialized_transaction(b'x', expected_wallet='wallet', expected_mint='wallet')

def test_rejects_undecodable_bytes():
    with pytest.raises(InspectionError):
        inspect_serialized_transaction(b'not a transaction', expected_wallet='wallet', expected_mint='mint')

def test_no_report_can_authorize_execution():
    report = Inspection('wallet', ('wallet',), (), 1, ())
    assert report.approved_for_execution is False
    with pytest.raises(InspectionError, match='unavailable'):
        require_execution_approval(report)
