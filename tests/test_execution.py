import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from execution import execution_price, execution_fee, sell_settlement, hypothetical_partial_fill, execution_stress_scenarios, sniper_book_preview, assess_exit_bar, assess_exit_ticks


class TestExecution(unittest.TestCase):
    def test_exit_ohlc_prefers_stop_when_both_touched(self):
        d=assess_exit_bar({'open':100,'high':111,'low':94},stop=95,target=110)
        self.assertEqual(d['reason'],'Stop loss')
        self.assertEqual(d['reference'],95)
        self.assertTrue(d['ambiguous_both_touched'])
    def test_exit_gap_down_uses_worse_open(self):
        d=assess_exit_bar({'open':90,'high':97,'low':89},stop=95,target=110)
        self.assertEqual(d['reference'],90)
        self.assertTrue(d['gap_through_stop'])
    def test_exit_target_capped_even_after_gap_up(self):
        d=assess_exit_bar({'open':120,'high':122,'low':115},stop=95,target=110)
        self.assertEqual(d['reason'],'Take profit')
        self.assertEqual(d['reference'],110)
    def test_exit_suppress_target_only_on_gap(self):
        d=assess_exit_bar({'open':101,'high':115,'low':98},stop=95,target=110,allow_target=False)
        self.assertIsNone(d['reference'])
        self.assertTrue(d['target_suppressed'])
        bad=assess_exit_bar({'open':90,'high':114,'low':88},stop=95,target=110,allow_target=False)
        self.assertEqual(bad['reason'],'Stop loss')
    def test_exit_validate_incoherent_candle(self):
        for c in ({'open':100,'high':90,'low':99},
                  {'open':100,'high':110,'low':float('nan')},
                  {'open':100,'high':110,'low':101}):
            with self.assertRaises(ValueError):
                assess_exit_bar(c,95,110)
    def test_tick_replay_ignores_pre_entry_hits(self):
        ticks=[(1000,130),(1001,100),(1002,94),(1003,120)]
        d=assess_exit_ticks(ticks,1001,95,110)
        self.assertEqual(d['reason'],'Stop loss')
        self.assertEqual(d['observed_at'],1002)
        self.assertEqual(d['evidence'],'TRADE_PRINT_ONLY_NOT_EXECUTABLE')
    def test_tick_replay_first_hit_is_target(self):
        ticks=[(1000,120),(1001,110),(1002,91)]
        d=assess_exit_ticks(ticks,1001,95,110)
        self.assertEqual(d['reason'],'Take profit')
        self.assertEqual(d['observed_at'],1001)
    def test_tick_replay_rejects_unsorted_data(self):
        with self.assertRaises(ValueError):
            assess_exit_ticks([(1001,100),(1000,95)],999,95,110)
        self.assertIsNone(assess_exit_ticks([(1000,96)],1001,95,110)['reason'])
    def sample_book(self):
        return {'symbol':'BTC','observed_at':1700000000,'best_ask':101.0,'best_bid':99.0,
                'asks':[{'price':101.0,'volume':1.0},{'price':102.0,'volume':2.0}]}
    def test_sniper_full_study_no_live_orders(self):
        b=self.sample_book()
        report=sniper_book_preview(b,order_eur=25,participation_rate=.5)
        self.assertEqual(report['status'],'ESTIMATE_FULL')
        self.assertTrue(report['budget_ok'])
        self.assertLessEqual(report['estimated_total_eur'],25.00000001)
        self.assertEqual(report['mode'],'READ ONLY / MIXED OBSERVED DEPTH + HYPOTHETICAL COSTS')
        self.assertIn('Nessun fill garantito',report['warning'])
    def test_sniper_partial_fill_does_not_invent_depth(self):
        b=self.sample_book()
        b['asks']=[{'price':101.,'volume':0.001}]
        report=sniper_book_preview(b,order_eur=25,participation_rate=.1)
        self.assertEqual(report['status'],'ESTIMATE_PARTIAL')
        self.assertLess(report['estimated_fill_pct'],100)
        self.assertAlmostEqual(report['estimated_filled_qty']+report['estimated_unfilled_qty'],report['requested_qty'])
    def test_sniper_higher_asks_can_exceed_budget(self):
        b=self.sample_book()
        b['asks']=[{'price':101.,'volume':0.0001},{'price':150.,'volume':10.}]
        report=sniper_book_preview(b,order_eur=25,participation_rate=.5)
        self.assertEqual(report['status'],'OVER_BUDGET')
        self.assertFalse(report['budget_ok'])
    def test_sniper_rejects_bad_depth_and_params(self):
        b=self.sample_book()
        for kwargs in ({'participation_rate':0},{'slippage_bps':float('nan')},
                       {'delay_impact_bps':10000},{'fee_rate':1},{'order_eur':0}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    sniper_book_preview(b,**kwargs)
        b['asks'][1]['price']=100
        with self.assertRaises(ValueError):sniper_book_preview(b)
    def test_sniper_no_mutation(self):
        b=self.sample_book()
        original=repr(b)
        sniper_book_preview(b)
        self.assertEqual(repr(b),original)
    def test_buy_price_is_adverse(self):
        self.assertAlmostEqual(execution_price('BUY',100,.0005),100.05)
    def test_sell_price_is_adverse(self):
        self.assertAlmostEqual(execution_price('SELL',100,.0005),99.95)
    def test_fee_is_based_on_notional(self):
        self.assertAlmostEqual(execution_fee(2,100,.0025),.5)
    def test_round_trip_same_reference_loses_costs(self):
        buy=execution_price('BUY',100,.0005)
        fee=execution_fee(1,buy,.0025)
        result=sell_settlement(1,buy,fee,100,fee_rate=.0025,slippage_rate=.0005)
        self.assertLess(result['pnl'],0)
        self.assertAlmostEqual(result['net_proceeds']-buy-fee,result['pnl'])
    def test_settlement_uses_sell_side(self):
        result=sell_settlement(2,100,.5,110,fee_rate=.0025,slippage_rate=.0005)
        self.assertAlmostEqual(result['price'],109.945)
        self.assertAlmostEqual(result['exit_fee'],2*109.945*.0025)
        self.assertAlmostEqual(result['pnl'],result['net_proceeds']-200.5)
    def test_hypothetical_no_liquidity_means_no_fill(self):
        f=hypothetical_partial_fill('BUY',2,100,0)
        self.assertEqual(f['status'],'NO_FILL')
        self.assertEqual(f['filled_qty'],0)
        self.assertEqual(f['unfilled_qty'],2)
        self.assertIsNone(f['price'])
    def test_hypothetical_partial_fill_and_conservation(self):
        f=hypothetical_partial_fill('BUY',10,100,20,participation_rate=.1,
                                     spread_bps=10,slippage_bps=5,latency_bps=5)
        self.assertEqual(f['status'],'PARTIAL')
        self.assertAlmostEqual(f['filled_qty'],2)
        self.assertAlmostEqual(f['unfilled_qty'],8)
        self.assertAlmostEqual(f['filled_qty']+f['unfilled_qty'],10)
        self.assertAlmostEqual(f['price'],100.15)
        self.assertAlmostEqual(f['fee'],f['gross']*.0025)
    def test_hypothetical_sell_side_adverse(self):
        f=hypothetical_partial_fill('SELL',1,100,100,spread_bps=10,
                                    slippage_bps=5,latency_bps=5)
        self.assertEqual(f['status'],'FILLED')
        self.assertAlmostEqual(f['price'],99.85)
    def test_hypothetical_scarcity_cannot_improve_fill(self):
        a=hypothetical_partial_fill('BUY',1,100,1)
        b=hypothetical_partial_fill('BUY',1,100,10)
        self.assertLessEqual(a['filled_qty'],b['filled_qty'])
    def test_hypothetical_invalid_assumptions_fail_closed(self):
        for kw in ({'available_quantity':-1}, {'spread_bps':float('nan')},
                   {'latency_bps':10000}, {'participation_rate':1},
                   {'available_quantity':float('inf')}):
            kwargs={'side':'BUY','requested_quantity':1,'midpoint':100,'available_quantity':10}
            kwargs.update(kw)
            with self.assertRaises(ValueError):
                hypothetical_partial_fill(**kwargs)
    def test_hypothetical_scenario_report_has_no_execution(self):
        r=execution_stress_scenarios(100,25)
        self.assertEqual(len(r['scenarios']),3)
        self.assertEqual(r['mode'],'HYPOTHETICAL STUDY - NO ORDERS')
        self.assertIn('NON misure',r['warning'])
        fills=[x['fill_percentage'] for x in r['scenarios']]
        self.assertEqual(fills[0],100)
        self.assertGreater(fills[1],fills[2])
    def test_stress_report_rejects_invalid_reference(self):
        with self.assertRaises(ValueError): execution_stress_scenarios(float('nan'))
        with self.assertRaises(ValueError): execution_stress_scenarios(100,-25)
    def test_rejects_invalid_rates_and_prices(self):
        for bad in (0,-1,float('nan'),float('inf')):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    execution_price('BUY',bad,.0005)
        for bad_rate in (-.01,1,float('nan'),float('inf')):
            with self.subTest(rate=bad_rate):
                with self.assertRaises(ValueError):
                    execution_price('BUY',100,bad_rate)
        with self.assertRaises(ValueError):
            execution_price('HOLD',100,.001)
        with self.assertRaises(ValueError):
            execution_fee(0,100,.002)
        with self.assertRaises(ValueError):
            sell_settlement(1,100,-.2,110,fee_rate=.0025,slippage_rate=.0005)


if __name__=='__main__':
    unittest.main()
