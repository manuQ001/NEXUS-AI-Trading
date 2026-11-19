import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from agents import review

class TestAgents(unittest.TestCase):
    def setUp(self):
        self.candles=[{'time':1700000000+i*300,'close':100.0} for i in range(100)]
        self.indicator={'buy':True,'atr':1.2,'why':'TEST'}
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
