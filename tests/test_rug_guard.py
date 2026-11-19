import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from rug_guard import analyze,inspect,_status,API
A='So11111111111111111111111111111111111111112'
def response(**fields):return {'code':1,'result':{A:fields}}
class TestRugGuard(unittest.TestCase):
    def test_risky_mint_freeze_and_holder_concentration(self):
        holders=[{'percent':'0.08'} for _ in range(10)]
        r=analyze(A,response(mintable={'status':'1'},freezable={'status':'1'},holders=holders),now=1)
        self.assertEqual(r['status'],'RISCHI_RILEVATI')
        self.assertAlmostEqual(r['top10_holder_pct'],80)
        self.assertIn('Autorità mint',r['findings'])
        self.assertIn('Autorità freeze',r['findings'])
        self.assertFalse(r['trade_authorized'])
        self.assertEqual(r['sellability'],'NON_VERIFICATA')
        self.assertEqual(r['meme_execution'],'BLOCKED')
    def test_all_clear_fields_do_not_mean_safe(self):
        fields={x:{'status':'0'} for x in ('mintable','freezable','close_authority','balance_mutable','metadata_mutable','transfer_hook','non_transferable')}
        fields['holders']=[{'percent':'0.01'} for _ in range(10)]
        r=analyze(A,response(**fields))
        self.assertEqual(r['status'],'NESSUN_FLAG_NEI_CAMPI_LETTI')
        self.assertEqual(r['missing'],[])
        self.assertFalse(r['trade_authorized'])
        self.assertEqual(r['liquidity_lock'],'NON_VERIFICATA')
    def test_missing_and_malformed_status_fail_closed(self):
        r=analyze(A,response(mintable={'status':'unknown'},holders=[]))
        self.assertEqual(r['status'],'DATI_INCOMPLETI')
        self.assertIn('Autorità mint',r['missing'])
        self.assertIsNone(r['top10_holder_pct'])
        self.assertEqual(_status({'status':'not-a-code'}),'NON_DISPONIBILE')
    def test_wrong_mint_and_failed_provider(self):
        for payload in ({'code':0,'result':{}},{'code':1,'result':{}},
                        {'code':1,'result':{A.upper():{'mintable':{'status':'0'}}}}):
            with self.assertRaises(ValueError):analyze(A,payload)
        with self.assertRaises(ValueError):inspect('../bad',fetch=lambda _:None)
    def test_read_only_call_is_address_scoped(self):
        seen=[]
        def fake(mint):
            seen.append(mint)
            return response(mintable={'status':'1'})
        r=inspect(A,fetch=fake)
        self.assertEqual(seen,[A])
        self.assertTrue(r['findings'])
        self.assertFalse(r['trade_authorized'])
if __name__=='__main__':unittest.main()
