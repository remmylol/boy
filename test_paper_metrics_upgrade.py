import unittest
from unittest.mock import patch
import bot

class PaperMetricsTests(unittest.TestCase):
    def make_candidate(self):
        return {"address":"metrics-mint", "symbol":"MET", "name":"Metric", "price":1.0,
                "score":83, "pool_address":"pool-metrics", "pool_dex":"pumpswap",
                "m5_volume":5000, "ch5":7}

    def test_position_metrics_and_close(self):
        state={"cash_usd":36.0,"positions":{},"closed_trades":[],"seen_tokens":[],"exit_issues":{},"paper_trade_metrics":{},"day":"2026-10-16","day_start_equity":36.0,"halted":False}
        bot._first_discovered_at['metrics-mint']=1000
        with patch.object(bot.time,'time',return_value=1010):
            bot.paper_buy(state,self.make_candidate())
        self.assertEqual(state['paper_trade_metrics']['metrics-mint']['entry_delay_seconds'],10)
        self.assertEqual(len(state['positions']),1)
        with patch.object(bot.time,'time',return_value=1045):
            bot.manage_positions(state,{'metrics-mint':{'price':1.1,'liquidity':50000}})
        observations=state['paper_trade_metrics']['metrics-mint']['observed_points']
        self.assertIn('30',observations)
        self.assertGreater(state['paper_trade_metrics']['metrics-mint']['max_favorable_net_pct'],0)
        with patch.object(bot.time,'time',return_value=1060):
            self.assertTrue(bot.close_position(state,'metrics-mint',1.1,'time_limit',50000))
        self.assertEqual(len(state['closed_trades']),1)
        self.assertIn('paper_metrics',state['closed_trades'][0])
        self.assertNotIn('metrics-mint',state['paper_trade_metrics'])

    def test_executable_quote_unavailable_retains_metrics(self):
        state={"cash_usd":36.0,"positions":{},"closed_trades":[],"seen_tokens":[],"exit_issues":{},"paper_trade_metrics":{},"day":"2026-10-16","day_start_equity":36.0,"halted":False}
        with patch.object(bot.time,'time',return_value=2000):
            bot.paper_buy(state,self.make_candidate())
        with patch.object(bot.time,'time',return_value=2005):
            self.assertFalse(bot.close_position(state,'metrics-mint',1.1,'time_limit',0))
        self.assertIn('metrics-mint',state['positions'])
        self.assertIn('metrics-mint',state['paper_trade_metrics'])

    def test_fast_scan_default_and_safety(self):
        self.assertGreaterEqual(bot.ENTRY_SCAN_INTERVAL_SECONDS,15)
        self.assertGreaterEqual(bot.MIN_SOL_PAIR_LIQUIDITY_USD,5000)
        self.assertGreaterEqual(bot.SNIPER_MIN_ENTRY_LIQUIDITY_MULTIPLIER,1.0)

if __name__=='__main__':
    unittest.main()
