import json
import bot


def test_control_frame_counted(monkeypatch):
    before = bot.curve_activity_diagnostics()
    assert bot._handle_curve_trade_frame(json.dumps({'message': 'Subscribed'}), set()) == 'control'
    after = bot.curve_activity_diagnostics()
    assert after['raw_frames'] == before['raw_frames'] + 1
    assert after['control_frames'] == before['control_frames'] + 1


def test_unwatched_trade_counted_without_recording():
    before = bot.curve_activity_diagnostics()
    event = {'mint': 'A'*32, 'txType': 'buy', 'solAmount': 0.2}
    assert bot._handle_curve_trade_frame(json.dumps(event), set()) == 'unwatched_mint'
    after = bot.curve_activity_diagnostics()
    assert after['unwatched_mint_frames'] == before['unwatched_mint_frames'] + 1
    assert after['valid_trades'] == before['valid_trades']


def test_watched_trade_is_recorded():
    mint = 'B'*32
    before = bot.curve_activity_diagnostics()
    event = {'mint': mint, 'txType': 'buy', 'solAmount': 0.2}
    assert bot._handle_curve_trade_frame(json.dumps(event), {mint}) == 'valid_trade'
    assert bot.curve_activity_diagnostics()['valid_trades'] == before['valid_trades'] + 1
    assert bot._curve_activity.summary(mint)['trades'] >= 1


def test_malformed_trade_and_json_counted():
    mint = 'C'*32
    before = bot.curve_activity_diagnostics()
    assert bot._handle_curve_trade_frame('bad json', {mint}) == 'invalid_json'
    assert bot._handle_curve_trade_frame(json.dumps({'mint': mint, 'txType': 'buy'}), {mint}) == 'invalid_trade'
    after = bot.curve_activity_diagnostics()
    assert after['parse_errors'] == before['parse_errors'] + 1
    assert after['invalid_trade_frames'] == before['invalid_trade_frames'] + 1
