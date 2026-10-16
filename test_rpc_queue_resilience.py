"""Regression cases for RPC queue prioritization and non-blocking retries."""
from curve_activity import CurveActivity
from curve_rpc_activity import RpcCurveTradeTracker, RpcTradeError

MINT = "mint_for_test"

def _sig(name, ts):
    return {"signature": name, "blockTime": ts, "err": None}

def test_one_failed_transaction_does_not_block_newer_transactions():
    calls = []
    def rpc(method, args):
        if method == "getSignaturesForAddress":
            return [_sig("newest", 1000), _sig("broken", 999)]
        signature = args[0]
        calls.append(signature)
        if signature == "broken":
            raise RpcTradeError(-32000, "temporary upstream problem")
        return {"blockTime": 1000, "meta": {"err": None}, "transaction": {"message": {"accountKeys": []}}}
    tracker = RpcCurveTradeTracker(rpc, CurveActivity(), address_fn=lambda _: "curve", transaction_limit=2)
    tracker.poll([MINT], now_wall=1001, now_mono=100)
    assert "newest" in calls
    assert tracker.diagnostics()["tx_fetched"] == 1
    assert tracker.diagnostics()["tx_error_codes"]["-32000"] == 1
    assert tracker.diagnostics()["pending_signatures"] == 1

def test_pending_recent_first_and_stale_removed():
    scanned = []
    def rpc(method, args):
        if method == "getSignaturesForAddress":
            return [_sig("new", 1000), _sig("old", 600)]
        scanned.append(args[0])
        return {"blockTime": 1000, "meta": {"err": None}, "transaction": {"message": {"accountKeys": []}}}
    tracker = RpcCurveTradeTracker(rpc, CurveActivity(), address_fn=lambda _: "curve", transaction_limit=1)
    tracker.poll([MINT], now_wall=1002, now_mono=100)
    assert scanned == ["new"]
    assert tracker.diagnostics()["pending_signatures"] == 0

def test_retries_are_bounded_without_repeated_immediate_requests():
    calls = []
    def rpc(method, args):
        if method == "getSignaturesForAddress":
            return [_sig("bad", 1000)]
        calls.append(args[0])
        raise RpcTradeError(-32603, "temporary")
    tracker = RpcCurveTradeTracker(rpc, CurveActivity(), address_fn=lambda _: "curve", transaction_limit=5)
    tracker.poll([MINT], now_wall=1001, now_mono=100)
    tracker.poll([MINT], now_wall=1002, now_mono=101)
    assert calls == ["bad"]
    tracker.poll([MINT], now_wall=1012, now_mono=111)
    tracker.poll([MINT], now_wall=1033, now_mono=132)
    assert len(calls) == 3
    assert tracker.diagnostics()["tx_dropped"] == 1
    assert tracker.diagnostics()["pending_signatures"] == 0
