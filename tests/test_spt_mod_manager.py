#!/usr/bin/env python3
"""
SPT Stash — Native Unit Tests Suite
Tests catalog matching, semver parsing, metadata sidecars, preset exports, and staging helpers.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add repo root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Set headless Qt rendering environment
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import spt_stash  # noqa: E402
from spt_stash import config, manifest, paths, version  # noqa: E402
from spt_stash.staging import links, metadata  # noqa: E402


class TestSPTModManagerCore(unittest.TestCase):

    def test_package_version(self):
        """Test package version string presence."""
        self.assertTrue(hasattr(spt_stash, "__version__"))
        self.assertEqual(spt_stash.__version__, "1.2.0")

    def test_find_app_icon(self):
        """Test application icon resolution."""
        icon = paths.find_app_icon()
        self.assertIsNotNone(icon)
        self.assertTrue(icon.exists())

    @classmethod
    def setUpClass(cls):
        # Provide self-contained catalog entries for offline unit testing
        paths.CATALOG_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        mock_catalog = [
            {
                "title": "ASBP - Acid's Scalable BepinEx Panel",
                "creator": "acidphantasm",
                "version": "1.0.0",
                "link": "https://sp-mod.com/mod/2931/asbp-acids-scalable-bepinex-panel",
                "fika_status": "🟢 Compatible"
            },
            {
                "title": "UI Fixes",
                "creator": "Tyfon",
                "version": "1.8.0",
                "link": "https://sp-mod.com/mod/538/ui-fixes",
                "fika_status": "🟢 Compatible"
            },
            {
                "title": "SAIN - Solarint's AI Modifications - Full AI Package",
                "creator": "Solarint",
                "version": "3.0.0",
                "link": "https://sp-mod.com/mod/123/sain-solarints-ai-modifications",
                "fika_status": "🟢 Compatible"
            }
        ]
        with open(paths.CATALOG_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(mock_catalog, f)

    def test_version_parsing(self):
        """Test semver tuple parsing and comparison."""
        self.assertEqual(version.parse_version_tuple("v1.8.0"), (1, 8, 0))
        self.assertEqual(version.parse_version_tuple("2.2.3-beta"), (2, 2, 3))
        self.assertEqual(version.parse_version_tuple(""), (0, 0, 0))
        self.assertEqual(version.parse_version_tuple(None), (0, 0, 0))
        self.assertEqual(version.parse_version_tuple("invalid_text"), (0, 0, 0))

        self.assertTrue(version.is_version_newer("v2.0.0", "v1.8.0"))
        self.assertFalse(version.is_version_newer("v2.2.3", "v2.2.3"))
        self.assertFalse(version.is_version_newer("v1.9.9", "v2.0.0"))
        self.assertFalse(version.is_version_newer("1.0", "1.0"))

    def test_catalog_matching_and_aliases(self):
        """Test catalog resolution and alias mappings."""
        match1 = spt_stash.find_best_catalog_match_global("acidphantasm-bepinexconfigurationmanager")
        self.assertIsNotNone(match1)
        self.assertIn("ASBP", match1["title"])

        match2 = spt_stash.find_best_catalog_match_global("Tyfon.UIFixes.dll")
        self.assertIsNotNone(match2)
        self.assertEqual(match2["title"], "UI Fixes")

        match3 = spt_stash.find_best_catalog_match_global("Solarint-SAIN-ServerMod")
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
            metadata.save_mod_meta(tmppath, test_meta)
            loaded = metadata.load_mod_meta(tmppath)
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
        html_out = manifest.generate_html_stash_manifest(dummy_manifest)
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

            dummy_mod_dict = {
                "client_items": [(mod_staged, mod_live, True)],
                "server_items": []
            }
            links.purge_mod_files_and_symlinks(dummy_mod_dict)

            self.assertFalse(mod_staged.exists())
            self.assertFalse(mod_live.exists())

    def test_load_config_defaults(self):
        """Test load_config default paths."""
        cfg = config.load_config()
        self.assertIn("spt_path", cfg)
        self.assertIn("staged_dir", cfg)
        spt_root = Path(cfg["spt_path"]).resolve()
        staged_dir = Path(cfg["staged_dir"]).resolve()
        self.assertEqual(staged_dir, (spt_root / ".staged").resolve())

    def test_create_relative_symlink(self):
        """Test relative in-tree symlink helper."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            staged_mod = base / ".staged" / "server" / "SampleMod"
            staged_mod.mkdir(parents=True)
            (staged_mod / "mod.json").touch()

            live_dir = base / "user" / "mods"
            live_dir.mkdir(parents=True)
            live_target = live_dir / "SampleMod"

            links.create_relative_symlink(staged_mod, live_target)

            self.assertTrue(live_target.is_symlink())
            self.assertTrue(live_target.exists())
            self.assertEqual(live_target.resolve(), staged_mod.resolve())
            self.assertIn(".staged", os.readlink(live_target))

    def test_import_no_side_effects(self):
        """Importing spt_stash must not create directories under HOME."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            old_home = os.environ.get("HOME")
            try:
                os.environ["HOME"] = str(home)
                # Force re-import in a clean sub-interpreter context is hard; reload instead.
                import importlib
                importlib.reload(spt_stash)
                self.assertFalse((home / ".cache" / "spt-mod-manager").exists())
                self.assertFalse((home / ".config" / "spt-mod-manager").exists())
                self.assertFalse((home / "Games" / "SPT" / ".staged").exists())
            finally:
                os.environ["HOME"] = old_home or "/home/jon"


if __name__ == "__main__":
    unittest.main()
