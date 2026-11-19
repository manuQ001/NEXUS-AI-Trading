import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from meme_scout import analyze,scan,PROFILES,PAIRS_ROOT,MAX_TOKENS

A='So11111111111111111111111111111111111111112'
B='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
NOW=1800000000000


def pair(address, liquidity=25000, volume=70000, created=NOW-48*3600000):
    return {'chainId':'solana','baseToken':{'address':address,'symbol':'MEME','name':'Meme example'},
            'quoteToken':{'address':'QUOTE'},'liquidity':{'usd':liquidity},
            'volume':{'h24':volume},'pairCreatedAt':created,
            'priceUsd':'0.005','txns':{'h24':{'buys':20,'sells':12}},
            'url':'https://dexscreener.com/solana/mockpair','dexId':'raydium'}


class TestMemeScout(unittest.TestCase):
    def test_manual_fetch_and_no_execution(self):
        calls=[]
        profiles=[{'chainId':'solana','tokenAddress':A},
                  {'chainId':'ethereum','tokenAddress':B}]
        def fake(url):
            calls.append(url)
            return profiles if url==PROFILES else [pair(A)]
        result=scan(fake)
        self.assertEqual(calls,[PROFILES,PAIRS_ROOT+A])
        self.assertEqual(len(result['candidates']),1)
        self.assertEqual(result['candidates'][0]['security'],'NON_VERIFICATA')
        self.assertFalse(result['candidates'][0]['trade_authorized'])
        self.assertEqual(result['meme_execution'],'BLOCKED')
        self.assertEqual(result['mode'],'READ_ONLY')
    def test_sort_by_observed_liquidity_not_safety(self):
        profiles=[{'chainId':'solana','tokenAddress':A},{'chainId':'solana','tokenAddress':B}]
        results=analyze(profiles,[pair(A,200),pair(B,50000)],NOW)
        self.assertEqual(results['candidates'][0]['address'],B)
        self.assertTrue(all(x['security']=='NON_VERIFICATA' for x in results['candidates']))
        self.assertIn('Liquidità osservata sotto $10k',results['candidates'][1]['warnings'])
    def test_missing_fields_fail_closed_and_invalid_links_not_exposed(self):
        p=pair(A)
        p.update({'priceUsd':float('nan'),'volume':{},'liquidity':{},'url':'javascript:alert(1)'})
        result=analyze([{'chainId':'solana','tokenAddress':A}],[p],NOW)
        token=result['candidates'][0]
        self.assertIsNone(token['price_usd'])
        self.assertIsNone(token['liquidity_usd'])
        self.assertIsNone(token['url'])
        self.assertFalse(token['trade_authorized'])
        self.assertGreater(len(token['warnings']),1)
    def test_invalid_profile_and_foreign_chain_never_included(self):
        data=analyze([{'chainId':'solana','tokenAddress':'../../bad'},
                      {'chainId':'ethereum','tokenAddress':A}],[pair(A)],NOW)
        self.assertEqual(data['candidates'],[])
        with self.assertRaises(ValueError):analyze({},[],NOW)
    def test_bounded_addresses_and_no_pairs_call_on_empty(self):
        calls=[]
        def fake(url):
            calls.append(url)
            return [] if url==PROFILES else None
        result=scan(fake)
        self.assertEqual(calls,[PROFILES])
        self.assertEqual(result['candidates'],[])
        self.assertLessEqual(result['sampled_profiles'],MAX_TOKENS)


if __name__=='__main__':unittest.main()
