"""V4 autonomous deterministic PAPER experiment: separate ledgers and hard limits."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from meme_auto import init_auto
from meme_prices import observe
from meme_portfolio import portfolio
from v4_agents import (initialize,tick,report,agents_decide,MAX_POSITIONS,
                       MAX_ALLOCATION,INITIAL_EUR)
A='So11111111111111111111111111111111111111112'
B='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
C='3fWhdo8bQCamw5ed6yNGdvaru1qS5UVwB6dYp9znpump'
D='C2As2w55q3V3snKVCyA3nZvmQJSx2NApM5SLK5krpump'

def quote(a,p,liq=30000,vol=80000):
    return {'address':a,'symbol':'PAPER','price_usd':p,
            'liquidity_usd':liq,'volume_24h_usd':vol}

class TestV4Paper(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.tmp.name)/'v4.sqlite')
        init_auto(self.c)
        initialize(self.c)
    def tearDown(self):
        self.c.close();self.tmp.cleanup()
    def seed(self,a,at=1000,liq=30000,vol=80000):
        for t,p in [(at-20,.0100),(at-10,.0105),(at,.0108)]:
            observe(self.c,a,quote(a,p,liq,vol),now=t)
    def test_v4_initial_wallet_is_isolated_from_legacy_wallet_and_risk(self):
        self.c.execute("UPDATE wallets SET cash=37 WHERE strategy='meme'")
        self.c.execute("UPDATE meme_auto_state SET risk_latched=1 WHERE id=1")
        self.seed(A)
        status=tick(self.c,now=1000)
        self.assertEqual(status['status'],'BUY_PAPER')
        d=report(self.c,now=1000)
        self.assertEqual(d['mode'],'ISOLATED_MULTIAGENT_PAPER')
        self.assertEqual(d['initial_eur'],INITIAL_EUR)
        self.assertEqual(len(d['positions']),1)
        self.assertEqual(d['positions'][0]['stake_eur'],INITIAL_EUR*MAX_ALLOCATION)
        self.assertEqual(d['cash_eur'],INITIAL_EUR-INITIAL_EUR*MAX_ALLOCATION)
        self.assertFalse(d['real_trades_enabled'])
        self.assertFalse(d['security_verified'])
        self.assertEqual(portfolio(self.c)['cash_eur'],37)
        self.assertEqual(self.c.execute('SELECT risk_latched FROM meme_auto_state WHERE id=1').fetchone()[0],1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],0)
    def test_no_entry_on_low_liquidity_or_missing_momentum(self):
        self.seed(A,liq=100)
        self.seed(B,vol=100)
        result=tick(self.c,now=1000)
        self.assertEqual(result['new_trades'],0)
        self.assertEqual(report(self.c)['trade_count'],0)
    def test_buy_and_auto_sell_are_modeled_with_both_3pct_costs(self):
        self.seed(A)
        tick(self.c,now=1000)
        observe(self.c,A,quote(A,.0138),now=1010)
        tick(self.c,now=1010)
        d=report(self.c,now=1011)
        self.assertEqual(d['closed_count'],1)
        self.assertEqual(d['positions'],[])
        self.assertEqual(d['trades'][0]['side'],'SELL_PAPER')
        self.assertEqual(d['trades'][0]['reason'],'TAKE_PROFIT_NET_12')
        self.assertGreater(d['trades'][0]['pnl_eur'],0)
        self.assertEqual(portfolio(self.c)['cash_eur'],45)
    def test_stale_quotes_cannot_force_sale_or_fake_price(self):
        self.seed(A)
        tick(self.c,now=1000)
        old=report(self.c,now=2000)
        tick(self.c,now=2000)
        current=report(self.c,now=2000)
        self.assertEqual(len(current['positions']),1)
        self.assertTrue(current['positions'][0]['stale_quote'])
        self.assertEqual(current['closed_count'],0)
        self.assertEqual(current['positions'][0]['last_price_usd'],
                         old['positions'][0]['last_price_usd'])
    def test_max_three_positions_and_only_5pct_virtual_capital(self):
        for a in [A,B,C,D]:self.seed(a)
        for now in [1000,1001,1002,1003,1004]:
            tick(self.c,now=now)
        d=report(self.c,now=1005)
        self.assertEqual(len(d['positions']),MAX_POSITIONS)
        self.assertEqual(d['trade_count'],MAX_POSITIONS)
        self.assertTrue(all(x['stake_eur']<=25 for x in d['positions']))
        self.assertGreaterEqual(d['cash_eur'],425)
    def test_equity_drawdown_latches_independently_and_survives_restarts(self):
        self.seed(A)
        tick(self.c,now=1000)
        self.c.execute("""UPDATE v4_paper_state SET cash_eur=420,
            peak_equity_eur=500 WHERE id=1""")
        tick(self.c,now=1001)
        self.assertTrue(report(self.c)['risk_latched'])
        self.c.commit()
        tick(self.c,now=1002)
        self.assertTrue(report(self.c)['risk_latched'])
        self.assertEqual(self.c.execute('SELECT risk_latched FROM meme_auto_state WHERE id=1').fetchone()[0],0)
    def test_agent_verdicts_are_explicit_rules_not_llm(self):
        row=quote(A,.0108)
        history=[{'price_usd':p} for p in (.010,.0105,.0108)]
        action,reason,agents=agents_decide(row,history)
        self.assertEqual(action,'BUY')
        self.assertEqual(agents['strategy'],'PAPER_ENTRY_CANDIDATE')
        self.assertIn('NOT_SECURITY_VERIFIED',agents['risk'])
        action,_,agents=agents_decide(quote(A,.0108,liq=100),history)
        self.assertEqual(action,'WAIT')
        self.assertEqual(agents['risk'],'LOW_LIQUIDITY_OR_VOLUME')
    def test_dashboard_v4_panel_is_read_only(self):
        html=(Path(__file__).resolve().parents[1]/'src'/'dashboard.html').read_text('utf-8')
        for term in ['nx-v4-panel','nx-v4-equity','nx-v4-drawdown',
                     'nx-v4-positions','nx-v4-trades','data-nx-focus="v4"',
                     "fetch('/api/v4-agents'"]:
            self.assertIn(term,html)
        self.assertNotIn("fetch('/api/v4-agents',{method:'POST'",html)
if __name__=='__main__':unittest.main()
