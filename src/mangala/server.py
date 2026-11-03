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
import contextlib
import json
import math
import mimetypes
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
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

# In-memory rooms for lightweight multiplayer matches
_ROOMS_LOCK = threading.Lock()
_ROOMS: dict[str, dict[str, Any]] = {}

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


def _parse_time_limit(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        raise BadRequest("'time_limit' must be a number")
    return min(max(float(raw), MIN_TIME_LIMIT), MAX_TIME_LIMIT)


# ── HTTP handler ────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    server_version = f"Mangala/{__version__}"
    quiet = True

    def log_message(self, format: str, *args: Any) -> None:
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
        if path.endswith(".json") or path.endswith(".webmanifest"):
            if path.endswith("manifest.json"):
                ctype = "application/manifest+json"
            else:
                ctype = "application/json; charset=utf-8"
        elif ctype.startswith("text/") or ctype == "application/javascript":
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
            with contextlib.suppress(Exception):
                self.rfile.read(min(length, 65536))
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

    def do_GET(self) -> None:
        path = self._route()
        try:
            if path in ("/", "/index.html"):
                self._send_file(os.path.join(WEB_DIR, "index.html"))
            elif path == "/api/new":
                self._send_json({"state": state_to_dict(initial_state())})
            elif path == "/api/room/poll":
                self._api_room_poll()
            elif path in (
                "/api/move",
                "/api/ai",
                "/api/room/create",
                "/api/room/join",
                "/api/room/move",
            ):
                self._send_error_json(405, "use POST")
            elif path.startswith("/api/"):
                self._send_error_json(404, "not found")
            else:
                self._serve_static(path)
        except BadRequest as e:
            self._send_error_json(400, str(e))
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

    def _drain_body(self) -> None:
        """Drain any pending request body to avoid connection reset errors on Windows/HTTP 1.1."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            if 0 < length <= MAX_BODY_BYTES:
                self.rfile.read(length)
        except Exception:
            pass

    def do_POST(self) -> None:
        path = self._route()
        try:
            if path == "/api/move":
                self._api_move(self._read_json())
            elif path == "/api/ai":
                self._api_ai(self._read_json())
            elif path == "/api/room/create":
                self._api_room_create()
            elif path == "/api/room/join":
                self._api_room_join(self._read_json())
            elif path == "/api/room/move":
                self._api_room_move(self._read_json())
            else:
                self._drain_body()
                self._send_error_json(404, "not found")
        except BadRequest as e:
            self._send_error_json(400, str(e))
        except Exception:  # pragma: no cover - last-resort safety net
            self._send_error_json(500, "internal server error")

    # -- endpoints -----------------------------------------------------------

    def _api_room_create(self) -> None:
        import secrets

        with _ROOMS_LOCK:
            room_id = secrets.token_hex(2).upper()
            while room_id in _ROOMS:  # pragma: no cover - collision safety
                room_id = secrets.token_hex(2).upper()
            s = initial_state()
            _ROOMS[room_id] = {
                "state": s,
                "moves": [],
                "guest_joined": False,
            }
        self._send_json({"room": room_id, "player": 0, "state": state_to_dict(s)})

    def _api_room_join(self, data: dict) -> None:
        room_id = str(data.get("room", "")).strip().upper()
        if not room_id:
            raise BadRequest("'room' code is required")
        with _ROOMS_LOCK:
            room = _ROOMS.get(room_id)
            if not room:
                raise BadRequest(f"room '{room_id}' not found")
            if room["guest_joined"]:
                raise BadRequest(f"room '{room_id}' is full")
            room["guest_joined"] = True
            s = room["state"]
        self._send_json({"room": room_id, "player": 1, "state": state_to_dict(s)})

    def _api_room_move(self, data: dict) -> None:
        room_id = str(data.get("room", "")).strip().upper()
        player = data.get("player")
        pit = data.get("pit")
        if not room_id or player not in (0, 1) or not isinstance(pit, int) or isinstance(pit, bool):
            raise BadRequest("valid 'room', 'player' (0 or 1), and integer 'pit' required")

        with _ROOMS_LOCK:
            room = _ROOMS.get(room_id)
            if not room:
                raise BadRequest(f"room '{room_id}' not found")
            s = room["state"]
            if s.current_player != player:
                raise BadRequest("not your turn")
            if pit not in legal_moves(s):
                raise BadRequest(f"pit {pit} is not legal")

            next_state, events = apply_move(s, pit)
            room["state"] = next_state
            seq = len(room["moves"])
            ev_dict = {"capture": events["capture"], "extra_turn": events["extra_turn"]}
            room["moves"].append({
                "seq": seq,
                "player": player,
                "pit": pit,
                "events": ev_dict,
                "state": state_to_dict(next_state),
            })
        self._send_json({
            "seq": seq,
            "state": state_to_dict(next_state),
            "events": ev_dict,
        })

    def _api_room_poll(self) -> None:
        from urllib.parse import parse_qs

        qs = parse_qs(urlsplit(self.path).query)
        room_id = qs.get("room", [""])[0].strip().upper()
        since_raw = qs.get("since", ["0"])[0]
        try:
            since = int(since_raw)
        except ValueError:
            raise BadRequest("'since' must be an integer sequence") from None

        if not room_id:
            raise BadRequest("'room' query parameter required")

        with _ROOMS_LOCK:
            room = _ROOMS.get(room_id)
            if not room:
                raise BadRequest(f"room '{room_id}' not found")
            moves = [m for m in room["moves"] if m["seq"] >= since]
            s = room["state"]
            guest = room["guest_joined"]

        self._send_json({
            "room": room_id,
            "guest_joined": guest,
            "state": state_to_dict(s),
            "moves": moves,
        })


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
                use_book=True,
            )
        self._send_json({"pit": result.move, "score": result.score, "depth": result.depth})


def launch_app_window(url: str) -> bool:
    """Attempt to launch the URL in a dedicated, frameless desktop application window."""
    candidates = ["msedge", "google-chrome", "chrome", "chromium", "brave"]
    for cmd in candidates:
        exe = shutil.which(cmd)
        if exe:
            try:
                subprocess.Popen(
                    [exe, f"--app={url}"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                pass
    return False


def make_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    """Create (but do not start) the HTTP server. ``port=0`` picks a free port."""
    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mangala", description="Play Turkish Mangala in your browser or desktop.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help=f"interface to bind (default {DEFAULT_HOST}; use 0.0.0.0 to share on your LAN)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port (default {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    parser.add_argument("--app", action="store_true", help="launch in dedicated desktop application window")
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
        opened = False
        if args.app:
            with contextlib.suppress(Exception):
                opened = launch_app_window(url)
        if not opened:
            with contextlib.suppress(Exception):
                webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        server.server_close()


def main_app(argv: list[str] | None = None) -> None:
    """Launch Turkish Mangala in desktop application mode (entry point for `mangala-gui`)."""
    args = list(argv) if argv is not None else sys.argv[1:]
    if "--app" not in args:
        args.append("--app")
    main(args)


if __name__ == "__main__":
    main()
