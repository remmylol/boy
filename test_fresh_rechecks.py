import bot

MINT_A = '7BGgw7k7WteUgdvgM3yZ7HQ3yRvzajFSG4H8ZhaYpump'
MINT_B = '8BGgw7k7WteUgdvgM3yZ7HQ3yRvzajFSG4H8ZhaYpump'


def setup_function():
    with bot._fresh_lock:
        bot._fresh_launches.clear()
        bot._fresh_checks.clear()


def test_due_launches_are_rechecked_after_delay():
    bot.record_fresh_launch(MINT_A, seen_at=1000)
    assert bot.due_fresh_launches(now=1000) == [MINT_A]
    bot.mark_fresh_checked(MINT_A, 'pair_not_indexed', now=1000)
    assert bot.due_fresh_launches(now=1059) == []
    assert bot.due_fresh_launches(now=1060) == [MINT_A]
    bot.mark_fresh_checked(MINT_A, 'liquidity_below_minimum', now=1060)
    assert bot.due_fresh_launches(now=1179) == []
    assert bot.due_fresh_launches(now=1180) == [MINT_A]


def test_due_selection_prioritizes_oldest_due_not_latest():
    bot.record_fresh_launch(MINT_A, seen_at=1000)
    bot.record_fresh_launch(MINT_B, seen_at=1001)
    assert bot.due_fresh_launches(now=1002, limit=1) == [MINT_A]
    bot.mark_fresh_checked(MINT_A, 'pair_not_indexed', now=1002)
    assert bot.due_fresh_launches(now=1002, limit=1) == [MINT_B]


def test_missing_market_data_distinct_from_low_liquidity():
    bot.record_fresh_launch(MINT_A, seen_at=1000)
    bot.mark_fresh_checked(MINT_A, 'pair_not_indexed', now=1000)
    assert bot.fresh_check_counts()['pair_not_indexed'] == 1

def teardown_function():
    with bot._fresh_lock:
        bot._fresh_launches.clear()
        bot._fresh_checks.clear()
