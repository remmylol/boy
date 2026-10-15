"""Inspect saved unsigned Macca transaction, resolving ALT with RPC, never sign/send."""
import argparse
import json
import os
from pathlib import Path
from pumpportal_unsigned_inspector import inspect_bytes, InspectionError
from pumpportal_lookup_review import resolve_message_accounts, LookupReviewError
from pump_spend_review import review_instructions, SpendReviewError

DEFAULT_WALLET = 'ymJbeWeq78GPPzpdUa1awjGmTpMUMTuuqBxdTCgRmv4'
DEFAULT_MINT = 'AKotzk1dhcNangAJBtvNKtT9bhbSVZc2mMhRFgkFpump'

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--file', required=True, type=Path)
    p.add_argument('--wallet', default=DEFAULT_WALLET)
    p.add_argument('--mint', default=DEFAULT_MINT)
    a = p.parse_args()
    if not os.environ.get('SOLANA_RPC_URL'):
        p.error('SOLANA_RPC_URL is required (keep it private)')
    try:
        raw = a.file.read_bytes()
        baseline = inspect_bytes(raw, wallet=a.wallet, mint=a.mint)
        from solders.transaction import VersionedTransaction
        tx = VersionedTransaction.from_bytes(raw)
        resolved = resolve_message_accounts(tx.message, os.environ['SOLANA_RPC_URL'])
        spend_review = review_instructions(resolved, wallet=a.wallet, mint=a.mint)
        print(json.dumps({'baseline':baseline, 'resolved':resolved,
                          'spend_review':spend_review, 'approved_for_execution':False}, indent=2))
    except (OSError, InspectionError, LookupReviewError, SpendReviewError, ValueError) as exc:
        p.exit(2, f'Inspection failed: {exc}\n')

if __name__ == '__main__':
    main()
