import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from execution import execution_price, execution_fee, sell_settlement, hypothetical_partial_fill, execution_stress_scenarios


class TestExecution(unittest.TestCase):
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
