"""Autonomous MEME PAPER rules: no blockchain, key, or core wallet access."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from meme_auto import tick,status,choose_candidate,decide_exit,init_auto
from meme_demo import demo_state,quick_trade

M='So11111111111111111111111111111111111111112'
Q={'price_usd':0.01,'liquidity_usd':1200,'volume_24h_usd':1200,'symbol':'DEMO'}
def report():return {'ok':True,'candidates':[dict(Q,address=M)]}

class TestMemeAuto(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.t.name)/'test.sqlite3')
    def tearDown(self):
        self.c.close();self.t.cleanup()
    def test_auto_buys_and_sells_on_take_profit(self):
        calls=[]
        def quote(mint):
            calls.append(mint)
            return dict(Q,price_usd=.01 if len(calls)==1 else .014)
        first=tick(self.c,now=2000,scout=report,quote=quote)
        self.assertTrue(first['enabled'])
        self.assertEqual(len(demo_state(self.c)['positions']),1)
        self.assertEqual(demo_state(self.c)['cash_credits'],42)
        second=tick(self.c,now=2030,scout=report,quote=quote)
        self.assertEqual(len(demo_state(self.c)['positions']),0)
        self.assertTrue(any(x['action']=='AUTO_SELL' for x in second['journal']))
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
        self.assertEqual(self.c.execute("SELECT cash FROM wallets WHERE strategy='meme'").fetchone()[0],45)
        self.assertEqual(self.c.execute("SELECT cash FROM wallets WHERE strategy='core'").fetchone()[0],105)
    def test_stop_loss_and_timeout(self):
        quick_trade(self.c,M,'BUY',Q,now=50)
        pos=dict(self.c.execute('SELECT * FROM meme_demo_positions').fetchone())
        self.assertEqual(decide_exit(pos,.008,80),'STOP_LOSS')
        self.assertEqual(decide_exit(pos,.01,50+2*3600),'TIMEOUT_2H')
        self.assertIsNone(decide_exit(pos,.01,80))
    def test_disabled_does_not_use_any_market_data(self):
        init_auto(self.c)
        self.c.execute('UPDATE meme_auto_state SET enabled=0 WHERE id=1')
        self.c.commit()
        tick(self.c,now=2000,scout=lambda:1/0,quote=lambda a:1/0)
        self.assertEqual(demo_state(self.c)['positions'],[])
    def test_no_repeat_and_bounded_scan_interval(self):
        calls=[]
        def scout():
            calls.append(1)
            return report()
        tick(self.c,now=2000,scout=scout,quote=lambda addr:Q)
        tick(self.c,now=2010,scout=scout,quote=lambda addr:Q)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(demo_state(self.c)['positions']),1)
    def test_missing_market_quote_never_creates_buy(self):
        tick(self.c,now=2000,scout=report,quote=lambda mint:dict(Q,price_usd=None))
        self.assertEqual(demo_state(self.c)['positions'],[])
        self.assertFalse(any(x['action']=='AUTO_BUY' for x in status(self.c)['journal']))
    def test_weak_candidate_does_not_trigger(self):
        tick(self.c,now=2000,scout=lambda:{'candidates':[dict(Q,address=M,liquidity_usd=2)]},
             quote=lambda _:Q)
        self.assertEqual(len(demo_state(self.c)['positions']),0)

if __name__=='__main__':unittest.main()
