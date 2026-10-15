import pytest
from live_execution import preview_buy, execute_buy, execute_sell, ExecutionBlocked
from order_journal import Journal

MINT='So11111111111111111111111111111111111111112'

def test_preview_valid(tmp_path):
    p=preview_buy(mint=MINT,requested_usd=10,sol_usd=200,balance_sol=.18,
                  open_positions=1,wallet_verified=True,quote_age_seconds=1,
                  journal_dir=str(tmp_path))
    assert p.estimated_sol == pytest.approx(.05)
    assert list(tmp_path.iterdir()) == []

def test_preview_rejects_over_limit(tmp_path):
    with pytest.raises(ExecutionBlocked):
        preview_buy(mint=MINT,requested_usd=11,sol_usd=200,balance_sol=.18,
                    open_positions=0,wallet_verified=True,quote_age_seconds=1,journal_dir=str(tmp_path))

def test_preview_rejects_pending_order(tmp_path):
    Journal(str(tmp_path)).create_intent(action='buy',mint=MINT,usd=5)
    with pytest.raises(ExecutionBlocked,match='pending'):
        preview_buy(mint=MINT,requested_usd=5,sol_usd=200,balance_sol=.18,
                    open_positions=0,wallet_verified=True,quote_age_seconds=1,journal_dir=str(tmp_path))

def test_live_execution_disabled():
    with pytest.raises(ExecutionBlocked): execute_buy()
    with pytest.raises(ExecutionBlocked): execute_sell()
