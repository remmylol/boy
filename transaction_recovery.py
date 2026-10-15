"""Offline signed-transaction staging and read-only Solana status inspection.

This module NEVER signs, sends, retries, or authorizes transactions. A future
reviewed executor must validate swap instructions and actual spending first.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from pathlib import Path

from order_journal import Journal, JournalError, _atomic_write

BASE58 = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')

class RecoveryError(RuntimeError):
    pass


def _entry_path(journal: Journal, order_id: str) -> Path:
    if not re.fullmatch(r'[0-9a-f]{32}', order_id):
        raise RecoveryError('invalid order identifier')
    return journal.directory / (order_id + '.json')


def _load(journal: Journal, order_id: str) -> dict:
    path = _entry_path(journal, order_id)
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RecoveryError('missing or corrupt order record') from exc
    if record.get('id') != order_id:
        raise RecoveryError('order identifier mismatch')
    return record


def stage_signed_transaction(journal: Journal, order_id: str, *, signature: str,
                             signed_transaction: bytes) -> dict:
    """Save signed bytes before any broadcast; fail closed if record is staged.

    Only safe when the caller has independently verified the exact transaction,
    fees, slippage, spending, and wallet authority. No broadcast occurs here.
    """
    record = _load(journal, order_id)
    if record.get('status') != 'intent' or record.get('signature'):
        raise RecoveryError('order is not a fresh intent')
    if not isinstance(signature, str) or not 64 <= len(signature) <= 90 or any(c not in BASE58 for c in signature):
        raise RecoveryError('invalid signature format')
    if not isinstance(signed_transaction, bytes) or not 100 <= len(signed_transaction) <= 1232:
        raise RecoveryError('invalid signed transaction size')
    # Refuse to overwrite any existing signed record, including after a crash.
    path = _entry_path(journal, order_id)
    staged = dict(record, status='uncertain', signature=signature,
                  signed_transaction_b64=base64.b64encode(signed_transaction).decode('ascii'),
                  transaction_sha256=hashlib.sha256(signed_transaction).hexdigest(),
                  note='Signed and staged; broadcast status unknown. Never automatically resubmit.')
    _atomic_write(path, staged)
    try:
        os.chmod(path, 0o600)
    except OSError as exc:
        raise RecoveryError('could not restrict journal file permissions') from exc
    return {'id': order_id, 'status': 'uncertain', 'signature': signature}


def inspect_signature_status(signature: str, rpc_call) -> dict:
    """Read-only check. Unknown/absent signatures stay uncertain, never retry."""
    if not isinstance(signature, str) or not 64 <= len(signature) <= 90 or any(c not in BASE58 for c in signature):
        raise RecoveryError('invalid signature')
    try:
        result = rpc_call('getSignatureStatuses', [[signature], {'searchTransactionHistory': True}])
        status = result['value'][0]
    except Exception as exc:
        raise RecoveryError('RPC status unavailable; order remains blocked') from exc
    if status is None:
        return {'status': 'uncertain', 'reason': 'signature not found; no retry authorized'}
    if status.get('err') is not None:
        return {'status': 'failed_on_chain', 'error': str(status['err'])}
    confirmation = status.get('confirmationStatus')
    if confirmation in ('confirmed', 'finalized'):
        return {'status': confirmation, 'reason': 'confirmation only; token/SOL reconciliation still required'}
    return {'status': 'uncertain', 'reason': 'not yet confirmed'}


def inspect_pending_orders(journal: Journal, rpc_call) -> list[dict]:
    """Inspect only; never clear blockers or mutate the journal."""
    findings = []
    for entry in journal.entries():
        if entry.get('status') not in {'intent', 'submitted', 'uncertain', 'confirmed'}:
            continue
        sig = entry.get('signature')
        if not sig:
            findings.append({'id': entry['id'], 'status': 'uncertain', 'reason': 'no signature; manual review required'})
        else:
            findings.append({'id': entry['id'], **inspect_signature_status(sig, rpc_call)})
    return findings
