"""Shared application paths, with an explicit override for isolated tests."""

import os
import sys
import tempfile


def is_temporary_storage(path):
    """Return true only when a storage override is inside a system temp root."""
    candidate = os.path.realpath(os.path.abspath(path))
    for root in (tempfile.gettempdir(), "/tmp", "/private/tmp"):
        resolved_root = os.path.realpath(root)
        try:
            if (
                candidate != resolved_root
                and os.path.commonpath((resolved_root, candidate)) == resolved_root
            ):
                return True
        except ValueError:
            continue
    return False


def require_isolated_test_storage(path=None):
    """Fail closed unless tests explicitly use a dedicated temporary folder."""
    if os.environ.get("STASH_TEST_MODE") != "1":
        raise RuntimeError("Tests require STASH_TEST_MODE=1 and a temporary STASH_STORAGE_DIR.")
    configured = path or os.environ.get("STASH_STORAGE_DIR")
    if not configured or not is_temporary_storage(configured):
        raise RuntimeError("Tests refused to start: STASH_STORAGE_DIR must be a dedicated temporary directory.")
    return os.path.realpath(os.path.abspath(configured))


def _test_runner_is_active():
    """Catch direct unittest/pytest launches that bypass the Stash test script."""
    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    main = sys.modules.get("__main__")
    module_name = getattr(getattr(main, "__spec__", None), "name", "") or ""
    main_file = os.path.realpath(getattr(main, "__file__", "") or "")
    return module_name.startswith("unittest.") or (
        os.sep + "ava" + os.sep + "tests" + os.sep in main_file
        and os.path.basename(main_file).startswith("test_")
    )


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_STORAGE_OVERRIDE = os.environ.get("STASH_STORAGE_DIR")
if os.environ.get("STASH_TEST_MODE") == "1":
    require_isolated_test_storage(_STORAGE_OVERRIDE)
elif _test_runner_is_active():
    raise RuntimeError(
        "Stash refused to start under a test runner without isolated temporary storage. "
        "Use scripts/stash test or set STASH_TEST_MODE=1 and STASH_STORAGE_DIR to a temp folder."
    )
STORAGE_DIR = os.path.abspath(
    _STORAGE_OVERRIDE or os.path.join(BASE_DIR, "storage")
)
