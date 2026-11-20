"""NEXUS 4.3 outcome checks: genuine REST reads, no order authority."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from meme_prices import observe
from v4_ai_shadow import initialize as init_ai,finish
from v4_ai_intelligence import initialize,seed,evaluate,report

MINT='3fWhdo8bQCamw5ed6yNGdvaru1qS5UVwB6dYp9znpump'
OTHER='7R4MP6VX7n3RMNhL9zsk5Zu5ibZvwq8npUYnRq7epump'

def q(p):
    return {'address':MINT,'symbol':'PROBE','price_usd':p,
            'liquidity_usd':45000,'volume_24h_usd':95000}

class TestOutcomeIntelligence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.tmp.name)/'nexus.db')
        init_ai(self.c);initialize(self.c)
    def tearDown(self):
        self.c.close();self.tmp.cleanup()
    def _finish(self,now=1000,verdict='WAIT',python='BUY'):
        self.c.execute("""INSERT INTO v4_ai_shadow_audit(timestamp,date_utc,
            month_utc,address,symbol,observed_at,model,outcome)
            VALUES(1000,'2026-01-01','2026-01',?,?,990,'gpt-6-luna','RESERVED')""",
            (MINT,'PROBE'))
        id=self.c.execute('SELECT last_insert_rowid()').fetchone()[0]
        request={'audit_id':id,'rules_verdict':python}
        v={'verdict':verdict,'analyst':'x','risk':'x','strategy':'x',
           'portfolio':'x','rationale':'Research only'}
        # finish calls seed at wall-clock now; patch only the seed's clock.
        from unittest.mock import patch
        original=__import__('v4_ai_intelligence').seed
        with patch('v4_ai_intelligence.seed',
                   side_effect=lambda c,r,v:original(c,r,v,now=now)):
            finish(self.c,request,v)
        return id
    def test_exact_5_15_30_frozen_anchor(self):
        observe(self.c,MINT,q(.01),now=990)
        id=self._finish(now=1000)
        o=report(self.c)
        self.assertEqual(o['stats']['evaluated_reviews'],1)
        self.assertEqual(o['stats']['rule_disagreements'],1)
        self.assertEqual([x['status'] for x in o['checks']],
                         ['PENDING','PENDING','PENDING'])
        self.assertEqual(o['checks'][0]['reference_price_usd'],.01)
        self.assertEqual(o['checks'][0]['reference_quote_at'],990)
        observe(self.c,MINT,q(.02),now=1299) # BEFORE target, MUST NOT be used
        self.assertEqual(evaluate(self.c,now=1300),0)
        observe(self.c,MINT,q(.009),now=1307)
        self.assertEqual(evaluate(self.c,now=1310),1)
        self.assertEqual(evaluate(self.c,now=1315),0)
        observe(self.c,MINT,q(.0105),now=1905)
        observe(self.c,MINT,q(.015),now=1910)
        self.assertEqual(evaluate(self.c,now=1915),1)
        observe(self.c,MINT,q(.011),now=2800)
        self.assertEqual(evaluate(self.c,now=2801),1)
        d=report(self.c)
        self.assertEqual([x['return_pct'] for x in d['checks']],[-10,5,10])
        self.assertEqual(d['horizons'][0]['wait_declines'],1)
        self.assertEqual(d['horizons'][1]['wait_rises'],1)
        self.assertEqual(d['horizons'][2]['wait_rises'],1)
        self.assertEqual(d['checks'][1]['followup_at'],1905)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM v4_ai_outcome_checks').fetchone()[0],3)
    def test_missing_and_never_use_later_quote(self):
        observe(self.c,MINT,q(.01),now=995)
        self._finish()
        # After the two-minute tolerance the horizon is irreversibly missing.
        self.assertEqual(evaluate(self.c,now=1421),1)
        observe(self.c,MINT,q(.03),now=1450)
        self.assertEqual(evaluate(self.c,now=1451),0)
        self.assertEqual(report(self.c)['checks'][0]['status'],'MISSING_QUOTE')
        self.assertIsNone(report(self.c)['checks'][0]['return_pct'])
    def test_no_fresh_baseline_and_no_later_backfill(self):
        observe(self.c,MINT,q(.02),now=800)
        id=self._finish(now=1000)
        self.assertFalse(seed(self.c,{'audit_id':id,'rules_verdict':'BUY'},
                              {'verdict':'WAIT'},now=1001))
        observe(self.c,MINT,q(.03),now=1301)
        self.assertEqual(evaluate(self.c,now=4000),0)
        self.assertTrue(all(x['status']=='NO_BASELINE' for x in report(self.c)['checks']))
    def test_only_actual_mint_quotes_and_first_read(self):
        observe(self.c,MINT,q(.01),now=1000)
        self._finish(now=1000,verdict='BUY',python='WAIT')
        observe(self.c,OTHER,dict(q(.9),address=OTHER),now=1300)
        self.assertEqual(evaluate(self.c,now=1300),0)
        observe(self.c,MINT,q(.012),now=1300)
        observe(self.c,MINT,q(.013),now=1300)
        self.assertEqual(evaluate(self.c,now=1300),1)
        d=report(self.c)
        self.assertEqual(d['checks'][0]['return_pct'],20)
        self.assertEqual(d['horizons'][0]['directional_correct'],1)
        self.assertTrue(d['metrics_are_not_trading_performance'])
    def test_unfinished_api_requests_and_legacy_no_backfill(self):
        self.c.execute("""INSERT INTO v4_ai_shadow_audit(timestamp,date_utc,month_utc,
            address,symbol,observed_at,model,outcome,verdict)
            VALUES(1000,'2026-01-01','2026-01',?,?,990,'gpt-6-luna',
                   'COMPLETED','WAIT')""",(MINT,'PROBE'))
        self.assertEqual(report(self.c)['stats']['legacy_no_reference'],1)
        self.assertEqual(report(self.c)['checks'],[])
    def test_dashboard_exposes_research_disclaimer(self):
        html=(Path(__file__).resolve().parents[1]/'src'/'dashboard.html').read_text('utf8')
        for val in ('nx-v4-intelligence','nx-v4-outcome-grid',
                    'Risultati osservati','NON sono profitti'):
            self.assertIn(val,html)
if __name__=='__main__': unittest.main()
