import sys, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect, signal, process_candles, wallet_status, handle_exit, try_buy, startup_events, state, store_closed_candles, load_closed_history, historical_coverage, closed_candle_fresh, assess_paper_order, risk_limits_status
from selftest import run_selftest

class TestCore(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.temp.name)/'t.sqlite3')
    def tearDown(self):
        self.c.close();self.temp.cleanup()
    def candles(self,n=45):
        return [{'time':1700000000+i*300,'open':100+i,'high':101+i,'low':99+i,'close':100+i,'volume':100} for i in range(n)]
    def test_search_wait_explains_ema_without_changing_buy_gate(self):
        result=signal(self.candles(45))
        self.assertFalse(result['buy'])
        self.assertEqual(result['reason_code'],'EMA_NO_CROSS')
        self.assertIn('EMA',result['why'])
        self.assertIn('filters',result)
    def test_search_short_history_explains_wait(self):
        result=signal(self.candles(8))
        self.assertFalse(result['buy'])
        self.assertEqual(result['reason_code'],'INSUFFICIENT_HISTORY')
    def test_search_rsi_diagnostic_when_ema_crosses(self):
        with patch('core.ema',side_effect=[102,100,99,100]),patch('core.rsi',return_value=80),patch('core.atr',return_value=1):
            result=signal(self.candles(45))
        self.assertEqual(result['reason_code'],'RSI_OUT_OF_RANGE')
        self.assertFalse(result['buy'])
    def test_search_buy_logic_unmodified_for_valid_filters(self):
        with patch('core.ema',side_effect=[102,100,99,100]),patch('core.rsi',return_value=60),patch('core.atr',return_value=1):
            result=signal(self.candles(45))
        self.assertTrue(result['buy'])
        self.assertEqual(result['reason_code'],'BUY_VALID')
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
    def test_missing_quote_blocks_virtual_buy(self):
        candles=self.candles()
        try_buy(self.c,'BTC',candles,{'buy':True,'atr':1,'why':'TEST'})
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
    def test_invalid_or_distant_quote_blocks_virtual_buy(self):
        candles=self.candles();ind={'buy':True,'atr':1,'why':'TEST'}
        for quote in (0,float('nan'),candles[-1]['close']*1.02):
            try_buy(self.c,'BTC',candles,ind,quote_price=quote)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
    def test_fresh_quote_sets_entry_price_and_fee(self):
        candles=self.candles();ask=candles[-1]['close']*1.001
        try_buy(self.c,'BTC',candles,{'buy':True,'atr':1,'why':'TEST'},quote_price=ask)
        p=self.c.execute('SELECT * FROM positions').fetchone()
        self.assertIsNotNone(p)
        self.assertAlmostEqual(p['entry'],ask*1.0005)
        self.assertGreater(p['entry_fee'],0)
    def test_unified_risk_gate_read_only(self):
        candles=self.candles()
        indicator={'buy':True,'atr':1.0,'why':'TEST'}
        before=[dict(row) for row in self.c.execute('SELECT * FROM wallets')]
        result=assess_paper_order(self.c,'BTC',candles,indicator,quote_price=candles[-1]['close'])
        self.assertTrue(result['approved'])
        self.assertLessEqual(result['estimated_stop_risk'],.75+1e-7)
        self.assertEqual([dict(row) for row in self.c.execute('SELECT * FROM wallets')],before)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
    def test_risk_gate_explains_quote_and_signal_vetos(self):
        candles=self.candles()
        ind={'buy':True,'atr':1,'why':'TEST'}
        self.assertIn('Manca',assess_paper_order(self.c,'BTC',candles,ind)['reason'])
        self.assertIn('distante',assess_paper_order(self.c,'BTC',candles,ind,quote_price=200)['reason'])
        self.assertIn('SEARCH',assess_paper_order(self.c,'BTC',candles,{'buy':False},quote_price=144)['reason'])
        self.assertFalse(assess_paper_order(self.c,'MEME',candles,ind,quote_price=144)['approved'])
    def test_risk_circuit_breaker_blocks_further_paper_buys(self):
        self.c.execute('UPDATE wallets SET cash=94.49 WHERE strategy="core"')
        candles=self.candles()
        d=assess_paper_order(self.c,'BTC',candles,{'buy':True,'atr':1},quote_price=candles[-1]['close'])
        self.assertFalse(d['approved'])
        self.assertIn('Circuit breaker',d['reason'])
        try_buy(self.c,'BTC',candles,{'buy':True,'atr':1},quote_price=candles[-1]['close'])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
    def test_risk_existing_position_is_non_bypassable(self):
        candles=self.candles()
        ind={'buy':True,'atr':1,'why':'TEST'}
        self.assertTrue(try_buy(self.c,'BTC',candles,ind,quote_price=candles[-1]['close'])['approved'])
        second=try_buy(self.c,'ETH',candles,ind,quote_price=candles[-1]['close'])
        self.assertFalse(second['approved'])
        self.assertIn('posizione',second['reason'])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades WHERE action="BUY"').fetchone()[0],1)
    def test_risk_daily_loss_blocks_buy(self):
        from datetime import datetime, timezone
        now=int(datetime.now(timezone.utc).timestamp())
        self.c.execute('INSERT INTO trades(timestamp,symbol,action,qty,price,fee,pnl,details) VALUES(?,?,?,?,?,?,?,?)',
                       (now,'BTC','SELL',1,100,0,-3.10,'TEST'))
        candles=self.candles()
        decision=assess_paper_order(self.c,'BTC',candles,{'buy':True,'atr':1},quote_price=candles[-1]['close'])
        self.assertFalse(decision['approved'])
        self.assertIn('giornaliera',decision['reason'])
    def test_risk_dashboard_report_is_read_only(self):
        before=self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0]
        report=risk_limits_status(self.c,now=1700000000)
        self.assertEqual(report['daily_buy_count'],0)
        self.assertEqual(report['daily_buy_limit'],6)
        self.assertEqual(report['stop_cooldown_seconds_remaining'],0)
        self.assertFalse(report['new_entries_blocked'])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],before)
    def test_risk_max_six_daily_paper_entries(self):
        from datetime import datetime, timezone
        now=int(datetime.now(timezone.utc).timestamp())
        for index in range(6):
            self.c.execute('''INSERT INTO trades(timestamp,symbol,action,qty,price,fee,pnl,details)
                VALUES(?,?,?,?,?,?,?,?)''',(now-index,'BTC','BUY',.01,100,0,0,'TEST'))
        candles=self.candles()
        result=assess_paper_order(self.c,'BTC',candles,{'buy':True,'atr':1},quote_price=candles[-1]['close'])
        self.assertFalse(result['approved'])
        self.assertIn('6 acquisti',result['reason'])
        before=self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0]
        try_buy(self.c,'BTC',candles,{'buy':True,'atr':1},quote_price=candles[-1]['close'])
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],before)
    def test_risk_stop_loss_cooldown(self):
        from datetime import datetime, timezone
        now=int(datetime.now(timezone.utc).timestamp())
        self.c.execute('''INSERT INTO trades(timestamp,symbol,action,qty,price,fee,pnl,details)
            VALUES(?,?,?,?,?,?,?,?)''',(now-60,'BTC','SELL',.01,100,0,-.10,'Stop loss'))
        candles=self.candles()
        result=assess_paper_order(self.c,'BTC',candles,{'buy':True,'atr':1},quote_price=candles[-1]['close'])
        self.assertFalse(result['approved'])
        self.assertIn('30 minuti',result['reason'])
        self.c.execute('UPDATE trades SET timestamp=? WHERE action="SELL"',(now-1801,))
        result=assess_paper_order(self.c,'BTC',candles,{'buy':True,'atr':1},quote_price=candles[-1]['close'])
        self.assertTrue(result['approved'])
    def test_risk_does_not_count_yesterday_buys(self):
        from datetime import datetime, timezone
        today=datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0)
        yesterday=int(today.timestamp())-1
        for _ in range(6):
            self.c.execute('''INSERT INTO trades(timestamp,symbol,action,qty,price,fee,pnl,details)
                VALUES(?,?,?,?,?,?,?,?)''',(yesterday,'BTC','BUY',.01,100,0,0,'OLD'))
        candles=self.candles()
        result=assess_paper_order(self.c,'BTC',candles,{'buy':True,'atr':1},quote_price=candles[-1]['close'])
        self.assertTrue(result['approved'])
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
        try_buy(self.c,'BTC',cand,ind,quote_price=cand[-1]['close'])
        p=self.c.execute('SELECT * FROM positions').fetchone()
        self.assertIsNotNone(p)
        self.assertGreater(p['entry_fee'],0)
        handle_exit(self.c,'BTC',{'open':p['target']+1,'high':p['target']+2,'low':p['target']+0.1})
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM positions').fetchone()[0],0)
        t=self.c.execute('SELECT * FROM trades WHERE action="SELL"').fetchone()
        self.assertGreater(t['pnl'],0)
    def test_exit_skips_candle_started_before_entry(self):
        candles=self.candles()
        with patch('core.time.time',return_value=1700000500):
            try_buy(self.c,'BTC',candles,{'buy':True,'atr':1,'why':'TEST'},quote_price=candles[-1]['close'])
        p=self.c.execute('SELECT * FROM positions WHERE symbol="BTC"').fetchone()
        self.assertEqual(p['opened_at'],1700000500)
        # The earlier bar touched both levels, but was already underway at entry.
        handle_exit(self.c,'BTC',{'time':1700000400,'open':p['entry'],
            'high':p['target']+3,'low':p['stop']-3})
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM positions').fetchone()[0],1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades WHERE action="SELL"').fetchone()[0],0)
        # Next fully observed bar is eligible; stop wins if both levels touched.
        handle_exit(self.c,'BTC',{'time':1700000500,'open':p['entry'],
            'high':p['target']+3,'low':p['stop']-3})
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM positions').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT details FROM trades WHERE action="SELL"').fetchone()[0],'Stop loss')
    def test_pre_entry_history_cannot_generate_profit(self):
        candles=self.candles()
        with patch('core.time.time',return_value=1700000900):
            try_buy(self.c,'BTC',candles,{'buy':True,'atr':1,'why':'TEST'},quote_price=candles[-1]['close'])
        p=self.c.execute('SELECT * FROM positions').fetchone()
        handle_exit(self.c,'BTC',{'time':1700000600,'open':p['entry'],
            'high':p['target']+10,'low':p['stop']+0.01})
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades WHERE action="SELL"').fetchone()[0],0)
    def test_exit_ambiguous_stop_preserves_cooldown_reason(self):
        candles=self.candles()
        try_buy(self.c,'BTC',candles,{'buy':True,'atr':1,'why':'TEST'},
                quote_price=candles[-1]['close'])
        p=self.c.execute('SELECT * FROM positions').fetchone()
        handle_exit(self.c,'BTC',{'open':p['entry'],
                                  'high':p['target']+1,'low':p['stop']-1})
        trade=self.c.execute('SELECT details FROM trades WHERE action="SELL"').fetchone()
        self.assertEqual(trade['details'],'Stop loss')
        event=self.c.execute('SELECT message FROM events WHERE agent="EXIT" ORDER BY id DESC LIMIT 1').fetchone()
        self.assertIn('stop prioritario',event['message'])
        self.assertGreater(risk_limits_status(self.c)['stop_cooldown_seconds_remaining'],0)
    def test_gap_reconnect_can_close_stop_but_not_open_new_buy(self):
        base=self.candles(80)
        process_candles(self.c,'BTC',base)
        with patch('core.time.time',return_value=base[-1]['time']+301):
            decision=try_buy(self.c,'BTC',base,{'buy':True,'atr':1,'why':'TEST'},
                             quote_price=base[-1]['close'])
            self.assertTrue(decision['approved'])
        pos=self.c.execute('SELECT * FROM positions').fetchone()
        newer=[dict(x) for x in base]
        newer.append({'time':base[-1]['time']+900,'open':pos['stop']-2,
                      'high':pos['stop']+1,'low':pos['stop']-3,
                      'close':pos['stop']-1,'volume':100})
        process_candles(self.c,'BTC',newer)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM positions').fetchone()[0],0)
        trade=self.c.execute('SELECT details,price FROM trades WHERE action="SELL"').fetchone()
        self.assertEqual(trade['details'],'Stop loss')
        self.assertLess(trade['price'],pos['stop'])
    def test_gap_reconnect_does_not_claim_unobserved_target(self):
        base=self.candles(80)
        process_candles(self.c,'BTC',base)
        with patch('core.time.time',return_value=base[-1]['time']+301):
            decision=try_buy(self.c,'BTC',base,{'buy':True,'atr':1,'why':'TEST'},
                             quote_price=base[-1]['close'])
            self.assertTrue(decision['approved'])
        pos=self.c.execute('SELECT * FROM positions').fetchone()
        newer=[dict(x) for x in base]
        newer.append({'time':base[-1]['time']+900,'open':pos['target']+1,
                      'high':pos['target']+3,'low':pos['target']+.5,
                      'close':pos['target']+2,'volume':100})
        process_candles(self.c,'BTC',newer)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM positions').fetchone()[0],1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM trades WHERE action="SELL"').fetchone()[0],0)
    def test_stop_first(self):
        try_buy(self.c,'BTC',self.candles(),{'buy':True,'atr':1,'why':'TEST'},quote_price=self.candles()[-1]['close'])
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
