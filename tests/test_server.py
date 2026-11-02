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
