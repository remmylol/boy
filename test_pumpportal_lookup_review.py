from types import SimpleNamespace as NS
import pytest
from pumpportal_lookup_review import resolve_message_accounts, LookupReviewError

def test_order_and_account_resolution():
    lookup = NS(account_key='table', writable_indexes=[1], readonly_indexes=[0])
    ins = NS(program_id_index=2, accounts=[0,1,3], data=b'\x01')
    msg = NS(account_keys=['wallet','mint'], address_table_lookups=[lookup], instructions=[ins])
    r = resolve_message_accounts(msg, 'https://example.org', fetch=lambda rpc, table:['readonly','program'])
    assert r['instructions'][0]['program'] == 'program'
    assert r['instructions'][0]['accounts'] == ['wallet','mint','readonly']
    assert r['approved_for_execution'] is False

def test_bad_lookup_index_fails_closed():
    lookup = NS(account_key='table', writable_indexes=[9], readonly_indexes=[])
    msg = NS(account_keys=['wallet'], address_table_lookups=[lookup], instructions=[])
    with pytest.raises(LookupReviewError):
        resolve_message_accounts(msg, 'https://example.org', fetch=lambda *_:['only'])

def test_bad_instruction_index_fails_closed():
    msg = NS(account_keys=['wallet'], address_table_lookups=[], instructions=[NS(program_id_index=2,accounts=[],data=b'')])
    with pytest.raises(LookupReviewError):
        resolve_message_accounts(msg, 'https://example.org')
