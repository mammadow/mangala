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


def test_opening_book_lookup_and_fastpath() -> None:
    from mangala.book import OPENING_BOOK, get_book_move

    s0 = initial_state()
    # Book lookup on starting state
    mv = get_book_move(s0)
    assert mv is not None
    assert mv in legal_moves(s0)
    assert ((tuple(s0.pits), 0) in OPENING_BOOK)

    # Off-book state
    custom_pits = [0] * TOTAL
    custom_pits[0] = 48
    s_off = GameState(pits=custom_pits, current_player=0)
    assert get_book_move(s_off) is None

    # analyse with use_book=True returns instant result
    res = analyse(s0, use_book=True)
    assert res.move == mv
    assert res.depth == 16
    assert res.nodes == 1
    assert res.pv == [mv]

    # Test 180-degree rotational symmetry involution for Player 2
    s_p1 = GameState(pits=list(s0.pits), current_player=1)
    mv_p1 = get_book_move(s_p1)
    assert mv_p1 == (mv + 7) % 14


def test_searcher_heuristics_and_ordering() -> None:
    from mangala.ai import Searcher

    searcher = Searcher()
    # Test cutoff recording updates killers and history table
    searcher._record_cutoff(player=0, move=3, ply=2, depth=4)
    searcher._record_cutoff(player=0, move=4, ply=2, depth=3)
    searcher._record_cutoff(player=0, move=5, ply=2, depth=2)
    # Should keep max 2 killers per ply
    assert searcher.killer_moves[2] == [5, 4]
    assert searcher.history_table[0][3] == 16
    assert searcher.history_table[0][4] == 9

    s0 = initial_state()
    # Ordered children prioritizes PV move then killers/history
    children = searcher._ordered_children(s0, pv_move=2, ply=2)
    assert children[0][0] == 2  # PV move first


def test_enhanced_evaluation_features() -> None:
    from mangala.ai import _evaluate

    # Test ladder single-stone bonus
    pits = [0] * TOTAL
    pits[5] = 1   # direct single step into P1 treasury (pit 6)
    pits[6] = 24
    pits[13] = 23
    s_ladder = GameState(pits=pits, current_player=0)
    score_ladder = _evaluate(s_ladder, 0)
    assert score_ladder > 1.0  # treasury lead + positive ladder bonus

    # Test sweep proximity bonus when few stones remain on own side
    pits_sweep = [0] * TOTAL
    pits_sweep[0] = 1
    pits_sweep[7] = 5
    pits_sweep[6] = 18
    pits_sweep[13] = 18
    s_sweep = GameState(pits=pits_sweep, current_player=0)
    eval_sweep = _evaluate(s_sweep, 0)
    # own_stones = 1 vs opp_stones = 5: sweep bonus overcomes stone deficit
    assert eval_sweep > 0.1


def test_twenty_five_stone_threshold_victory_and_suppression() -> None:
    from mangala.ai import _WIN, Searcher, _evaluate, best_move

    # 1. Evaluate gives immediate forced win score when treasury has >= 25 stones
    pits_win = [0] * TOTAL
    pits_win[0] = 1
    pits_win[6] = 25   # Player 0 has 25 stones (majority of 48)
    pits_win[7] = 2
    pits_win[13] = 20
    s_win = GameState(pits=pits_win, current_player=0)
    score_p0 = _evaluate(s_win, 0)
    assert score_p0 >= _WIN

    # Player 1's perspective: opponent has 25 stones -> forced loss
    score_p1 = _evaluate(s_win, 1)
    assert score_p1 <= -_WIN

    # 2. Searcher orders winning move (reaching >= 25 stones) with maximum priority (20,000,000)
    pits_turn = [0] * TOTAL
    pits_turn[5] = 1   # Lands directly into treasury (pit 6), turning 24 into 25!
    pits_turn[1] = 4   # Alternative move
    pits_turn[6] = 24
    pits_turn[13] = 19
    s_turn = GameState(pits=pits_turn, current_player=0)

    searcher = Searcher()
    ordered = searcher._ordered_children(s_turn)
    # Pit 5 must be ordered first as the decisive 25-stone win
    assert ordered[0][0] == 5

    # 3. best_move finds the immediate winning 25-stone capture/step
    m = best_move(s_turn, depth=2)
    assert m == 5

    # 4. Exact endgame solver activates when board stones <= 12
    pits_12 = [0] * TOTAL
    pits_12[0] = 2; pits_12[2] = 2; pits_12[4] = 2; pits_12[6] = 18
    pits_12[7] = 2; pits_12[9] = 2; pits_12[11] = 2; pits_12[13] = 18
    s_12 = GameState(pits=pits_12, current_player=0)
    res_12 = analyse(s_12, depth=5)
    assert res_12.is_forced_result


def test_combinadic_egtb_and_exact_endgame_parity(tmp_path) -> None:
    from mangala.engine import SWEEP_LAST_MOVER, Rules, zobrist_hash
    from mangala.tablebase import (
        BINOM,
        _generate_compositions,
        _simulate_canonical_move,
        build_egtb,
        combinadic_index,
        compress_egtb,
        probe_egtb,
        probe_egtb_move,
    )
    from mangala.tablebase import main as egtb_main

    # 1. Verify combinadic_index is a strict bijection onto [0, C(K+12, 12)) for K <= 4
    seen_indices: set[int] = set()
    for k in range(5):
        for comp in _generate_compositions(k, 12):
            idx = combinadic_index(comp)
            assert 0 <= idx < BINOM[4 + 12][12]
            seen_indices.add(idx)
    assert len(seen_indices) == BINOM[4 + 12][12]

    # 2. Build EGTB up to K=4 and verify probe_egtb matches exact terminal alpha-beta
    tbl = build_egtb(max_stones=4)
    assert len(tbl) == BINOM[4 + 12][12]
    # Slice from cached K=4 tablebase when requesting K=2
    tbl_sub = build_egtb(max_stones=2)
    assert len(tbl_sub) == BINOM[2 + 12][12]

    with pytest.raises(ValueError, match="max_stones must be between 0 and 16"):
        build_egtb(max_stones=20)

    # Simulate canonical move that wraps past opponent treasury (idx == 13) and SWEEP_LAST_MOVER
    wrap_pits = (0, 0, 0, 0, 0, 10, 0, 0, 0, 0, 0, 1)
    c12, _gain, _ext, _go = _simulate_canonical_move(wrap_pits, 5, sweep_emptied=False)
    assert len(c12) == 12
    tbl_last = build_egtb(max_stones=2, rules=Rules(sweep_to=SWEEP_LAST_MOVER))
    assert len(tbl_last) == BINOM[2 + 12][12]

    pits = [0] * TOTAL
    pits[4] = 1
    pits[5] = 1
    pits[6] = 22
    pits[11] = 1
    pits[12] = 1
    pits[13] = 22
    for stm in (0, 1):
        st = GameState(pits=list(pits), current_player=stm)
        egtb_diff = probe_egtb(st, max_stones=4)
        assert egtb_diff is not None
        mv_info = probe_egtb_move(st, max_stones=4)
        assert mv_info is not None
        best_m, best_diff = mv_info
        assert best_diff == egtb_diff
        assert best_m in legal_moves(st)

    # Probe edge cases: game_over, k > max_stones, and immediate terminal move in probe_egtb_move
    s_over = GameState(pits=[0, 0, 0, 0, 0, 0, 26, 0, 0, 0, 0, 0, 0, 22], current_player=0, game_over=True)
    assert probe_egtb(s_over, max_stones=4) == 4
    assert probe_egtb_move(s_over, max_stones=4) is None
    assert probe_egtb(initial_state(), max_stones=4) is None
    assert probe_egtb_move(initial_state(), max_stones=4) is None

    s_one_left = GameState(pits=[0, 0, 0, 0, 0, 1, 23, 0, 0, 0, 0, 0, 1, 23], current_player=0)
    mv_term = probe_egtb_move(s_one_left, max_stones=4)
    assert mv_term == (5, 2)

    # 3. Verify zlib compression and CLI main()
    comp_bytes = compress_egtb(max_stones=3)
    assert len(comp_bytes) > 0
    out_file = tmp_path / "test.egtb.zlib"
    rc = egtb_main(["--max-stones", "2", "--out", str(out_file)])
    assert rc == 0
    assert out_file.exists()

    # 4. Zobrist hash out-of-range pit count fallback
    s_huge = GameState(pits=[60, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0], current_player=0)
    assert zobrist_hash(s_huge) > 0


def test_quantized_nnue_incremental_and_distillation() -> None:
    from mangala.ai import _evaluate, analyse
    from mangala.engine import apply_move
    from mangala.nnue import DEFAULT_NNUE, feature_index, train_nnue_distillation

    assert feature_index(0, -5) == 0
    s0 = initial_state()
    acc0 = DEFAULT_NNUE.compute_accumulator(s0.pits)
    acc_copy = acc0.copy()
    assert list(acc_copy.acc_p0) == list(acc0.acc_p0)
    ev0 = DEFAULT_NNUE.evaluate(s0, root=0)
    assert isinstance(ev0, float)

    # Verify incremental accumulator update matches full recomputation across a sequence of moves
    curr_s = s0
    curr_acc = acc0
    for mv in (2, 0, 8, 4):
        if mv not in legal_moves(curr_s):
            break
        next_s, _ = apply_move(curr_s, mv)
        inc_acc = DEFAULT_NNUE.update_accumulator(curr_acc, curr_s.pits, next_s.pits)
        full_acc = DEFAULT_NNUE.compute_accumulator(next_s.pits)
        assert list(inc_acc.acc_p0) == list(full_acc.acc_p0)
        assert list(inc_acc.acc_p1) == list(full_acc.acc_p1)
        curr_s = next_s
        curr_acc = inc_acc

    # Verify distillation trainer and hybrid NNUE search mode
    samples = [(s0, _evaluate(s0, 0)), (curr_s, _evaluate(curr_s, curr_s.current_player))]
    trained_nnue = train_nnue_distillation(samples, epochs=5, lr=0.02)
    ev_trained = trained_nnue.evaluate(s0, root=0)
    assert isinstance(ev_trained, float)

    res_nnue = analyse(s0, depth=2, use_nnue=True)
    assert res_nnue.move in legal_moves(s0)


def test_exponential_merdiven_and_wrap_around_capture_eval() -> None:
    from mangala.ai import EvalWeights, Searcher, _evaluate

    # 3-pit staircase (pits 3, 4, 5 have 3, 2, 1 stones -> 2^3 - 1 = 7 extra turns)
    pits_stair = [0] * TOTAL
    pits_stair[3] = 3
    pits_stair[4] = 2
    pits_stair[5] = 1
    pits_stair[6] = 20
    pits_stair[7] = 2
    pits_stair[13] = 20
    s_stair = GameState(pits=pits_stair, current_player=0)

    # Wrap-around empty hole capture: pit 5 has 9 stones (sow_count=8, lands on empty pit 0)
    pits_wrap = [0] * TOTAL
    pits_wrap[0] = 0
    pits_wrap[5] = 9
    pits_wrap[6] = 19
    pits_wrap[7] = 4
    pits_wrap[12] = 0  # opposite of pit 0 is pit 12, which gets +1 during wrap-around!
    pits_wrap[13] = 16
    s_wrap = GameState(pits=pits_wrap, current_player=0)

    assert _evaluate(s_stair, 0) > _evaluate(s_stair, 0, EvalWeights(w_ladder_cascade=0.0)) + 1.0
    assert abs(
        _evaluate(s_wrap, 0) - _evaluate(s_wrap, 0, EvalWeights(w_empty_hole_offense=0.0)) - 0.50
    ) < 1e-9

    # Countermove recording and ordering priority
    searcher = Searcher()
    searcher._record_cutoff(player=0, move=4, ply=2, depth=3, prev_move=9)
    assert searcher.counter_moves[0][9] == 4
    ordered = searcher._ordered_children(initial_state(), pv_move=-1, ply=3, prev_move=9)
    assert len(ordered) == 6




