"""Read-only, fail-closed inspection of serialized Solana transactions.

This module is intentionally NOT an approval oracle for swaps. A transaction
cannot be signed/broadcast based solely on this report. It refuses address
lookup tables and unknown programs; swap-specific debit bounds need a reviewed
instruction decoder and trusted account-state snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

class InspectionError(ValueError):
    pass

# Solana's standard programs. Listing a program here does NOT mean an
# instruction calling it is safe or authorized.
KNOWN_PROGRAMS = frozenset({
    "11111111111111111111111111111111",  # System
    "ComputeBudget111111111111111111111111111111",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFZhXjzkKpN8VQ5DA",
})

@dataclass(frozen=True)
class Inspection:
    fee_payer: str
    required_signers: tuple[str, ...]
    invoked_programs: tuple[str, ...]
    instruction_count: int
    warnings: tuple[str, ...]
    approved_for_execution: bool = False

def inspect_serialized_transaction(raw: bytes, *, expected_wallet: str,
                                   expected_mint: str) -> Inspection:
    """Inspect a raw unsigned/signed versioned transaction, without secrets.

    No swap instruction is approved for execution. Reject anything not
    independently understood instead of trusting quote or provider metadata.
    """
    if not isinstance(raw, bytes) or not raw or len(raw) > 1232:
        raise InspectionError("invalid serialized transaction size")
    if not expected_wallet or not expected_mint or expected_wallet == expected_mint:
        raise InspectionError("wallet and mint must be distinct")
    try:
        from solders.transaction import VersionedTransaction
        tx = VersionedTransaction.from_bytes(raw)
        msg = tx.message
        keys = tuple(str(k) for k in msg.account_keys)
        count = int(msg.header.num_required_signatures)
        instructions = tuple(msg.instructions)
    except Exception as exc:
        raise InspectionError("unable to decode serialized Solana transaction") from exc
    if not keys or count < 1 or count > len(keys) or keys[0] != expected_wallet:
        raise InspectionError("unexpected fee payer or required signers")
    if tuple(keys[:count]) != (expected_wallet,):
        raise InspectionError("unexpected additional required signer")
    if hasattr(msg, "address_table_lookups") and msg.address_table_lookups:
        raise InspectionError("address lookup tables are not supported for review")
    if not instructions:
        raise InspectionError("transaction has no instructions")
    programs = []
    for instruction in instructions:
        index = int(instruction.program_id_index)
        if index < 0 or index >= len(keys):
            raise InspectionError("invalid program index")
        program = keys[index]
        programs.append(program)
        if program not in KNOWN_PROGRAMS:
            raise InspectionError("unrecognized program; cannot bound token/SOL movements")
    if expected_mint not in keys:
        raise InspectionError("expected mint not found in static accounts")
    return Inspection(
        fee_payer=keys[0],
        required_signers=tuple(keys[:count]),
        invoked_programs=tuple(programs),
        instruction_count=len(instructions),
        warnings=(
            "Instruction payloads and inner instructions are not decoded.",
            "SOL debits, token authority, fees, rent and slippage are NOT proven.",
            "No transaction may be signed or broadcast based on this inspection.",
        ),
    )

def require_execution_approval(report: Inspection) -> None:
    """Fail closed until a fully audited swap validator is implemented."""
    raise InspectionError("execution approval unavailable: swap semantics not verified")
