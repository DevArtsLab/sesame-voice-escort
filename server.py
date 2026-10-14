#!/usr/bin/env python3
"""
sesame-voice-escort - local send box for Sesame Voice Capture.

Serves index.html and forwards audio to the Sesame device endpoint.
The device secret stays server-side; the browser never sees it.
Derived from the voce demo (https://github.com/29-Cu/voce).

Endpoints:
  GET  /            -> index.html
  GET  /health      -> {"configured": bool, "device_name": str}
  POST /send        -> raw audio body; headers: X-Filename, X-Recorded-At, Idempotency-Key
  POST /test        -> forwards X-Voice-Capture-Test ping
  GET  /history     -> JSON list of sent notes
  GET  /audio/<id>  -> stored copy of a sent note

Port 8377 (PORT env to override). Config: config.json or env vars
SESAME_DEVICE_URL / SESAME_DEVICE_SECRET.
"""

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

BASE_DIR = Path(__file__).parent.resolve()
SENT_DIR = BASE_DIR / "sent"
SENT_DIR.mkdir(exist_ok=True)
HISTORY_FILE = SENT_DIR / "history.json"

MAX_BYTES = 10 * 1024 * 1024  # Sesame limit: 10 MB per note

EXT_TO_MIME = {
    ".m4a": "audio/mp4", ".aac": "audio/mp4", ".mp3": "audio/mpeg",
    ".wav": "audio/wav", ".ogg": "audio/ogg", ".opus": "audio/ogg",
    ".webm": "audio/webm", ".flac": "audio/flac",
}
MIME_TO_EXT = {v: k for k, v in EXT_TO_MIME.items()}
MIME_TO_EXT.update({"audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/ogg": ".ogg",
                    "audio/x-wav": ".wav", "audio/wave": ".wav",
                    "audio/webm;codecs=opus": ".webm"})


def load_config():
    cfg = {}
    cfg_path = BASE_DIR / "config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text())
        except json.JSONDecodeError as e:
            print(f"[sesame-voice-escort] WARNING: bad config.json: {e}", flush=True)
    return {
        "device_url": os.environ.get("SESAME_DEVICE_URL") or cfg.get("device_url", ""),
        "device_secret": os.environ.get("SESAME_DEVICE_SECRET") or cfg.get("device_secret", ""),
        "device_name": cfg.get("device_name", "device"),
    }


CONFIG = load_config()

# macOS keychain holds TLS-inspection roots (Cloudflare Gateway, Zscaler) that
# Python's OpenSSL never sees. setup-certs.sh merges them into certs/ca-bundle.pem.
_CA_BUNDLE = BASE_DIR / "certs" / "ca-bundle.pem"
SSL_CONTEXT = ssl.create_default_context(
    cafile=str(_CA_BUNDLE) if _CA_BUNDLE.exists() else None)


def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return []


def save_history(items):
    tmp = HISTORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=1))
    tmp.replace(HISTORY_FILE)


def mime_for_filename(name):
    return EXT_TO_MIME.get(Path(name).suffix.lower())


def post_to_sesame(audio_bytes, content_type, extra_headers=None):
    """Forward audio to the device endpoint. Returns (status, response_body)."""
    if not CONFIG["device_url"] or not CONFIG["device_secret"]:
        return 503, b'{"error":"device not configured"}'
    headers = {
        "Authorization": f"Bearer {CONFIG['device_secret']}",
        "Content-Type": content_type,
        # Cloudflare bot rules (error 1010) block the default Python-urllib UA.
        "User-Agent": "sesame-voice-escort/1.0 (macOS; +https://capture.sesameai.app)",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(
        CONFIG["device_url"], data=audio_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        return 502, json.dumps({"error": f"upstream unreachable: {e.reason}"}).encode()
    except TimeoutError:
        return 504, b'{"error":"upstream timeout"}'


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "sesame-voice-escort/1.0"

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}", flush=True)

    def _set_headers(self, code=200, content_type="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._set_headers(code, extra={"Content-Length": str(len(body))})
        self.wfile.write(body)

    def _error(self, code, msg):
        self._json({"error": msg}, code)

    def _read_body(self):
        return self.rfile.read(int(self.headers.get("Content-Length", 0)))

    # ── GET ──────────────────────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._serve_file(BASE_DIR / "index.html", "text/html; charset=utf-8")
        elif path == "/health":
            self._json({
                "configured": bool(CONFIG["device_url"] and CONFIG["device_secret"]),
                "device_name": CONFIG["device_name"],
            })
        elif path == "/history":
            self._json(load_history())
        elif path.startswith("/audio/"):
            self._serve_audio(path.rsplit("/", 1)[-1])
        else:
            self._error(404, "Not found")

    # ── POST ─────────────────────────────────────────────────────────────────
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/send":
            self._handle_send()
        elif path == "/test":
            self._handle_test()
        else:
            self._error(404, "Not found")

    def _handle_send(self):
        audio = self._read_body()
        if not audio:
            return self._error(400, "Empty body")
        if len(audio) > MAX_BYTES:
            return self._error(413, f"{len(audio)} bytes exceeds the 10 MB limit")

        filename = self.headers.get("X-Filename", "note.webm")
        content_type = self.headers.get("Content-Type", "").split(";")[0].strip()
        if content_type not in EXT_TO_MIME.values():
            content_type = mime_for_filename(filename) or "application/octet-stream"

        ext = Path(filename).suffix.lower()
        if ext not in EXT_TO_MIME:
            ext = MIME_TO_EXT.get(content_type, ".webm")

        extra = {}
        idem = self.headers.get("Idempotency-Key")
        if idem:
            extra["Idempotency-Key"] = idem
        recorded_at = self.headers.get("X-Recorded-At")
        if recorded_at and recorded_at.isdigit():
            extra["X-Recorded-At"] = recorded_at

        status, upstream = post_to_sesame(audio, content_type, extra)
        ok = 200 <= status < 300

        entry = {
            "id": idem or f"{int(time.time() * 1000)}",
            "filename": filename,
            "content_type": content_type,
            "size": len(audio),
            "sent_at": int(time.time() * 1000),
            "recorded_at": int(recorded_at) if recorded_at and recorded_at.isdigit() else None,
            "ok": ok,
            "upstream_status": status,
        }
        if ok:
            stored = f"{entry['id']}{ext}"
            (SENT_DIR / stored).write_bytes(audio)
            entry["stored"] = stored
        else:
            try:
                entry["upstream_error"] = json.loads(upstream).get("error", upstream[:200].decode("utf-8", "replace"))
            except Exception:
                entry["upstream_error"] = upstream[:200].decode("utf-8", "replace")

        history = load_history()
        history.append(entry)
        save_history(history)
        print(f"[send] {filename} ({len(audio):,} B) -> upstream {status}", flush=True)

        self._json(entry, code=status if ok else 502)

    def _handle_test(self):
        status, upstream = post_to_sesame(b"", "application/octet-stream",
                                        {"X-Voice-Capture-Test": "true"})
        print(f"[test] upstream {status}", flush=True)
        self._json({"ok": 200 <= status < 300, "upstream_status": status,
                    "detail": upstream[:300].decode("utf-8", "replace")},
                   code=200 if status < 500 else 502)

    # ── Static ────────────────────────────────────────────────────────────────
    def _serve_file(self, path, content_type):
        if not path.exists():
            return self._error(404, "File not found")
        data = path.read_bytes()
        self._set_headers(200, content_type, {"Content-Length": str(len(data))})
        self.wfile.write(data)

    def _serve_audio(self, stored_name):
        # Only serve files recorded in the history; no traversal
        safe = Path(stored_name).name
        history = load_history()
        if not any(h.get("stored") == safe for h in history):
            return self._error(404, "Unknown note")
        path = SENT_DIR / safe
        if not path.exists():
            return self._error(404, "Audio file missing")
        ct = EXT_TO_MIME.get(path.suffix.lower(), "application/octet-stream")
        self._serve_file(path, ct)


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 8377))
    if not (CONFIG["device_url"] and CONFIG["device_secret"]):
        print("[sesame-voice-escort] WARNING: no device configured; set config.json or env vars.", flush=True)
    server = HTTPServer((host, port), Handler)
    server.allow_reuse_address = True
    print(f"[sesame-voice-escort] Listening on http://{host}:{port}", flush=True)
    print(f"[sesame-voice-escort] Device: {CONFIG['device_name'] or 'unnamed'}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[sesame-voice-escort] Shutting down.", flush=True)
        server.server_close()


if __name__ == "__main__":
    main()
