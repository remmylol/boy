"""Fail-closed, OFFLINE-only supervised lifecycle rehearsal.

No network, wallet secrets, signer, or transaction broadcast are used here.
Never use this module to authorize a live transaction.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from order_journal import Journal, JournalError
from transaction_recovery import stage_signed_transaction, inspect_signature_status
from wallet_reconciliation import inspect_transaction

class LifecycleError(RuntimeError):
    pass

@dataclass(frozen=True)
class RehearsalResult:
    order_id: str
    signature: str
    status: str
    sol_delta: str | None = None
    token_delta: str | None = None


def prepare_offline_buy(*, journal_dir: str, mint: str, usd: float, approved: bool,
                        signature: str, synthetic_signed_tx: bytes) -> RehearsalResult:
    """Record an explicitly approved *simulation*, then stage synthetic bytes.

    Uses the real journal layout to exercise persistence, but never signs or sends.
    Use a separate temporary journal directory, NOT /data/live_orders.
    """
    directory = Path(journal_dir).resolve()
    if str(directory) == '/data/live_orders' or str(directory).startswith('/data/live_orders/'):
        raise LifecycleError('offline rehearsal must not touch live order journal')
    if not approved:
        raise LifecycleError('explicit offline rehearsal approval required')
    try:
        size = Decimal(str(usd))
    except InvalidOperation as exc:
        raise LifecycleError('invalid size') from exc
    if not size.is_finite() or size <= 0 or size > 10:
        raise LifecycleError('simulated buy must be $0-$10')
    journal = Journal(str(directory))
    journal.assert_no_unresolved()
    intent = journal.create_intent(action='buy', mint=mint, usd=float(size))
    stage_signed_transaction(journal, intent['id'], signature=signature,
                             signed_transaction=synthetic_signed_tx)
    return RehearsalResult(intent['id'], signature, 'uncertain')


def inspect_offline_order(*, journal_dir: str, order_id: str, signature: str,
                          wallet: str, mint: str, rpc_call) -> RehearsalResult:
    """Read-only inspection. Never marks a journal entry reconciled or unblocks it."""
    journal = Journal(journal_dir)
    matches = [e for e in journal.entries() if e.get('id') == order_id]
    if len(matches) != 1 or matches[0].get('signature') != signature:
        raise LifecycleError('journal entry/signature mismatch')
    status = inspect_signature_status(signature, rpc_call)
    if status['status'] != 'finalized':
        return RehearsalResult(order_id, signature, status['status'])
    balances = inspect_transaction(signature, wallet, mint, rpc_call)
    return RehearsalResult(order_id, signature, 'observed_finalized',
                           balances['sol_delta'], balances['token_delta'])
