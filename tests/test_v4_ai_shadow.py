"""Real OpenAI shadow integration: no network in tests, never trades."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from meme_prices import observe
from meme_auto import init_auto
from meme_portfolio import portfolio
from v4_agents import initialize as init_v4,report as v4_report
from v4_ai_shadow import (initialize,config_status,reserve,finish,report,
                           _validate,_make_request,MAX_PER_DAY,MIN_INTERVAL_SECONDS)

MINT='3fWhdo8bQCamw5ed6yNGdvaru1qS5UVwB6dYp9znpump'
def quote(p):
    return {'address':MINT,'symbol':'OBS','price_usd':p,
            'liquidity_usd':40000,'volume_24h_usd':90000}

class TestRealAIShadow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.tmp.name)/'test.sqlite')
        init_auto(self.c)
        init_v4(self.c)
        initialize(self.c)
        for t,p in [(1000,.01),(1010,.0104),(1020,.0108)]:
            observe(self.c,MINT,quote(p),now=t)
    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()
    def test_v45_scanner_diagnostics_explain_observed_market_without_orders(self):
        from v4_ai_shadow import scanner_diagnostics
        from v4_agents import report as paper_report
        before=paper_report(self.c,now=1021)
        d=scanner_diagnostics(self.c,now=1021)
        self.assertEqual(d['mode'],'V45_SCANNER_DIAGNOSTICS')
        self.assertEqual(d['source'],'PERSISTED_DEX_SCREENER_REST_ONLY')
        self.assertEqual(d['fresh_tokens'],1)
        self.assertEqual(d['evaluated_tokens'],1)
        self.assertEqual(d['reasons']['PYTHON_BUY_SIGNAL'],1)
        self.assertEqual(d['candidates'][0]['price_changes'],3)
        self.assertEqual(paper_report(self.c,now=1021)['trade_count'],
                         before['trade_count'])
        self.assertEqual(d['ai_cooldown_remaining_seconds'],0)

    def test_v45_diagnostics_exclude_stale_and_distinguish_low_liquidity(self):
        from v4_ai_shadow import scanner_diagnostics
        low='So11111111111111111111111111111111111111112'
        for t,p in [(1000,.01),(1010,.0104),(1020,.0108)]:
            observe(self.c,low,{'address':low,'symbol':'LOW',
                'price_usd':p,'liquidity_usd':1000,
                'volume_24h_usd':1000},now=t)
        d=scanner_diagnostics(self.c,now=1021)
        self.assertEqual(d['reasons']['LOW_LIQUIDITY_OR_VOLUME'],1)
        stale=scanner_diagnostics(self.c,now=2000)
        self.assertEqual(stale['fresh_tokens'],0)
        self.assertEqual(stale['candidates'],[])

    def test_ai_candidate_prefers_python_buy_over_higher_liquidity_wait(self):
        from v4_ai_shadow import candidate
        other='So11111111111111111111111111111111111111112'
        for t,p in [(1000,.01),(1010,.01001),(1020,.01002)]:
            observe(self.c,other,{'address':other,'symbol':'WAIT_HIGH_LIQ',
                'price_usd':p,'liquidity_usd':200000,
                'volume_24h_usd':250000},now=t)
        item=candidate(self.c,1021)
        self.assertEqual(item['address'],MINT)
        self.assertEqual(item['rules_verdict'],'BUY')

    def test_off_by_default_and_no_key_leaks(self):
        d=config_status({})
        self.assertFalse(d['active'])
        self.assertFalse(d['orders_authorized'])
        self.assertFalse(d['can_override_risk'])
        d=config_status({'NEXUS_V4_AI_SHADOW_ENABLED':'1','NEXUS_OPENAI_API_KEY':'sk-secret'})
        self.assertTrue(d['active'])
        self.assertNotIn('sk-secret',str(d))
    def test_real_candidates_require_observed_fresh_prices_and_limits(self):
        item,status=reserve(self.c,now=1021)
        self.assertEqual(status,'RESERVED')
        self.assertEqual(item['address'],MINT)
        self.assertEqual(item['market']['observations'][-1]['price_usd'],.0108)
        again,status=reserve(self.c,now=1040)
        self.assertIsNone(again)
        self.assertEqual(status,'COOLDOWN')
        too_old,status=reserve(self.c,now=2000)
        self.assertIsNone(too_old)
        self.assertEqual(status,'NO_ELIGIBLE_OBSERVATION')
        self.assertEqual(v4_report(self.c)['trade_count'],0)
        self.assertEqual(portfolio(self.c)['cash_eur'],45)
    def test_status_stays_reserved_after_process_restart_and_failed_call(self):
        item,status=reserve(self.c,now=1021)
        self.c.commit()
        self.c.close()
        self.c=connect(Path(self.tmp.name)/'test.sqlite')
        initialize(self.c)
        self.assertEqual(report(self.c)['reviews'][0]['outcome'],'RESERVED')
        finish(self.c,item,error='HTTPError')
        self.c.commit()
        d=report(self.c)
        self.assertEqual(d['reviews'][0]['issue'],'HTTPError')
        self.assertEqual(d['reviews'][0]['outcome'],'ERROR')
        self.assertEqual(d['attempts_month'],1 if d['attempts_month'] else 0)
    def test_bad_json_is_rejected_and_never_controls_trading(self):
        with self.assertRaises(ValueError):_validate('{"verdict":"EXECUTE"}')
        with self.assertRaises(ValueError):_validate(json.dumps({
            'verdict':'BUY','analyst':'x','risk':'x','strategy':'x',
            'portfolio':'x','rationale':'x','command':'RESET_LOCK'}))
        item,_=reserve(self.c,now=1021)
        verdict={'verdict':'BUY','analyst':'Momentum REST',
                 'risk':'Sicurezza ignota','strategy':'Ipotesi',
                 'portfolio':'No ordini','rationale':'Studio'}
        finish(self.c,item,verdict,{'input':340,'output':90})
        review=report(self.c)['reviews'][0]
        self.assertEqual(review['verdict'],'BUY')
        self.assertEqual(review['roles']['risk'],'Sicurezza ignota')
        self.assertEqual(v4_report(self.c)['trade_count'],0)
        self.assertEqual(self.c.execute('SELECT risk_latched FROM meme_auto_state WHERE id=1').fetchone()[0],0)
    def test_mocked_model_response_is_validated_and_never_uses_tools(self):
        item,_=reserve(self.c,now=1021)
        verdict={'verdict':'WAIT','analyst':'Campioni insufficienti',
                 'risk':'Unknown','strategy':'Aspettare',
                 'portfolio':'Nessun trade','rationale':'Quote non eseguibili'}
        result={'status':'completed',
          'output':[{'content':[{'type':'output_text','text':json.dumps(verdict)}]}],
          'usage':{'input_tokens':100,'output_tokens':80}}
        class FakeResponse:
            headers={'Content-Length':'600'}
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return json.dumps(result).encode()
        class FakeOpener:
            def open(self,req,timeout):
                body=json.loads(req.data)
                self_body=body
                assert body['model']=='gpt-6-luna'
                assert body['store'] is False
                assert body['text']['format']['strict']
                assert not body.get('tools')
                assert req.full_url=='https://api.openai.com/v1/responses'
                return FakeResponse()
        with patch('v4_ai_shadow.urllib.request.build_opener',return_value=FakeOpener()):
            out,usage=_make_request(item,'sk-secret1234567890')
        self.assertEqual(out['verdict'],'WAIT')
        self.assertEqual(usage['input'],100)
    def test_incomplete_response_has_safe_specific_error_code(self):
        from v4_ai_shadow import _safe_api_error
        self.assertEqual(
            _safe_api_error(ValueError('AI_INCOMPLETE_MAX_OUTPUT_TOKENS')),
            'AI_INCOMPLETE_MAX_OUTPUT_TOKENS')
        self.assertEqual(
            _safe_api_error(ValueError('AI_INVALID_STRUCTURED_OUTPUT')),
            'AI_INVALID_STRUCTURED_OUTPUT')
        self.assertEqual(
            _safe_api_error(ValueError('private_token_from_provider')),
            'ValueError')

    def test_incomplete_response_is_not_a_consensus_buy(self):
        from v4_ai_shadow import _safe_api_error
        item,_=reserve(self.c,now=1021)
        result={'status':'incomplete',
                'incomplete_details':{'reason':'max_output_tokens'},
                'output':[]}
        class FakeResponse:
            headers={}
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return json.dumps(result).encode()
        class FakeOpener:
            def open(self,req,timeout):return FakeResponse()
        with patch('v4_ai_shadow.urllib.request.build_opener',return_value=FakeOpener()):
            with self.assertRaisesRegex(ValueError,'AI_INCOMPLETE_MAX_OUTPUT_TOKENS') as err:
                _make_request(item,'sk-secret1234567890')
        finish(self.c,item,error=_safe_api_error(err.exception))
        state=report(self.c)['reviews'][0]
        self.assertEqual(state['outcome'],'ERROR')
        self.assertEqual(state['issue'],'AI_INCOMPLETE_MAX_OUTPUT_TOKENS')
        self.assertIsNone(state['verdict'])

    def test_http_errors_show_safe_status_and_never_raw_body(self):
        import io
        from urllib.error import HTTPError
        from v4_ai_shadow import _safe_api_error
        raw=b'{"error":{"code":"insufficient_quota","message":"PRIVATE_DO_NOT_LOG"}}'
        exc=HTTPError('https://api.openai.com/v1/responses',429,
                      'Too Many Requests',{},io.BytesIO(raw))
        safe=_safe_api_error(exc)
        self.assertEqual(safe,'HTTP_429_insufficient_quota')
        self.assertNotIn('PRIVATE',safe)
        self.assertNotIn('api.openai.com',safe)
        self.assertEqual(_safe_api_error(ValueError('key_secret_here')),'ValueError')
        exc2=HTTPError('https://api.openai.com/v1/responses',401,
                       'Unauthorized',{},io.BytesIO(b'not-json'))
        self.assertEqual(_safe_api_error(exc2),'HTTP_401')

    def test_ui_contains_real_model_disclaimer(self):
        html=(Path(__file__).resolve().parents[1]/'src'/'dashboard.html').read_text('utf-8')
        for anchor in ['/api/v4-ai-shadow','nx-v4-ai-reviews','nx-v4-ai-count',
                       'AI SHADOW','Nessuna autorità sugli ordini']:
            self.assertIn(anchor,html)
if __name__=='__main__':unittest.main()
