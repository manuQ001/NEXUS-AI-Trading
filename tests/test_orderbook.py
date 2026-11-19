import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from orderbook import parse_depth, walk_book, depth_study, fetch_depth, inspect_book_quality


def sample():
    return {'error':[],'result':{'XXBTZEUR':{
        'asks':[['101','0.1',1700000000],['102','0.2',1700000001]],
        'bids':[['99','0.15',1700000000],['98','0.3',1700000001]]
    }}}


class TestOrderBook(unittest.TestCase):
    def book_with_timing(self, at=1700001000):
        b=parse_depth(sample(),'BTC',received_at=at)
        b['request_duration_ms']=100
        return b
    def test_consistent_book_quality_pass(self):
        first=self.book_with_timing()
        second=self.book_with_timing(at=1700001002)
        q=inspect_book_quality(first,second,now=1700001003,max_spread_bps=250)
        self.assertEqual(q['status'],'PASS')
        self.assertEqual(q['age_seconds'],1)
        self.assertIn('NOT TRADING APPROVAL',q['scope'])
    def test_old_response_is_caution(self):
        b=self.book_with_timing()
        q=inspect_book_quality(b,b,now=1700001010,max_spread_bps=250)
        self.assertEqual(q['status'],'CAUTION')
        self.assertTrue(any('scaduti' in x for x in q['reasons']))
    def test_wide_spread_or_slow_http_is_caution(self):
        a=self.book_with_timing()
        b=self.book_with_timing()
        b['request_duration_ms']=3000
        q=inspect_book_quality(a,b,now=1700001000)
        self.assertEqual(q['status'],'CAUTION')
        self.assertTrue(any('HTTP' in x for x in q['reasons']))
        self.assertTrue(any('spread' in x for x in q['reasons']))
    def test_quote_drift_triggers_caution(self):
        a=self.book_with_timing()
        b=self.book_with_timing()
        b['best_bid']=97
        q=inspect_book_quality(a,b,now=1700001000,max_spread_bps=500)
        self.assertEqual(q['status'],'CAUTION')
        self.assertGreater(q['bid_ask_drift_bps'],25)
    def test_missing_timing_fails_closed(self):
        a=self.book_with_timing()
        b=self.book_with_timing()
        del b['request_duration_ms']
        with self.assertRaises(ValueError):
            inspect_book_quality(a,b,now=1700001000)
    def test_depth_spread_midpoint(self):
        book=parse_depth(sample(),'BTC',received_at=1700001000)
        self.assertEqual(book['best_ask'],101)
        self.assertEqual(book['best_bid'],99)
        self.assertEqual(book['midpoint'],100)
        self.assertAlmostEqual(book['spread_bps'],200)
        self.assertEqual(book['observed_at'],1700001000)
    def test_buy_depth_walk_and_partial(self):
        book=parse_depth(sample(),'BTC')
        order=walk_book(book,'BUY',.15)
        self.assertEqual(order['status'],'INDICATIVE_FULL')
        self.assertAlmostEqual(order['vwap'],(101*.1+102*.05)/.15)
        self.assertAlmostEqual(order['estimated_fee_eur'],order['gross_eur']*.0025)
        large=walk_book(book,'BUY',1)
        self.assertEqual(large['status'],'INDICATIVE_PARTIAL')
        self.assertAlmostEqual(large['filled_qty'],.3)
        self.assertAlmostEqual(large['unfilled_qty'],.7)
    def test_sell_consumes_bids(self):
        book=parse_depth(sample(),'BTC')
        result=walk_book(book,'SELL',.2)
        self.assertAlmostEqual(result['vwap'],(99*.15+98*.05)/.2)
    def test_study_read_only(self):
        book=parse_depth(sample(),'BTC')
        before=repr(book)
        study=depth_study(book,25)
        self.assertEqual(study['mode'],'READ ONLY - LIVE BOOK SNAPSHOT')
        self.assertIn('Nessun ordine',study['warning'])
        self.assertEqual(repr(book),before)
    def test_reject_crossed_book(self):
        obj=sample();obj['result']['XXBTZEUR']['bids'][0][0]='101'
        with self.assertRaises(ValueError):parse_depth(obj,'BTC')
    def test_reject_unsorted_levels(self):
        obj=sample();obj['result']['XXBTZEUR']['asks'].reverse()
        with self.assertRaises(ValueError):parse_depth(obj,'BTC')
    def test_reject_nan_and_bad_levels(self):
        for bad in ('nan','0','-1','inf'):
            obj=sample();obj['result']['XXBTZEUR']['asks'][0][1]=bad
            with self.assertRaises(ValueError):parse_depth(obj,'BTC')
        obj=sample();obj['result']['XXBTZEUR']['asks']=[]
        with self.assertRaises(ValueError):parse_depth(obj,'BTC')
    def test_invalid_symbol_never_requests_network(self):
        with patch('orderbook.urlopen') as http:
            with self.assertRaises(ValueError):fetch_depth('MEME')
            http.assert_not_called()
    def test_partial_book_does_not_invent_full_fill(self):
        book=parse_depth(sample(),'BTC')
        study=depth_study(book,1000)
        self.assertEqual(study['buy']['status'],'INDICATIVE_PARTIAL')
        self.assertLess(study['buy']['filled_pct'],100)


if __name__=='__main__':
    unittest.main()
