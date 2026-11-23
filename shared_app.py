"""WSGI entry point for hosting the shared Stash website."""

import os

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix

from auth import initialize_auth
from shared_service import (
    MAX_UPLOAD_BYTES,
    initialize_shared_service,
    shared_blueprint,
    shared_service_enabled,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UI_DIR = os.path.join(BASE_DIR, "ui")
PUBLIC_UI_ASSETS = {
    "app.js",
    "auth-providers.js",
    "settings.js",
    "shared.css",
    "shared.js",
    "stash-icon-192.png",
    "stash-icon-512.png",
    "stash-sw.js",
    "stash.webmanifest",
    "style.css",
}

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES + 1024 * 1024
initialize_auth(app)
if shared_service_enabled():
    initialize_shared_service(app)
app.register_blueprint(shared_blueprint)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=15552000")
    if request.path.startswith("/api/shared/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
@app.get("/shared")
def shared_home():
    return send_from_directory(UI_DIR, "shared.html")


@app.get("/ui/<path:filename>")
def shared_ui_files(filename):
    if filename not in PUBLIC_UI_ASSETS:
        return "Not found", 404
    return send_from_directory(UI_DIR, filename)


@app.get("/site.webmanifest")
def shared_web_manifest():
    response = send_from_directory(
        UI_DIR,
        "stash.webmanifest",
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/stash-sw.js")
def shared_service_worker():
    response = send_from_directory(
        UI_DIR,
        "stash-sw.js",
        mimetype="application/javascript",
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/healthz")
def health_check():
    return jsonify({"status": "ok", "sharedMode": shared_service_enabled()})
