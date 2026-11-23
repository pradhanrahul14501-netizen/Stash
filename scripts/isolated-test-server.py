"""Serve Stash for browser tests with explicit temporary storage only."""

import os
import sys
from pathlib import Path

from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if os.environ.get("STASH_TEST_MODE") != "1":
    raise SystemExit("The browser test server requires STASH_TEST_MODE=1.")

from app_paths import require_isolated_test_storage

require_isolated_test_storage()

import auth
import main

main.initialize_local_runtime()
port = int(os.environ.get("STASH_TEST_PORT", "0"))
server = make_server(
    "127.0.0.1",
    port,
    main.app,
    threaded=True,
)
auth._LOCAL_HOSTS.update({
    f"127.0.0.1:{server.server_port}",
    f"localhost:{server.server_port}",
})
server.serve_forever()
