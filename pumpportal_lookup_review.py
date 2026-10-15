"""Read-only address lookup table resolution for PumpPortal transaction reports.

RPC is used exclusively for getAddressLookupTable. No signing or sending.
Reports are descriptive and never approve execution.
"""
from __future__ import annotations
import json
from urllib.request import Request, urlopen

class LookupReviewError(ValueError):
    pass

def get_lookup_addresses(rpc_url: str, table_address: str, *, opener=urlopen) -> list[str]:
    if not rpc_url.startswith(('https://', 'http://')):
        raise LookupReviewError('Expected HTTP(S) RPC endpoint')
    body = json.dumps({'jsonrpc':'2.0','id':1,'method':'getAddressLookupTable',
                       'params':[table_address]}).encode()
    req = Request(rpc_url, data=body, headers={'Content-Type':'application/json'}, method='POST')
    try:
        with opener(req, timeout=15) as response:
            result = json.loads(response.read(1_000_000))
        if result.get('error'):
            raise LookupReviewError('RPC lookup failed')
        value = result['result']['value']
        if not value or not isinstance(value['state']['addresses'], list):
            raise LookupReviewError('Lookup table missing or invalid')
        addresses = value['state']['addresses']
        if not all(isinstance(a, str) for a in addresses):
            raise LookupReviewError('Invalid address list')
        return addresses
    except LookupReviewError:
        raise
    except Exception as exc:
        # Do not echo RPC URLs, which can contain credentials.
        raise LookupReviewError('Could not resolve lookup table') from exc

def resolve_message_accounts(message, rpc_url: str, *, fetch=get_lookup_addresses) -> dict:
    """Resolve v0 account indices in canonical static + writable + readonly order."""
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
        if any(a >= len(keys) for a in [program_idx] + indices):
            raise LookupReviewError('Instruction account index out of bounds')
        instructions.append({'index':i, 'program':keys[program_idx],
                             'accounts':[keys[a] for a in indices],
                             'data_hex':bytes(ins.data).hex()})
    return {'static_account_count':len(static), 'loaded_writable_count':len(writable),
            'loaded_readonly_count':len(readonly), 'lookup_tables':tables,
            'instructions':instructions, 'approved_for_execution':False,
            'warnings':['Read-only report; does not validate opaque swap instruction semantics, max debit, slippage, rent, or downstream effects',
                        'Lookup table contents are RPC observations; a later transaction may see different chain state']}
