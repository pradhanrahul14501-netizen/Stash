# Start Stash on macOS

From the project folder, run:

```sh
./scripts/stash
```

That command creates `.venv` if needed, installs the complete pinned dependency lock (including `cryptography`), checks package consistency, initializes the local encrypted library, and starts the app on `http://127.0.0.1:5050`. Keep the terminal open while using Stash. `GET /health` returns `200` when the server is reachable.

The first run can take a few minutes while it downloads dependencies. A failed package install stops before the app starts and prints a setup error.

To install the environment without starting Stash, run `./scripts/stash setup`. To run the Python API tests, run `./scripts/stash test`; tests are forced to use a new temporary storage folder and a test-only encryption key.

The beta currently targets CPython 3.14 on macOS. It depends on macOS Keychain, AppKit, Finder, and system clipboard APIs. The lock file is pinned for macOS arm64.
