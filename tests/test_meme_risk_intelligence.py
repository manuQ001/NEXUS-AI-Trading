"""Tests: read-only risk evidence, opt-in provider, honest unknowns, wallet intact."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from core import connect
from meme_auto import init_auto
from meme_portfolio import portfolio
from meme_desk import record_scan
from meme_risk_intelligence import record_candidates,inspect_next,report,external_enabled
A='So11111111111111111111111111111111111111112'
B='DezXAZ8z7PnrnRJjz3wXBoRgixCaKGYcB2bM9aBfM3'
ROW={'address':A,'symbol':'SEC','price_usd':.02,'liquidity_usd':25000,
     'volume_24h_usd':78000,'pool_age_hours':1.0}
class TestRiskIntelligence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.c=connect(Path(self.tmp.name)/'risk.sqlite')
        init_auto(self.c)
    def tearDown(self):
        self.c.close();self.tmp.cleanup()
    def test_record_real_scanner_data_is_not_security_clearance(self):
        record_scan(self.c,[dict(ROW)],now=1000,guard_blocked=True)
        d=report(self.c,now=1000,env={})
        self.assertEqual(d['total_candidates'],1)
        self.assertFalse(d['external_goplus_enabled'])
        self.assertEqual(d['recent'][0]['provider_status'],'NOT_CHECKED')
        self.assertEqual(d['recent'][0]['scanner_risk'],'FILTERS_PASSED_NOT_SECURITY_VERIFIED')
        self.assertFalse(d['recent'][0]['trade_authorized'])
        self.assertEqual(len(portfolio(self.c)['positions']),0)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM meme_eur_trades').fetchone()[0],0)
    def test_external_disabled_performs_zero_calls(self):
        record_candidates(self.c,[ROW],now=1000)
        calls=[]
        r=inspect_next(self.c,now=1200,env={},inspect=lambda a:calls.append(a))
        self.assertEqual(r['status'],'DISABLED')
        self.assertEqual(calls,[])
        self.assertEqual(report(self.c,env={})['external_checks_used'],0)
        self.assertFalse(external_enabled({'NEXUS_RISK_GOPLUS_ENABLED':'false'}))
    def test_opt_in_safe_provider_findings_and_rate_limit(self):
        record_candidates(self.c,[ROW,dict(ROW,address=B)],now=1000)
        calls=[]
        def fake(a):
            calls.append(a)
            return {'ok':True,'address':a,'status':'RISCHI_RILEVATI',
                    'findings':['Autorità mint'], 'missing':['Holder'],
                    'checks':[],'top10_holder_pct':None}
        env={'NEXUS_RISK_GOPLUS_ENABLED':'1'}
        self.assertEqual(inspect_next(self.c,now=1000,env=env,inspect=fake)['attempted'],1)
        self.assertEqual(inspect_next(self.c,now=1001,env=env,inspect=fake)['status'],'RATE_LIMITED')
        self.assertEqual(inspect_next(self.c,now=1091,env=env,inspect=fake)['attempted'],1)
        self.assertEqual(len(set(calls)),2)
        d=report(self.c,now=1100,env=env)
        self.assertEqual(d['external_checks_used'],2)
        self.assertEqual(d['provider_status_counts']['RISCHI_RILEVATI'],2)
        self.assertEqual(len(portfolio(self.c)['positions']),0)
    def test_provider_failure_must_be_unknown(self):
        record_candidates(self.c,[ROW],now=1000)
        result=inspect_next(self.c,now=1000,env={'NEXUS_RISK_GOPLUS_ENABLED':'1'},
                    inspect=lambda a: (_ for _ in ()).throw(OSError('offline')))
        self.assertEqual(result['status'],'PROVIDER_ERROR')
        d=report(self.c,env={'NEXUS_RISK_GOPLUS_ENABLED':'1'})
        self.assertEqual(d['recent'][0]['provider_status'],'PROVIDER_ERROR')
        self.assertEqual(d['external_errors'],1)
        self.assertNotIn('SICURO',str(d['recent']))
    def test_overwrite_scanner_metadata_preserves_prior_provider_evidence(self):
        record_candidates(self.c,[ROW],now=1000)
        inspect_next(self.c,now=1000,env={'NEXUS_RISK_GOPLUS_ENABLED':'1'},
                    inspect=lambda a: {'ok':True,'address':a,
                    'status':'DATI_INCOMPLETI','findings':[],
                    'missing':['Holder'],'checks':[]})
        record_candidates(self.c,[dict(ROW,liquidity_usd=32000)],now=1010)
        d=report(self.c,env={})['recent'][0]
        self.assertEqual(d['liquidity_usd'],32000)
        self.assertEqual(d['provider_status'],'DATI_INCOMPLETI')
    def test_dashboard_exposes_evidence_without_safety_claim(self):
        html=(Path(__file__).resolve().parents[1]/'src'/'dashboard.html').read_text('utf-8')
        self.assertIn('id="nx-risk-lab"',html)
        self.assertIn("fetch('/api/meme-risk-intelligence'",html)
        self.assertIn('Nessuna autorizzazione agli acquisti',html)
if __name__=='__main__':unittest.main()
