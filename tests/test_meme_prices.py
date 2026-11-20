"""NEXUS 3.8: real observed REST quote samples, SSE journal and risk invariants."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from meme_auto import init_auto,tick
from meme_desk import record_scan
from meme_prices import observe,changes_after,snapshot,refresh_watchlist,observed_candles
from meme_portfolio import portfolio
from server import publish_paper_event,events_after

A='So11111111111111111111111111111111111111112'
B='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
Q={'address':A,'symbol':'TEST','price_usd':.01,
   'liquidity_usd':20000,'volume_24h_usd':50000,'pool_age_hours':1.0}
FX={'usd_eur':.9,'rate_date':'2026-11-20'}

class TestMarketPulse(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.temp.name)/'market.sqlite3')
        init_auto(self.c)
    def tearDown(self):
        self.c.close();self.temp.cleanup()
    def test_only_real_price_changes_are_events(self):
        first=observe(self.c,A,Q,now=100)
        self.assertGreater(first,0)
        self.assertIsNone(observe(self.c,A,Q,now=110))
        newer=observe(self.c,A,dict(Q,price_usd=.011),now=120)
        self.assertGreater(newer,first)
        self.assertIsNone(observe(self.c,A,dict(Q,price_usd=.008),now=119))
        observed=changes_after(self.c,first)
        self.assertEqual(len(observed),1)
        self.assertEqual(observed[0]['price_usd'],.011)
        state=snapshot(self.c,now=125)
        self.assertEqual(state['sample_count'],2)
        self.assertEqual(len(state['quotes'][0]['observations']),2)
        self.assertEqual(state['quotes'][0]['age_seconds'],5)
        self.assertTrue(state['quotes'][0]['fresh'])
        self.assertFalse(snapshot(self.c,now=200)['quotes'][0]['fresh'])
        self.assertEqual(portfolio(self.c)['cash_eur'],45)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],0)
    def test_watched_token_refresh_every_ten_seconds_without_positions(self):
        self.c.execute("UPDATE wallets SET cash=37 WHERE strategy='meme'")
        self.c.commit()
        with patch('meme_auto.review_meme_agents',side_effect=AssertionError('paid API')):
            tick(self.c,now=2000,scout=lambda:{'candidates':[dict(Q)]},
                 quote=lambda _:Q,fx_rate=lambda c,now=None:FX)
        calls=[]
        def quote(address):
            calls.append(address)
            return dict(Q,price_usd=.011 if len(calls)==1 else .012)
        first=refresh_watchlist(self.c,now=2001,quote=quote)
        early=refresh_watchlist(self.c,now=2005,quote=quote)
        later=refresh_watchlist(self.c,now=2011,quote=quote)
        self.assertEqual([first['checked'],early['checked'],later['checked']],[1,0,1])
        self.assertEqual(len(calls),2)
        latest=snapshot(self.c,now=2011)
        self.assertEqual(latest['quotes'][0]['price_usd'],.012)
        self.assertEqual(latest['quotes'][0]['age_seconds'],0)
        self.assertEqual(len(latest['quotes'][0]['observations']),3)
        self.assertTrue(latest['risk']['latched'])
        self.assertEqual(portfolio(self.c)['cash_eur'],37)
        self.assertEqual(len(portfolio(self.c)['positions']),0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],0)
    def test_monitor_rejects_paid_fake_and_failed_quotes_without_crash(self):
        observe(self.c,A,Q,now=100)
        observation_count=snapshot(self.c,now=100)['sample_count']
        bad=refresh_watchlist(self.c,now=101,quote=lambda _:dict(Q,price_usd='NaN'))
        self.assertEqual(bad['checked'],0)
        self.assertEqual(bad['errors'],1)
        self.assertEqual(snapshot(self.c,now=101)['sample_count'],observation_count)
        self.assertEqual(snapshot(self.c,now=101)['monitor']['last_error'],'ValueError')
    def test_monitor_respects_user_auto_suspension(self):
        observe(self.c,A,Q,now=100)
        self.c.execute("UPDATE meme_auto_state SET enabled=0 WHERE id=1")
        calls=[]
        stopped=refresh_watchlist(self.c,now=101,quote=lambda _:calls.append('called'))
        self.assertEqual(stopped['status'],'AUTO_SUSPENDED')
        self.assertEqual(calls,[])
    def test_watchlist_stops_polling_expired_or_illiquid_profiles(self):
        observe(self.c,A,dict(Q,liquidity_usd=100),now=100)
        calls=[]
        self.assertEqual(refresh_watchlist(self.c,now=101,quote=lambda a:calls.append(a))['checked'],0)
        self.assertEqual(calls,[])
        self.c.execute("UPDATE meme_quote_monitor SET last_attempt=0 WHERE id=1")
        observe(self.c,A,Q,now=120)
        self.assertEqual(refresh_watchlist(self.c,now=900,quote=lambda a:calls.append(a))['checked'],0)
        self.assertEqual(calls,[])
    def test_invalid_source_address_quote_never_yields_sample(self):
        self.assertIsNone(observe(self.c,'invalid',Q,now=100))
        self.assertIsNone(observe(self.c,A,dict(Q,price_usd=0),now=100))
        self.assertIsNone(observe(self.c,A,dict(Q,price_usd='NaN'),now=100))
        self.assertIsNone(observe(self.c,A,Q,now=100,source='UNVERIFIED_TRADE'))
        self.assertEqual(snapshot(self.c)['sample_count'],0)
    def test_real_scanner_quote_updates_even_with_risk_lock(self):
        self.c.execute("UPDATE wallets SET cash=37 WHERE strategy='meme'")
        self.c.commit()
        with patch('meme_auto.review_meme_agents',side_effect=AssertionError('paid API')):
            tick(self.c,now=2000,scout=lambda:{'candidates':[dict(Q)]},
                 quote=lambda _:Q,fx_rate=lambda c,now=None:FX)
            tick(self.c,now=2061,scout=lambda:{'candidates':[dict(Q,price_usd=.0105)]},
                 quote=lambda _:Q,fx_rate=lambda c,now=None:FX)
        pulse=snapshot(self.c,now=2062)
        self.assertTrue(pulse['risk']['blocked'])
        self.assertTrue(pulse['risk']['latched'])
        self.assertEqual(len(pulse['quotes']),1)
        self.assertEqual(len(pulse['quotes'][0]['observations']),2)
        self.assertEqual(len(portfolio(self.c)['positions']),0)
    def test_candles_use_actual_reads_including_identical_quotes_only(self):
        # Reads 01:00/01:20 and 02:00/02:30. The missing minute 03
        # stays absent; no interpolated bar is allowed.
        for t,price in [(60,.010),(80,.010),(120,.011),(150,.009),(240,.012)]:
            observe(self.c,A,dict(Q,price_usd=price),now=t)
        d=observed_candles(self.c,A,interval_seconds=60,now=245)
        self.assertEqual(d['mode'],'REST_SAMPLED_OHLC')
        self.assertEqual([x['time'] for x in d['candles']],[60,120,240])
        self.assertEqual(d['candles'][0]['observations'],2)
        self.assertEqual(d['candles'][0]['open'],.01)
        self.assertEqual(d['candles'][0]['close'],.01)
        self.assertEqual(d['candles'][1]['open'],.011)
        self.assertEqual(d['candles'][1]['high'],.011)
        self.assertEqual(d['candles'][1]['low'],.009)
        self.assertEqual(d['candles'][1]['close'],.009)
        self.assertEqual(d['candles'][2]['close'],.012)
        self.assertNotIn('volume',d['candles'][2])
        self.assertEqual(len(portfolio(self.c)['positions']),0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],0)
    def test_candle_timeframe_and_no_fake_data(self):
        self.assertEqual(observed_candles(self.c,A,now=100)['candles'],[])
        with self.assertRaises(ValueError):observed_candles(self.c,A,interval_seconds=10)
        with self.assertRaises(ValueError):observed_candles(self.c,'BAD')
        observe(self.c,A,Q,now=60)
        observe(self.c,A,dict(Q,price_usd=.02),now=360)
        d=observed_candles(self.c,A,interval_seconds=300,now=400)
        self.assertEqual([x['time'] for x in d['candles']],[0,300])
        self.assertFalse(d['fresh'])
        # Future observations are never backfilled into earlier reports.
        d=observed_candles(self.c,A,interval_seconds=60,now=80)
        self.assertEqual([x['time'] for x in d['candles']],[60])
    def test_candle_rejects_invalid_quotes_and_stale_delayed_reads(self):
        observe(self.c,A,Q,now=500)
        observe(self.c,A,dict(Q,price_usd=float('nan')),now=600)
        observe(self.c,A,dict(Q,price_usd=.2),now=499)
        d=observed_candles(self.c,A,now=600)
        self.assertEqual(len(d['candles']),1)
        self.assertEqual(d['candles'][0]['observations'],1)
        self.assertAlmostEqual(d['candles'][0]['close'],.01)
    def test_chart_ui_displays_observation_caveat_and_selection(self):
        source=(Path(__file__).resolve().parents[1]/'src'/'dashboard.html').read_text('utf-8')
        for anchor in ('nx-candle-chart','nx-candle-token','nx-candle-timeframe',
                       'nx-candle-status','function nxDrawObservedCandles',
                       "fetch('/api/meme-market-candles?address='"):
            self.assertIn(anchor,source)
        self.assertIn('nessun prezzo o intervallo inventato',source)
        self.assertIn('prefers-reduced-motion',source)

    def test_cost_model_reports_gross_vs_net_friction(self):
        cost=snapshot(self.c)['cost_model']
        self.assertAlmostEqual(cost['minimum_gross_move_to_break_even_pct'],6.186,places=2)
        self.assertGreater(cost['gross_move_for_net_target_12_pct'],18)
        self.assertLess(cost['estimated_net_at_gross_stop_minus5_pct'],-10)
    def test_sse_quote_notification_is_based_on_record(self):
        obs=observe(self.c,A,Q,now=100)
        self.assertEqual(changes_after(self.c,obs-1)[0]['id'],obs)
        msg=publish_paper_event('PAPER_QUOTES',{
            'count':1,'last_change_id':obs,'source':'DEX_SCREENER_REST_SERVER_OBSERVATIONS'},
            timestamp=101)
        self.assertEqual(events_after(msg['id']-1)[-1]['kind'],'PAPER_QUOTES')
    def test_market_ui_is_labeled_source_and_reduced_motion(self):
        source=(Path(__file__).resolve().parents[1]/'src'/'dashboard.html').read_text('utf-8')
        self.assertIn('id="nx-market-pulse"',source)
        self.assertIn("fetch('/api/meme-market-pulse'",source)
        self.assertIn('Quote DEX Screener REST',source)
        self.assertIn('prefers-reduced-motion',source)
        self.assertNotIn('Math.random()',source)

if __name__=='__main__':unittest.main()
