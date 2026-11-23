"""Release smoke: capture text, search, open, restart, and search again."""

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_paths import is_temporary_storage

PYTHON = Path(os.environ.get("STASH_VENV_DIR", ROOT / ".venv")) / "bin" / "python"
SERVER_SCRIPT = ROOT / "scripts" / "isolated-test-server.py"
STORAGE_ROOT = Path(tempfile.mkdtemp(prefix="stash-browser-journey-"))
if not is_temporary_storage(STORAGE_ROOT / "storage"):
    raise RuntimeError("Browser tests refused to start outside a dedicated temporary storage directory.")
ARTIFACT_ROOT = Path(os.environ.get(
    "STASH_BROWSER_ARTIFACT_DIR",
    STORAGE_ROOT / "screenshots",
))
ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
SERVER = None


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


PORT = free_port()
BASE_URL = f"http://127.0.0.1:{PORT}"


def start_server():
    global SERVER
    environment = {
        **os.environ,
        "STASH_TEST_MODE": "1",
        "STASH_STORAGE_DIR": str(STORAGE_ROOT / "storage"),
        "STASH_DISABLE_CLIPBOARD_MONITOR": "1",
        "STASH_DISABLE_BACKGROUND_WORKERS": "1",
        "STASH_TEST_PORT": str(PORT),
        "PYTHONUNBUFFERED": "1",
    }
    SERVER = subprocess.Popen(
        [str(PYTHON), str(SERVER_SCRIPT)],
        cwd=ROOT,
        env=environment,
    )
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if SERVER.poll() is not None:
            raise RuntimeError(f"Temporary Stash server exited with status {SERVER.returncode}.")
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    raise TimeoutError("Temporary Stash server did not become healthy in 30 seconds.")


def stop_server():
    global SERVER
    if SERVER is None or SERVER.poll() is not None:
        return
    SERVER.terminate()
    try:
        SERVER.wait(timeout=5)
    except subprocess.TimeoutExpired:
        SERVER.kill()
        SERVER.wait(timeout=5)


def screenshot(page, name, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.wait_for_timeout(200)
    dimensions = page.evaluate("""() => ({
      viewport: window.innerWidth,
      document: document.documentElement.scrollWidth,
      body: document.body.scrollWidth
    })""")
    if dimensions["document"] > dimensions["viewport"]:
        raise AssertionError(f"{name} has horizontal overflow at {width}px: {dimensions}")
    page.screenshot(path=str(ARTIFACT_ROOT / f"{name}-{width}.png"), full_page=True)


def main():
    if not PYTHON.is_file():
        raise FileNotFoundError(f"Stash test environment is missing: {PYTHON}")
    page_errors = []
    start_server()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(BASE_URL, wait_until="networkidle")
            page.locator("#authForm").wait_for(state="visible")
            screenshot(page, "first-run", 1440)
            screenshot(page, "first-run", 600)

            page.locator("#authUsername").fill("journeytester")
            page.locator("#authPassword").fill("StashJourneyPass!2026")
            page.locator("#authPasswordConfirm").fill("StashJourneyPass!2026")
            page.locator("#authSubmit").click()
            page.locator("#app:not([hidden])").wait_for(state="visible", timeout=15_000)
            page.locator("#searchInput").wait_for(state="visible")

            phrase = f"browser journey item {time.time_ns()}"
            captured = page.evaluate("""async phrase => {
              const response = await fetch('/api/clipboard/mobile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: phrase })
              });
              return { status: response.status, body: await response.json() };
            }""", phrase)
            if captured["status"] != 201:
                raise AssertionError(f"Capture failed: {captured}")

            page.locator("#searchInput").fill(phrase)
            row = page.locator(".copy-row").filter(has_text=phrase)
            row.wait_for(state="visible", timeout=10_000)
            row.click()
            page.locator("#copyViewer:not([hidden])").wait_for(state="visible")
            page.locator("#viewerContent").get_by_text(phrase, exact=True).wait_for(state="visible")
            page.locator("#closeViewer").click()
            page.locator("#searchInput").fill("")
            screenshot(page, "main-navigation", 1440)
            screenshot(page, "main-navigation", 600)

            stop_server()
            start_server()
            page.reload(wait_until="networkidle")
            page.locator("#app:not([hidden])").wait_for(state="visible", timeout=15_000)
            page.locator("#searchInput").fill(phrase)
            reopened = page.locator(".copy-row").filter(has_text=phrase)
            reopened.wait_for(state="visible", timeout=10_000)
            reopened.click()
            page.locator("#viewerContent").get_by_text(phrase, exact=True).wait_for(state="visible")
            if page_errors:
                raise AssertionError(f"Browser JavaScript errors: {page_errors}")
            browser.close()
        print(
            "PASS: encrypted temporary-library capture -> search -> open -> server restart -> search/open; "
            f"responsive screenshots: {ARTIFACT_ROOT}"
        )
    finally:
        stop_server()


if __name__ == "__main__":
    main()
