"""Evidence-only live decision timeline: no fictional trades or wallet mutations."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from meme_auto import init_auto
from meme_desk import record_scan
from meme_shadow import evaluate
from meme_prices import observe
from meme_portfolio import portfolio
from meme_timeline import timeline
A='So11111111111111111111111111111111111111112'
Q={'address':A,'symbol':'OBS','price_usd':.01,
   'liquidity_usd':21000,'volume_24h_usd':50000,'pool_age_hours':1.0}
class TestDecisionTimeline(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.temp.name)/'timeline.sqlite3')
        init_auto(self.c)
    def tearDown(self):
        self.c.close()
        self.temp.cleanup()
    def test_empty_database_never_fabricates_events(self):
        result=timeline(self.c,now=100)
        self.assertEqual(result['events'],[])
        self.assertEqual(result['total_returned'],0)
        self.assertEqual(result['mode'],'RECORDED_DECISIONS_ONLY')
    def test_genuine_scans_and_shadow_only(self):
        record_scan(self.c,[dict(Q)],now=1000,guard_blocked=True)
        result=timeline(self.c,now=1001)
        self.assertTrue(any(e['category']=='scan' and e['source']=='SCANNER' for e in result['events']))
        self.assertTrue(any(e['category']=='shadow' and e['action']=='SIGNAL_CAPTURED'
                            for e in result['events']))
        self.assertFalse(any(e['verified_trade'] for e in result['events']))
        observe(self.c,A,dict(Q,price_usd=.013),now=1300)
        evaluate(self.c,now=1300)
        result=timeline(self.c,now=1301)
        self.assertTrue(any(e['source']=='SHADOW_EVALUATION' for e in result['events']))
        self.assertEqual(portfolio(self.c)['cash_eur'],45)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],0)
    def test_journal_actions_are_labelled_paper_not_actual_orders(self):
        self.c.execute("""INSERT INTO meme_auto_journal(timestamp,address,action,note)
            VALUES(?,?,?,?)""",(1000,A,'AUTO_BUY','Ordine virtuale da test'))
        self.c.execute("""INSERT INTO meme_auto_journal(timestamp,address,action,note)
            VALUES(?,?,?,?)""",(1001,A,'RISK_CIRCUIT','BUY bloccati'))
        self.c.execute("""INSERT INTO meme_auto_journal(timestamp,address,action,note)
            VALUES(?,?,?,?)""",(1002,A,'UNSUPPORTED_ACTION','No UI event'))
        records=timeline(self.c,now=1010)['events']
        self.assertEqual(len(records),2)
        buy=next(x for x in records if x['action']=='AUTO_BUY')
        self.assertEqual(buy['category'],'trade')
        self.assertTrue(buy['paper_only'])
        self.assertFalse(buy['verified_trade'])
        risk=next(x for x in records if x['action']=='RISK_CIRCUIT')
        self.assertEqual(risk['category'],'risk')
    def test_order_limit_and_stable_keys(self):
        for i in range(42):
            self.c.execute("""INSERT INTO meme_auto_journal(timestamp,address,action,note)
                VALUES(?,?,?,?)""",(1000+i,A,'AI_DESK','Registro '+str(i)))
        first=timeline(self.c,now=2000,limit=9)
        second=timeline(self.c,now=2001,limit=9)
        self.assertEqual(first['events'],second['events'])
        self.assertEqual(len(first['events']),9)
        self.assertEqual(len(set(x['key'] for x in first['events'])),9)
        self.assertEqual(first['events'][0]['timestamp'],1041)
        self.assertEqual(len(timeline(self.c,limit=999)['events']),36)
    def test_dashboard_reuses_real_sse_not_mocked_timeline_events(self):
        html=(Path(__file__).resolve().parents[1]/'src'/'dashboard.html').read_text('utf-8')
        for name in ['nx-decision-timeline','nx-timeline-count',
                     'nx-timeline-caveat','nxRenderDecisionTimeline',
                     'nxLoadDecisionTimeline','/api/meme-decision-timeline',
                     'data-timeline-filter="risk"','data-timeline-filter="shadow"',
                     'prefers-reduced-motion:reduce']:
            self.assertIn(name,html)
        self.assertNotIn('Math.random()',html)
        self.assertNotIn('fakeTrade',html)
if __name__=='__main__':unittest.main()
