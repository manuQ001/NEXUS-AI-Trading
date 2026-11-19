"""Prospective AI hypothesis audit — no lookahead, no orders."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from hypothesis import validate_hypotheses, check_hypothesis, NEUTRAL_BPS
from research_journal import record, latest, update_outcomes

class TestProspectiveHypotheses(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.temp.name)/'test.sqlite3')
        self.base=1800000000
        self.report={'symbol':'BTC','time':self.base,'reference_close':100.,
                     'proposal':'WAIT','risk_veto':False}
        self.hypotheses=[
            {'horizon_bars':3,'direction':'UP','rationale':'Trend osservato'},
            {'horizon_bars':12,'direction':'ABSTAIN','rationale':'Dati non sufficienti'}]
        self.advice={'available':True,'status':'advisory_only','provider':'OpenAI',
                     'model':'gpt-4.1-mini','analysis':{'search':'Attendere'},
                     'hypotheses':self.hypotheses}
    def tearDown(self):
        self.c.close()
        self.temp.cleanup()
    def candles(self):
        return [{'time':self.base+300*i,'close':100.+i} for i in range(13)]
    def test_fixed_threshold_and_abstention(self):
        self.assertEqual(NEUTRAL_BPS,10.)
        self.assertEqual(check_hypothesis('UP','OBSERVED',11)['status'],'MATCH')
        self.assertEqual(check_hypothesis('UP','OBSERVED',10)['status'],'MISMATCH')
        self.assertEqual(check_hypothesis('FLAT','OBSERVED',-10)['status'],'MATCH')
        self.assertEqual(check_hypothesis('DOWN','OBSERVED',-11)['status'],'MATCH')
        self.assertEqual(check_hypothesis('ABSTAIN','OBSERVED',150)['status'],'ABSTAINED')
        self.assertEqual(check_hypothesis('UP','DATA_GAP',None)['matches'],None)
    def test_reject_malformed_or_reversed_predictions(self):
        with self.assertRaises(ValueError):
            validate_hypotheses([self.hypotheses[1],self.hypotheses[0]])
        with self.assertRaises(ValueError):
            validate_hypotheses([dict(self.hypotheses[0],direction='BUY'),self.hypotheses[1]])
        with self.assertRaises(ValueError):
            validate_hypotheses([dict(self.hypotheses[0],horizon_bars=True),self.hypotheses[1]])
    def test_before_and_after_future_candle_close(self):
        self.assertTrue(record(self.c,self.report,self.advice,now=self.base+350)['saved'])
        n=update_outcomes(self.c,'BTC',self.candles(),now=self.base+1199)
        self.assertEqual(n,0)
        before=latest(self.c)['entries'][0]
        self.assertEqual(before['hypotheses'][0]['assessment']['status'],'PENDING')
        n=update_outcomes(self.c,'BTC',self.candles(),now=self.base+1200)
        self.assertEqual(n,1)
        after=latest(self.c)['entries'][0]
        self.assertEqual(after['hypotheses'][0]['assessment']['status'],'MATCH')
        self.assertTrue(after['hypotheses'][0]['assessment']['matches'])
        self.assertEqual(after['hypotheses'][1]['assessment']['status'],'ABSTAINED')
        update_outcomes(self.c,'BTC',self.candles(),now=self.base+3900)
        after=latest(self.c)['entries'][0]
        self.assertEqual(after['hypotheses'][1]['assessment']['status'],'ABSTAINED')
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM positions').fetchone()[0],0)
    def test_missing_candles_never_score_prediction(self):
        record(self.c,self.report,self.advice,now=self.base+350)
        candles=[c for c in self.candles() if c['time']!=self.base+600]
        update_outcomes(self.c,'BTC',candles,now=self.base+3900)
        outcome=latest(self.c)['entries'][0]['hypotheses'][0]['assessment']
        self.assertEqual(outcome['status'],'DATA_GAP')
        self.assertIsNone(outcome['matches'])
    def test_old_advice_without_hypotheses_is_unscored(self):
        advice=dict(self.advice)
        advice.pop('hypotheses')
        record(self.c,self.report,advice,now=self.base+350)
        self.assertIsNone(latest(self.c)['entries'][0]['hypotheses'])
    def test_invalid_advice_hypotheses_are_not_recorded(self):
        advice=dict(self.advice,hypotheses=[{'horizon_bars':3,
                   'direction':'UP','rationale':'solo uno'}])
        self.assertEqual(record(self.c,self.report,advice,now=self.base+350)['reason'],
                         'INVALID_HYPOTHESES')
        self.assertEqual(latest(self.c)['entries'],[])

if __name__=='__main__':
    unittest.main()
