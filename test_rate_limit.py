import time
import pytest
import bot


def test_http_429_starts_global_cooldown(monkeypatch):
    class Response:
        status_code = 429
        headers = {'Retry-After': '35'}
    monkeypatch.setattr(bot.session, 'get', lambda *args, **kwargs: Response())
    monkeypatch.setattr(bot, '_api_cooldown_until', 0.0)
    monkeypatch.setattr(bot, '_last_market_request_at', 0.0)
    monkeypatch.setattr(bot, 'MARKET_REQUEST_SPACING_SECONDS', 0.0)
    with pytest.raises(bot.DexRateLimited):
        bot.dex_request('https://api.dexscreener.com/test')
    assert bot.api_cooldown_remaining() >= 30
    with pytest.raises(bot.DexRateLimited):
        bot.dex_request('https://api.dexscreener.com/test')
    monkeypatch.setattr(bot, '_api_cooldown_until', 0.0)


def test_discovery_cache_keeps_previous_list_on_failure(monkeypatch):
    monkeypatch.setattr(bot, '_api_cooldown_until', 0.0)
    monkeypatch.setattr(bot, 'get_json', lambda url: (_ for _ in ()).throw(RuntimeError('offline')))
    monkeypatch.setattr(bot, 'DISCOVERY_SEARCH_TERMS', ())
    bot._discovery_cache.update(until=0.0, addresses=['previous'])
    assert bot.latest_candidate_addresses() == ['previous']
