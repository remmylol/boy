import base64
import io
import json
from pumpportal_lookup_review import ALT_PROGRAM, decode_lookup_account, get_lookup_addresses, LookupReviewError
import pytest

def account(owner=ALT_PROGRAM, raw=None):
    raw = raw if raw is not None else (1).to_bytes(4,'little') + bytes(52) + bytes([1])*32
    return {'owner':owner,'executable':False,'data':[base64.b64encode(raw).decode(),'base64']}

def test_decode():
    assert len(decode_lookup_account(account())) == 1

def test_bad_owner():
    with pytest.raises(LookupReviewError): decode_lookup_account(account(owner='bad'))

def test_bad_length():
    with pytest.raises(LookupReviewError): decode_lookup_account(account(raw=bytes(57)))

def test_rpc_method():
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return json.dumps({'result':{'value':account()}}).encode()
    def opener(req, timeout):
        payload = json.loads(req.data)
        assert payload['method'] == 'getAccountInfo'
        assert payload['params'][1]['encoding'] == 'base64'
        return Response()
    assert len(get_lookup_addresses('https://example.org','test',opener=opener)) == 1
