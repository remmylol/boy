"""Offline regression tests for read-only Solana RPC tracking and event decoding."""
import base64
import struct
from curve_activity import CurveActivity
from curve_rpc_activity import (
    BASE58_ALPHABET, PUMP_PROGRAM_ID, SELF_CPI_TAG, TRADE_DISC,
    RpcCurveTradeTracker, RpcTradeError, ReadOnlySolanaRPC,
    b58_decode, b58_encode, decode_trade_event, extract_curve_trades,
)

MINT_RAW = bytes(range(1, 33))
MINT = b58_encode(MINT_RAW)


def event_bytes(buy=True, amount=2_000_000_000):
    return (TRADE_DISC + MINT_RAW + struct.pack('<QQ', amount, 123_000_000) +
            bytes([1 if buy else 0]) + bytes(range(33, 65)) + struct.pack('<q', 1700000000))


def as_tx(encoded, *, failed=False, block_time=1700000290):
    return {'blockTime': block_time, 'transaction': {'message': {'accountKeys': ['11111111111111111111111111111111', PUMP_PROGRAM_ID]}},
            'meta': {'err': {'InstructionError': [0, 'Custom']} if failed else None,
                     'innerInstructions': [{'instructions': [{'programIdIndex': 1, 'data': encoded}]}],
                     'logMessages': []}}


def test_base58_roundtrip_including_zeros():
    for raw in (MINT_RAW, bytes([0, 0, 7]), bytes(32), b'\x01\x02\x03'):
        assert b58_decode(b58_encode(raw)) == raw


def test_anchor_self_cpi_buy_and_sell():
    for buy in (True, False):
        raw = SELF_CPI_TAG + event_bytes(buy)
        trade = decode_trade_event(raw, expected_mint=MINT)
        assert trade['txType'] == ('buy' if buy else 'sell')
        assert trade['solAmount'] == 2.0
        assert extract_curve_trades(as_tx(b58_encode(raw)), MINT)[0]['txType'] == trade['txType']


def test_nontrade_wrong_mint_and_malformed_are_ignored():
    assert decode_trade_event(SELF_CPI_TAG + bytes(8) + event_bytes(), expected_mint=MINT) is None
    assert decode_trade_event(event_bytes(), expected_mint=b58_encode(bytes(range(2, 34)))) is None
    assert decode_trade_event(TRADE_DISC + b'\x00' * 16, expected_mint=MINT) is None
    assert extract_curve_trades(as_tx(b58_encode(SELF_CPI_TAG + event_bytes()), failed=True), MINT) == []
    assert extract_curve_trades({'meta': {'err': None}, 'transaction': {'message': {'accountKeys': []}}}, MINT) == []


def test_legacy_log_parser_verifies_pump_program_context():
    raw = event_bytes()
    tx = as_tx('1')
    tx['meta']['innerInstructions'] = []
    tx['meta']['logMessages'] = [
        f'Program {PUMP_PROGRAM_ID} invoke [1]',
        'Program data: ' + base64.b64encode(raw).decode(),
        f'Program {PUMP_PROGRAM_ID} success',
    ]
    assert len(extract_curve_trades(tx, MINT)) == 1
    tx['meta']['logMessages'] = ['Program data: ' + base64.b64encode(raw).decode()]
    assert extract_curve_trades(tx, MINT) == []


def test_rpc_poll_records_real_trade_time_only_once():
    events = {'s1': as_tx(b58_encode(SELF_CPI_TAG + event_bytes()), block_time=1700000290),
              's2': as_tx(b58_encode(SELF_CPI_TAG + event_bytes(False)), block_time=1700000295)}
    calls = []
    def rpc(method, params):
        calls.append(method)
        if method == 'getSignaturesForAddress':
            return [{'signature': 's2', 'err': None, 'blockTime': 1700000295},
                    {'signature': 's1', 'err': None, 'blockTime': 1700000290}]
        return events[params[0]]
    activity = CurveActivity()
    tracker = RpcCurveTradeTracker(rpc, activity, address_fn=lambda _mint: 'fake-curve',
                                   transaction_limit=2)
    tracker.poll([MINT], now_wall=1700000300, now_mono=1000)
    assert tracker.diagnostics()['valid_trades'] == 2
    assert activity.summary(MINT, now=1000) == {'trades': 2, 'buys': 1, 'sells': 1, 'volume_sol': 4.0}
    tracker.poll([MINT], now_wall=1700000320, now_mono=1020)
    assert tracker.diagnostics()['valid_trades'] == 2
    assert calls.count('getTransaction') == 2
    assert activity.summary(MINT, now=1400)['trades'] == 0


def test_pending_budget_does_not_lose_transactions():
    rows = [{'signature': 's3', 'err': None, 'blockTime': 1700000298},
            {'signature': 's2', 'err': None, 'blockTime': 1700000297},
            {'signature': 's1', 'err': None, 'blockTime': 1700000296}]
    def rpc(method, params):
        return rows if method == 'getSignaturesForAddress' else as_tx(
            b58_encode(SELF_CPI_TAG + event_bytes()), block_time=1700000296)
    activity = CurveActivity()
    tracker = RpcCurveTradeTracker(rpc, activity, address_fn=lambda _: 'curve',
                                   transaction_limit=1)
    tracker.poll([MINT], now_wall=1700000300, now_mono=1000)
    assert tracker.diagnostics()['pending_signatures'] == 2
    tracker.poll([MINT], now_wall=1700000301, now_mono=1001)
    tracker.poll([MINT], now_wall=1700000302, now_mono=1002)
    assert tracker.diagnostics()['valid_trades'] == 3
    assert tracker.diagnostics()['pending_signatures'] == 0


def test_rpc_rate_limit_cooldown_and_fails_closed():
    def rpc(method, params):
        raise RpcTradeError(429, 'RPC rate limited')
    tracker = RpcCurveTradeTracker(rpc, CurveActivity(), address_fn=lambda _: 'curve')
    tracker.poll([MINT])
    diag = tracker.diagnostics()
    assert diag['rate_limits'] == 1 and diag['valid_trades'] == 0
    assert diag['last_error'] == 'getSignaturesForAddress:RpcTradeError'
    tracker.poll([MINT])
    assert tracker.diagnostics()['rate_limits'] == 1


def test_read_only_rpc_blocks_write_methods():
    rpc = ReadOnlySolanaRPC('https://example.invalid/?api-key=secret')
    try:
        rpc('sendTransaction', ['fake'])
    except ValueError:
        pass
    else:
        assert False, 'write method was accepted'
