"""Offline safety tests for true provider mint events and live terminal bindings."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from meme_mints import MintFeed,listen
from meme_live import _connect
from server import publish_paper_event,events_after
A='So11111111111111111111111111111111111111112'
B='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'

class TestMintStream(unittest.TestCase):
    def test_creation_only_bounded_and_deduplicated(self):
        feed=MintFeed()
        self.assertIsNone(feed.ingest({'mint':A,'txType':'buy'},now=100))
        self.assertIsNone(feed.ingest({'mint':'not a mint','txType':'create'},now=100))
        self.assertIsNone(feed.ingest({'error':'provider-notice'},now=100))
        item=feed.ingest({'mint':A,'txType':'create','symbol':'S'*900},now=101)
        self.assertEqual(item['mint'],A)
        self.assertEqual(len(item['symbol']),48)
        self.assertFalse(item['trade_authorized'])
        self.assertFalse(item['verified_on_chain'])
        self.assertEqual(item['time'],101)
        self.assertIsNone(feed.ingest({'mint':A,'txType':'create'},now=102))
        self.assertEqual(feed.state()['mints'],1)
        self.assertEqual(feed.state()['recent'][0]['mint'],A)
        self.assertEqual(len(feed.state()['recent']),1)
    def test_only_actual_mint_event_can_publish_sse(self):
        packet=publish_paper_event('PAPER_MINT',{'mint':B,'source':'test'},timestamp=123)
        found=events_after(packet['id']-1)
        self.assertEqual(found[-1]['data']['mint'],B)
        self.assertEqual(found[-1]['kind'],'PAPER_MINT')
        self.assertEqual(found[-1]['time'],123)
    def test_only_fixed_tls_hosts_allowed(self):
        # The function rejects untrusted endpoints before attempting sockets.
        with self.assertRaises(ValueError):
            _connect(target='ws://pumpportal.fun/api/data')
        with self.assertRaises(ValueError):
            _connect(target='wss://evil.example/api/data')
        with self.assertRaises(ValueError):
            _connect(target='wss://pumpportal.fun:444/api/data')
    def test_no_real_trade_code_in_mint_listener(self):
        source=(Path(__file__).resolve().parents[1]/'src'/'meme_mints.py').read_text(encoding='utf-8')
        self.assertIn("'subscribeNewToken'",source)
        for term in ("'subscribeTokenTrade'","'subscribeAccountTrade'",
                     "'trade-local'","'buy'","'sell'"):
            self.assertNotIn(term,source)
    def test_live_dashboard_has_no_synthetic_market_randomizer(self):
        html=(Path(__file__).resolve().parents[1]/'src'/'dashboard.html').read_text(encoding='utf-8')
        self.assertIn('id="nx-live-console"',html)
        self.assertIn("fetch('/api/meme-mints'",html)
        self.assertIn("packet.kind",html)
        self.assertIn('prefers-reduced-motion',html)
        self.assertNotIn('Math.random()',html)

if __name__=='__main__':unittest.main()
