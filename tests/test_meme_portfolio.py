"""EUR MEME wallet integration, FX validation and preservation of the USD archive."""
import sys
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect,wallet_status
from meme_demo import quick_trade as legacy_buy
from meme_portfolio import trade,portfolio,get_fx,mark,MAX_POSITIONS,FX_URL
M='So11111111111111111111111111111111111111112'
A='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
B='11111111111111111111111111111111'
Q={'price_usd':0.01,'liquidity_usd':3000,'volume_24h_usd':10000,'symbol':'MEME'}
FX={'usd_eur':0.9,'rate_date':'2026-11-19'}

class TestMemePortfolioEUR(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.t.name)/'test.sqlite3')
    def tearDown(self):self.c.close();self.t.cleanup()
    def test_single_wallet_buy_mark_and_sell(self):
        trade(self.c,M,'BUY',Q,FX,now=10)
        p=portfolio(self.c,now=11)
        self.assertEqual(p['cash_eur'],42)
        self.assertEqual(p['starting_eur'],45)
        self.assertEqual(len(p['positions']),1)
        self.assertLess(p['equity_eur'],45) # modeled fees
        wallets={w['strategy']:w for w in wallet_status(self.c,{})}
        self.assertAlmostEqual(wallets['meme']['equity'],p['equity_eur'],places=3)
        self.assertEqual(wallets['core']['equity'],105)
        mark(self.c,M,dict(Q,price_usd=.015),FX,now=20)
        marked=portfolio(self.c,now=21)['positions'][0]
        self.assertEqual(marked['last_price_usd'],.015)
        self.assertGreater(marked['estimated_pnl_eur'],0)
        sell=trade(self.c,M,'SELL',dict(Q,price_usd=.015),FX,now=30)
        self.assertTrue(sell['ok'])
        self.assertEqual(portfolio(self.c)['positions'],[])
        self.assertAlmostEqual(portfolio(self.c)['cash_eur'],45+sell['pnl_eur'],places=6)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
    def test_legacy_demo_is_preserved_but_not_counted(self):
        legacy_buy(self.c,A,'BUY',Q,now=3)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_demo_positions').fetchone()[0],1)
        p=portfolio(self.c)
        self.assertEqual(p['legacy_demo_positions_archived'],1)
        self.assertEqual(p['equity_eur'],45)
        self.assertEqual(p['positions'],[])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_demo_positions').fetchone()[0],1)
    def test_quote_and_rate_must_be_valid(self):
        for quote,rate in ((dict(Q,price_usd=0),FX),(Q,{'usd_eur':None}),(Q,{'usd_eur':float('inf')})):
            with self.assertRaises(ValueError):trade(self.c,M,'BUY',quote,rate)
        self.assertEqual(portfolio(self.c)['cash_eur'],45)
    def test_fx_daily_reference_and_cached_when_provider_down(self):
        now=int(datetime(2026,11,19,18,tzinfo=timezone.utc).timestamp())
        calls=[]
        def fetch():
            calls.append(1)
            return {'base':'USD','quote':'EUR','date':'2026-11-19','rate':0.90}
        value=get_fx(self.c,fetch=fetch,now=now)
        self.assertAlmostEqual(value['usd_eur'],.9)
        cached=get_fx(self.c,fetch=lambda:1/0,now=now+60)
        self.assertAlmostEqual(cached['usd_eur'],.9)
        self.assertEqual(len(calls),1)
        with self.assertRaises(ValueError):
            get_fx(self.c,fetch=lambda: (_ for _ in ()).throw(ValueError('offline')),
                   now=now+4*86400)
    def test_fx_rejects_stale_or_wrong_base(self):
        now=int(datetime(2026,11,19,18,tzinfo=timezone.utc).timestamp())
        for payload in (
            {'base':'EUR','quote':'USD','date':'2026-11-19','rate':1.1},
            {'base':'USD','quote':'EUR','date':'2025-01-01','rate':.9},
            {'base':'USD','quote':'EUR','date':'2026-11-19','rate':float('nan')}):
            with self.assertRaises(ValueError):
                get_fx(self.c,fetch=lambda:payload,now=now)
if __name__=='__main__':unittest.main()
