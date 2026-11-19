"""Tests of the isolated AI research journal: no lookahead, no trading writes."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from research_journal import record, update_outcomes, latest


class TestJournal(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.tmp.name)/'paper.sqlite3')
        self.base=1800000000
        self.report={'symbol':'BTC','time':self.base,'reference_close':100.,
                     'proposal':'WAIT','risk_veto':False}
        self.advice={'available':True,'status':'advisory_only',
                     'provider':'OpenAI','model':'gpt-4.1-mini',
                     'analysis':{'search':'WAIT','head_of_desk':'Attesa',
                                 'risks':'Commissioni','uncertainty':'Alta'}}
    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()
    def candles(self,missing=()):
        return [{'time':self.base+i*300,'close':100.+i}
                for i in range(13) if i not in missing]
    def test_fresh_advice_recorded_no_trade_or_wallet_changes(self):
        before=[tuple(r) for r in self.c.execute('SELECT * FROM wallets')]
        result=record(self.c,self.report,self.advice,now=self.base+350)
        self.assertTrue(result['saved'])
        self.assertEqual([tuple(r) for r in self.c.execute('SELECT * FROM wallets')],before)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM positions').fetchone()[0],0)
        snapshot=latest(self.c)
        self.assertEqual(snapshot['entries'][0]['analysis']['search'],'WAIT')
        self.assertEqual(snapshot['entries'][0]['base_close'],100.)
    def test_no_lookahead_before_horizon_close(self):
        record(self.c,self.report,self.advice,now=self.base+350)
        n=update_outcomes(self.c,'BTC',self.candles(),now=self.base+1199)
        self.assertEqual(n,0)
        self.assertEqual(latest(self.c)['entries'][0]['outcomes'],[])
        n=update_outcomes(self.c,'BTC',self.candles(),now=self.base+1200)
        self.assertEqual(n,1)
        out=latest(self.c)['entries'][0]['outcomes']
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]['horizon_bars'],3)
        self.assertEqual(out[0]['status'],'OBSERVED')
        self.assertAlmostEqual(out[0]['price_change_bps'],300.)
    def test_two_horizons_and_repeat_are_idempotent(self):
        record(self.c,self.report,self.advice,now=self.base+350)
        self.assertEqual(update_outcomes(self.c,'BTC',self.candles(),now=self.base+3900),2)
        self.assertEqual(update_outcomes(self.c,'BTC',self.candles(),now=self.base+4000),0)
        out=latest(self.c)['entries'][0]['outcomes']
        self.assertEqual([x['horizon_bars'] for x in out],[3,12])
        self.assertEqual([x['status'] for x in out],['OBSERVED','OBSERVED'])
        self.assertAlmostEqual(out[-1]['price_change_bps'],1200.)
    def test_missing_intermediate_candle_is_data_gap(self):
        record(self.c,self.report,self.advice,now=self.base+350)
        self.assertEqual(update_outcomes(self.c,'BTC',self.candles(missing=(2,)),
                                         now=self.base+3900),2)
        out=latest(self.c)['entries'][0]['outcomes']
        self.assertEqual([x['status'] for x in out],['DATA_GAP','DATA_GAP'])
        self.assertTrue(all(x['price_change_bps'] is None for x in out))
    def test_stale_or_unconfigured_advice_not_saved(self):
        self.assertEqual(record(self.c,self.report,self.advice,now=self.base+900)['reason'],
                         'STALE_CANDLE')
        self.assertEqual(record(self.c,self.report,{'available':False},now=self.base+350)['reason'],
                         'NO_VALID_ADVICE')
        self.assertEqual(latest(self.c)['entries'],[])
    def test_duplicate_same_candle_rejected(self):
        first=record(self.c,self.report,self.advice,now=self.base+350)
        duplicate=record(self.c,self.report,self.advice,now=self.base+360)
        self.assertTrue(first['saved'])
        self.assertEqual(duplicate['reason'],'DUPLICATE_SNAPSHOT')
        self.assertEqual(len(latest(self.c)['entries']),1)
    def test_symbol_isolated_and_no_wallet_mutation_on_evaluation(self):
        record(self.c,self.report,self.advice,now=self.base+350)
        before=[tuple(r) for r in self.c.execute('SELECT * FROM wallets')]
        self.assertEqual(update_outcomes(self.c,'ETH',self.candles(),now=self.base+3900),0)
        self.assertEqual([tuple(r) for r in self.c.execute('SELECT * FROM wallets')],before)
    def test_no_secret_value_in_research_snapshot(self):
        analysis=dict(self.advice['analysis'])
        analysis['secret_note']='Local commentary only'
        safe=dict(self.advice,analysis=analysis)
        record(self.c,self.report,safe,now=self.base+350)
        blob=''.join(r[0] for r in self.c.execute('SELECT analysis_json FROM ai_research'))
        self.assertNotIn('api_key',blob)


if __name__=='__main__':
    unittest.main()
