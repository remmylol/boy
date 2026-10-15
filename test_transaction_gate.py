from decimal import Decimal
import pytest
from transaction_gate import GateError, ReviewedTransaction, stage_reviewed_buy
from order_journal import Journal, JournalError

SIG = '1' * 88

def params(tmp_path, **changes):
    base = dict(journal_dir=str(tmp_path / 'orders'), mint='mint', wallet='wallet',
                requested_usd='3', sol_usd='100', balance_sol='0.36',
                open_positions=0, quote_age_seconds=1, approved=True)
    base.update(changes)
    return base

def builder(**kw):
    return ReviewedTransaction(SIG, b'x' * 150, kw['wallet'], kw['mint'], 'buy', Decimal('0.029'), True)

def test_stages_without_broadcast(tmp_path):
    result = stage_reviewed_buy(**params(tmp_path), build_and_validate=builder)
    assert result['status'] == 'uncertain'
    assert Journal(str(tmp_path / 'orders')).status()['unresolved'] == 1
    with pytest.raises(JournalError):
        stage_reviewed_buy(**params(tmp_path), build_and_validate=builder)

def test_rejects_excess_total_outflow(tmp_path):
    def excessive(**kw):
        r = builder(**kw)
        return ReviewedTransaction(r.signature, r.signed_bytes, r.wallet, r.mint, r.action, Decimal('0.031'), True)
    with pytest.raises(GateError, match='USD limit'):
        stage_reviewed_buy(**params(tmp_path), build_and_validate=excessive)
    assert Journal(str(tmp_path / 'orders')).status()['unresolved'] == 1

def test_rejects_unreviewed(tmp_path):
    def unreviewed(**kw):
        r = builder(**kw)
        return ReviewedTransaction(r.signature, r.signed_bytes, r.wallet, r.mint, r.action, r.max_total_sol_outflow, False)
    with pytest.raises(GateError, match='validation'):
        stage_reviewed_buy(**params(tmp_path), build_and_validate=unreviewed)

def test_refuses_approval_or_stale_quote_without_intent(tmp_path):
    with pytest.raises(GateError):
        stage_reviewed_buy(**params(tmp_path, approved=False), build_and_validate=builder)
    with pytest.raises(GateError):
        stage_reviewed_buy(**params(tmp_path, quote_age_seconds=31), build_and_validate=builder)
    assert Journal(str(tmp_path / 'orders')).status()['orders'] == 0

def test_reserve_includes_total_outflow(tmp_path):
    with pytest.raises(GateError, match='reserve'):
        stage_reviewed_buy(**params(tmp_path, balance_sol='0.07'), build_and_validate=builder)

def test_builder_failure_leaves_blocker(tmp_path):
    def broken(**kw):
        raise RuntimeError('invalid swap instructions')
    with pytest.raises(RuntimeError):
        stage_reviewed_buy(**params(tmp_path), build_and_validate=broken)
    assert Journal(str(tmp_path / 'orders')).status()['unresolved'] == 1
