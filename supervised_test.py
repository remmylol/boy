"""Read-only supervised-trade preflight. Never signs or broadcasts transactions."""
import argparse
import json
import os
import time
from pathlib import Path
import requests
from live_safety import buy_preflight, checked_sol_price, SafetyError


def preflight(mint: str, amount_usd: float, *, rpc_url: str, wallet_address: str, state_dir: str = '/data') -> dict:
    from solders.pubkey import Pubkey
    try:
        Pubkey.from_string(mint)
        Pubkey.from_string(wallet_address)
    except Exception as exc:
        raise SafetyError('invalid token mint or public wallet address') from exc
    if not rpc_url.startswith('https://'):
        raise SafetyError('RPC must use HTTPS')
    state_path = Path(state_dir)
    if not state_path.is_dir() or not os.access(state_path, os.W_OK):
        raise SafetyError('persistent state directory unavailable or not writable')
    if (state_path / 'live_orders.json').exists():
        raise SafetyError('existing live order ledger requires reconciliation before trading')
    try:
        response = requests.post(rpc_url, json={'jsonrpc':'2.0','id':1,'method':'getBalance','params':[wallet_address,{'commitment':'confirmed'}]},timeout=12)
        response.raise_for_status()
        body = response.json()
        if 'error' in body:
            raise SafetyError('wallet RPC returned error')
        balance_sol = int(body['result']['value']) / 1e9
        quote = requests.get('https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd',timeout=12)
        quote.raise_for_status()
        sol_usd = checked_sol_price(quote.json())
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        raise SafetyError('wallet balance or SOL price unavailable; no trade permitted') from exc
    # Price is sampled during this function; quote-age cannot be measured from a timestamp-less feed.
    # Fail closed for execution use: this output is diagnostic only.
    sol_amount = buy_preflight(requested_usd=amount_usd, sol_usd=sol_usd,
        balance_sol=balance_sol, open_positions=0, pending_orders=0,
        wallet_verified=True, quote_age_seconds=0)
    return {'mode':'READ_ONLY_PREFLIGHT', 'wallet_sol':balance_sol, 'sol_usd_estimate':sol_usd,
            'requested_usd':amount_usd, 'estimated_sol':sol_amount, 'mint':mint,
            'limitations':['No transaction quote or sellability check','No on-chain position count',
                           'No timestamped price freshness','No signing or broadcasting']}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--mint',required=True)
    p.add_argument('--usd',type=float,default=2.0)
    p.add_argument('--state-dir',default='/data')
    args = p.parse_args()
    if os.getenv('LIVE_TRADING_ENABLED','false').lower() == 'true':
        p.error('LIVE_TRADING_ENABLED must remain false for this read-only preflight')
    try:
        result = preflight(args.mint,args.usd,rpc_url=os.getenv('SOLANA_RPC_URL',''),
                           wallet_address=os.getenv('SOLANA_WALLET_ADDRESS',''),state_dir=args.state_dir)
    except SafetyError as exc:
        p.error(str(exc))
    print(json.dumps(result,indent=2))
    print('NO REAL TRANSACTION SENT')

if __name__ == '__main__':
    main()
