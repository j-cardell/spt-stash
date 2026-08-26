#!/usr/bin/env python3
"""
SPT Stash — Native Unit Tests Suite
Tests catalog matching, semver parsing, metadata sidecars, preset exports, and purge helpers.
"""

import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

# Add parent directory to path so we can import spt_mod_manager
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Set QT_QPA_PLATFORM offscreen to allow Qt tests to run headless without a display server
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import spt_mod_manager


class TestSPTModManagerCore(unittest.TestCase):

    def test_version_parsing(self):
        """Test semver tuple parsing and comparison."""
        self.assertEqual(spt_mod_manager.parse_version_tuple("v1.8.0"), (1, 8, 0))
        self.assertEqual(spt_mod_manager.parse_version_tuple("2.2.3-beta"), (2, 2, 3))
        self.assertEqual(spt_mod_manager.parse_version_tuple(""), (0, 0, 0))
        self.assertEqual(spt_mod_manager.parse_version_tuple(None), (0, 0, 0))
        self.assertEqual(spt_mod_manager.parse_version_tuple("invalid_text"), (0, 0, 0))

        # Comparison checks
        self.assertTrue(spt_mod_manager.is_version_newer("v2.0.0", "v1.8.0"))
        self.assertFalse(spt_mod_manager.is_version_newer("v2.2.3", "v2.2.3"))
        self.assertFalse(spt_mod_manager.is_version_newer("v1.9.9", "v2.0.0"))
        self.assertFalse(spt_mod_manager.is_version_newer("1.0", "1.0"))

    def test_catalog_matching_and_aliases(self):
        """Test catalog resolution and alias mappings."""
        # Alias test for ASBP
        match1 = spt_mod_manager.find_best_catalog_match_global("acidphantasm-bepinexconfigurationmanager")
        self.assertIsNotNone(match1)
        self.assertIn("ASBP", match1["title"])

        # Alias test for UI Fixes
        match2 = spt_mod_manager.find_best_catalog_match_global("Tyfon.UIFixes.dll")
        self.assertIsNotNone(match2)
        self.assertEqual(match2["title"], "UI Fixes")

        # Alias test for SAIN
        match3 = spt_mod_manager.find_best_catalog_match_global("Solarint-SAIN-ServerMod")
        self.assertIsNotNone(match3)
        self.assertIn("SAIN", match3["title"])

    def test_metadata_load_and_save(self):
        """Test metadata sidecar reading and writing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir) / "TestMod"
            tmppath.mkdir()

            test_meta = {
                "title": "Test Mod Package",
                "version": "1.2.3",
                "link": "https://sp-mod.com/mod/999/test-mod",
                "fika_status": "🟢 Compatible"
            }
            spt_mod_manager.save_mod_meta(tmppath, test_meta)

            loaded = spt_mod_manager.load_mod_meta(tmppath)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["title"], "Test Mod Package")
            self.assertEqual(loaded["version"], "1.2.3")
            self.assertEqual(loaded["fika_status"], "🟢 Compatible")

    def test_html_manifest_generator(self):
        """Test HTML manifest export generator output."""
        dummy_manifest = {
            "spt_version": "SPT 4.1.3",
            "total_packages": 1,
            "total_files": 2,
            "mods": [
                {
                    "name": "Tyfon.UIFixes",
                    "title": "UI Fixes",
                    "author": "Tyfon",
                    "version": "v1.8.0",
                    "type": "Dual (Client + Server)",
                    "link": "https://sp-mod.com/mod/538/ui-fixes",
                    "enabled": True
                }
            ]
        }
        html_out = spt_mod_manager.generate_html_stash_manifest(dummy_manifest)
        self.assertIn("SPT Stash Manifest", html_out)
        self.assertIn("UI Fixes", html_out)
        self.assertIn("1 Mod Packages", html_out)
        self.assertIn("2 Component Files", html_out)

    def test_purge_helper(self):
        """Test purge helper removing staged and live symlinks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            staged = base / "staged_test"
            live = base / "live_test"
            staged.mkdir()
            live.mkdir()

            mod_staged = staged / "SampleMod"
            mod_live = live / "SampleMod"
            mod_staged.mkdir()
            os.symlink(str(mod_staged), str(mod_live))

            self.assertTrue(mod_staged.exists())
            self.assertTrue(mod_live.exists())

            # Test dict purge
            dummy_mod_dict = {
                "client_items": [(mod_staged, mod_live, True)],
                "server_items": []
            }
            spt_mod_manager.purge_mod_files_and_symlinks(dummy_mod_dict)

            self.assertFalse(mod_staged.exists())
            self.assertFalse(mod_live.exists())


if __name__ == "__main__":
    unittest.main()
