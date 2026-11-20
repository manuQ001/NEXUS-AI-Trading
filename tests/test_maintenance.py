import unittest,sys,tempfile,hashlib,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from maintenance import check_updates,VERSION
from updater import sha256,safe_package
class TestMaintenance(unittest.TestCase):
    def test_version(self):self.assertEqual(VERSION,'2.9.0')
    def test_manifest_unconfigured(self):
        from unittest.mock import patch
        with patch('maintenance.get_config', return_value={}):
            x=check_updates()
        self.assertFalse(x['configured'])
    def test_hash(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x';p.write_bytes(b'abc');self.assertEqual(sha256(p),hashlib.sha256(b'abc').hexdigest())
    def test_rejects_zip_traversal(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bad.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr('../bad.txt','unsafe')
            with self.assertRaises(ValueError):safe_package(p,Path(t))
