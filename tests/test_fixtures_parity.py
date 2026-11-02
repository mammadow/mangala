"""Verifies engine_parity_fixtures.json against python engine to ensure fixture validity."""
import json
import os

from mangala.engine import apply_move
from mangala.server import dict_to_state, state_to_dict

FIXTURES_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "engine_parity_fixtures.json")


def test_python_engine_matches_parity_fixtures() -> None:
    assert os.path.isfile(FIXTURES_PATH), "Parity fixture file missing"
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        fixtures = json.load(f)

    assert len(fixtures) >= 600

    for i, item in enumerate(fixtures):
        state = dict_to_state(item["initial"])
        move = item["move"]
        ns, ev = apply_move(state, move)

        expected_state = item["expected_state"]
        expected_events = item["expected_events"]

        actual_dict = state_to_dict(ns)
        assert actual_dict["pits"] == expected_state["pits"], f"Pits mismatch at #{i}"
        assert actual_dict["current_player"] == expected_state["current_player"]
        assert actual_dict["game_over"] == expected_state["game_over"]
        assert actual_dict["winner"] == expected_state["winner"]
        assert dict(ev) == expected_events, f"Events mismatch at #{i}"


def test_generate_fixtures_tool() -> None:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from generate_parity_fixtures import generate_fixtures
    fixtures = generate_fixtures(count=3)
    assert len(fixtures) > 0
    assert "initial" in fixtures[0]
    assert "move" in fixtures[0]
    assert "expected_state" in fixtures[0]
    assert "expected_events" in fixtures[0]
