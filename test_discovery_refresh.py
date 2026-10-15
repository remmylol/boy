from collections import Counter
import bot


def test_discovery_search_adds_solana_mints(monkeypatch):
    monkeypatch.setattr(bot, 'DISCOVERY_SEARCH_TERMS', ('pump',))
    monkeypatch.setattr(bot, 'DISCOVERY_SEARCHES_PER_SCAN', 1)
    monkeypatch.setattr(bot, 'DISCOVERY_CACHE_SECONDS', 30)
    monkeypatch.setattr(bot, '_discovery_round', 0)
    monkeypatch.setattr(bot, '_discovery_seen', set())
    bot._discovery_cache.update(until=0, addresses=[])
    monkeypatch.setattr(bot, 'get_json', lambda url: [{'chainId': 'solana', 'tokenAddress': 'A'}])
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {'pairs': [{'chainId': 'solana', 'baseToken': {'address': 'B'}},
                              {'chainId': 'ethereum', 'baseToken': {'address': 'C'}}]}
    monkeypatch.setattr(bot.session, 'get', lambda *a, **kw: Response())
    assert bot.latest_candidate_addresses() == ['A', 'B']
    assert bot.latest_candidate_addresses() == ['A', 'B']


def test_momentum_rejections_are_counted():
    counts = Counter()
    pair = {'baseToken': {'address': 'Mint', 'symbol': 'M'}, 'priceUsd': '0.1',
            'liquidity': {'usd': 30000}, 'volume': {'m5': 0},
            'pairCreatedAt': 1}
    assert bot.analyze_pair(pair, counts) is None
    assert counts
