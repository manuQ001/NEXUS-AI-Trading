import sys, unittest, json
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from agents import review, local_ai_advice

class TestAgents(unittest.TestCase):
    def setUp(self):
        self.candles=[{'time':1700000000+i*300,'close':100.0} for i in range(100)]
        self.indicator={'buy':True,'atr':1.2,'why':'TEST'}
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
