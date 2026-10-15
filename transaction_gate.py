"""Fail-closed transaction staging boundary. NO signing or broadcasting.

The validator must independently verify actual serialized Solana instructions,
wallet signer, mint, SOL outflow, fee/rent reserve, and slippage. This module
never treats caller-supplied metadata as proof of transaction safety.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from order_journal import Journal
from transaction_recovery import stage_signed_transaction


class GateError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReviewedTransaction:
    signature: str
    signed_bytes: bytes
    wallet: str
    mint: str
    action: str
    max_total_sol_outflow: Decimal
    validated: bool


def stage_reviewed_buy(*, journal_dir: str, mint: str, wallet: str,
                       requested_usd: str, sol_usd: str, balance_sol: str,
                       open_positions: int, quote_age_seconds: float,
                       approved: bool, build_and_validate: Callable[..., ReviewedTransaction]):
    """Create durable intent before invoking an injected *offline* validator.

    The callback MUST NOT broadcast. If it fails, intent stays blocking.
    No signing keys are loaded here. The signed bytes are persisted before
    any possible future separate submission, which is NOT implemented.
    """
    if not approved:
        raise GateError('explicit supervised staging approval required')
    if not Path(journal_dir).is_absolute():
        raise GateError('journal directory must be absolute')
    try:
        usd = Decimal(requested_usd)
        price = Decimal(sol_usd)
        balance = Decimal(balance_sol)
        age = Decimal(str(quote_age_seconds))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise GateError('invalid numerical input') from exc
    if not all(x.is_finite() for x in (usd, price, balance, age)):
        raise GateError('non-finite numerical input')
    if not (Decimal('0') < usd <= Decimal('10')) or price <= 0 or balance < 0:
        raise GateError('invalid size, price or balance')
    if age < 0 or age > 30 or type(open_positions) is not int or not (0 <= open_positions < 2):
        raise GateError('stale quote or position limit')
    if not mint or not wallet:
        raise GateError('mint and wallet required')
    journal = Journal(journal_dir)
    journal.assert_no_unresolved()
    # An intent is persisted *before* building any signed transaction.
    intent = journal.create_intent(action='buy', mint=mint, usd=float(usd))
    try:
        reviewed = build_and_validate(order_id=intent['id'], mint=mint, wallet=wallet,
                                       max_usd=usd, sol_usd=price)
        if not isinstance(reviewed, ReviewedTransaction) or reviewed.validated is not True:
            raise GateError('independent instruction validation required')
        if (reviewed.wallet != wallet or reviewed.mint != mint or reviewed.action != 'buy'
                or not isinstance(reviewed.max_total_sol_outflow, Decimal)
                or not reviewed.max_total_sol_outflow.is_finite()
                or reviewed.max_total_sol_outflow <= 0):
            raise GateError('reviewed transaction mismatch')
        # Include all fees/rent in the maximum total debit, not only swap input.
        if reviewed.max_total_sol_outflow * price > usd:
            raise GateError('signed transaction could exceed USD limit')
        if (balance - reviewed.max_total_sol_outflow) * price < Decimal('5'):
            raise GateError('signed transaction would breach $5 SOL reserve')
        return stage_signed_transaction(journal, intent['id'], signature=reviewed.signature,
                                        signed_transaction=reviewed.signed_bytes)
    except Exception:
        # Never automatically delete or retry the persisted intent.
        raise
