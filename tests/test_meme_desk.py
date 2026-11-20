"""NEXUS 3.6: eight role reporting, scan evidence and persistent risk latch."""
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from meme_auto import init_auto,tick,status
from meme_desk import classify,record_scan,report
from meme_portfolio import portfolio,trade

A='So11111111111111111111111111111111111111112'
B='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
Q={'address':A,'symbol':'ABC','price_usd':.001,
   'liquidity_usd':30000,'volume_24h_usd':48000,'pool_age_hours':1.5}
FX={'usd_eur':.9,'rate_date':'2026-11-20'}
def fx(c,now=None):return FX

class TestDeskControl(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.path=Path(self.t.name)/'db.sqlite'
        self.c=connect(self.path)
        init_auto(self.c)
    def tearDown(self):
        self.c.close();self.t.cleanup()
    def test_reject_reason_and_screened_not_order_approval(self):
        self.assertEqual(classify(Q),( 'SCREENED',
                 'REQUIRES_QUOTE_RISK_AGENT_AND_CAPITAL_CHECK'))
        self.assertEqual(classify(dict(Q,liquidity_usd=500)),('REJECTED','LIQUIDITA_BASSA'))
        self.assertEqual(classify(dict(Q,volume_24h_usd=0)),('REJECTED','VOLUME_NON_VERIFICABILE'))
        self.assertEqual(classify(dict(Q,pool_age_hours=.1)),('REJECTED','POOL_TROPPO_RECENTE'))
        self.assertEqual(classify(Q,guard_blocked=True),('WATCH_ONLY','CIRCUIT_BREAKER'))
    def test_scan_decisions_are_bounded_and_read_only_to_wallet(self):
        before=portfolio(self.c)['cash_eur']
        result=record_scan(self.c,[Q,Q,dict(Q,address=B,liquidity_usd=800)],
                           now=1000,guard_blocked=True,source='STREAM')
        self.assertEqual(result,{'WATCH_ONLY':1,'REJECTED':1})
        self.assertEqual(portfolio(self.c)['cash_eur'],before)
        d=report(self.c,now=1001,stream={'connected':True,'last_message':1000})
        self.assertEqual(len(d['roles']),8)
        self.assertEqual(d['decision_counts']['REJECTED'],1)
        self.assertEqual(d['decision_counts']['WATCH_ONLY'],1)
        self.assertEqual(len(d['latest']),2)
        self.assertEqual(d['roles'][0]['status'],'WS_RECENT')
        self.assertEqual(d['roles'][1]['status'],'NOT_AUTOMATED')
        self.assertEqual(d['roles'][6]['status'],'NOT_CONNECTED')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],0)
    def test_drawdown_lock_survives_balance_recovery_and_database_reopen(self):
        self.c.execute("UPDATE wallets SET cash=37 WHERE strategy='meme'")
        self.c.commit()
        tick(self.c,now=2000,scout=lambda:{'candidates':[dict(Q)]},
             quote=lambda _:Q,fx_rate=fx)
        risk=self.c.execute('SELECT risk_latched FROM meme_auto_state WHERE id=1').fetchone()
        self.assertEqual(risk['risk_latched'],1)
        self.c.execute("UPDATE wallets SET cash=45 WHERE strategy='meme'")
        self.c.commit()
        self.assertTrue(status(self.c)['risk_circuit']['latched'])
        self.c.close()
        self.c=connect(self.path)
        with patch('meme_auto.review_meme_agents',side_effect=AssertionError('paid API')):
            tick(self.c,now=2100,scout=lambda:{'candidates':[dict(Q)]},
                 quote=lambda _:Q,fx_rate=fx)
        self.assertTrue(status(self.c)['risk_circuit']['blocked'])
        self.assertEqual(len(portfolio(self.c)['positions']),0)
        self.assertEqual(self.c.execute(
            "SELECT COUNT(*) FROM meme_scan_decisions WHERE decision='WATCH_ONLY'"
        ).fetchone()[0],2)
    def test_latch_does_not_disable_exit_of_existing_position(self):
        trade(self.c,A,'BUY',Q,FX,now=100,stake_eur=3)
        self.c.execute("UPDATE meme_auto_state SET risk_latched=1 WHERE id=1")
        self.c.commit()
        tick(self.c,now=1100,scout=lambda:{'candidates':[dict(Q,address=B)]},
             quote=lambda _:dict(Q,price_usd=.0012),fx_rate=fx)
        self.assertEqual(len(portfolio(self.c)['positions']),0)
        self.assertTrue(any(t['action']=='SELL' for t in portfolio(self.c)['trades']))

if __name__=='__main__':unittest.main()
