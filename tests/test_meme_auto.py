"""MEME AUTO trades in the original €45 virtual wallet; never real orders."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect,wallet_status
from meme_auto import tick,status,choose_candidate,decide_exit,init_auto,dynamic_stake
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
        self.assertEqual(portfolio(self.c)['cash_eur'],43.5)
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
        self.assertEqual(decide_exit(p,.01,50+900,FX['usd_eur']),'TIMEOUT_15M')
    def test_trailing_peak_persisted_and_sell_when_net_roi_reverses(self):
        trade(self.c,M,'BUY',Q,FX,now=100)
        prices=[.0118, .0112]
        def quote(_):
            return dict(Q,price_usd=prices.pop(0))
        first=tick(self.c,now=110,scout=lambda:{'candidates':[]},quote=quote,fx_rate=fx)
        self.assertEqual(len(portfolio(self.c)['positions']),1)
        self.assertIsNotNone(self.c.execute('SELECT peak_net_roi FROM meme_auto_trail WHERE address=?',(M,)).fetchone())
        second=tick(self.c,now=125,scout=lambda:{'candidates':[]},quote=quote,fx_rate=fx)
        self.assertEqual(len(portfolio(self.c)['positions']),0)
        self.assertTrue(any(x['action']=='AUTO_SELL' and 'TRAILING_STOP' in x['note'] for x in second['journal']))
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_auto_trail').fetchone()[0],0)
    def test_missing_quote_does_not_trigger_timeout_or_fake_sale(self):
        trade(self.c,M,'BUY',Q,FX,now=100)
        tick(self.c,now=1100,scout=lambda:{'candidates':[]},
             quote=lambda _: (_ for _ in ()).throw(ValueError('feed unavailable')),fx_rate=fx)
        self.assertEqual(len(portfolio(self.c)['positions']),1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades WHERE action="SELL"').fetchone()[0],0)
    def test_disabled_does_not_call_sources(self):
        init_auto(self.c)
        self.c.execute('UPDATE meme_auto_state SET enabled=0 WHERE id=1')
        self.c.commit()
        tick(self.c,now=2000,scout=lambda:1/0,quote=lambda a:1/0,
             fx_rate=lambda c,now=None:1/0)
        self.assertEqual(portfolio(self.c)['positions'],[])
    def test_live_scan_cadence_is_one_minute(self):
        from meme_auto import SCAN_SECONDS
        self.assertEqual(SCAN_SECONDS,60)
        calls=[]
        def scout():
            calls.append(1)
            return {'candidates':[]}
        tick(self.c,now=1000,scout=scout,quote=lambda _:Q,fx_rate=fx)
        tick(self.c,now=1050,scout=scout,quote=lambda _:Q,fx_rate=fx)
        tick(self.c,now=1060,scout=scout,quote=lambda _:Q,fx_rate=fx)
        self.assertEqual(len(calls),2)

    def test_real_quote_change_emits_observed_event(self):
        trade(self.c,M,'BUY',Q,FX,now=100)
        first=tick(self.c,now=120,scout=lambda:{'candidates':[]},
                   quote=lambda _:dict(Q,price_usd=0.0105),fx_rate=fx)
        self.assertTrue(any(x['action']=='PRICE_OBSERVED' for x in first['journal']))
        self.assertTrue(any('0.0105' in x['note'] for x in first['journal']
                            if x['action']=='PRICE_OBSERVED'))

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
    def test_dynamic_sizing_and_cash_reserve(self):
        w=self.c.execute("SELECT initial FROM wallets WHERE strategy='meme'").fetchone()
        self.assertEqual(w['initial'],45)
        self.assertEqual(dynamic_stake(self.c,Q,Q),1.5)
        medium=dict(Q,liquidity_usd=4000,volume_24h_usd=5000)
        strong=dict(Q,liquidity_usd=20000,volume_24h_usd=30000)
        self.assertEqual(dynamic_stake(self.c,medium,medium),3.0)
        self.assertEqual(dynamic_stake(self.c,strong,strong),4.5)
        self.c.execute("UPDATE wallets SET cash=10 WHERE strategy='meme'")
        self.assertIsNone(dynamic_stake(self.c,strong,strong))
        self.c.execute("UPDATE wallets SET cash=12 WHERE strategy='meme'")
        self.assertEqual(dynamic_stake(self.c,strong,strong),3.0)
    def test_orders_have_different_stakes(self):
        rows=[dict(Q,address=M),dict(Q,address=A,liquidity_usd=5000,volume_24h_usd=5000),
              dict(Q,address=B,liquidity_usd=20000,volume_24h_usd=20000)]
        by_addr={r['address']:r for r in rows}
        tick(self.c,now=2000,scout=lambda:{'candidates':rows},
             quote=lambda a:by_addr[a],fx_rate=fx)
        costs=sorted(p['cost_eur'] for p in portfolio(self.c)['positions'])
        self.assertEqual(costs,[1.5,3.0,4.5])
        self.assertEqual(portfolio(self.c)['cash_eur'],36.0)
    def test_terminal_records_scan_counts_and_buy_rationale(self):
        rows=[dict(Q,address=M),dict(Q,address=A,liquidity_usd=2)]
        state=tick(self.c,now=2000,scout=lambda:{'candidates':rows},
                   quote=lambda mint:Q,fx_rate=fx)
        events=state['journal']
        self.assertTrue(any(x['action']=='AUTO_SCAN' and 'Analizzati 2 token' in x['note'] for x in events))
        self.assertTrue(any(x['action']=='AUTO_BUY' and 'liquidita USD' in x['note'] for x in events))
        self.assertEqual(len(portfolio(self.c)['positions']),1)
    def test_multiple_distinct_orders_same_scan(self):
        rows=[dict(Q,address=x) for x in (M,A,B)]
        tick(self.c,now=2000,scout=lambda:{'candidates':rows},quote=lambda _:Q,fx_rate=fx)
        positions=portfolio(self.c)['positions']
        self.assertEqual(len(positions),3)
        self.assertEqual(portfolio(self.c)['cash_eur'],40.5)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],3)
        values={x['address'] for x in positions}
        self.assertEqual(len(values),3)
        self.assertEqual(wallet_status(self.c,{})[1]['strategy'],'meme')
if __name__=='__main__':unittest.main()
