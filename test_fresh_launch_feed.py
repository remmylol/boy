import bot


def test_fresh_launch_validation_and_deduplication():
    with bot._fresh_lock:
        bot._fresh_launches.clear()
    mint = '7BGgw7k7WteUgdvgM3yZ7HQ3yRvzajFSG4H8ZhaYpump'
    assert bot.record_fresh_launch(mint)
    assert bot.record_fresh_launch(mint)
    assert not bot.record_fresh_launch('not-a-mint')
    assert not bot.record_fresh_launch(bot.SOL_MINT)
    assert bot.fresh_launch_snapshot() == [mint]
    with bot._fresh_lock:
        bot._fresh_launches.clear()


def test_old_launches_expire():
    with bot._fresh_lock:
        bot._fresh_launches.clear()
    mint = '7BGgw7k7WteUgdvgM3yZ7HQ3yRvzajFSG4H8ZhaYpump'
    assert bot.record_fresh_launch(mint, seen_at=-1000000)
    assert bot.fresh_launch_snapshot() == []
