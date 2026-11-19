import unittest,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from backtest import test_strategy, validate_holdout
from core import connect,process_candles

class TestBacktest(unittest.TestCase):
    def candles(self,n=100):
        return [{'time':1700000100+i*300,'open':100+i*.01,'high':101+i*.01,'low':99+i*.01,'close':100+i*.01,'volume':100} for i in range(n)]
    def test_rejects_invalid_ohlc(self):
        for field, value in [('high', 1), ('low', 999), ('volume', -3), ('open', float('nan'))]:
            c=self.candles();c[45][field]=value
            self.assertFalse(test_strategy(c)['ok'],field)
    def test_reports_candle_gaps(self):
        c=self.candles()
        for row in c[70:]:row['time']+=300
        r=test_strategy(c)
        self.assertTrue(r['ok'])
        self.assertEqual(r['gaps_over_5m'],1)
        self.assertIsNotNone(r['data_quality_warning'])
    def test_exit_uncertainty_metrics_present_and_nonnegative(self):
        report=test_strategy(self.candles())
        self.assertTrue(report['ok'])
        for key in ('ambiguous_exit_bars','gap_stop_fills','targets_suppressed_after_feed_gap'):
            self.assertIn(key,report)
            self.assertIsInstance(report[key],int)
            self.assertGreaterEqual(report[key],0)
    def test_empty_average_trade(self):
        r=test_strategy(self.candles())
        self.assertIsNone(r['avg_closed_trade_pnl'])
    def test_holdout_too_short(self):
        self.assertFalse(validate_holdout(self.candles(100))['ok'])
    def test_holdout_chronological_split(self):
        c=self.candles(300)
        report=validate_holdout(c)
        self.assertTrue(report['ok'])
        self.assertEqual(report['train_candles'],210)
        self.assertEqual(report['holdout_candles'],90)
        self.assertEqual(report['train']['end'],c[209]['time'])
        self.assertEqual(report['holdout']['start'],c[210]['time'])
        self.assertFalse(report['enough_evidence'])
    def test_holdout_future_does_not_change_training(self):
        a=self.candles(300);b=[dict(x) for x in a]
        b[-1].update(close=150,high=151)
        x=validate_holdout(a);y=validate_holdout(b)
        self.assertEqual(x['train']['final_equity'],y['train']['final_equity'])
        self.assertEqual(x['train']['closed_trades'],y['train']['closed_trades'])
    def test_holdout_invalid_data(self):
        c=self.candles(300);c[250]['low']=500
        self.assertFalse(validate_holdout(c)['ok'])
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
