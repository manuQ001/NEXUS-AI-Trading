"""Validate agent architecture, bounded LLM veto and no fabricated approvals."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import meme_agents

M='So11111111111111111111111111111111111111112'
A='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
Q={'address':M,'symbol':'TEST','price_usd':0.01,'liquidity_usd':3000,'volume_24h_usd':4000}

class Response:
    def __init__(self,text):
        self.data=json.dumps({'output':[{'content':[{'type':'output_text','text':text}]}]}).encode()
    def geturl(self):return meme_agents.ENDPOINT
    def read(self,maxlen):return self.data
    def __enter__(self):return self
    def __exit__(self,*args):return False

class FakeOpener:
    def __init__(self,reply):self.reply=reply;self.calls=0
    def open(self,request,timeout):
        self.calls+=1
        assert request.full_url==meme_agents.ENDPOINT
        assert request.get_method()=='POST'
        return Response(json.dumps(self.reply))

class TestMemeAgents(unittest.TestCase):
    def setUp(self):
        self.previous=meme_agents._calls
        meme_agents._calls=0
    def tearDown(self):
        meme_agents._calls=self.previous
    def test_empty_candidate_scan_does_not_consume_paid_llm_budget(self):
        opener=FakeOpener({})
        result=meme_agents.review([],model='gpt-4.1-mini',
                                  api_key='x'*25,opener=opener)
        self.assertEqual(opener.calls,0)
        self.assertEqual(meme_agents._calls,0)
        self.assertEqual(result['approved_addresses'],[])

    def test_tiny_memecoin_price_is_not_rounded_to_zero(self):
        row=dict(Q,price_usd=0.00000000123)
        result=meme_agents.rule_agents([row])
        self.assertIn(M,result['approved_addresses'])

    def test_no_key_means_explicit_rule_agents(self):
        with patch.dict('os.environ',{'NEXUS_MEME_AI_MODEL':'','NEXUS_MEME_AI_API_KEY':''}):
            r=meme_agents.review([Q])
        self.assertEqual(r['mode'],'RULE_AGENTS')
        self.assertEqual(r['status'],'RULES_ONLY')
        self.assertIn(M,r['approved_addresses'])
    def test_llm_can_only_veto_and_never_approve_noneligible(self):
        bad=dict(Q,address=A,liquidity_usd=3)
        obj={'search':'Dati limitati','risk':'Liquidita insufficiente',
             'strategist':'Non prevedibile','head_of_desk':'Attendere',
             'rejected_addresses':[M]}
        client=FakeOpener(obj)
        r=meme_agents.review([Q,bad],model='gpt-4.1-mini',
                             api_key='x'*25,opener=client)
        self.assertEqual(r['status'],'REVIEWED')
        self.assertEqual(r['approved_addresses'],[])
        self.assertEqual(client.calls,1)
        self.assertFalse(any(x['name']=='RISK' and x['status']=='APPROVED'
                             for x in r['agents']))
    def test_invalid_output_blocks_all_when_model_enabled(self):
        obj={'search':'OK','risk':'OK','strategist':'OK',
             'head_of_desk':'OK','rejected_addresses':['unknown-address']}
        r=meme_agents.review([Q],model='gpt-4.1-mini',
                             api_key='x'*25,opener=FakeOpener(obj))
        self.assertEqual(r['approved_addresses'],[])
        self.assertEqual(r['status'],'UNAVAILABLE')
    def test_response_with_no_key_never_calls_endpoint(self):
        with patch.dict('os.environ',{'NEXUS_MEME_AI_MODEL':'','NEXUS_MEME_AI_API_KEY':''}):
            with patch.object(meme_agents.urllib.request,'build_opener',side_effect=AssertionError('network')):
                self.assertEqual(meme_agents.review([Q])['mode'],'RULE_AGENTS')
    def test_model_session_cap_blocks_trading_when_configured(self):
        meme_agents._calls=meme_agents.MAX_CALLS_PER_PROCESS
        r=meme_agents.review([Q],model='gpt-4.1-mini',api_key='x'*25)
        self.assertEqual(r['status'],'SESSION_CAP')
        self.assertEqual(r['approved_addresses'],[])

if __name__=='__main__':unittest.main()
