"""AI HTTP endpoint requires an intentional same-origin POST, not a GET."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import server


def handler(path='/api/ai-review?symbol=BTC',headers=None):
    h=object.__new__(server.Handler)
    h.path=path
    h.headers=headers if headers is not None else {}
    h.out=Mock()
    return h


class TestAiHttp(unittest.TestCase):
    def test_plain_get_refused_without_model_call(self):
        h=handler()
        with patch('server.external_ai_advice') as ai:
            h.do_GET()
        ai.assert_not_called()
        self.assertEqual(h.out.call_args.args[1],405)
    def test_plain_post_without_click_header_refused(self):
        h=handler()
        with patch('server.external_ai_advice') as ai:
            h.do_POST()
        ai.assert_not_called()
        self.assertEqual(h.out.call_args.args[1],403)
    def test_cross_site_origin_refused(self):
        h=handler(headers={'X-NEXUS-Research-Click':'1',
                           'Origin':'https://other.example',
                           'Sec-Fetch-Site':'cross-site'})
        with patch('server.external_ai_advice') as ai:
            h.do_POST()
        ai.assert_not_called()
        self.assertEqual(h.out.call_args.args[1],403)
    def test_same_origin_click_is_only_consult_and_record(self):
        h=handler(headers={'X-NEXUS-Research-Click':'1',
                           'Origin':'http://127.0.0.1:8765',
                           'Sec-Fetch-Site':'same-origin'})
        database=MagicMock()
        data={'candles':{'BTC':[{'time':1800000000,'close':100.}]},
              'indicators':{'BTC':{}},'positions':[],
              'status':{'BTC':'OK'},'wallets':[{'strategy':'core','cash':105.}]}
        advice={'available':True,'status':'advisory_only','model':'sample',
                'analysis':{'summary':'attesa'}}
        with patch('server.connect',return_value=database), \
             patch('server.snapshot',return_value=data), \
             patch('server.daily_loss',return_value=0), \
             patch('server.review',return_value={'symbol':'BTC','time':1800000000}) as review, \
             patch('server.local_ai_advice',return_value=advice) as ai, \
             patch('server.record_ai_research',return_value={'saved':True,'reason':'SAVED'}) as record, \
             patch.dict('os.environ',{},clear=True):
            h.do_POST()
        review.assert_called_once()
        ai.assert_called_once()
        record.assert_called_once()
        self.assertEqual(record.call_args.args[1]['reference_close'],100.)
        database.commit.assert_called_once()
        self.assertEqual(h.out.call_args.args[0]['advice']['research_journal']['reason'],'SAVED')
    def test_unknown_endpoint_post_refused(self):
        h=handler(path='/api/refresh',headers={'X-NEXUS-Research-Click':'1'})
        h.do_POST()
        self.assertEqual(h.out.call_args.args[1],404)


if __name__=='__main__':
    unittest.main()
