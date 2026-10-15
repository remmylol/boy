import struct
import pytest
from swap_instruction_review import (
    SYSTEM, COMPUTE, TOKEN, TOKEN_2022, SwapReviewError,
    decode_instruction, audit_instruction_set, authorize_swap,
)

def test_system_transfer_decodes_exact_lamports():
    d = struct.pack("<IQ", 2, 123456)
    result = decode_instruction(program=SYSTEM, accounts=("wallet", "recipient"), data=d)
    assert result.operation == "system_transfer"
    assert result.lamports == 123456

def test_rejects_system_authority_and_create_account():
    for tag in (0, 1, 3, 4):
        with pytest.raises(SwapReviewError):
            decode_instruction(program=SYSTEM, accounts=("wallet", "x"), data=struct.pack("<I", tag))

def test_rejects_transfer_with_extra_accounts():
    with pytest.raises(SwapReviewError):
        decode_instruction(program=SYSTEM, accounts=("a", "b", "c"), data=struct.pack("<IQ", 2, 1))

def test_compute_budget_price():
    result = decode_instruction(program=COMPUTE, accounts=(), data=bytes([3])+struct.pack("<Q", 10000))
    assert result.operation == "set_compute_unit_price"

def test_compute_budget_invalid_limit():
    with pytest.raises(SwapReviewError):
        decode_instruction(program=COMPUTE, accounts=(), data=bytes([2])+struct.pack("<I", 1400001))

def test_transfer_checked_read_only():
    result = decode_instruction(program=TOKEN, accounts=("source", "mint", "dest", "owner"),
                                data=bytes([12])+struct.pack("<Q", 200)+bytes([6]))
    assert result.token_amount == 200 and result.token_decimals == 6

def test_rejects_approve_and_unchecked_transfer():
    for tag in (3, 4, 6):
        with pytest.raises(SwapReviewError):
            decode_instruction(program=TOKEN, accounts=("a", "b", "c", "d"), data=bytes([tag])+b"\\0"*9)

def test_rejects_token2022_and_dex_program():
    for program in (TOKEN_2022, "DEX_UNKNOWN"):
        with pytest.raises(SwapReviewError):
            decode_instruction(program=program, accounts=(), data=b"abc")

def test_audit_rejects_one_unknown_instruction():
    with pytest.raises(SwapReviewError):
        audit_instruction_set(((SYSTEM, ("a", "b"), struct.pack("<IQ", 2, 5)),
                               ("DEX_UNKNOWN", (), b"x")))

def test_authorization_always_blocked():
    with pytest.raises(SwapReviewError, match="disabled"):
        authorize_swap()
