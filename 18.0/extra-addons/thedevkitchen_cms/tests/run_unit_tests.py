#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit test runner for thedevkitchen_cms.

Runs every plain unittest.TestCase file under tests/unit/ (no Odoo
environment, no database). TransactionCase-based tests live in
tests/integration/ instead and are run separately, via
`odoo -u thedevkitchen_cms --test-enable` — scripts/validate_coverage.sh
auto-detects and runs tests/integration/ once this file exists (see its
"runner exists" branch, which additionally checks for a tests/integration
directory), which is why this file needs to exist even though tests/unit/
alone previously worked fine with the generic fallback runner.

Usage: python3 run_unit_tests.py
"""
import sys
import unittest
from pathlib import Path

import odoo.addons

_ADDONS_ROOT = str(Path(__file__).resolve().parents[2])  # /mnt/extra-addons
if _ADDONS_ROOT not in odoo.addons.__path__:
    odoo.addons.__path__.insert(0, _ADDONS_ROOT)

_MODULE_DIR = Path(__file__).resolve().parent.parent  # .../thedevkitchen_cms
_UNIT_DIR = _MODULE_DIR / "tests" / "unit"


def main():
    loader = unittest.TestLoader()
    suite = loader.discover(str(_UNIT_DIR), pattern="test_*.py", top_level_dir=str(_MODULE_DIR))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
