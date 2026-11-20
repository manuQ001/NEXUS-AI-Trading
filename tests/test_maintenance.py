import unittest,sys,tempfile,hashlib,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from maintenance import check_updates,VERSION
from updater import sha256,safe_package
class TestMaintenance(unittest.TestCase):
    def test_version(self):self.assertEqual(VERSION,'4.3.0')
    def test_manifest_unconfigured(self):
        from unittest.mock import patch
        with patch('maintenance.get_config', return_value={}):
            x=check_updates()
        self.assertFalse(x['configured'])
    def test_neon_terminal_ids_and_existing_controls_preserved(self):
        from html.parser import HTMLParser
        class Inspect(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids=[]
                self.details=[]
            def handle_starttag(self,tag,attrs):
                props=dict(attrs)
                if 'id' in props:self.ids.append(props['id'])
                if tag=='details':self.details.append(props.get('id'))
        html=(Path(__file__).resolve().parents[1]/'src'/'dashboard.html').read_text(encoding='utf-8')
        parsed=Inspect()
        parsed.feed(html)
        for name in ('nx-terminal','nx-equity','nx-scanner','nx-agents','nx-positions',
                     'nx-feed','nx-advanced','meme-demo-positions','meme-auto-toggle',
                     'meme-hunter','meme-rows'):
            self.assertEqual(parsed.ids.count(name),1,name)
        self.assertIn('nx-advanced',parsed.details)
        self.assertIn("const id=WORKSPACE_IDS.includes(requested)?requested:'meme-section';",html)
        self.assertIn("renderNexusCockpitAuto(d)",html)
        self.assertIn("renderNexusCockpitPortfolio(d)",html)
        self.assertNotIn('fakeTrade',html)

    def test_v311_focus_views_preserve_live_sources_and_controls(self):
        from html.parser import HTMLParser
        class Inspect(HTMLParser):
            def __init__(self):
                super().__init__()
                self.views=[]
                self.ids=[]
                self.nav_links=[]
            def handle_starttag(self,tag,attrs):
                props=dict(attrs)
                if 'id' in props:self.ids.append(props['id'])
                if 'data-nx-focus' in props:self.views.append(props['data-nx-focus'])
                if tag=='a' and props.get('href','').startswith('#'):
                    self.nav_links.append(props['href'])
        html=(Path(__file__).resolve().parents[1]/'src'/'dashboard.html').read_text('utf-8')
        p=Inspect();p.feed(html)
        self.assertEqual(p.views,['live','prices','shadow','risk','desk','v4','tools'])
        for name in ['nx-event-tape','nx-event-counter','nx-active-focus-label',
                     'nx-market-pulse','nx-shadow-lab','nx-risk-lab','nx-desk-control',
                     'nx-advanced','meme-auto-toggle']:
            self.assertEqual(p.ids.count(name),1,name)
        for section in ['#overview','#market','#meme-section','#performance-section',
                        '#lab-section','#agents-section','#history-section','#execution-section']:
            self.assertIn(section,p.nav_links)
        self.assertIn('function nxRecordObservedEvent(packet)',html)
        self.assertIn("['PAPER_MINT','PAPER_PROFILE','PAPER_QUOTES','PAPER_JOURNAL']",html)
        self.assertIn("if(nxObservedSessionEvents===0)tape.replaceChildren()",html)
        self.assertIn('prefers-reduced-motion:reduce',html)
        self.assertIn('nx-focus-button:focus-visible',html)
        self.assertIn("fetch('/api/meme-shadow'",html)
        self.assertIn("fetch('/api/meme-risk-intelligence'",html)
        self.assertNotIn('Math.random()',html)
        self.assertNotIn('fakeTrade',html)

    def test_hash(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x';p.write_bytes(b'abc');self.assertEqual(sha256(p),hashlib.sha256(b'abc').hexdigest())
    def test_rejects_zip_traversal(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bad.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr('../bad.txt','unsafe')
            with self.assertRaises(ValueError):safe_package(p,Path(t))
