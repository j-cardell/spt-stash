#!/usr/bin/env python3
"""
SPT Stash — Automated Test & Linting Suite Runner
Performs AST syntax validation and executes native unit tests.
"""

import sys
import os
import py_compile
import shutil
import subprocess
import unittest
from pathlib import Path

# Ensure headless Qt rendering environment
os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT_DIR = Path(__file__).resolve().parent
TARGET_FILE = ROOT_DIR / "spt_mod_manager.py"
TESTS_DIR = ROOT_DIR / "tests"


def run_linter():
    print("🧹 [1/3] Running Syntax & AST Linter...")
    try:
        py_compile.compile(str(TARGET_FILE), doraise=True)
        print("  ✅ Syntax check passed cleanly for spt_mod_manager.py!")
    except py_compile.PyCompileError as e:
        print(f"  ❌ Syntax Error detected: {e}")
        return False

    print("🧹 [2/3] Running Ruff lint gate...")
    ruff = shutil.which("ruff")
    if not ruff and sys.prefix != sys.base_prefix:
        # We are inside a venv; look for ruff in the venv's bin directory
        venv_ruff = Path(sys.prefix) / "bin" / "ruff"
        if venv_ruff.exists():
            ruff = str(venv_ruff)
    if ruff:
        res = subprocess.run(
            [ruff, "check", str(ROOT_DIR / "spt_stash"), str(TARGET_FILE)],
            cwd=str(ROOT_DIR),
        )
        if res.returncode == 0:
            print("  ✅ Ruff check passed!")
            return True
        print("  ❌ Ruff found issues (see above).")
        return False
    print("  ⚠️ ruff not installed; skipping ruff gate.")
    return True


def run_unit_tests():
    print("\n🧪 [2/2] Running Unit Test Suite...")
    loader = unittest.TestLoader()
    suite = loader.discover(str(TESTS_DIR))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


def main():
    print("==================================================")
    print(" 🚀 SPT Stash Automated Test & Linting Runner ")
    print("==================================================")

    lint_ok = run_linter()
    if not lint_ok:
        sys.exit(1)

    tests_ok = run_unit_tests()
    if not tests_ok:
        sys.exit(1)

    print("\n==================================================")
    print(" ✨ ALL LINTING & UNIT TESTS PASSED CLEANLY! ")
    print("==================================================")


if __name__ == "__main__":
    main()
