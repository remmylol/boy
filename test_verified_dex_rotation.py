"""The rotating discovery scanner must not starve executable DEX markets."""

import bot
from curve_activity import CurveActivity
from curve_rpc_activity import RpcCurveTradeTracker


def test_verified_dex_has_reserved_scan_slots(monkeypatch):
    monkeypatch.setattr(bot, 'VERIFIED_DEX_RECHECK_QUOTA', 2)
    monkeypatch.setattr(bot, 'FRESH_LAUNCH_SCAN_QUOTA', 3)
    monkeypatch.setattr(bot, '_verified_dex_mints', bot.OrderedDict())
    monkeypatch.setattr(bot, '_discovery_priority', {})
    bot.note_verified_dex_mint('usableA', now=100)
    bot.note_verified_dex_mint('usableB', now=100)
    monkeypatch.setattr(bot.time, 'monotonic', lambda: 101)
    chosen, cursor, fresh = bot.select_entry_mints(
        [f'fresh{i}' for i in range(12)], [f'fresh{i}' for i in range(12)],
        count=8, cursor=0)
    assert set(('usableA', 'usableB')).issubset(chosen)
    assert fresh == 3
    assert len(chosen) == len(set(chosen)) == 8
    assert cursor >= 0


def test_verified_dex_expires(monkeypatch):
    monkeypatch.setattr(bot, '_verified_dex_mints', bot.OrderedDict())
    monkeypatch.setattr(bot, 'VERIFIED_DEX_TTL_SECONDS', 30)
    bot.note_verified_dex_mint('old', now=100)
    assert bot.verified_dex_due(now=101) == ['old']
    assert bot.verified_dex_due(now=131) == []


def test_rpc_accepts_version_one_transactions():
    captured = []
    def rpc(method, params):
        if method == 'getSignaturesForAddress':
            return [{'signature': 'sig', 'blockTime': 1000, 'err': None}]
        captured.append(params)
        return {'blockTime': 1000, 'meta': {'err': None},
                'transaction': {'message': {'accountKeys': []}}}
    tracker = RpcCurveTradeTracker(rpc, CurveActivity(), address_fn=lambda _: 'curve')
    tracker.poll(['mint'], now_wall=1001, now_mono=100)
    assert captured[0][1]['maxSupportedTransactionVersion'] == 1
