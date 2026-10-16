import unittest
from unittest.mock import patch
import sys
import types
import bot

class FollowupTests(unittest.TestCase):
    def state(self):
        return {"cash_usd":36.,"positions":{},"seen_tokens":[],"paper_trade_metrics":{}}

    def test_default_primary_score_not_relaxed(self):
        s=self.state()
        with patch.object(bot,'MIN_SCORE',68), patch.object(bot,'PAPER_MODE',True), patch.object(bot,'PAPER_EXPLORATION_ENABLED',True), patch.object(bot,'PAPER_EXPLORATION_MIN_SCORE',60):
            self.assertEqual(bot.paper_entry_profile(s,70)[0],'standard')
            self.assertEqual(bot.paper_entry_profile(s,62)[0],'exploration')
            self.assertEqual(bot.paper_entry_profile(s,59)[1],'low_score')

    def test_exploration_never_runs_in_live_mode(self):
        with patch.object(bot,'PAPER_MODE',False), patch.object(bot,'PAPER_EXPLORATION_ENABLED',True):
            self.assertEqual(bot.paper_entry_profile(self.state(),62)[0],None)

    def test_limits_on_exploration(self):
        s=self.state()
        with patch.object(bot,'PAPER_MODE',True), patch.object(bot,'PAPER_EXPLORATION_ENABLED',True), patch.object(bot,'PAPER_EXPLORATION_DAILY_LIMIT',2):
            self.assertEqual(bot.paper_entry_profile(s,62)[0],'exploration')
            s['paper_exploration_fills_today']=2
            self.assertEqual(bot.paper_entry_profile(s,62)[1],'paper_exploration_daily_limit')
            s['paper_exploration_fills_today']=1
            s['positions']['mint']={}
            s['paper_trade_metrics']['mint']={'entry_profile':'exploration'}
            self.assertEqual(bot.paper_entry_profile(s,62)[1],'paper_exploration_position_limit')

    def test_websocket_502_does_not_echo_html_or_secret(self):
        class StopWorker(Exception):
            pass
        class BadHandshake(Exception):
            status_code = 502
        fake_socket = types.SimpleNamespace(create_connection=lambda *a, **kw: (_ for _ in ()).throw(
            BadHandshake("Handshake status 502 Bad Gateway -+-+- <html>secret response</html>")))
        with patch.dict(sys.modules, {"websocket": fake_socket}), \
             patch.object(bot, "PUMPPORTAL_API_KEY", "supersecretkey"), \
             patch.object(bot.time, "sleep", side_effect=StopWorker), \
             self.assertLogs(bot.log, level="WARNING") as captured:
            with self.assertRaises(StopWorker):
                bot._fresh_launch_worker()
        output=" ".join(captured.output)
        self.assertIn("HTTP502", output)
        self.assertIn("retry_in=60s", output)
        self.assertNotIn("<html>", output)
        self.assertNotIn("supersecretkey", output)

    def test_small_paper_buy_tagged_and_reversal_logic_kept(self):
        s=self.state()
        c={'address':'exp','symbol':'EXP','name':'Test','price':1.,'score':62.,'pool_address':'pool-exp','pool_dex':'pumpswap','m5_volume':5000}
        bot.paper_buy(s,c,size_usd=5,entry_profile='exploration')
        self.assertEqual(s['cash_usd'],31.)
        self.assertEqual(s['positions']['exp']['amount_usd'],5.)
        self.assertEqual(s['paper_trade_metrics']['exp']['entry_profile'],'exploration')

if __name__=='__main__': unittest.main()
