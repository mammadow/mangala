"""Integration tests for the HTTP server and REST API."""
import json
import threading
from collections.abc import Generator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from mangala.server import make_server


@pytest.fixture(scope="module")
def server_url() -> Generator[str, None, None]:
    # Bind to localhost on port 0 (ephemeral port assigned by OS)
    server = make_server("127.0.0.1", 0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def _request(url: str, method: str = "GET", data: dict | None = None,
             raw_data: bytes | None = None) -> tuple[int, dict, dict]:
    headers = {}
    body_bytes = None
    if data is not None:
        body_bytes = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif raw_data is not None:
        body_bytes = raw_data
        headers["Content-Type"] = "application/json"

    req = Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urlopen(req, timeout=5.0) as resp:
            code = resp.status
            resp_headers = dict(resp.headers)
            body = resp.read().decode("utf-8")
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = body
            return code, resp_headers, parsed
    except HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = body
        return e.code, dict(e.headers), parsed


def test_get_root_and_security_headers(server_url: str) -> None:
    code, headers, body = _request(f"{server_url}/")
    assert code == 200
    assert "Turkish Mangala" in body
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in headers


def test_api_new(server_url: str) -> None:
    code, _, data = _request(f"{server_url}/api/new")
    assert code == 200
    state = data["state"]
    assert sum(state["pits"]) == 48
    assert state["current_player"] == 0
    assert not state["game_over"]
    assert state["legal"] == [0, 1, 2, 3, 4, 5]


def test_api_move_valid(server_url: str) -> None:
    code, _, new_res = _request(f"{server_url}/api/new")
    s0 = new_res["state"]

    code, _, res = _request(f"{server_url}/api/move", method="POST", data={
        "state": s0,
        "pit": 0,
    })
    assert code == 200
    assert "state" in res
    assert "events" in res
    assert res["state"]["pits"][0] == 1  # leaves 1 behind


def test_api_move_illegal(server_url: str) -> None:
    code, _, new_res = _request(f"{server_url}/api/new")
    s0 = new_res["state"]

    # Player 0 picking Player 2 pit (pit 7)
    code, _, res = _request(f"{server_url}/api/move", method="POST", data={
        "state": s0,
        "pit": 7,
    })
    assert code == 400
    assert "error" in res


def test_api_move_invalid_state(server_url: str) -> None:
    code, _, res = _request(f"{server_url}/api/move", method="POST", data={
        "state": {"pits": [-1] * 14, "current_player": 0},
        "pit": 0,
    })
    assert code == 400
    assert "invalid state" in res["error"]


def test_api_ai_search(server_url: str) -> None:
    code, _, new_res = _request(f"{server_url}/api/new")
    s0 = new_res["state"]

    code, _, res = _request(f"{server_url}/api/ai", method="POST", data={
        "state": s0,
        "time_limit": 0.2,
    })
    assert code == 200
    assert res["pit"] in [0, 1, 2, 3, 4, 5]
    assert "score" in res
    assert "depth" in res


def test_api_ai_terminal_state(server_url: str) -> None:
    term_state = {
        "pits": [0] * 14,
        "current_player": 0,
        "game_over": True,
        "winner": 0,
    }
    term_state["pits"][6] = 25
    term_state["pits"][13] = 23
    code, _, res = _request(f"{server_url}/api/ai", method="POST", data={
        "state": term_state,
    })
    assert code == 200
    assert res["pit"] is None


def test_api_ai_invalid_time_limit(server_url: str) -> None:
    code, _, new_res = _request(f"{server_url}/api/new")
    code, _, res = _request(f"{server_url}/api/ai", method="POST", data={
        "state": new_res["state"],
        "time_limit": "infinity",
    })
    assert code == 400
    assert "time_limit" in res["error"]


def test_request_body_too_large(server_url: str) -> None:
    oversized = b"x" * 5000
    code, _, res = _request(f"{server_url}/api/move", method="POST", raw_data=oversized)
    assert code == 400
    assert "too large" in res["error"]


def test_method_not_allowed(server_url: str) -> None:
    code, _, res = _request(f"{server_url}/api/move", method="GET")
    assert code == 405
    assert "use POST" in res["error"]


def test_not_found(server_url: str) -> None:
    code, _, res = _request(f"{server_url}/nonexistent")
    assert code == 404
    assert res["error"] == "not found"


def test_path_traversal_blocked(server_url: str) -> None:
    code, _, _res = _request(f"{server_url}/../pyproject.toml")
    assert code == 404


def test_serve_static_engine_js(server_url: str) -> None:
    code, headers, body = _request(f"{server_url}/engine.js")
    assert code == 200
    assert "javascript" in headers.get("Content-Type", "")
    assert "applyMove" in body


def test_api_unknown_endpoints(server_url: str) -> None:
    code, _, res = _request(f"{server_url}/api/unknown_route")
    assert code == 404
    assert res["error"] == "not found"

    code, _, res = _request(f"{server_url}/api/unknown_route", method="POST", data={})
    assert code == 404
    assert res["error"] == "not found"


def test_api_move_invalid_pit_types(server_url: str) -> None:
    code, _, new_res = _request(f"{server_url}/api/new")
    s0 = new_res["state"]

    # String pit
    code, _, res = _request(f"{server_url}/api/move", method="POST", data={"state": s0, "pit": "three"})
    assert code == 400
    assert "pit" in res["error"]

    # Boolean pit
    code, _, res = _request(f"{server_url}/api/move", method="POST", data={"state": s0, "pit": True})
    assert code == 400
    assert "pit" in res["error"]


def test_api_bad_request_payloads(server_url: str) -> None:
    # Not an object
    code, _, res = _request(f"{server_url}/api/move", method="POST", data={"state": "string_state", "pit": 0})
    assert code == 400
    assert "must be an object" in res["error"]

    # Missing field in state
    code, _, res = _request(f"{server_url}/api/move", method="POST", data={"state": {"pits": [4] * 14}, "pit": 0})
    assert code == 400
    assert "missing field" in res["error"]

    # Malformed JSON
    code, _, res = _request(f"{server_url}/api/move", method="POST", raw_data=b"{bad-json")
    assert code == 400
    assert "valid JSON" in res["error"]

    # JSON array instead of dict
    code, _, res = _request(f"{server_url}/api/move", method="POST", raw_data=b"[1, 2, 3]")
    assert code == 400
    assert "JSON object" in res["error"]

    # Empty payload
    code, _, res = _request(f"{server_url}/api/move", method="POST", raw_data=b"")
    assert code == 400
    assert "request body required" in res["error"]


def test_server_main_version() -> None:
    from mangala.server import main
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_server_main_run_and_stop() -> None:
    from unittest.mock import patch

    from mangala.server import main

    with (
        patch("http.server.ThreadingHTTPServer.serve_forever", side_effect=KeyboardInterrupt),
        patch("webbrowser.open"),
    ):
        main(["--port", "0", "--no-browser", "--verbose"])


def test_handler_log_message_verbose() -> None:
    from unittest.mock import patch

    from mangala.server import Handler

    h = Handler.__new__(Handler)
    h.quiet = False
    h.client_address = ("127.0.0.1", 12345)
    with patch.object(Handler, "log_date_time_string", return_value="now"), patch("sys.stderr.write"):
        h.log_message("test format %s", "arg")
    Handler.quiet = True


def test_handler_send_file_oserror() -> None:
    from unittest.mock import patch

    from mangala.server import Handler

    h = Handler.__new__(Handler)
    with (
        patch("builtins.open", side_effect=OSError("not found")),
        patch.object(h, "_send_error_json") as mock_err,
    ):
        h._send_file("non_existent_file.xyz")
        assert mock_err.called
        assert mock_err.call_args[0] == (404, "not found")


def test_handler_send_file_generic_json() -> None:
    from unittest.mock import MagicMock, mock_open, patch

    from mangala.server import Handler

    h = Handler.__new__(Handler)
    h.wfile = MagicMock()
    with (
        patch("builtins.open", mock_open(read_data=b'{"key": 1}')),
        patch.object(h, "_headers") as mock_headers,
    ):
        h._send_file("sample.json")
        assert mock_headers.called
        assert mock_headers.call_args[0][1] == "application/json; charset=utf-8"
        assert h.wfile.write.called


def test_handler_read_json_bad_content_length() -> None:
    from mangala.server import BadRequest, Handler

    h = Handler.__new__(Handler)
    h.headers = {"Content-Length": "not_an_int"}
    with pytest.raises(BadRequest, match="invalid Content-Length"):
        h._read_json()


def test_handler_drain_body_exception() -> None:
    from mangala.server import Handler

    h = Handler.__new__(Handler)
    h.headers = {"Content-Length": "10"}

    class BadRFile:
        def read(self, n: int) -> bytes:
            raise OSError("connection reset")

    h.rfile = BadRFile()
    # Must suppress silently
    h._drain_body()


def test_server_main_with_browser_launch() -> None:
    from unittest.mock import patch

    from mangala.server import main

    with (
        patch("http.server.ThreadingHTTPServer.serve_forever", side_effect=KeyboardInterrupt),
        patch("webbrowser.open") as mock_open,
    ):
        main(["--port", "0"])
        assert mock_open.called


def test_static_manifest_and_sw(server_url: str) -> None:
    code, headers, body = _request(f"{server_url}/manifest.json")
    assert code == 200
    assert "application/manifest+json" in headers.get("Content-Type", "")
    assert isinstance(body, dict) and body.get("name") == "Turkish Mangala"

    code, headers, body = _request(f"{server_url}/sw.js")
    assert code == 200
    assert "javascript" in headers.get("Content-Type", "")


def test_room_lifecycle_and_multiplayer_flow(server_url: str) -> None:
    # 1. Create Room
    code, _, data = _request(f"{server_url}/api/room/create", method="POST", data={})
    assert code == 200
    room_id = data["room"]
    assert len(room_id) == 4
    assert data["player"] == 0
    assert "state" in data

    # 2. Poll initial state
    code, _, poll_data = _request(f"{server_url}/api/room/poll?room={room_id}&since=0")
    assert code == 200
    assert not poll_data["guest_joined"]
    assert len(poll_data["moves"]) == 0

    # 3. Join Room
    code, _, join_data = _request(f"{server_url}/api/room/join", method="POST", data={"room": room_id})
    assert code == 200
    assert join_data["player"] == 1

    # 4. Join full room -> 400
    code, _, err = _request(f"{server_url}/api/room/join", method="POST", data={"room": room_id})
    assert code == 400
    assert "full" in err["error"]

    # 5. Wrong turn move -> 400
    code, _, err = _request(f"{server_url}/api/room/move", method="POST", data={
        "room": room_id,
        "player": 1,
        "pit": 7,
    })
    assert code == 400
    assert "not your turn" in err["error"]

    # 6. Illegal pit move -> 400
    code, _, err = _request(f"{server_url}/api/room/move", method="POST", data={
        "room": room_id,
        "player": 0,
        "pit": 99,
    })
    assert code == 400
    assert "not legal" in err["error"]

    # 7. Valid move -> 200
    code, _, mv_data = _request(f"{server_url}/api/room/move", method="POST", data={
        "room": room_id,
        "player": 0,
        "pit": 0,
    })
    assert code == 200
    assert mv_data["seq"] == 0

    # 8. Poll pending moves -> returns 1 move
    code, _, poll_data = _request(f"{server_url}/api/room/poll?room={room_id}&since=0")
    assert code == 200
    assert poll_data["guest_joined"]
    assert len(poll_data["moves"]) == 1
    assert poll_data["moves"][0]["pit"] == 0


def test_room_error_handling(server_url: str) -> None:
    # Join empty or invalid room
    code, _, err = _request(f"{server_url}/api/room/join", method="POST", data={"room": ""})
    assert code == 400
    assert "required" in err["error"]

    code, _, err = _request(f"{server_url}/api/room/join", method="POST", data={"room": "ZZZZ"})
    assert code == 400
    assert "not found" in err["error"]

    # Move on invalid room
    code, _, err = _request(f"{server_url}/api/room/move", method="POST", data={
        "room": "ZZZZ", "player": 0, "pit": 0
    })
    assert code == 400
    assert "not found" in err["error"]

    # Move with invalid payload
    code, _, err = _request(f"{server_url}/api/room/move", method="POST", data={
        "room": "", "player": 9, "pit": "bad"
    })
    assert code == 400

    # Poll errors
    code, _, err = _request(f"{server_url}/api/room/poll")
    assert code == 400
    assert "required" in err["error"]

    code, _, err = _request(f"{server_url}/api/room/poll?room=ABCD&since=invalid")
    assert code == 400
    assert "integer" in err["error"]

    code, _, err = _request(f"{server_url}/api/room/poll?room=ZZZZ&since=0")
    assert code == 400
    assert "not found" in err["error"]

    # Method not allowed for room POST endpoints
    for ep in ("/api/room/create", "/api/room/join", "/api/room/move"):
        code, _, err = _request(f"{server_url}{ep}", method="GET")
        assert code == 405
        assert "use POST" in err["error"]

