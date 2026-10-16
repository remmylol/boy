import requests
import bot
from fomo_boards import extract_fomo_mints

M1 = 'A' * 32
M2 = 'B' * 32


def _cache():
    return {'until': 0.0, 'graduated': [], 'trending': [], 'warn_at': 0.0, 'disabled': set()}


def test_sol_only_token_board_shape_and_dedupe():
    payload = {'board':'graduated', 'tokens': [
        {'token': {'address': M1}, 'network': 'solana'},
        {'token': {'address': M1}, 'network': 'sol'},
        {'token': {'address': M2}, 'network': 'ethereum'},
        {'token': {'address': M2}},
        {'token': {'address': '0x'+'a'*40}, 'network': 'solana'},
    ]}
    assert extract_fomo_mints(payload) == [M1]
    assert extract_fomo_mints({**payload, 'stale': True}) == []
    assert extract_fomo_mints({'available':False,'tokens':payload['tokens']}) == []


def test_no_key_no_requests(monkeypatch):
    monkeypatch.setattr(bot, 'FOMO_BOARDS_ENABLED', True)
    monkeypatch.setattr(bot, 'FOMO_API_KEY', '')
    monkeypatch.setattr(bot.session, 'get', lambda *a, **k: (_ for _ in ()).throw(AssertionError('unexpected call')))
    assert bot.fomo_board_candidates() == {'graduated': [], 'trending': []}


def test_fomo_fetch_two_boards_and_cache(monkeypatch):
    calls = []
    class FakeResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {'source':'live-fomo', 'tokens':[{'token':{'address':M1}, 'network':'solana'}]}
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()
    monkeypatch.setattr(bot, 'FOMO_BOARDS_ENABLED', True)
    monkeypatch.setattr(bot, 'FOMO_API_KEY', 'test-key')
    monkeypatch.setattr(bot, 'FOMO_GRADUATED_ENABLED', True)
    monkeypatch.setattr(bot, 'FOMO_TRENDING_ENABLED', True)
    monkeypatch.setattr(bot, '_fomo_cache', _cache())
    monkeypatch.setattr(bot.session, 'get', get)
    assert bot.fomo_board_candidates() == {'graduated':[M1], 'trending':[M1]}
    assert bot.fomo_board_candidates() == {'graduated':[M1], 'trending':[M1]}
    assert len(calls) == 2
    assert calls[0][1]['headers']['Authorization'] == 'Bearer test-key'
    assert calls[1][0].endswith('/tokens/trending')


def test_auth_failure_disables_board_without_disabling_other_source(monkeypatch):
    class Response:
        def __init__(self, code): self.status_code = code
        def raise_for_status(self): pass
        def json(self): return {'tokens':[{'token':{'address':M2},'network':'sol'}]}
    monkeypatch.setattr(bot, 'FOMO_BOARDS_ENABLED', True)
    monkeypatch.setattr(bot, 'FOMO_API_KEY', 'key')
    monkeypatch.setattr(bot, 'FOMO_GRADUATED_ENABLED', True)
    monkeypatch.setattr(bot, 'FOMO_TRENDING_ENABLED', True)
    monkeypatch.setattr(bot, '_fomo_cache', _cache())
    monkeypatch.setattr(bot.session,'get', lambda url, **k: Response(402 if url.endswith('graduated') else 200))
    assert bot.fomo_board_candidates() == {'graduated': [], 'trending': [M2]}
    assert 'graduated' in bot._fomo_cache['disabled']


def test_unavailable_and_network_failure_are_safe(monkeypatch):
    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {'available':False, 'tokens': []}
    monkeypatch.setattr(bot, 'FOMO_BOARDS_ENABLED', True)
    monkeypatch.setattr(bot, 'FOMO_API_KEY', 'key')
    monkeypatch.setattr(bot, 'FOMO_GRADUATED_ENABLED', True)
    monkeypatch.setattr(bot, 'FOMO_TRENDING_ENABLED', True)
    monkeypatch.setattr(bot, '_fomo_cache', _cache())
    monkeypatch.setattr(bot.session,'get',lambda url, **k: Response() if url.endswith('graduated') else (_ for _ in ()).throw(requests.ConnectionError()))
    assert bot.fomo_board_candidates() == {'graduated': [], 'trending': []}
