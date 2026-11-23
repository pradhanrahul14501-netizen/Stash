#!/usr/bin/env python3
"""Run Stash's unittest suite only against an explicit temporary library."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_paths import require_isolated_test_storage


try:
    isolated_storage = require_isolated_test_storage()
except RuntimeError as error:
    raise SystemExit(str(error)) from error

print(f"Running Stash tests with isolated storage: {isolated_storage}", flush=True)
environment = os.environ.copy()
environment["STASH_TEST_MODE"] = "1"
environment["STASH_STORAGE_DIR"] = isolated_storage
environment["STASH_DISABLE_CLIPBOARD_MONITOR"] = "1"
raise SystemExit(subprocess.call(
    [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "ava" / "tests"), "-p", "test_*.py", "-v"],
    cwd=ROOT,
    env=environment,
))
