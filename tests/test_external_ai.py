"""Tests for optional user-triggered external AI advisory, mocked network only."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import external_ai
from agents import review


class FakeResponse:
    def __init__(self, data, url=external_ai.ENDPOINT):
        self.data=data
        self.url=url
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def geturl(self):return self.url
    def read(self,n):return self.data[:n]


def response_json(**overrides):
    a={'search':'EMA non confermate','head_of_desk':'Attendere',
       'risks':'Commissioni','uncertainty':'Dati parziali',
       'hypotheses':[{'horizon_bars':3,'direction':'ABSTAIN','rationale':'Dati scarsi'},
                     {'horizon_bars':12,'direction':'FLAT','rationale':'Scenario neutrale'}]}
    a.update(overrides)
    return json.dumps({'status':'completed','output':[{
        'type':'message','content':[{'type':'output_text','text':json.dumps(a)}]}]}).encode('utf-8')


class TestExternalAI(unittest.TestCase):
    def setUp(self):
        external_ai._calls=0
        candles=[{'time':1700000000+300*i,'close':100.} for i in range(100)]
        self.report=review('BTC',candles,{'buy':False,'atr':1,'why':'WAIT'})
    def tearDown(self):
        external_ai._calls=0
    def test_disabled_without_model_and_key_never_connects(self):
        with patch.dict('os.environ',{},clear=True),patch('external_ai.urllib.request.build_opener') as http:
            result=external_ai.external_ai_advice(self.report)
            self.assertEqual(result['status'],'disabled')
            http.assert_not_called()
    def test_read_only_success_protects_veto_and_does_not_send_key_as_data(self):
        report=review('BTC',[{'time':1700000000+300*i,'close':100.} for i in range(100)],
                      {'buy':True,'atr':1.,'why':'BUY'},daily_realized=-4)
        previous=repr(report)
        captured=[]
        def fake_urlopen(req,timeout=None):
            captured.append(req)
            return FakeResponse(response_json())
        with patch('external_ai.urllib.request.build_opener') as build:
            build.return_value.open.side_effect=fake_urlopen
            result=external_ai.external_ai_advice(report,model='gpt-4.1-mini',
                                                   api_key='sk-testing-token-123456')
        self.assertEqual(result['status'],'advisory_only')
        self.assertTrue(result['risk_veto'])
        self.assertFalse(result['paper_candidate'])
        self.assertFalse(result['execution_authorized'])
        self.assertEqual(result['analysis']['head_of_desk'],'Attendere')
        self.assertEqual(repr(report),previous)
        request=captured[0]
        self.assertEqual(request.full_url,external_ai.ENDPOINT)
        payload=json.loads(request.data)
        self.assertFalse(payload['store'])
        self.assertEqual(payload['tool_choice'],'none')
        self.assertLessEqual(payload['max_output_tokens'],550)
        self.assertNotIn('sk-testing-token-123456',request.data.decode())
        self.assertNotIn('sk-testing-token-123456',str(result))
        self.assertEqual(external_ai._calls,1)
    def test_session_limit_is_five_calls(self):
        with patch('external_ai.urllib.request.build_opener') as build:
            http=build.return_value.open
            http.return_value=FakeResponse(response_json())
            for _ in range(5):
                self.assertTrue(external_ai.external_ai_advice(
                    self.report,model='gpt-4.1-mini',api_key='sk-testing-token-123456')['available'])
            last=external_ai.external_ai_advice(
                self.report,model='gpt-4.1-mini',api_key='sk-testing-token-123456')
        self.assertEqual(last['status'],'session_limit')
        self.assertEqual(http.call_count,5)
    def test_structured_hypotheses_only_and_no_order(self):
        with patch('external_ai.urllib.request.build_opener') as build:
            build.return_value.open.return_value=FakeResponse(response_json())
            result=external_ai.external_ai_advice(
                self.report,model='gpt-4.1-mini',api_key='sk-testing-token-123456')
        self.assertTrue(result['available'])
        self.assertEqual([h['direction'] for h in result['hypotheses']],['ABSTAIN','FLAT'])
        self.assertFalse(result['execution_authorized'])
    def test_wrong_hypothesis_horizon_rejected(self):
        bad=[{'horizon_bars':12,'direction':'UP','rationale':'Trend'},
             {'horizon_bars':3,'direction':'DOWN','rationale':'Trend'}]
        with patch('external_ai.urllib.request.build_opener') as build:
            build.return_value.open.return_value=FakeResponse(response_json(hypotheses=bad))
            result=external_ai.external_ai_advice(
                self.report,model='gpt-4.1-mini',api_key='sk-testing-token-123456')
        self.assertEqual(result['status'],'unavailable')
    def test_schema_failure_never_authorizes(self):
        with patch('external_ai.urllib.request.build_opener') as build:
            build.return_value.open.return_value=FakeResponse(response_json(buy='BUY NOW'))
            result=external_ai.external_ai_advice(self.report,model='gpt-4.1-mini',
                                                  api_key='sk-testing-token-123456')
        self.assertFalse(result['available'])
        self.assertEqual(result['status'],'unavailable')
    def test_http_exception_sanitized_and_counted(self):
        with patch('external_ai.urllib.request.build_opener') as build:
            build.return_value.open.side_effect=OSError('sensitive error string')
            result=external_ai.external_ai_advice(self.report,model='gpt-4.1-mini',
                                                  api_key='sk-testing-token-123456')
        self.assertNotIn('sensitive',str(result))
        self.assertEqual(result['status'],'unavailable')
        self.assertEqual(external_ai._calls,1)
    def test_redirect_is_refused(self):
        with patch('external_ai.urllib.request.build_opener') as build:
            build.return_value.open.return_value=FakeResponse(response_json(),url='https://other.example/')
            result=external_ai.external_ai_advice(self.report,model='gpt-4.1-mini',
                                                  api_key='sk-testing-token-123456')
        self.assertEqual(result['status'],'unavailable')
    def test_redirect_handler_does_not_forward_authorization(self):
        handler=external_ai.NoRedirect()
        self.assertIsNone(handler.redirect_request(
            object(),None,302,'Found',{},'https://other.example'))
    def test_invalid_credential_does_not_connect(self):
        with patch('external_ai.urllib.request.build_opener') as http:
            result=external_ai.external_ai_advice(self.report,model='https://bad.example',
                                                  api_key='sk-testing-token-123456')
            self.assertEqual(result['status'],'invalid_model')
            http.assert_not_called()


if __name__=='__main__':
    unittest.main()
