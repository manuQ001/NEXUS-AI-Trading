import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from whale_tracker import analyze,inspect,_amount,MAX_U64

M='So11111111111111111111111111111111111111112'
A='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
B='11111111111111111111111111111111'
C='SysvarRent111111111111111111111111111111111'
def fixture():
    supply={'value':{'amount':'1000','decimals':6}}
    largest={'value':[{'address':A,'amount':'500'},
                      {'address':B,'amount':'200'},
                      {'address':C,'amount':'100'}]}
    owners={'value':[{'data':{'parsed':{'info':{'owner':M}}}},
                     {'data':{'parsed':{'info':{'owner':M}}}},
                     {'data':{'parsed':{'info':{'owner':A}}}}]}
    return supply,largest,owners

class TestWhaleTracker(unittest.TestCase):
    def test_concentration_uses_raw_amounts_and_always_blocks(self):
        s,l,o=fixture()
        result=analyze(M,s,l,o,now=1700000000)
        self.assertEqual(result['returned_token_accounts'],3)
        self.assertEqual(result['top10_token_accounts_pct'],80)
        self.assertEqual(result['top20_token_accounts_pct'],80)
        self.assertEqual(result['status'],'CONCENTRAZIONE_ELEVATA')
        self.assertTrue(result['owners_resolved'])
        self.assertEqual(result['owner_groups_observed'][0]['percentage_supply_observed'],70)
        self.assertFalse(result['trade_authorized'])
        self.assertEqual(result['meme_execution'],'BLOCKED')
        self.assertFalse(result['liquidity_pool_excluded'])
    def test_missing_owner_data_is_not_wallet_claim(self):
        s,l,o=fixture()
        result=analyze(M,s,l,None)
        self.assertFalse(result['owners_resolved'])
        self.assertEqual(result['owner_groups_observed'],[])
        self.assertIn('Proprietari dei token account non verificati',result['warnings'])
    def test_bad_supply_account_or_duplicate_rejected(self):
        s,l,o=fixture()
        for amount in ('-1','NaN','1.0',str(MAX_U64+1)):
            with self.assertRaises(ValueError):_amount(amount)
        for wrong in ('0','100','-100'):
            broken={'value':dict(s['value'],amount=wrong)}
            with self.assertRaises(ValueError):analyze(M,broken,l)
        dup={'value':[l['value'][0],l['value'][0]]}
        with self.assertRaises(ValueError):analyze(M,s,dup)
        overflow={'value':[dict(l['value'][0],amount='1001')]}
        with self.assertRaises(ValueError):analyze(M,s,overflow)
    def test_manual_rpc_calls_are_read_only(self):
        s,l,o=fixture()
        calls=[]
        def fake(method,params):
            calls.append(method)
            return {'getTokenSupply':s,'getTokenLargestAccounts':l,'getMultipleAccounts':o}[method]
        result=inspect(M,rpc=fake)
        self.assertEqual(calls,['getTokenSupply','getTokenLargestAccounts','getMultipleAccounts'])
        self.assertEqual(result['top10_token_accounts_pct'],80)
    def test_owner_rpc_failure_can_only_degrade_to_unknown(self):
        s,l,o=fixture()
        def fake(method,params):
            if method=='getMultipleAccounts':raise ValueError('rate limit')
            return s if method=='getTokenSupply' else l
        result=inspect(M,rpc=fake)
        self.assertFalse(result['owners_resolved'])
        self.assertFalse(result['trade_authorized'])
    def test_foreign_mint_and_invalid_response_fail_closed(self):
        s,l,o=fixture()
        with self.assertRaises(ValueError):inspect('../bad')
        with self.assertRaises(ValueError):analyze(M,{},l)
        with self.assertRaises(ValueError):analyze(M,s,{'value':'wrong'})

if __name__=='__main__':unittest.main()
