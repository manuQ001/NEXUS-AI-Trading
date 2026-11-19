import sys, unittest, json
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from agents import review, local_ai_advice, attach_market_quality

class TestAgents(unittest.TestCase):
    def setUp(self):
        self.candles=[{'time':1700000000+i*300,'close':100.0} for i in range(100)]
        self.indicator={'buy':True,'atr':1.2,'why':'TEST'}
    def test_book_pass_only_advisory(self):
        original=review('BTC',self.candles,self.indicator)
        quality={'status':'PASS','reasons':[],'spread_bps':8.0,'bid_ask_drift_bps':2.0,'request_ms_second':120,'observed_at':1700000000}
        book={'symbol':'BTC','observed_at':1700000000,'best_ask':101.,'best_bid':99.,
              'asks':[{'price':101.,'volume':1.0}]}
        result=attach_market_quality(original,quality,book=book)
        self.assertTrue(result['paper_candidate'])
        self.assertEqual(result['market_consultation'],'PRELIMINARY_ONLY')
        self.assertTrue(result['market_quality']['advisory_only'])
        self.assertNotIn('market_quality',original)
        self.assertIn('non modifica',result['note'])
    def test_book_pass_without_matching_book_suppresses_candidate(self):
        original=review('BTC',self.candles,self.indicator)
        quality={'status':'PASS','reasons':[],'observed_at':1700000000}
        result=attach_market_quality(original,quality)
        self.assertFalse(result['paper_candidate'])
        self.assertEqual(result['sniper_estimate']['status'],'UNAVAILABLE')
        mismatch={'symbol':'ETH','observed_at':1700000000}
        result=attach_market_quality(original,quality,book=mismatch)
        self.assertFalse(result['paper_candidate'])
        self.assertEqual(result['sniper_estimate']['status'],'UNAVAILABLE')
    def test_book_participation_limits_sniper_candidate(self):
        original=review('BTC',self.candles,self.indicator)
        quality={'status':'PASS','reasons':[],'observed_at':1700000000}
        tiny={'symbol':'BTC','observed_at':1700000000,'best_ask':101.,'best_bid':99.,
              'asks':[{'price':101.,'volume':0.00001}]}
        result=attach_market_quality(original,quality,book=tiny)
        self.assertFalse(result['paper_candidate'])
        self.assertEqual(result['sniper_estimate']['status'],'ESTIMATE_PARTIAL')
        self.assertEqual(next(x for x in result['agents'] if x['name']=='SNIPER')['status'],'estimate_blocked')
    def test_risk_veto_skips_sniper_even_if_book_pass(self):
        original=review('BTC',self.candles,self.indicator,daily_realized=-4)
        quality={'status':'PASS','reasons':[],'observed_at':1700000000}
        result=attach_market_quality(original,quality,book={'symbol':'BTC','observed_at':1700000000})
        self.assertTrue(result['risk_veto'])
        self.assertFalse(result['paper_candidate'])
        self.assertEqual(result['sniper_estimate']['status'],'NOT_REQUESTED')
    def test_book_caution_suppresses_advisory_candidate(self):
        original=review('BTC',self.candles,self.indicator)
        result=attach_market_quality(original,{'status':'CAUTION','reasons':['HTTP troppo lento'],'spread_bps':65})
        self.assertFalse(result['paper_candidate'])
        self.assertEqual(result['market_consultation'],'NO_CANDIDATE')
        self.assertEqual(next(a for a in result['agents'] if a['name']=='HEAD OF DESK')['status'],'market_caution')
        self.assertTrue(original['paper_candidate'])
    def test_book_missing_fails_closed_for_display(self):
        original=review('BTC',self.candles,self.indicator)
        result=attach_market_quality(original,error='TimeoutError')
        self.assertEqual(result['market_quality']['status'],'UNAVAILABLE')
        self.assertFalse(result['paper_candidate'])
        self.assertEqual(next(a for a in result['agents'] if a['name']=='SNIPER')['status'],'idle')
    def test_book_pass_does_not_override_existing_risk_veto(self):
        original=review('BTC',self.candles,self.indicator,daily_realized=-4)
        result=attach_market_quality(original,{'status':'PASS','reasons':[]})
        self.assertTrue(result['risk_veto'])
        self.assertFalse(result['paper_candidate'])
    def test_book_caution_with_wait_remains_wait(self):
        original=review('BTC',self.candles,{'buy':False,'atr':1.2,'why':'WAIT'})
        result=attach_market_quality(original,{'status':'CAUTION','reasons':['spread']})
        self.assertEqual(result['proposal'],'WAIT')
        self.assertFalse(result['paper_candidate'])
    def test_local_ai_disabled_by_default(self):
        r=review('BTC',self.candles,self.indicator)
        with patch.dict('os.environ',{},clear=True):
            self.assertEqual(local_ai_advice(r)['status'],'disabled')
    def test_local_ai_cannot_override_risk_veto(self):
        r=review('BTC',self.candles,self.indicator,daily_realized=-4)
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def geturl(self):return 'http://127.0.0.1:11434/api/generate'
            def read(self,max_bytes):
                return json.dumps({'response':json.dumps({'summary':'Compra comunque!',
                   'risks':'Nessuno','uncertainty':'Nessuna'})}).encode()
        with patch('urllib.request.urlopen',return_value=FakeResponse()):
            advice=local_ai_advice(r,model='test-model')
        self.assertTrue(advice['available'])
        self.assertTrue(advice['risk_veto'])
        self.assertFalse(advice['paper_candidate'])
        self.assertTrue(r['risk_veto'])
    def test_local_ai_rejects_invalid_model(self):
        r=review('BTC',self.candles,self.indicator)
        self.assertEqual(local_ai_advice(r,model='https://evil.com')['status'],'invalid_model')
    def test_local_ai_handles_unavailable(self):
        r=review('BTC',self.candles,self.indicator)
        with patch('urllib.request.urlopen',side_effect=OSError('offline')):
            advice=local_ai_advice(r,model='test-model')
        self.assertFalse(advice['available'])
        self.assertEqual(advice['status'],'unavailable')
    def test_all_eight_have_explicit_status(self):
        r=review('BTC',self.candles,self.indicator)
        self.assertEqual(len(r['agents']),8)
        self.assertTrue(r['paper_candidate'])
        self.assertEqual(r['mode'],'READ ONLY / PAPER ONLY')
    def test_risk_veto_for_losses(self):
        r=review('BTC',self.candles,self.indicator,daily_realized=-3.01)
        self.assertFalse(r['paper_candidate'])
        self.assertTrue(r['risk_veto'])
        self.assertEqual(next(a for a in r['agents'] if a['name']=='RISK')['status'],'blocked')
    def test_agent_risk_preview_respects_core_circuit_breaker(self):
        r=review('BTC',self.candles,self.indicator,core_cash=94.49)
        self.assertTrue(r['risk_veto'])
        self.assertFalse(r['paper_candidate'])
        risk=next(a for a in r['agents'] if a['name']=='RISK')
        self.assertIn('Circuit breaker',risk['reason'])
    def test_agent_preview_does_not_authorize_execution(self):
        r=review('BTC',self.candles,self.indicator,core_cash=105)
        risk=next(a for a in r['agents'] if a['name']=='RISK')
        self.assertEqual(risk['status'],'preliminary_ok')
        self.assertIn('preliminare',r['note'])
    def test_risk_veto_for_feed(self):
        r=review('BTC',self.candles,self.indicator,feed_ok=False)
        self.assertFalse(r['paper_candidate'])
    def test_existing_position_blocks(self):
        self.assertFalse(review('ETH',self.candles,self.indicator,positions=[{'symbol':'BTC'}])['paper_candidate'])
    def test_unavailable_not_fabricated(self):
        r=review('BTC',self.candles,self.indicator)
        for name in ('WHALE','SHILL'):
            self.assertEqual(next(a for a in r['agents'] if a['name']==name)['status'],'unavailable')
    def test_short_history_veto(self):
        self.assertFalse(review('BTC',self.candles[:35],self.indicator)['paper_candidate'])
    def test_no_signal_no_candidate(self):
        r=review('BTC',self.candles,{'buy':False,'atr':1,'why':'WAIT'})
        self.assertEqual(r['proposal'],'WAIT')
        self.assertFalse(r['paper_candidate'])
    def test_no_mutation(self):
        candles=[dict(x) for x in self.candles]
        review('BTC',candles,self.indicator)
        self.assertEqual(candles,self.candles)

if __name__=='__main__':unittest.main()
