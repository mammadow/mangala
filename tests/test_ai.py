"""Tests for the Mangala search engine (ai.py)."""
import threading
import time

import pytest

from mangala.ai import (
    analyse,
    best_move,
    best_move_for_level,
)
from mangala.engine import (
    TOTAL,
    GameState,
    initial_state,
    legal_moves,
)


def test_initial_move_legal() -> None:
    s = initial_state()
    move = best_move(s, depth=2)
    assert move in legal_moves(s)


def test_tactical_capture_preferred() -> None:
    # State where pit 4 captures 10 stones in pit 7
    pits = [0] * TOTAL
    pits[4] = 4   # sows into 5, 6, 7
    pits[7] = 9   # 9 + 1 = 10 (even capture!)
    pits[1] = 2   # distraction move
    pits[6] = 16
    pits[13] = 17
    s = GameState(pits=pits, current_player=0)
    res = analyse(s, depth=3)
    assert res.move == 4
    assert res.score > 5.0


def test_single_legal_move_instant() -> None:
    pits = [0] * TOTAL
    pits[2] = 3
    pits[6] = 22
    pits[13] = 23
    s = GameState(pits=pits, current_player=0)
    res = analyse(s, time_limit=2.0)
    assert res.move == 2
    assert res.nodes == 0  # no tree search required
    assert res.pv == [2]


def test_terminal_state_raises() -> None:
    s = GameState(pits=[0] * TOTAL, current_player=0, game_over=True)
    with pytest.raises(ValueError, match="no legal moves"):
        analyse(s)


def test_invalid_depth_or_time() -> None:
    s = initial_state()
    with pytest.raises(ValueError, match="depth must be >= 1"):
        analyse(s, depth=0)
    with pytest.raises(ValueError, match="time_limit must be > 0"):
        analyse(s, time_limit=0)


def test_fixed_depth_determinism() -> None:
    s = initial_state()
    r1 = analyse(s, depth=4)
    r2 = analyse(s, depth=4)
    assert r1.move == r2.move
    assert abs(r1.score - r2.score) < 1e-9


def test_difficulty_presets() -> None:
    s = initial_state()
    for level in ("easy", "medium", "hard", "expert"):
        m = best_move_for_level(s, level=level)
        assert m in legal_moves(s)

    with pytest.raises(ValueError, match="unknown level"):
        best_move_for_level(s, level="godmode")


def test_time_limit_adherence() -> None:
    s = initial_state()
    budget = 0.2
    t0 = time.monotonic()
    res = analyse(s, time_limit=budget)
    elapsed = time.monotonic() - t0
    # Search should finish reasonably close to the budget
    assert elapsed < budget + 0.8
    assert res.depth >= 2
    assert res.move in legal_moves(s)


def test_concurrent_searches_thread_safety() -> None:
    """Verify that multiple threads running searches simultaneously do not

    pollute or cancel each other's time limit / transposition table.
    """
    s = initial_state()
    results: dict[str, float] = {}

    def run_search(label: str, budget: float) -> None:
        t0 = time.monotonic()
        res = analyse(s, time_limit=budget)
        results[label] = time.monotonic() - t0
        assert res.move in legal_moves(s)

    t_long = threading.Thread(target=run_search, args=("long", 0.6))
    t_short = threading.Thread(target=run_search, args=("short", 0.1))

    t_long.start()
    time.sleep(0.03)  # start short while long is in progress
    t_short.start()

    t_short.join(timeout=3.0)
    t_long.join(timeout=3.0)

    assert not t_short.is_alive()
    assert not t_long.is_alive()
    # If the bug was present, the short search would overwrite the long search's
    # deadline, causing long to terminate at ~0.1s!
    assert results["short"] < 0.35
    assert results["long"] >= 0.50


def test_search_result_properties_and_terminal_tie() -> None:
    from mangala.ai import SearchResult, _terminal_value
    r_normal = SearchResult(move=0, score=2.5, depth=4, nodes=100, elapsed=0.01)
    assert not r_normal.is_forced_result

    r_forced = SearchResult(move=0, score=10010.0, depth=4, nodes=100, elapsed=0.01)
    assert r_forced.is_forced_result

    # Terminal tie evaluation
    pits = [0] * 14
    pits[6] = 24
    pits[13] = 24
    s_tie = GameState(pits=pits, current_player=0, game_over=True, winner=-1)
    assert _terminal_value(s_tie, root=0) == 0.0


def test_tiny_time_budget_fallback() -> None:
    from unittest.mock import patch

    from mangala.ai import Searcher, _TimeUp

    s = initial_state()
    # Mock _TimeUp occurring before iteration 1 finishes to test the fallback branch
    with patch.object(Searcher, "_search_root", side_effect=_TimeUp):
        res = analyse(s, time_limit=0.1)
        assert res.move in legal_moves(s)
        assert res.depth == 0


def test_quiescence_terminal_state() -> None:
    from mangala.ai import Searcher
    from mangala.engine import GameState

    pits = [0] * 14
    pits[6] = 30
    pits[13] = 18
    s_term = GameState(pits=pits, current_player=0, game_over=True, winner=0)
    searcher = Searcher()
    val = searcher._quiescence(s_term, alpha=-100.0, beta=100.0, root=0, q_depth=2)
    assert val > 1000.0


def test_search_children_empty_fallback() -> None:
    from unittest.mock import patch

    from mangala.ai import Searcher

    s = initial_state()
    searcher = Searcher()
    searcher._deadline = float("inf")
    with patch.object(Searcher, "_ordered_children", return_value=[]):
        val = searcher._search(s, depth=2, alpha=-100.0, beta=100.0, root=0)
        assert isinstance(val, float)


def test_extract_pv_terminal_and_missing() -> None:
    from mangala.ai import Searcher

    searcher = Searcher()
    s = initial_state()
    pv = searcher._extract_pv(s, first=0, max_len=5)
    assert pv == [0]


def test_analyse_forced_win_cutoff() -> None:
    from unittest.mock import patch

    from mangala.ai import Searcher, analyse

    s = initial_state()
    with patch.object(Searcher, "_search_root", return_value=(0, 10050.0)):
        res = analyse(s, time_limit=1.0)
        assert res.move == 0
        assert res.score == 10050.0


def test_deadline_expired_before_first_iteration() -> None:
    import time
    from unittest.mock import patch

    from mangala.ai import analyse

    s = initial_state()
    start_time = time.monotonic()
    calls = 0

    def mock_monotonic() -> float:
        nonlocal calls
        calls += 1
        # First call records start time; all subsequent calls report time well past deadline
        if calls == 1:
            return start_time
        return start_time + 100.0

    with patch("mangala.ai._time.monotonic", side_effect=mock_monotonic):
        res = analyse(s, time_limit=1.0)
        assert res.move in legal_moves(s)
        assert res.depth == 0


