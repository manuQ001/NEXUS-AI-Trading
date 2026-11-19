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
        with self.assertRaises(ValueError):quick_trade(self.c,M,'SELL',dict(Q,liquidity_usd=1))
        self.assertEqual(len(demo_state(self.c)['positions']),MAX_POSITIONS)
    def test_invalid_and_broken_quote_fail_closed(self):
        for action,mint,quote in [('BUY','bad',Q),('SELL',M,Q),('BUY',M,dict(Q,price_usd=float('nan'))),
                                  ('BUY',M,dict(Q,volume_24h_usd=100)),('BUY',M,dict(Q,liquidity_usd=10)),
                                  ('RESET',M,Q)]:
            with self.assertRaises(ValueError):quick_trade(self.c,mint,action,quote)
        self.assertEqual(demo_state(self.c)['cash_credits'],45)
        self.assertEqual(demo_state(self.c)['positions'],[])
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
