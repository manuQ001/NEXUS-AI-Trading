import unittest,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from backtest import test_strategy
from core import connect,process_candles

class TestBacktest(unittest.TestCase):
    def candles(self,n=100):
        return [{'time':1700000100+i*300,'open':100+i*.01,'high':101+i*.01,'low':99+i*.01,'close':100+i*.01,'volume':100} for i in range(n)]
    def test_no_data(self):self.assertFalse(test_strategy(self.candles(20))['ok'])
    def test_results_without_trades(self):
        r=test_strategy(self.candles());self.assertTrue(r['ok']);self.assertEqual(r['closed_trades'],0);self.assertEqual(r['net_pnl'],0)
    def test_invalid_timestamp(self):
        c=self.candles();c[-1]['time']=c[-2]['time'];self.assertFalse(test_strategy(c)['ok'])
    def test_history_not_mutated(self):
        with tempfile.TemporaryDirectory() as t:
            c=connect(Path(t)/'db.sqlite3');process_candles(c,'BTC',self.candles());c.commit()
            old=c.execute('SELECT count(*) FROM trades').fetchone()[0]
            test_strategy(self.candles())
            self.assertEqual(old,c.execute('SELECT count(*) FROM trades').fetchone()[0]);c.close()
    def test_signal_cannot_use_future_candle(self):
        # A divergent final candle may affect only the final simulation step.
        a=self.candles(90);b=[dict(x) for x in a];b[-1].update(close=999,high=1000)
        r1=test_strategy(a);r2=test_strategy(b)
        self.assertEqual(r1['closed_trades'],r2['closed_trades'])
        self.assertEqual(r1['signals'],r2['signals'])
if __name__=='__main__':unittest.main()
