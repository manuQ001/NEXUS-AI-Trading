"""Quick MEME HTTP integration: real endpoint behavior with no external network."""
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import server
from core import connect as db_connect

M='So11111111111111111111111111111111111111112'
H={'X-NEXUS-Demo-Click':'1','Origin':'http://127.0.0.1:8765',
   'Sec-Fetch-Site':'same-origin','Content-Length':'0'}

def handler(path,headers=None):
    h=object.__new__(server.Handler)
    h.path=path
    h.headers={} if headers is None else headers
    h.out=Mock()
    return h

class TestMemeQuickHttp(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=Path(self.temp.name)/'demo.sqlite3'
        server.MEME_SCOUT_QUOTES.clear()
    def tearDown(self):
        server.MEME_SCOUT_QUOTES.clear()
        self.temp.cleanup()
    def test_sse_notifications_are_actual_and_resumable(self):
        before=server.EVENT_SERIAL
        item=server.publish_paper_event('PAPER_TICK',
             {'last_tick':1234,'status':'MONITORAGGIO'},timestamp=1234)
        self.assertGreater(item['id'],before)
        pending=server.events_after(before)
        self.assertTrue(any(x['id']==item['id'] and x['time']==1234
                            and x['kind']=='PAPER_TICK' for x in pending))
        self.assertFalse(server.events_after(item['id']))
        with self.assertRaises(ValueError):
            server.publish_paper_event('FAKE_BUY',{},timestamp=1234)

    def test_scan_then_quick_buy_uses_recent_server_quote_when_pair_refresh_fails(self):
        report={'ok':True,'candidates':[{'address':M,'price_usd':.02,
            'liquidity_usd':None,'volume_24h_usd':0,'symbol':'MEME'}]}
        h=handler('/api/meme-scout')
        with patch('meme_scout.scan',return_value=report):
            h.do_GET()
        self.assertEqual(h.out.call_args.args[0]['candidates'][0]['address'],M)
        self.assertIn(M,server.MEME_SCOUT_QUOTES)
        h=handler('/api/meme-demo-trade?action=BUY&address='+M,H)
        with patch('server.connect',side_effect=lambda: db_connect(self.db)),\
             patch('meme_portfolio.indicative_quote',side_effect=ValueError('No second quote')),\
             patch('meme_portfolio.get_fx',return_value={'usd_eur':0.9,'rate_date':'2026-11-19'}):
            h.do_POST()
        result=h.out.call_args.args[0]
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['trade']['quote_source'].split(':')[0],'MEME SCOUT')
        self.assertEqual(result['account']['cash_eur'],42)
        self.assertEqual(len(result['account']['positions']),1)
        c=db_connect(self.db)
        try:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM trades').fetchone()[0],0)
        finally:c.close()
    def test_stale_quote_never_creates_position(self):
        server.MEME_SCOUT_QUOTES[M]={
            'quote':{'price_usd':.02,'symbol':'MEME'},
            'observed_at':time.time()-server.MEME_SCOUT_TTL_SECONDS-10}
        h=handler('/api/meme-demo-trade?action=BUY&address='+M,H)
        with patch('meme_portfolio.indicative_quote',side_effect=ValueError('not found')):
            h.do_POST()
        self.assertEqual(h.out.call_args.args[1],400)
        self.assertIn('Analizza Solana',h.out.call_args.args[0]['error'])
    def test_cross_origin_refused_without_quote_call(self):
        h=handler('/api/meme-demo-trade?action=BUY&address='+M,
            dict(H,Origin='https://evil.example'))
        with patch('meme_portfolio.indicative_quote') as quote:
            h.do_POST()
        quote.assert_not_called()
        self.assertEqual(h.out.call_args.args[1],403)
if __name__=='__main__':unittest.main()
