"""Supervised DRY-RUN controller. No signer, wallet secrets, or network broadcast.

The approval phrase authorizes a preview only, never a real transaction.
Existing pending journal entries block new previews. The controller does not
create order intents, mutate journal files, or mark transactions reconciled.
"""
from __future__ import annotations
import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from live_execution import preview_buy, ExecutionBlocked
from order_journal import Journal, JournalError
from transaction_recovery import inspect_pending_orders
from wallet_reconciliation import inspect_transaction


class ControllerError(RuntimeError):
    pass


@dataclass(frozen=True)
class DryRunResult:
    mode: str
    action: str
    mint: str
    requested_usd: float
    estimated_sol: float
    journal_unresolved: int
    approved_preview: bool
    broadcast: bool = False
    note: str = 'No private key loaded, no transaction signed or broadcast'


def preview_approved_buy(*, mint: str, requested_usd: float, sol_usd: float,
                         balance_sol: float, open_positions: int,
                         wallet_verified: bool, quote_age_seconds: float,
                         approval: str, journal_dir: str = '/data/live_orders') -> DryRunResult:
    """Require a deliberate approval phrase to preview a buy. NOT trade approval."""
    if os.getenv('LIVE_TRADING_ENABLED', 'false').strip().lower() in ('1', 'true', 'yes', 'on'):
        raise ControllerError('dry-run controller refuses LIVE_TRADING_ENABLED=true')
    if approval != 'APPROVE DRY RUN ONLY':
        raise ControllerError('exact dry-run approval phrase required')
    try:
        journal = Journal(journal_dir)
        pending = journal.status()['unresolved']
        preview = preview_buy(mint=mint, requested_usd=requested_usd,
                              sol_usd=sol_usd, balance_sol=balance_sol,
                              open_positions=open_positions,
                              wallet_verified=wallet_verified,
                              quote_age_seconds=quote_age_seconds,
                              journal_dir=journal_dir)
    except (JournalError, ExecutionBlocked) as exc:
        raise ControllerError(str(exc)) from exc
    return DryRunResult('DRY_RUN_ONLY', 'buy', preview.mint, preview.usd,
                        preview.estimated_sol, pending, True)


def review_pending_readonly(*, journal_dir: str, rpc_call) -> list[dict]:
    """Review pending signatures; never clear blockers or retry transactions."""
    return inspect_pending_orders(Journal(journal_dir), rpc_call)


def reconcile_readonly(*, signature: str, wallet: str, mint: str, rpc_call) -> dict:
    """Observe finalized token and SOL deltas; never mark an order settled."""
    return inspect_transaction(signature, wallet, mint, rpc_call)


def main():
    parser = argparse.ArgumentParser(description='Offline dry-run only; no blockchain transactions')
    parser.add_argument('--mint', required=True)
    parser.add_argument('--usd', type=float, default=2.0)
    parser.add_argument('--sol-usd', type=float, required=True, help='Example SOL/USD price; not a live quote')
    parser.add_argument('--balance-sol', type=float, required=True, help='Example SOL balance; not verified on chain')
    parser.add_argument('--open-positions', type=int, default=0)
    parser.add_argument('--journal-dir', default='/data/live_orders')
    parser.add_argument('--approval', required=True, help='APPROVE DRY RUN ONLY')
    args = parser.parse_args()
    try:
        result = preview_approved_buy(mint=args.mint, requested_usd=args.usd,
            sol_usd=args.sol_usd, balance_sol=args.balance_sol,
            open_positions=args.open_positions, wallet_verified=True,  # SIMULATED for offline CLI preview only
            quote_age_seconds=0, approval=args.approval, journal_dir=args.journal_dir)
    except ControllerError as exc:
        parser.error(str(exc))
    print(json.dumps(asdict(result), indent=2))


if __name__ == '__main__':
    main()
