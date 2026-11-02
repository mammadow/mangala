"""Tests for the tools/selfplay.py tournament runner."""
import math
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure tools directory is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from selfplay import estimate_elo_diff, main, play_one_game


def test_estimate_elo_diff() -> None:
    assert estimate_elo_diff(0.0) == -math.inf
    assert estimate_elo_diff(1.0) == math.inf
    assert abs(estimate_elo_diff(0.5) - 0.0) < 1e-9
    # Score ratio 0.75 -> approx +190.8 Elo
    elo = estimate_elo_diff(0.75)
    assert elo is not None and 190 < elo < 192


def test_play_one_game_easy() -> None:
    p1_conf = {"level": "easy"}
    p2_conf = {"level": "easy"}

    # P1 starts
    s1, s2, moves = play_one_game(p1_conf, p2_conf, p1_is_starter=True)
    assert s1 + s2 == 48
    assert moves > 0

    # P2 starts
    s1, s2, moves = play_one_game(p1_conf, p2_conf, p1_is_starter=False)
    assert s1 + s2 == 48
    assert moves > 0


def test_play_one_game_fixed_depth() -> None:
    p1_conf = {"depth": 1}
    p2_conf = {"depth": 1}
    s1, s2, moves = play_one_game(p1_conf, p2_conf, p1_is_starter=True)
    assert s1 + s2 == 48
    assert moves > 0


def test_run_tournament_and_main(capsys: pytest.CaptureFixture[str]) -> None:
    with patch("sys.argv", ["selfplay.py", "--games", "2", "--p1", "easy", "--p2", "easy"]):
        main()
    captured = capsys.readouterr()
    assert "Mangala AI Benchmark Arena" in captured.out
    assert "Game   1/2" in captured.out
    assert "Game   2/2" in captured.out
