"""Offline decoding of a *subset* of Solana instruction payloads.

This module reports potential spending/authority changes; it never authorizes
a swap, signing, or broadcasting. Any unrecognized instruction fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct

SYSTEM = "11111111111111111111111111111111"
COMPUTE = "ComputeBudget111111111111111111111111111111"
TOKEN = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFZhXjzkKpN8VQ5DA"

class SwapReviewError(ValueError):
    pass

@dataclass(frozen=True)
class InstructionFinding:
    program: str
    operation: str
    accounts: tuple[str, ...]
    lamports: int = 0
    token_amount: int = 0
    token_decimals: int | None = None
    risk: str = ""

def decode_instruction(*, program: str, accounts: tuple[str, ...],
                       data: bytes) -> InstructionFinding:
    """Parse only exact, understood layouts. Unknown instructions are rejected."""
    if not isinstance(data, bytes) or not isinstance(accounts, tuple):
        raise SwapReviewError("invalid instruction inputs")
    if program == SYSTEM:
        if len(data) == 12 and data[:4] == bytes([2, 0, 0, 0]):
            if len(accounts) != 2:
                raise SwapReviewError("system transfer account layout mismatch")
            value = struct.unpack_from("<Q", data, 4)[0]
            return InstructionFinding(program, "system_transfer", accounts, lamports=value,
                                      risk="SOL debit; destination must be independently authorized")
        raise SwapReviewError("unsupported system instruction (possible rent/authority change)")
    if program == COMPUTE:
        if len(data) == 5 and data[0] == 2:
            units = struct.unpack_from("<I", data, 1)[0]
            if not 1 <= units <= 1_400_000:
                raise SwapReviewError("invalid compute unit limit")
            return InstructionFinding(program, "set_compute_unit_limit", accounts)
        if len(data) == 9 and data[0] == 3:
            price = struct.unpack_from("<Q", data, 1)[0]
            return InstructionFinding(program, "set_compute_unit_price", accounts,
                                      risk=f"priority fee price {price} micro-lamports/CU")
        raise SwapReviewError("unsupported compute budget instruction")
    if program == TOKEN:
        # SPL Token TransferChecked: tag 12, u64 amount, u8 decimals.
        if len(data) == 10 and data[0] == 12 and len(accounts) >= 4:
            amount = struct.unpack_from("<Q", data, 1)[0]
            decimals = data[9]
            if decimals > 18:
                raise SwapReviewError("invalid token decimals")
            return InstructionFinding(program, "transfer_checked", accounts,
                                      token_amount=amount, token_decimals=decimals,
                                      risk="Token debit; owner/mint/destination must be verified")
        raise SwapReviewError("unsupported SPL token instruction or authority operation")
    # Token-2022 extensions can add transfer hooks and fees; never infer safety.
    raise SwapReviewError("unknown or unsupported program; swap cannot be approved")

def audit_instruction_set(instructions: tuple[tuple[str, tuple[str, ...], bytes], ...]
                          ) -> tuple[InstructionFinding, ...]:
    """Return a read-only report; not an execution approval."""
    if not instructions:
        raise SwapReviewError("empty instruction list")
    return tuple(decode_instruction(program=p, accounts=a, data=d)
                 for p, a, d in instructions)

def authorize_swap(*_args, **_kwargs) -> None:
    raise SwapReviewError(
        "Swap execution remains disabled: DEX-specific instructions, inner transfers, "
        "token authorities, account state, rent, fees and slippage are not verified"
    )
