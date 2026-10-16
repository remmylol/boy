import hashlib
import struct
import pytest
from pump_curve_market import decode_curve_account


def curve_data(complete=0):
    return hashlib.sha256(b'account:BondingCurve').digest()[:8] + struct.pack('<5Q', 1073000000000000, 30000000000, 793100000000000, 5000000000, 1000000000000000) + bytes([complete])


def test_curve_decodes_real_and_virtual_separately():
    info = decode_curve_account(curve_data())
    assert info['real_sol_reserve'] == 5
    assert info['virtual_sol_lamports'] == 30_000_000_000
    assert info['market_cap_sol'] > 0
    assert not info['complete']


def test_curve_graduation():
    assert decode_curve_account(curve_data(1))['complete']


def test_reject_wrong_discriminator():
    with pytest.raises(ValueError):
        decode_curve_account(b'badbytes' + curve_data()[8:])


def test_reject_truncated():
    with pytest.raises(ValueError):
        decode_curve_account(b'abc')
