import bot
import pytest

@pytest.fixture(autouse=True)
def restore_launch_state():
    with bot._fresh_lock:
        launches = bot._fresh_launches.copy()
        checks = bot._fresh_checks.copy()
    with bot._curve_sub_lock:
        watched = bot._curve_subscriptions.copy()
    yield
    with bot._fresh_lock:
        bot._fresh_launches.clear()
        bot._fresh_launches.update(launches)
        bot._fresh_checks.clear()
        bot._fresh_checks.update(checks)
    with bot._curve_sub_lock:
        bot._curve_subscriptions.clear()
        bot._curve_subscriptions.update(watched)

MINTS = ['A' * 31 + str(i) for i in range(1, 5)]

def test_new_launch_immediately_watched(monkeypatch):
    monkeypatch.setattr(bot, 'CURVE_ACTIVITY_ENABLED', True)
    with bot._curve_sub_lock:
        bot._curve_subscriptions.clear()
    mint = MINTS[0]
    with bot._fresh_lock:
        bot._fresh_launches.pop(mint, None)
        bot._fresh_checks.pop(mint, None)
    assert bot.record_fresh_launch(mint)
    with bot._curve_sub_lock:
        assert mint in bot._curve_subscriptions

def test_scan_does_not_drop_existing_watches(monkeypatch):
    monkeypatch.setattr(bot, 'CURVE_ACTIVITY_ENABLED', True)
    with bot._curve_sub_lock:
        bot._curve_subscriptions.clear()
    bot.update_curve_subscriptions(MINTS[:2])
    bot.update_curve_subscriptions([MINTS[2]])
    with bot._curve_sub_lock:
        assert set(MINTS[:3]).issubset(bot._curve_subscriptions)

def test_watchlist_bounded(monkeypatch):
    monkeypatch.setattr(bot, 'CURVE_ACTIVITY_ENABLED', True)
    monkeypatch.setattr(bot, 'CURVE_ACTIVITY_MAX_SUBSCRIPTIONS', 2)
    with bot._curve_sub_lock:
        bot._curve_subscriptions.clear()
    bot.update_curve_subscriptions(MINTS[:3])
    with bot._curve_sub_lock:
        assert list(bot._curve_subscriptions) == MINTS[1:3]
