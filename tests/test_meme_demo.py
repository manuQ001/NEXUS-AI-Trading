import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from meme_demo import demo_state,quick_trade,indicative_quote,STAKE_USD,MAX_POSITIONS
from meme_scout import PAIRS_ROOT

M='So11111111111111111111111111111111111111112'
A='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
B='11111111111111111111111111111111'
Q={'price_usd':0.01,'liquidity_usd':9000,'volume_24h_usd':30000,'symbol':'TEST'}
class TestMemeDemo(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.temp.name)/'test.sqlite3')
    def tearDown(self):
        self.c.close();self.temp.cleanup()
    def test_manual_buy_sell_stay_in_demo_account(self):
        core_cash=self.c.execute("SELECT cash FROM wallets WHERE strategy='core'").fetchone()[0]
        meme_cash=self.c.execute("SELECT cash FROM wallets WHERE strategy='meme'").fetchone()[0]
        self.assertEqual(demo_state(self.c)['cash_credits'],45)
        buy=quick_trade(self.c,M,'BUY',Q,now=10)
        self.assertEqual(buy['cost_usd'],STAKE_USD)
        self.assertAlmostEqual(demo_state(self.c)['cash_credits'],42)
        self.assertEqual(len(demo_state(self.c)['positions']),1)
        sell=quick_trade(self.c,M,'SELL',Q,now=20)
        self.assertLess(sell['pnl_usd'],0)  # flat price pays costs
        self.assertEqual(demo_state(self.c)['positions'],[])
        self.assertAlmostEqual(demo_state(self.c)['cash_credits'],45+sell['pnl_usd'],places=5)
        self.assertEqual(core_cash,self.c.execute("SELECT cash FROM wallets WHERE strategy='core'").fetchone()[0])
        self.assertEqual(meme_cash,self.c.execute("SELECT cash FROM wallets WHERE strategy='meme'").fetchone()[0])
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM trades").fetchone()[0],0)
    def test_duplicate_max_positions_and_no_false_fills(self):
        for address in (M,A,B):quick_trade(self.c,address,'BUY',Q)
        self.assertEqual(len(demo_state(self.c)['positions']),MAX_POSITIONS)
        with self.assertRaises(ValueError):quick_trade(self.c,M,'BUY',Q)
        close=quick_trade(self.c,M,'SELL',dict(Q,liquidity_usd=1))
        self.assertTrue(close['ok'])
        self.assertTrue(close['warnings'])
        self.assertEqual(len(demo_state(self.c)['positions']),MAX_POSITIONS-1)
    def test_invalid_price_and_action_still_fail_closed(self):
        for action,mint,quote in [('BUY','bad',Q),('SELL',M,Q),('BUY',M,dict(Q,price_usd=float('nan'))),
                                  ('BUY',M,dict(Q,price_usd=None)),('BUY',M,dict(Q,price_usd=0)),
                                  ('RESET',M,Q)]:
            with self.assertRaises(ValueError):quick_trade(self.c,mint,action,quote)
        self.assertEqual(demo_state(self.c)['cash_credits'],45)
        self.assertEqual(demo_state(self.c)['positions'],[])
    def test_low_liquidity_and_volume_become_warnings_not_veto(self):
        buy=quick_trade(self.c,M,'BUY',dict(Q,volume_24h_usd=0,liquidity_usd=10))
        self.assertTrue(buy['ok'])
        self.assertEqual(len(buy['warnings']),2)
        sell=quick_trade(self.c,M,'SELL',dict(Q,volume_24h_usd=None,liquidity_usd=None))
        self.assertTrue(sell['ok'])
        self.assertEqual(len(sell['warnings']),2)
        self.assertEqual(len(demo_state(self.c)['positions']),0)
    def test_missing_market_metrics_accepted_only_with_price(self):
        result=quick_trade(self.c,A,'BUY',{'price_usd':0.001,'symbol':'TEST'})
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['warnings']),2)
    def test_quote_accepts_price_when_volume_or_liquidity_missing(self):
        result=indicative_quote(M,fetch=lambda url:[{
            'chainId':'solana','baseToken':{'address':M,'symbol':'TEST'},
            'priceUsd':'0.00000012','volume':{},'liquidity':{}}])
        self.assertEqual(result['price_usd'],0.00000012)
        self.assertIsNone(result['volume_24h_usd'])
        self.assertIsNone(result['liquidity_usd'])
    def test_quote_is_server_fetched_not_browser_submitted(self):
        seen=[]
        pairs=[{'chainId':'solana','baseToken':{'address':M,'symbol':'MEME'},
                'priceUsd':'0.02','liquidity':{'usd':2000},'volume':{'h24':4000}},
               {'chainId':'ethereum','baseToken':{'address':M},'priceUsd':'999',
                'liquidity':{'usd':999999},'volume':{'h24':999999}}]
        def fake(url):seen.append(url);return pairs
        quote=indicative_quote(M,fetch=fake)
        self.assertEqual(seen,[PAIRS_ROOT+M])
        self.assertEqual(quote['price_usd'],0.02)
        with self.assertRaises(ValueError):indicative_quote('../bad',fetch=fake)
if __name__=='__main__':unittest.main()
