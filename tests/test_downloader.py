import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from downloader import version_tuple,read_staged,download_if_available
class TestDownloader(unittest.TestCase):
    def test_version(self):
        self.assertGreater(version_tuple('2.4.0'),version_tuple('2.3.0'))
    def test_bad_version(self):
        with self.assertRaises(ValueError):version_tuple('bad')
    def test_no_older_update(self):
        self.assertFalse(download_if_available({'available_version':'2.3.0'})['downloaded'])
    def test_unconfigured_stage(self):
        self.assertIsNone(read_staged())
