"""Tests: strategy analytics never submits orders and the risk halt remains intact."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from meme_portfolio import trade,portfolio
from meme_auto import tick,init_auto
from meme_intelligence import observe_blocked,report,initialize

A='So11111111111111111111111111111111111111112'
B='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
Q={'symbol':'MEME','price_usd':.01,'liquidity_usd':22000,
   'volume_24h_usd':35000,'address':A,'pool_age_hours':1.0}
FX={'usd_eur':.9,'rate_date':'2026-11-20'}
def fx(c,now=None):return FX

class TestStrategyIntelligence(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/'test.sqlite3'
        self.c=connect(self.db)
        init_auto(self.c)
    def tearDown(self):
        self.c.close()
        self.temp.cleanup()
    def test_closed_trade_attribution_has_fee_drag_and_real_pnl(self):
        trade(self.c,A,'BUY',Q,FX,now=100,stake_eur=3)
        trade(self.c,A,'SELL',dict(Q,price_usd=.011),FX,now=125)
        self.c.execute("""INSERT INTO meme_auto_journal(timestamp,address,action,note)
            VALUES(?,?,?,?)""",(125,A,'AUTO_SELL','TRAILING_STOP · paper'))
        d=report(self.c,now=126)
        self.assertEqual(d['history']['matched_closed'],1)
        self.assertEqual(d['history']['by_exit_reason'],
                         [{'reason':'TRAILING_STOP','count':1}])
        self.assertGreater(d['history']['estimated_fee_drag_eur'],0)
        self.assertAlmostEqual(d['history']['realized_pnl_eur'],
            d['history']['recent'][0]['pnl_eur'],places=6)
    def test_blocked_scanner_keeps_watching_without_buy(self):
        self.c.execute("UPDATE wallets SET cash=37.67 WHERE strategy='meme'")
        self.c.commit()
        scans=0
        def scout():
            nonlocal scans
            scans+=1
            return {'candidates':[dict(Q)]}
        with patch('meme_auto.review_meme_agents',side_effect=AssertionError('paid AI called')):
            first=tick(self.c,now=1000,scout=scout,quote=lambda _:Q,fx_rate=fx)
            second=tick(self.c,now=1061,scout=lambda:{'candidates':[dict(Q,price_usd=.012)]},
                        quote=lambda _:Q,fx_rate=fx)
        self.assertTrue(first['risk_circuit']['blocked'])
        self.assertTrue(second['risk_circuit']['blocked'])
        self.assertEqual(scans,1)
        self.assertEqual(portfolio(self.c)['positions'],[])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],0)
        d=report(self.c,now=1062)
        self.assertEqual(len(d['watchlist']),1)
        self.assertEqual(d['watchlist'][0]['observations'],2)
        self.assertAlmostEqual(d['watchlist'][0]['observed_change_pct'],20,places=2)
        self.assertEqual(d['history']['matched_closed'],0)
        self.assertIsNone(d['history']['win_rate_pct'])
    def test_observation_filter_invalid_mint_and_no_simulated_fills(self):
        n=observe_blocked(self.c,[dict(Q,address='bad'),dict(Q,address=A),
              dict(Q,address=A),dict(Q,address=B,price_usd=None)],now=100)
        self.assertEqual(n,1)
        d=report(self.c,now=101)
        self.assertIsNone(d['watchlist'][0]['observed_change_pct'])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],0)
        self.assertEqual(portfolio(self.c)['cash_eur'],45)
    def test_unmatched_legacy_buy_is_not_reported_as_profit(self):
        trade(self.c,A,'BUY',Q,FX,now=100)
        d=report(self.c,now=101)
        self.assertEqual(d['history']['matched_closed'],0)
        self.assertEqual(d['history']['unmatched_buys'],1)
        self.assertEqual(d['history']['realized_pnl_eur'],0)

if __name__=='__main__':unittest.main()
