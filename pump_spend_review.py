"""Conservative read-only review of Pump transaction bytes and account constraints.

No Anchor schema is assumed; unknown program instruction data is NOT interpreted
as a guaranteed spending bound. No signing, broadcasting, or approval.
"""
from __future__ import annotations

from decimal import Decimal

PUMP_PROGRAM = 'FAdo9NCw1ssek6Z6yeWzWjhLVsr8uiCwcWNUnKgzTnHe'
COMPUTE_PROGRAM = 'ComputeBudget111111111111111111111111111111'
ATA_PROGRAM = 'ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL'
TOKEN_2022 = 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'

class SpendReviewError(ValueError):
    pass

def review_instructions(resolved: dict, *, wallet: str, mint: str, proposed_sol: str = '0.01') -> dict:
    instructions = resolved.get('instructions')
    if not isinstance(instructions, list):
        raise SpendReviewError('Missing resolved instructions')
    if not resolved.get('lookup_tables'):
        raise SpendReviewError('Expected lookup table resolution report')
    try:
        max_lamports = int(Decimal(proposed_sol) * Decimal(1_000_000_000))
    except Exception as exc:
        raise SpendReviewError('Invalid proposed SOL amount') from exc
    if max_lamports <= 0:
        raise SpendReviewError('Proposed amount must be positive')
    decoded = []
    pump_count = 0
    fee_limit = None
    cu_limit = None
    reasons = []
    for ins in instructions:
        program = ins.get('program')
        accounts = ins.get('accounts', [])
        try:
            raw = bytes.fromhex(ins['data_hex'])
        except (KeyError, ValueError, TypeError) as exc:
            raise SpendReviewError('Invalid instruction data') from exc
        item = {'index':ins.get('index'), 'program':program, 'data_length':len(raw)}
        if program == COMPUTE_PROGRAM:
            if len(raw)==5 and raw[0]==2:
                cu_limit = int.from_bytes(raw[1:], 'little')
                item['compute_unit_limit'] = cu_limit
            elif len(raw)==9 and raw[0]==3:
                fee_limit = int.from_bytes(raw[1:], 'little')
                item['micro_lamports_per_cu'] = fee_limit
            else:
                reasons.append('Unrecognized compute budget instruction')
        elif program == ATA_PROGRAM:
            item['ata_create_idempotent'] = raw == b'\x01'
            if not item['ata_create_idempotent'] or len(accounts)<4 or accounts[0]!=wallet or accounts[2]!=wallet or accounts[3]!=mint:
                reasons.append('Unexpected associated token account instruction')
        elif program == PUMP_PROGRAM:
            pump_count += 1
            item['anchor_discriminator_hex'] = raw[:8].hex() if len(raw)>=8 else None
            item['payload_hex'] = raw[8:].hex() if len(raw)>=8 else None
            if len(raw)>=24:
                item['unverified_u64_at_offset_8'] = int.from_bytes(raw[8:16],'little')
                item['unverified_u64_at_offset_16'] = int.from_bytes(raw[16:24],'little')
                item['remaining_hex'] = raw[24:].hex()
            if mint not in accounts or wallet not in accounts:
                reasons.append('Expected mint or wallet missing from Pump accounts')
            reasons.append('Pump instruction schema and debit semantics unverified')
        else:
            reasons.append('Unexpected instruction program: '+str(program))
        decoded.append(item)
    if pump_count != 1:
        reasons.append('Expected exactly one Pump instruction')
    if cu_limit is None or fee_limit is None:
        reasons.append('Missing compute budget limit or price')
    priority_lamports = ((cu_limit * fee_limit + 999_999)//1_000_000) if cu_limit is not None and fee_limit is not None else None
    return {'wallet':wallet,'mint':mint,'proposed_swap_lamports':max_lamports,
            'max_priority_fee_lamports_from_compute_budget':priority_lamports,
            'instructions':decoded,'max_swap_debit_verified':False,
            'rent_and_transaction_fees_verified':False,
            'approved_for_execution':False,
            'blocking_reasons':list(dict.fromkeys(reasons))}
