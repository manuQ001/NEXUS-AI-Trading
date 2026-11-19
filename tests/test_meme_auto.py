"""MEME AUTO trades in the original €45 virtual wallet; never real orders."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect,wallet_status
from meme_auto import tick,status,choose_candidate,decide_exit,init_auto
from meme_portfolio import trade,portfolio
M='So11111111111111111111111111111111111111112'
A='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
B='11111111111111111111111111111111'
Q={'price_usd':0.01,'liquidity_usd':1200,'volume_24h_usd':1200,'symbol':'MEME'}
FX={'usd_eur':0.90,'rate_date':'2026-11-19'}
def report():return {'ok':True,'candidates':[dict(Q,address=M)]}
def fx(c,now=None):return FX
class TestMemeAuto(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.temp.name)/'test.sqlite3')
    def tearDown(self):
        self.c.close();self.temp.cleanup()
    def test_buy_sell_and_wallet_separation(self):
        count=[]
        def quote(mint):
            count.append(mint)
            return dict(Q,price_usd=.01 if len(count)==1 else .014)
        first=tick(self.c,now=2000,scout=report,quote=quote,fx_rate=fx)
        self.assertEqual(len(portfolio(self.c)['positions']),1)
        self.assertEqual(portfolio(self.c)['cash_eur'],42)
        second=tick(self.c,now=2030,scout=report,quote=quote,fx_rate=fx)
        self.assertEqual(len(portfolio(self.c)['positions']),0)
        self.assertTrue(any(x['action']=='AUTO_SELL' for x in second['journal']))
        self.assertEqual(self.c.execute("SELECT cash FROM wallets WHERE strategy='core'").fetchone()[0],105)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
        self.assertNotEqual(self.c.execute("SELECT cash FROM wallets WHERE strategy='meme'").fetchone()[0],45)
    def test_stop_target_timeout(self):
        trade(self.c,M,'BUY',Q,FX,now=50)
        p=dict(self.c.execute('SELECT * FROM meme_eur_positions').fetchone())
        self.assertEqual(decide_exit(p,.008,80,FX['usd_eur']),'STOP_LOSS')
        self.assertEqual(decide_exit(p,.015,80,FX['usd_eur']),'TAKE_PROFIT')
        self.assertEqual(decide_exit(p,.01,50+7200,FX['usd_eur']),'TIMEOUT_2H')
    def test_disabled_does_not_call_sources(self):
        init_auto(self.c)
        self.c.execute('UPDATE meme_auto_state SET enabled=0 WHERE id=1')
        self.c.commit()
        tick(self.c,now=2000,scout=lambda:1/0,quote=lambda a:1/0,
             fx_rate=lambda c,now=None:1/0)
        self.assertEqual(portfolio(self.c)['positions'],[])
    def test_discovery_cadence(self):
        calls=[]
        def scout():
            calls.append(1)
            return report()
        tick(self.c,now=2000,scout=scout,quote=lambda _:Q,fx_rate=fx)
        tick(self.c,now=2010,scout=scout,quote=lambda _:Q,fx_rate=fx)
        self.assertEqual(len(calls),1)
        self.assertEqual(len(portfolio(self.c)['positions']),1)
    def test_price_or_fx_unavailable_blocks_auto_entries(self):
        tick(self.c,now=2000,scout=report,
             quote=lambda mint:dict(Q,price_usd=None),fx_rate=fx)
        self.assertEqual(portfolio(self.c)['positions'],[])
        self.c.execute('UPDATE meme_auto_state SET last_scan=0 WHERE id=1');self.c.commit()
        tick(self.c,now=2500,scout=report,quote=lambda _:Q,
             fx_rate=lambda c,now=None: (_ for _ in ()).throw(ValueError('no FX')))
        self.assertEqual(portfolio(self.c)['positions'],[])
    def test_weak_candidate_not_bought(self):
        tick(self.c,now=2000,scout=lambda:{'candidates':[dict(Q,address=M,liquidity_usd=2)]},
             quote=lambda _:Q,fx_rate=fx)
        self.assertEqual(portfolio(self.c)['positions'],[])
    def test_multiple_distinct_orders_same_scan(self):
        rows=[dict(Q,address=x) for x in (M,A,B)]
        tick(self.c,now=2000,scout=lambda:{'candidates':rows},quote=lambda _:Q,fx_rate=fx)
        positions=portfolio(self.c)['positions']
        self.assertEqual(len(positions),3)
        self.assertEqual(portfolio(self.c)['cash_eur'],36)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],3)
        values={x['address'] for x in positions}
        self.assertEqual(len(values),3)
        self.assertEqual(wallet_status(self.c,{})[1]['strategy'],'meme')
if __name__=='__main__':unittest.main()
