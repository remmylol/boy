"""New discovery tokens must rotate past structurally unusable markets."""
import bot


def test_cooldown_blocks_new_entry_lookups(monkeypatch):
    monkeypatch.setattr(bot, 'SNIPER_MODE', False)
    monkeypatch.setattr(bot, '_entry_reject_until', bot.OrderedDict())
    monkeypatch.setattr(bot, '_entry_reject_reason', {})
    monkeypatch.setattr(bot, '_verified_dex_mints', bot.OrderedDict())
    monkeypatch.setattr(bot, '_discovery_priority', {})
    monkeypatch.setattr(bot.time, 'monotonic', lambda: 100)
    bot.note_entry_rejection('untradeable', 'no_sol_quoted_pair')
    selected, _, _ = bot.select_entry_mints(['untradeable', 'good'], [], count=2, cursor=0)
    assert selected == ['good']
    assert bot.mint_cooling_down('untradeable', now=100)


def test_cooldown_expires(monkeypatch):
    monkeypatch.setattr(bot, '_entry_reject_until', bot.OrderedDict())
    monkeypatch.setattr(bot, '_entry_reject_reason', {})
    monkeypatch.setattr(bot, 'STRUCTURAL_REJECT_COOLDOWN_SECONDS', 300)
    bot.note_entry_rejection('old', 'unsupported_sol_route', now=100)
    assert bot.mint_cooling_down('old', now=399)
    assert not bot.mint_cooling_down('old', now=400)


def test_verified_market_clears_rejection(monkeypatch):
    monkeypatch.setattr(bot, '_entry_reject_until', bot.OrderedDict())
    monkeypatch.setattr(bot, '_entry_reject_reason', {})
    monkeypatch.setattr(bot, '_verified_dex_mints', bot.OrderedDict())
    bot.note_entry_rejection('recovered', 'supported_pair_missing_price', now=100)
    bot.note_verified_dex_mint('recovered', now=101)
    assert not bot.mint_cooling_down('recovered', now=102)
