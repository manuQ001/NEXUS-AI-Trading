import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from execution import execution_price, execution_fee, sell_settlement


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
