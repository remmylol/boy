"""Offline end-to-end state-machine rehearsal; NEVER signs or sends a transaction.

A fake signature and synthetic transaction bytes are used solely to exercise
journal persistence, unknown broadcast outcomes, and read-only reconciliation.
This module must not be imported as a live executor.
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from pathlib import Path
from order_journal import Journal, JournalError
from transaction_recovery import stage_signed_transaction, inspect_pending_orders
from wallet_reconciliation import inspect_transaction

class SimulationError(RuntimeError):
    pass

@dataclass(frozen=True)
class SimulationReport:
    order_id: str
    staged: bool
    broadcast_simulated: bool
    pending_blocked: bool
    signature_status: str
    reconciliation_status: str
    journal_unresolved: int


def run_offline_rehearsal(*, journal_dir: str, mint: str, wallet: str,
                          rpc_call, simulated_broadcast, usd: float = 2.0) -> SimulationReport:
    """Exercise only fake bytes and injected callbacks; never connects to Solana.

    The simulated_broadcast callback must be a test double. The journal is left
    unresolved deliberately: reconciliation is read-only, not settlement proof.
    """
    if not Path(journal_dir).is_absolute():
        raise SimulationError('absolute journal directory required')
    if not wallet or not mint:
        raise SimulationError('wallet and mint required')
    journal = Journal(journal_dir)
    journal.assert_no_unresolved()
    intent = journal.create_intent(action='buy', mint=mint, usd=usd)
    # Deterministic syntactically valid dummy signature; NOT a Solana signature.
    signature = '1' * 88
    fake_bytes = b'OFFLINE_FAKE_TRANSACTION_DO_NOT_BROADCAST_' + bytes(120)
    stage_signed_transaction(journal, intent['id'], signature=signature,
                             signed_transaction=fake_bytes)
    try:
        journal.assert_no_unresolved()
    except JournalError:
        blocked = True
    else:
        blocked = False
    if not blocked:
        raise SimulationError('CRITICAL: staged order did not block new orders')
    # A supplied callback only. This function never imports requests or live_adapter.
    simulated_broadcast(fake_bytes)
    findings = inspect_pending_orders(journal, rpc_call)
    matching = [x for x in findings if x.get('id') == intent['id']]
    if len(matching) != 1:
        raise SimulationError('missing simulated order status')
    try:
        observed = inspect_transaction(signature, wallet, mint, rpc_call)
        reconciliation_status = observed['status']
    except Exception:
        reconciliation_status = 'unavailable_keep_blocked'
    return SimulationReport(intent['id'], True, True, blocked,
                            matching[0]['status'], reconciliation_status,
                            journal.status()['unresolved'])
