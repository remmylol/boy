"""Read-only PumpPortal transaction inspection. Never signs or broadcasts.

Supply a serialized unsigned transaction from a trusted local file. The report
is descriptive, not a safe-to-trade authorization. Address lookup tables,
opaque DEX instructions, token ownership, fees, and slippage require additional
verification.
"""
from __future__ import annotations
import argparse
import base64
import json
from pathlib import Path

class InspectionError(ValueError):
    pass


def inspect_bytes(raw: bytes, *, wallet: str, mint: str) -> dict:
    if not raw or len(raw) > 1232:
        raise InspectionError('Transaction must be between 1 and 1232 bytes')
    try:
        from solders.transaction import VersionedTransaction
        from solders.pubkey import Pubkey
        Pubkey.from_string(wallet)
        Pubkey.from_string(mint)
        tx = VersionedTransaction.from_bytes(raw)
        message = tx.message
        keys = [str(k) for k in message.account_keys]
        n = message.header.num_required_signatures
        instructions = message.instructions
    except Exception as exc:
        raise InspectionError('Invalid Solana transaction or public key') from exc
    if not keys or keys[0] != wallet:
        raise InspectionError('Fee payer differs from expected wallet')
    if n != 1 or keys[:n] != [wallet]:
        raise InspectionError('Unexpected required signers')
    lookups = getattr(message, 'address_table_lookups', ())
    if not instructions:
        raise InspectionError('Transaction contains no instructions')
    # Loaded addresses are not available in a serialized message; instruction
    # indices beyond static keys must not be silently mapped to static keys.
    findings = []
    for i, instruction in enumerate(instructions):
        program_index = int(instruction.program_id_index)
        if program_index >= len(keys):
            program = '<address lookup table: unresolved>'
        else:
            program = keys[program_index]
        accounts = []
        for idx in instruction.accounts:
            idx = int(idx)
            accounts.append(keys[idx] if idx < len(keys) else '<lookup index: unresolved>')
        findings.append({'index': i, 'program': program, 'accounts': accounts,
                         'data_hex': bytes(instruction.data).hex()})
    warnings = [
        'NOT approved for signing or broadcast',
        'Opaque swap instructions and inner token/SOL transfers are not verified',
        'Actual spend, priority fees, rent, token authority, slippage and token balances are not proven',
    ]
    if lookups:
        warnings.append('Address lookup tables are present and have NOT been resolved')
    if mint not in keys:
        warnings.append('Expected token mint is absent from static account keys; may be looked up or implicit')
    return {'fee_payer': keys[0], 'required_signers': keys[:n],
            'expected_mint': mint, 'mint_in_static_keys': mint in keys,
            'address_lookup_tables': len(lookups), 'instructions': findings,
            'approved_for_execution': False, 'warnings': warnings}


def read_transaction(path: Path, encoding: str) -> bytes:
    data = path.read_bytes()
    if encoding == 'binary':
        return data
    try:
        return base64.b64decode(data.strip(), validate=True)
    except Exception as exc:
        raise InspectionError('Expected base64-encoded serialized transaction') from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', required=True, type=Path)
    parser.add_argument('--wallet', required=True, help='Public wallet address only')
    parser.add_argument('--mint', required=True, help='Public token mint')
    parser.add_argument('--encoding', choices=['binary', 'base64'], default='binary')
    args = parser.parse_args(argv)
    try:
        report = inspect_bytes(read_transaction(args.file, args.encoding), wallet=args.wallet, mint=args.mint)
    except (InspectionError, OSError) as exc:
        parser.exit(2, f'Inspection failed: {exc}\n')
    print(json.dumps(report, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
