"""Validate complete 2.7 upgrade inventory without executing untrusted updater."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import upgrade_from_26
from updater import FILES


class TestUpgrade26(unittest.TestCase):
    def test_current_release_includes_all_required_modules(self):
        root=Path(__file__).resolve().parents[1]
        self.assertTrue(all((root/f).is_file() for f in FILES))
        self.assertEqual(upgrade_from_26.files_from_package(root),FILES)
    def test_legacy_release_missing_ai_modules_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'updater.py').write_text(
                "FILES=['src/external_ai.py','src/hypothesis.py']",
                encoding='utf-8')
            with self.assertRaises(ValueError):
                upgrade_from_26.files_from_package(root)
    def test_manifest_is_fixed_to_release(self):
        self.assertEqual(upgrade_from_26.EXPECTED_VERSION,'2.7.0')
        self.assertIn('/v2.7.0/',upgrade_from_26.RELEASE_PREFIX)


if __name__=='__main__':
    unittest.main()
