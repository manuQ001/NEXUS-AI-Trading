import sys, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect, signal, process_candles, wallet_status, handle_exit, try_buy, startup_events, state, store_closed_candles, load_closed_history, historical_coverage, closed_candle_fresh
from selftest import run_selftest

class TestCore(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.temp.name)/'t.sqlite3')
    def tearDown(self):
        self.c.close();self.temp.cleanup()
    def candles(self,n=45):
        return [{'time':1700000000+i*300,'open':100+i,'high':101+i,'low':99+i,'close':100+i,'volume':100} for i in range(n)]
    def test_history_deduplicated_and_ordered(self):
        candles=self.candles()
        store_closed_candles(self.c,'BTC',candles)
        store_closed_candles(self.c,'BTC',list(reversed(candles)))
        result=load_closed_history(self.c,'BTC')
        self.assertEqual(len(result),len(candles))
        self.assertEqual(result[0]['time'],candles[0]['time'])
        self.assertEqual(result[-1]['close'],candles[-1]['close'])
        self.assertEqual(historical_coverage(self.c,'BTC')['candles'],len(candles))
        self.assertEqual(historical_coverage(self.c,'ETH')['candles'],0)
    def test_history_isolated_from_trading_wallet(self):
        before=[dict(x) for x in wallet_status(self.c,{})]
        store_closed_candles(self.c,'BTC',self.candles())
        self.assertEqual(before,[dict(x) for x in wallet_status(self.c,{})])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
    def test_history_rejects_invalid_candle(self):
        candles=self.candles()
        candles[0]['high']=0
        with self.assertRaises(ValueError):
            store_closed_candles(self.c,'BTC',candles)
    def test_history_rejects_unknown_symbol(self):
        with self.assertRaises(ValueError):
            load_closed_history(self.c,'MEME')
    def test_candle_freshness_uses_close_not_start(self):
        candle={'time':1700000000}
        self.assertFalse(closed_candle_fresh(candle,now=1700000299))
        self.assertTrue(closed_candle_fresh(candle,now=1700000300))
        self.assertTrue(closed_candle_fresh(candle,now=1700000390))
        self.assertFalse(closed_candle_fresh(candle,now=1700000391))
    def test_stale_signal_is_vetoed_without_paper_trade(self):
        first=self.candles(80)
        process_candles(self.c,'BTC',first)
        new=self.candles(81)
        new[-1]['time']=first[-1]['time']+300
        with patch('core.signal',return_value={'buy':True,'atr':1.0,'rsi':50,'why':'TEST'}):
            with patch('core.time.time',return_value=1800000000):
                process_candles(self.c,'BTC',new)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
        result=self.c.execute('SELECT outcome, reason FROM decisions ORDER BY id DESC LIMIT 1').fetchone()
        self.assertEqual(result['outcome'],'BLOCK')
        self.assertIn('vecchio',result['reason'])
    def test_wallets(self):
        w=wallet_status(self.c,{})
        self.assertEqual(sum(x['equity'] for x in w),150)
    def test_no_backdated_trade(self):
        candles=self.candles();process_candles(self.c,'BTC',candles)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
    def test_new_candle_duplicate_does_not_trade(self):
        candles=self.candles();process_candles(self.c,'BTC',candles)
        process_candles(self.c,'BTC',candles)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
    def test_buy_close_fee_and_pnl(self):
        cand=self.candles();ind={'buy':True,'atr':1.0,'why':'TEST'}
        try_buy(self.c,'BTC',cand,ind)
        p=self.c.execute('SELECT * FROM positions').fetchone()
        self.assertIsNotNone(p)
        self.assertGreater(p['entry_fee'],0)
        handle_exit(self.c,'BTC',{'open':p['target']+1,'high':p['target']+2,'low':p['target']+0.1})
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM positions').fetchone()[0],0)
        t=self.c.execute('SELECT * FROM trades WHERE action="SELL"').fetchone()
        self.assertGreater(t['pnl'],0)
    def test_stop_first(self):
        try_buy(self.c,'BTC',self.candles(),{'buy':True,'atr':1,'why':'TEST'})
        p=self.c.execute('SELECT * FROM positions').fetchone()
        handle_exit(self.c,'BTC',{'open':p['entry'],'high':p['target']+2,'low':p['stop']-2})
        t=self.c.execute('SELECT * FROM trades WHERE action="SELL"').fetchone()
        self.assertLess(t['pnl'],0)
        self.assertEqual(t['details'],'Stop loss')
    def test_meme_not_tradeable(self):
        startup_events(self.c)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades WHERE symbol NOT IN ("BTC","ETH")').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT cash FROM wallets WHERE strategy="meme"').fetchone()[0],45)
    def test_isolated_selftest(self):
        self.assertTrue(run_selftest()["ok"])
    def test_no_signal_short_data(self):
        self.assertFalse(signal(self.candles(8))['buy'])

if __name__=='__main__':unittest.main()
