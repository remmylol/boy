"""Read-only on-chain transaction accounting. Never signs, broadcasts or clears journal blockers."""
from __future__ import annotations
from decimal import Decimal

class ReconciliationError(RuntimeError):
    pass


def _token_amount(rows, owner, mint):
    total = Decimal(0)
    for row in rows or []:
        if row.get('owner') == owner and row.get('mint') == mint:
            info = row.get('uiTokenAmount') or {}
            raw = info.get('amount')
            decimals = info.get('decimals')
            if not isinstance(raw, str) or not raw.isdigit() or not isinstance(decimals, int) or not 0 <= decimals <= 18:
                raise ReconciliationError('invalid token amount data')
            total += Decimal(raw) / (Decimal(10) ** decimals)
    return total


def inspect_transaction(signature: str, wallet: str, mint: str, rpc_call) -> dict:
    """Compute observed SOL/token deltas for a finalized transaction; no journal mutation.

    Note: SOL delta includes network fees, rent and all transfers; it is not a
    verified swap quote or an independently proven spend cap.
    """
    if not all(isinstance(x, str) and x.strip() for x in (signature, wallet, mint)):
        raise ReconciliationError('signature, wallet and mint are required')
    try:
        result = rpc_call('getTransaction', [signature, {'encoding': 'jsonParsed', 'commitment': 'finalized', 'maxSupportedTransactionVersion': 0}])
    except Exception as exc:
        raise ReconciliationError('transaction RPC unavailable; keep order blocked') from exc
    if result is None:
        raise ReconciliationError('transaction unavailable; keep order blocked')
    meta = result.get('meta')
    if not isinstance(meta, dict) or meta.get('err') is not None:
        raise ReconciliationError('transaction missing metadata or failed; keep order blocked')
    message = (result.get('transaction') or {}).get('message') or {}
    keys = message.get('accountKeys') or []
    addresses = [x.get('pubkey') if isinstance(x, dict) else x for x in keys]
    if addresses.count(wallet) != 1:
        raise ReconciliationError('wallet not uniquely present in transaction')
    index = addresses.index(wallet)
    pre, post = meta.get('preBalances'), meta.get('postBalances')
    if not isinstance(pre, list) or not isinstance(post, list) or index >= len(pre) or index >= len(post):
        raise ReconciliationError('missing SOL balance information')
    try:
        sol_delta = Decimal(int(post[index]) - int(pre[index])) / Decimal(10**9)
        token_delta = _token_amount(meta.get('postTokenBalances'), wallet, mint) - _token_amount(meta.get('preTokenBalances'), wallet, mint)
        fee = Decimal(int(meta['fee'])) / Decimal(10**9)
    except (ValueError, TypeError, KeyError) as exc:
        raise ReconciliationError('invalid balance or fee information') from exc
    return {'signature': signature, 'wallet': wallet, 'mint': mint,
            'sol_delta': str(sol_delta), 'token_delta': str(token_delta),
            'network_fee_sol': str(fee), 'status': 'observed_finalized',
            'warning': 'Read-only observation, not verified trade intent; do not automatically clear journal.'}
