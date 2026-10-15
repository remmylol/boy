"""Read-only Solana v0 address lookup-table resolution via getAccountInfo.

Never signs, broadcasts, or approves transactions. RPC URLs are not printed.
"""
from __future__ import annotations
import base64
import json
from urllib.request import Request, urlopen

ALT_PROGRAM = 'AddressLookupTab1e1111111111111111111111111'
_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

class LookupReviewError(ValueError):
    pass

def _b58(data: bytes) -> str:
    n = int.from_bytes(data, 'big')
    chars = ''
    while n:
        n, rem = divmod(n, 58)
        chars = _ALPHABET[rem] + chars
    return '1' * (len(data) - len(data.lstrip(b'\x00'))) + chars

def decode_lookup_account(value: dict) -> list[str]:
    """Validate ALT account owner/layout and decode its stored 32-byte addresses."""
    if not isinstance(value, dict) or value.get('owner') != ALT_PROGRAM:
        raise LookupReviewError('Lookup table account missing or has unexpected owner')
    if value.get('executable') is not False:
        raise LookupReviewError('Unexpected executable lookup table account')
    encoded = value.get('data')
    if not isinstance(encoded, list) or len(encoded) != 2 or encoded[1] != 'base64':
        raise LookupReviewError('Lookup account data is not base64')
    try:
        raw = base64.b64decode(encoded[0], validate=True)
    except (ValueError, TypeError) as exc:
        raise LookupReviewError('Malformed lookup account base64') from exc
    if len(raw) < 56 or (len(raw) - 56) % 32:
        raise LookupReviewError('Invalid lookup account data length')
    if int.from_bytes(raw[:4], 'little') != 1:
        raise LookupReviewError('Unexpected lookup account type')
    if (len(raw) - 56) // 32 > 256:
        raise LookupReviewError('Lookup account exceeds maximum addresses')
    return [_b58(raw[i:i+32]) for i in range(56, len(raw), 32)]

def get_lookup_addresses(rpc_url: str, table_address: str, *, opener=urlopen) -> list[str]:
    if not rpc_url.startswith(('https://', 'http://')):
        raise LookupReviewError('Expected HTTP(S) RPC endpoint')
    body = json.dumps({'jsonrpc':'2.0','id':1,'method':'getAccountInfo',
                       'params':[table_address, {'encoding':'base64','commitment':'finalized'}]}).encode()
    req = Request(rpc_url, data=body, headers={'Content-Type':'application/json'}, method='POST')
    try:
        with opener(req, timeout=20) as response:
            result = json.loads(response.read(1_000_000))
    except Exception as exc:
        raise LookupReviewError('Could not fetch lookup table account from RPC') from exc
    if result.get('error'):
        error = result['error']
        code = error.get('code', 'unknown') if isinstance(error, dict) else 'unknown'
        raise LookupReviewError(f'RPC getAccountInfo returned error code {code}')
    try:
        value = result['result']['value']
    except (KeyError, TypeError) as exc:
        raise LookupReviewError('Unexpected getAccountInfo response') from exc
    return decode_lookup_account(value)

def resolve_message_accounts(message, rpc_url: str, *, fetch=get_lookup_addresses) -> dict:
    """Resolve v0 indices in static + all writable + all readonly order."""
    static = [str(a) for a in message.account_keys]
    writable, readonly, tables = [], [], []
    for lookup in getattr(message, 'address_table_lookups', ()):
        table = str(lookup.account_key)
        addresses = fetch(rpc_url, table)
        wi, ri = [int(x) for x in lookup.writable_indexes], [int(x) for x in lookup.readonly_indexes]
        if any(i < 0 or i >= len(addresses) for i in wi + ri):
            raise LookupReviewError('Lookup table index out of bounds')
        writable.extend(addresses[i] for i in wi)
        readonly.extend(addresses[i] for i in ri)
        tables.append({'table':table, 'writable_count':len(wi), 'readonly_count':len(ri)})
    keys = static + writable + readonly
    instructions = []
    for i, ins in enumerate(message.instructions):
        program_idx = int(ins.program_id_index)
        indices = [int(a) for a in ins.accounts]
        if any(a < 0 or a >= len(keys) for a in [program_idx] + indices):
            raise LookupReviewError('Instruction account index out of bounds')
        instructions.append({'index':i, 'program':keys[program_idx],
                             'accounts':[keys[a] for a in indices],
                             'data_hex':bytes(ins.data).hex()})
    return {'static_account_count':len(static), 'loaded_writable_count':len(writable),
            'loaded_readonly_count':len(readonly), 'lookup_tables':tables,
            'instructions':instructions, 'approved_for_execution':False,
            'warnings':['Read-only report; does not validate swap semantics, max debit, slippage, rent, or downstream effects',
                        'Lookup table contents are RPC observations, not proof of execution safety']}
