"""Targeted offline regressions for bounded discovery and RPC scheduling."""
from unittest.mock import Mock

import bot
from curve_activity import CurveActivity
from curve_rpc_activity import RpcCurveTradeTracker
from test_smart_reentry_and_secondary_liquidity import pair, gecko_resp, reset_secondary, MINT


def test_secondary_preflight_spends_no_requests_on_unfit_volume_or_flow(monkeypatch):
    reset_secondary(monkeypatch)
    low = pair()
    low['volume']['m5'] = 50
    assert bot.secondary_candidate_priority(low) is None
    sinking = pair()
    sinking['txns']['m5'] = {'buys': 1, 'sells': 30}
    assert bot.secondary_candidate_priority(sinking) is None
    good = pair()
    assert bot.secondary_candidate_priority(good) is not None
    assert bot.secondary_candidate_priority(pair(liq=100)) is None
    assert bot.secondary_candidate_priority(pair(quote='USDC')) is None
    requested = Mock()
    monkeypatch.setattr(bot.session, 'get', requested)
    assert not requested.called


def test_secondary_deferred_queue_priority_ttl_and_retry_gate(monkeypatch):
    monkeypatch.setattr(bot, '_secondary_deferred', bot.OrderedDict())
    bot.secondary_defer('A', 10, retry_at=130, now=100)
    bot.secondary_defer('B', 100, retry_at=115, now=100)
    bot.secondary_defer('C', 30, retry_at=115, now=100)
    assert bot.secondary_due_mints(now=105) == []
    # B and C due, sorted by observed momentum, capped by configured quota
    assert bot.secondary_due_mints(now=120) == ['B', 'C']
    assert bot.secondary_due_mints(now=140) == ['B', 'C']
    assert not bot.secondary_due_mints(now=100 + bot.PAPER_SECONDARY_DEFERRED_TTL_SECONDS + 2)


def test_secondary_cached_verified_evidence_available_during_rate_limit(monkeypatch):
    reset_secondary(monkeypatch)
    monkeypatch.setattr(bot.session, 'get', Mock(return_value=gecko_resp()))
    verified, reason = bot.independently_verify_missing_liquidity(pair())
    assert verified and reason == 'verified_indicative_only'
    monkeypatch.setattr(bot, '_secondary_paused_until', bot.time.monotonic() + 60)
    second, reason = bot.independently_verify_missing_liquidity(pair())
    assert second and reason == 'verified_indicative_only'
    # Price divergence never inherits old approval, even during outage.
    invalid, reason = bot.independently_verify_missing_liquidity(pair(price='0.20'))
    assert invalid is None and reason == 'secondary_price_disagreement'


def test_rpc_backpressure_drains_before_ingesting_new_signatures():
    calls = []
    def rpc(method, params):
        calls.append(method)
        if method == 'getSignaturesForAddress':
            return []
        return None
    t = RpcCurveTradeTracker(rpc, CurveActivity(), address_fn=lambda mint: 'curve',
                             transaction_limit=1, signature_limit=2, max_pending=16)
    for i in range(13):
        t.pending[f'sig{i}'] = ('mint0', 1000)
    t.poll(['mint0'], now_wall=1010, now_mono=1010)
    d = t.diagnostics()
    assert d['backpressure_cycles'] == 1
    assert d['signature_scans_deferred'] == 1
    assert 'getSignaturesForAddress' not in calls
    assert d['pending_signatures'] == 13
    assert d['tx_null'] == 1


def test_rpc_scan_work_budget_and_rotation():
    scanned = []
    def rpc(method, params):
        if method == 'getSignaturesForAddress':
            scanned.append(params[0])
            return []
        raise AssertionError('No signatures means no getTransaction')
    t = RpcCurveTradeTracker(rpc, CurveActivity(), address_fn=lambda mint: mint,
                             transaction_limit=4, signature_limit=8)
    t.poll(['m1', 'm2', 'm3'], now_wall=1000, now_mono=1000)
    t.poll(['m1', 'm2', 'm3'], now_wall=1001, now_mono=1001)
    assert scanned == ['m1', 'm2']
    assert t.diagnostics()['signature_scans_deferred'] == 4
