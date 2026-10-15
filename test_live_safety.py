import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
from live_safety import buy_preflight, checked_sol_price, SafetyError

BASE = dict(requested_usd=10, sol_usd=200, balance_sol=.18, open_positions=0,
            pending_orders=0, wallet_verified=True, quote_age_seconds=2)

def test_usd_to_sol():
    assert buy_preflight(**BASE) == pytest.approx(.05)

@pytest.mark.parametrize('update', [
    {'requested_usd': 10.01}, {'requested_usd': 0},
    {'balance_sol': .07}, {'open_positions': 2},
    {'pending_orders': 1}, {'wallet_verified': False},
    {'quote_age_seconds': 31}, {'sol_usd': float('nan')},
])
def test_fail_closed(update):
    with pytest.raises(SafetyError):
        buy_preflight(**(BASE | update))

def test_price_validation():
    assert checked_sol_price({'solana': {'usd': 200}}) == 200
    with pytest.raises(SafetyError):
        checked_sol_price({'solana': {'usd': None}})
