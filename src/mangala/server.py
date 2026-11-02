"""
server.py — Lightweight web backend for Turkish Mangala.

Reuses the pure engine (engine.py) and AI (ai.py). Serves a single-file
HTML/CSS/JS front-end (web/index.html) and exposes a tiny stateless JSON API:

    GET  /                 -> the web UI
    GET  /api/new          -> {state}
    POST /api/move         -> {state, pit}            -> {state, events}
    POST /api/ai           -> {state, time_limit?}    -> {pit}

Every request is validated; malformed input gets a JSON ``400`` response.

Run with:   mangala            (or: python -m mangala)
No extra dependencies — uses only the Python standard library.
"""
from __future__ import annotations

import argparse
import json
import math
import mimetypes
import os
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import urlsplit

from . import __version__
from . import ai as ai_module
from .engine import (
    GameState,
    apply_move,
    initial_state,
    is_terminal,
    legal_moves,
    validate_state,
)

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
DEFAULT_HOST, DEFAULT_PORT = "127.0.0.1", 8000

MAX_BODY_BYTES = 4096
MIN_TIME_LIMIT, MAX_TIME_LIMIT = 0.05, 5.0
MAX_CONCURRENT_SEARCHES = 4

# Caps CPU use: at most this many AI searches run at the same time.
_search_slots = threading.BoundedSemaphore(MAX_CONCURRENT_SEARCHES)

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'"
    ),
}


class BadRequest(Exception):
    """Client sent something invalid; message is returned as JSON."""


# ── (de)serialisation ──────────────────────────────────────────────────────────

def state_to_dict(s: GameState) -> dict:
    return {
        "pits": list(s.pits),
        "current_player": s.current_player,
        "game_over": s.game_over,
        "winner": s.winner,
        "legal": legal_moves(s),
    }


def dict_to_state(d: Any) -> GameState:
    """Build and validate a GameState from untrusted JSON."""
    if not isinstance(d, dict):
        raise BadRequest("'state' must be an object")
    try:
        state = GameState(
            pits=d["pits"],
            current_player=d["current_player"],
            game_over=d.get("game_over", False),
            winner=d.get("winner"),
        )
    except KeyError as e:
        raise BadRequest(f"state is missing field {e.args[0]!r}") from None
    try:
        validate_state(state)
    except ValueError as e:
        raise BadRequest(f"invalid state: {e}") from None
    return state


def _parse_time_limit(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        raise BadRequest("'time_limit' must be a number")
    return min(max(float(raw), MIN_TIME_LIMIT), MAX_TIME_LIMIT)


# ── HTTP handler ────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = f"Mangala/{__version__}"
    quiet = True

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        if not self.quiet:
            super().log_message(format, *args)

    # -- responses -----------------------------------------------------------

    def _headers(self, status: int, content_type: str, length: int,
                 cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        for k, v in _SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def _send_json(self, obj: Any, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _send_file(self, path: str) -> None:
        try:
            with open(path, "rb") as f:
                body = f.read()
        except OSError:
            self._send_error_json(404, "not found")
            return
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        self._headers(200, ctype, len(body), cache="no-cache")
        self.wfile.write(body)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            raise BadRequest("invalid Content-Length") from None
        if length <= 0:
            raise BadRequest("request body required")
        if length > MAX_BODY_BYTES:
            raise BadRequest("request body too large")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise BadRequest("body must be valid JSON") from None
        if not isinstance(data, dict):
            raise BadRequest("body must be a JSON object")
        return data

    # -- routing -------------------------------------------------------------

    def _route(self) -> str:
        return urlsplit(self.path).path

    def do_GET(self) -> None:  # noqa: N802
        path = self._route()
        try:
            if path in ("/", "/index.html"):
                self._send_file(os.path.join(WEB_DIR, "index.html"))
            elif path == "/api/new":
                self._send_json({"state": state_to_dict(initial_state())})
            elif path in ("/api/move", "/api/ai"):
                self._send_error_json(405, "use POST")
            elif path.startswith("/api/"):
                self._send_error_json(404, "not found")
            else:
                self._serve_static(path)
        except Exception:  # pragma: no cover - last-resort safety net
            self._send_error_json(500, "internal server error")

    def _serve_static(self, path: str) -> None:
        """Serve any other file under web/ (defensive; UI is single-file)."""
        rel = os.path.normpath(path.lstrip("/"))
        full = os.path.realpath(os.path.join(WEB_DIR, rel))
        root = os.path.realpath(WEB_DIR)
        if os.path.commonpath([full, root]) == root and os.path.isfile(full):
            self._send_file(full)
        else:
            self._send_error_json(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        path = self._route()
        try:
            if path == "/api/move":
                self._api_move(self._read_json())
            elif path == "/api/ai":
                self._api_ai(self._read_json())
            else:
                self._send_error_json(404, "not found")
        except BadRequest as e:
            self._send_error_json(400, str(e))
        except Exception:  # pragma: no cover - last-resort safety net
            self._send_error_json(500, "internal server error")

    # -- endpoints -----------------------------------------------------------

    def _api_move(self, data: dict) -> None:
        state = dict_to_state(data.get("state"))
        pit = data.get("pit")
        if isinstance(pit, bool) or not isinstance(pit, int):
            raise BadRequest("'pit' must be an integer")
        if pit not in legal_moves(state):
            raise BadRequest("illegal move")
        new_state, events = apply_move(state, pit)
        self._send_json({"state": state_to_dict(new_state), "events": dict(events)})

    def _api_ai(self, data: dict) -> None:
        state = dict_to_state(data.get("state"))
        time_limit = _parse_time_limit(data.get("time_limit"))
        if is_terminal(state) or not legal_moves(state):
            self._send_json({"pit": None})
            return
        with _search_slots:
            result = ai_module.analyse(
                state,
                time_limit=time_limit if time_limit is not None else ai_module.DEFAULT_TIME_LIMIT,
            )
        self._send_json({"pit": result.move, "score": result.score, "depth": result.depth})


def make_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """Create (but do not start) the HTTP server. ``port=0`` picks a free port."""
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="mangala", description="Play Turkish Mangala in your browser.")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help=f"interface to bind (default {DEFAULT_HOST}; use 0.0.0.0 to share on your LAN)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    parser.add_argument("--verbose", action="store_true", help="log every request")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    Handler.quiet = not args.verbose
    server = make_server(args.host, args.port)
    shown_host = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    url = f"http://{shown_host}:{server.server_address[1]}/"
    # ASCII only: the default Windows console codepage can't print arrows.
    print(f"Turkish Mangala  ->  {url}")
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
