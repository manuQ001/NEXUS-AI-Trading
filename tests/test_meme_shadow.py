"""NEXUS 3.9: no future leakage, no fake fills, and untouched PAPER wallet."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from meme_auto import init_auto
from meme_portfolio import portfolio
from meme_prices import observe,refresh_watchlist,snapshot
from meme_desk import record_scan
from meme_shadow import capture,evaluate,report,score_candidate

A='So11111111111111111111111111111111111111112'
B='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
Q={'address':A,'symbol':'SHADOW','price_usd':.01,'liquidity_usd':25000,
   'volume_24h_usd':55000,'pool_age_hours':1.0}

class TestShadowTrading(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.tmp.name)/'shadow.sqlite')
        init_auto(self.c)
    def tearDown(self):
        self.c.close();self.tmp.cleanup()
    def test_shadow_observation_uses_only_future_quote_and_never_trades(self):
        record_scan(self.c,[dict(Q)],now=1000,guard_blocked=True)
        before=portfolio(self.c)
        d=report(self.c,now=1000)
        self.assertEqual(d['pending'],1)
        self.assertEqual(d['observed'],0)
        observe(self.c,A,dict(Q,price_usd=.014),now=1299)
        self.assertEqual(evaluate(self.c,now=1300)['observed'],0)
        observe(self.c,A,dict(Q,price_usd=.012),now=1300)
        self.assertEqual(evaluate(self.c,now=1300)['observed'],1)
        summary=report(self.c,now=1301)
        self.assertEqual(summary['observed'],1)
        self.assertEqual(summary['signals'][0]['evaluated_at'],1300)
        self.assertAlmostEqual(summary['signals'][0]['gross_change_pct'],20,places=2)
        self.assertEqual(before['cash_eur'],portfolio(self.c)['cash_eur'])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],0)
    def test_constant_price_is_observation_not_fake_price_change(self):
        record_scan(self.c,[dict(Q)],now=1000)
        observe(self.c,A,Q,now=1300) # unchanged but real new provider REST read
        self.assertEqual(snapshot(self.c,now=1300)['sample_count'],1)
        self.assertEqual(evaluate(self.c,now=1300)['observed'],1)
        result=report(self.c)['signals'][0]
        self.assertEqual(result['gross_change_pct'],0)
        self.assertLess(result['modeled_net_change_pct'],0)
    def test_stale_future_quote_does_not_fabricate_outcome(self):
        record_scan(self.c,[dict(Q)],now=1000)
        observe(self.c,A,dict(Q,price_usd=.05),now=1700)
        self.assertEqual(evaluate(self.c,now=1701)['observed'],0)
        self.assertEqual(report(self.c)['signals'][0]['status'],'INSUFFICIENT_DATA')
        self.assertIsNone(report(self.c)['signals'][0]['modeled_net_change_pct'])
    def test_low_quality_scans_and_repeated_signal_cooldown(self):
        self.assertIsNone(score_candidate(dict(Q,volume_24h_usd=10)))
        self.assertIsNone(score_candidate(dict(Q,pool_age_hours=.01)))
        self.assertEqual(capture(self.c,[dict(Q),dict(Q)],now=1000),1)
        self.assertEqual(capture(self.c,[dict(Q)],now=1060),0)
        self.assertEqual(report(self.c)['pending'],1)
        self.assertEqual(capture(self.c,[dict(Q,address=B)],now=1060),1)
        self.assertEqual(report(self.c)['pending'],2)
    def test_shadow_keeps_watching_during_persistent_risk_lock(self):
        self.c.execute("UPDATE wallets SET cash=37,risk_latched=1 WHERE strategy='meme'") if False else None
        self.c.execute("UPDATE wallets SET cash=37 WHERE strategy='meme'")
        self.c.execute("UPDATE meme_auto_state SET risk_latched=1 WHERE id=1")
        record_scan(self.c,[dict(Q)],now=1000,guard_blocked=True)
        def quote(address):return dict(Q,price_usd=.011)
        self.assertEqual(refresh_watchlist(self.c,now=1300,quote=quote)['checked'],1)
        self.assertEqual(evaluate(self.c,now=1300)['observed'],1)
        self.assertEqual(portfolio(self.c)['cash_eur'],37)
        self.assertEqual(report(self.c)['pending'],0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],0)

if __name__=='__main__':unittest.main()
