import unittest
from unittest.mock import patch
import bot

class PendingEntryTests(unittest.TestCase):
    def setUp(self):
        bot._pending_entry_mints.clear()
        bot._candidate_price_history.clear()

    def test_pending_followup(self):
        with patch.object(bot, 'ENTRY_TREND_MIN_OBSERVATION_SECONDS', 10):
            ok, why = bot.candidate_momentum_confirm('pending-test', 1., now=1000)
            self.assertFalse(ok)
            bot.watch_pending_entry('pending-test', why, now=1000)
            self.assertIn('pending-test', bot.pending_entry_due(now=1005))
            ok, why = bot.candidate_momentum_confirm('pending-test', 1.01, now=1011)
            self.assertTrue(ok, why)
            bot.watch_pending_entry('pending-test', why, now=1011)
            self.assertNotIn('pending-test', bot._pending_entry_mints)

    def test_expiration(self):
        bot._pending_entry_mints['old'] = 1000
        self.assertEqual(bot.pending_entry_due(now=1200), [])

if __name__ == '__main__': unittest.main()
