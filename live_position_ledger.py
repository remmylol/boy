"""Fail-closed, read-only-derived position accounting; NEVER authorizes a trade.

Only manually reviewed, finalized observations may be recorded. This is not a
proof that the original swap instructions were safe or within spending limits.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import json

from order_journal import Journal, _atomic_write
from transaction_recovery import inspect_signature_status
from wallet_reconciliation import inspect_transaction


class PositionLedgerError(RuntimeError):
    pass


def _decimal(value):
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PositionLedgerError('invalid numeric observation') from exc
    if not n.is_finite():
        raise PositionLedgerError('nonfinite numeric observation')
    return n


def observe_finalized_order(*, journal_dir: str, ledger_path: str, order_id: str,
                            wallet: str, rpc_call) -> dict:
    """Persist a verified observation exactly once; never clear the order blocker.

    A human must still review instruction-level spending, fee/rent effects and
    token ownership before treating this as a position or authorizing a sell.
    """
    journal = Journal(journal_dir)
    entries = [e for e in journal.entries() if e.get('id') == order_id]
    if len(entries) != 1:
        raise PositionLedgerError('order not found or duplicated')
    order = entries[0]
    signature = order.get('signature')
    mint = order.get('mint')
    if not signature or not mint or order.get('status') not in {'uncertain', 'submitted', 'confirmed'}:
        raise PositionLedgerError('order is not a staged transaction')
    path = Path(ledger_path)
    if not path.is_absolute() or path == journal.directory or journal.directory in path.parents:
        raise PositionLedgerError('ledger path must be absolute and outside order journal')
    if path.exists():
        try:
            ledger = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise PositionLedgerError('corrupt ledger; refuse update') from exc
    else:
        ledger = {'schema': 1, 'wallet': wallet, 'observations': {}}
    if ledger.get('schema') != 1 or ledger.get('wallet') != wallet or not isinstance(ledger.get('observations'), dict):
        raise PositionLedgerError('ledger schema or wallet mismatch')
    existing = ledger['observations'].get(order_id)
    if existing is not None:
        if existing.get('signature') != signature:
            raise PositionLedgerError('order signature changed')
        return existing  # Idempotent: do not reapply balance deltas
    if any(e.get('signature') == signature for e in ledger['observations'].values()):
        raise PositionLedgerError('signature already recorded for another order')
    status = inspect_signature_status(signature, rpc_call)
    if status.get('status') != 'finalized':
        raise PositionLedgerError('signature not finalized; order remains blocked')
    result = inspect_transaction(signature, wallet, mint, rpc_call)
    sol_delta = _decimal(result['sol_delta'])
    token_delta = _decimal(result['token_delta'])
    fee = _decimal(result['network_fee_sol'])
    if fee < 0 or token_delta == 0:
        raise PositionLedgerError('unexpected fee or zero token delta; manual review required')
    if order.get('action') == 'buy' and (token_delta <= 0 or sol_delta >= 0):
        raise PositionLedgerError('buy direction inconsistent with observed balances')
    if order.get('action') == 'sell' and (token_delta >= 0 or sol_delta <= 0):
        raise PositionLedgerError('sell direction inconsistent with observed balances')
    observation = {'order_id': order_id, 'signature': signature, 'mint': mint,
                   'action': order['action'], 'sol_delta': str(sol_delta),
                   'token_delta': str(token_delta), 'network_fee_sol': str(fee),
                   'status': 'observed_finalized', 'requires_manual_review': True}
    ledger['observations'][order_id] = observation
    _atomic_write(path, ledger)
    return observation
