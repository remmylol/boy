import requests
import bot
from pumpfun_boards import board_mints, valid_pumpfun_endpoint

M1 = 'A' * 32
M2 = 'B' * 32


def test_board_parser_rejects_unknown_shapes_and_duplicates():
    assert board_mints({'data': [{'mint': M1}, {'mint': M1}, {'token': {'address': M2}}, {'mint': 'not-a-mint'}]}) == [M1, M2]
    assert board_mints({'message': 'not token data'}) == []
    assert board_mints('untrusted data') == []


def test_endpoint_allowlist():
    assert valid_pumpfun_endpoint('https://advanced-api-v2.pump.fun/boards/movers')
    assert not valid_pumpfun_endpoint('http://advanced-api-v2.pump.fun/boards/movers')
    assert not valid_pumpfun_endpoint('https://advanced-api-v2.pump.fun.evil.example/boards/movers')


def test_board_fetch_merges_and_caches(monkeypatch):
    calls = []
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self): return [{'mint': M1}] if len(calls) == 1 else {'coins': [{'mint': M2}]}
    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()
    monkeypatch.setattr(bot.session, 'get', fake_get)
    monkeypatch.setattr(bot, 'PUMPFUN_BOARDS_ENABLED', True)
    monkeypatch.setattr(bot, 'PUMPFUN_MOVERS_ENABLED', True)
    monkeypatch.setattr(bot, 'PUMPFUN_TRENDING_ENABLED', True)
    monkeypatch.setattr(bot, 'PUMPFUN_BOARD_JWT', 'fake-test-token')
    monkeypatch.setattr(bot, 'PUMPFUN_BOARD_SESSION_ID', 'test-session')
    monkeypatch.setattr(bot, 'PUMPFUN_BOARD_USER_ID', 'test-user')
    monkeypatch.setattr(bot, 'PUMPFUN_TRENDING_ENDPOINT', 'https://frontend-api-v3.pump.fun/coins/top-runners')
    monkeypatch.setattr(bot, 'PUMPFUN_BOARDS_CACHE_SECONDS', 60)
    monkeypatch.setattr(bot, '_board_cache', {'until': 0., 'movers': [], 'trending': [], 'warn_at': 0.})
    assert bot.pumpfun_board_candidates() == {'movers': [M1], 'trending': [M2]}
    assert bot.pumpfun_board_candidates() == {'movers': [M1], 'trending': [M2]}
    assert len(calls) == 2
    assert calls[0][1]['params']['userId'] == 'test-user'
    assert calls[0][1]['headers']['Authorization'] == 'Bearer fake-test-token'


def test_board_failure_is_not_entry_authorization(monkeypatch):
    monkeypatch.setattr(bot, 'PUMPFUN_BOARDS_ENABLED', True)
    monkeypatch.setattr(bot, 'PUMPFUN_MOVERS_ENABLED', False)
    monkeypatch.setattr(bot, 'PUMPFUN_TRENDING_ENABLED', True)
    monkeypatch.setattr(bot, 'PUMPFUN_TRENDING_ENDPOINT', 'https://frontend-api-v3.pump.fun/coins/top-runners')
    monkeypatch.setattr(bot, '_board_cache', {'until': 0., 'movers': [], 'trending': [], 'warn_at': 0.})
    def fail_get(*args, **kwargs):
        raise requests.HTTPError('503')
    monkeypatch.setattr(bot.session, 'get', fail_get)
    assert bot.pumpfun_board_candidates() == {'movers': [], 'trending': []}


def test_no_board_fetch_when_disabled(monkeypatch):
    monkeypatch.setattr(bot, 'PUMPFUN_BOARDS_ENABLED', False)
    assert bot.pumpfun_board_candidates() == {'movers': [], 'trending': []}
