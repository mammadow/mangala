"""Unit tests for the CLI interface (cli.py)."""
from unittest.mock import patch
from mangala.cli import (
    _prompt_level,
    _prompt_human_side,
    _prompt_move,
    _ai_move,
    _play_turn,
)
from mangala.engine import initial_state, legal_moves


def test_prompt_level() -> None:
    with patch("mangala.cli._read_line", side_effect=["easy"]):
        assert _prompt_level() == "easy"

    with patch("mangala.cli._read_line", side_effect=["2"]):  # "medium" is 2nd in LEVELS
        assert _prompt_level() == "medium"

    with patch("mangala.cli._read_line", side_effect=["invalid", ""]):
        assert _prompt_level(default="hard") == "hard"


def test_prompt_human_side() -> None:
    with patch("mangala.cli._read_line", side_effect=["1"]):
        assert _prompt_human_side() == 0

    with patch("mangala.cli._read_line", side_effect=["2"]):
        assert _prompt_human_side() == 1

    with patch("mangala.cli._read_line", side_effect=["q"]):
        assert _prompt_human_side() == -1


def test_prompt_move() -> None:
    moves = [1, 2, 3]
    with patch("mangala.cli._read_line", side_effect=["2"]):
        assert _prompt_move(0, moves) == 2

    with patch("mangala.cli._read_line", side_effect=["9", "1"]):  # 9 invalid, then 1
        assert _prompt_move(0, moves) == 1

    with patch("mangala.cli._read_line", side_effect=["quit"]):
        assert _prompt_move(0, moves) == -1


def test_ai_move() -> None:
    s = initial_state()
    pit = _ai_move(s, "easy")
    assert pit in legal_moves(s)


def test_play_turn_ai() -> None:
    s = initial_state()
    players = ["ai", "human"]
    new_s, aborted = _play_turn(s, players, "easy")
    assert not aborted
    assert new_s != s


def test_play_turn_human_abort() -> None:
    s = initial_state()
    players = ["human", "ai"]
    with patch("mangala.cli._prompt_move", return_value=-1):
        new_s, aborted = _play_turn(s, players, "easy")
        assert aborted
