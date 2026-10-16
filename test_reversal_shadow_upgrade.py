import unittest
from unittest.mock import patch
import bot

class ReversalShadowTests(unittest.TestCase):
    def state(self):
        return {"cash_usd": 36.0,"positions":{},"closed_trades":[],"seen_tokens":[],"exit_issues":{},"paper_trade_metrics":{},"halted":False}
    def candidate(self):
        return {"address":"shadow-mint","symbol":"SHADOW","name":"Test","price":1.0,
                "score":80,"pool_address":"pool-shdw","pool_dex":"pumpswap","m5_volume":5000,"ch5":8}
    def test_candidate_requires_second_favorable_observation(self):
        mint = 'test-unique-short-confirm'
        bot._candidate_price_history.pop(mint, None)
        with patch.object(bot, 'ENTRY_TREND_CONFIRM_ENABLED', True), patch.object(bot,'ENTRY_TREND_MIN_OBSERVATION_SECONDS',15):
            self.assertFalse(bot.candidate_momentum_confirm(mint,1.0,now=100)[0])
            self.assertFalse(bot.candidate_momentum_confirm(mint,0.98,now=120)[0])
            self.assertTrue(bot.candidate_momentum_confirm(mint,1.01,now=140)[0])
    def test_confirmed_reversal_needs_multiple_falling_prices(self):
        with patch.object(bot,'PAPER_REVERSAL_MIN_HOLD_SECONDS',20), patch.object(bot,'PAPER_REVERSAL_MIN_DROP_PCT',4):
            self.assertTrue(bot.detect_immediate_reversal([[100,1.0],[110,.97],[120,.94]],now=120,opened_at=90)[0])
            self.assertFalse(bot.detect_immediate_reversal([[100,1.0],[110,.94],[120,.97]],now=120,opened_at=90)[0])
            self.assertFalse(bot.detect_immediate_reversal([[100,1.0],[110,.97]],now=110,opened_at=90)[0])
    def test_reversal_closes_only_with_primary_pool_quote(self):
        state=self.state()
        with patch.object(bot.time,'time',return_value=100):
            bot.paper_buy(state,self.candidate())
        for t,p in ((130,1.0),(140,.97),(150,.94)):
            with patch.object(bot.time,'time',return_value=t):
                bot.manage_positions(state,{'shadow-mint':{'price':p,'liquidity':50000,'quote_source':'dexscreener'}})
        self.assertEqual(len(state['positions']),0)
        self.assertEqual(state['closed_trades'][0]['reason'],'immediate_reversal')
        self.assertEqual(state['closed_trades'][0]['paper_metrics']['shadow_c']['status'],'open' if False else 'closed_at_actual_exit')
    def test_fallback_only_cannot_trigger_paper_sale(self):
        state=self.state()
        with patch.object(bot.time,'time',return_value=100):
            bot.paper_buy(state,self.candidate())
        with patch.object(bot.time,'time',return_value=130):
            bot.manage_positions(state,{'shadow-mint':{'price':.90,'liquidity':50000,'quote_source':'geckoterminal_indicative'}})
        self.assertIn('shadow-mint',state['positions'])
        self.assertEqual(len(state['closed_trades']),0)
        self.assertNotIn('recent_primary_prices',state['paper_trade_metrics']['shadow-mint']) if False else self.assertEqual(state['paper_trade_metrics']['shadow-mint']['recent_primary_prices'],[])
    def test_shadow_c_tracks_trigger_without_closing_actual_position(self):
        state=self.state()
        with patch.object(bot.time,'time',return_value=100):
            bot.paper_buy(state,self.candidate())
        with patch.object(bot.time,'time',return_value=130):
            bot.manage_positions(state,{'shadow-mint':{'price':1.20,'liquidity':50000,'quote_source':'dexscreener'}})
        self.assertIn('shadow-mint',state['positions'])
        self.assertEqual(state['paper_trade_metrics']['shadow-mint']['shadow_c']['exit_reason'],'take_profit')

if __name__=='__main__':
    unittest.main()
