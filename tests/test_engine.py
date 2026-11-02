"""Unit tests for the pure Turkish Mangala engine."""
import pytest

from mangala.engine import (
    P1_PITS,
    P1_TREASURY,
    P2_PITS,
    P2_TREASURY,
    SWEEP_EMPTIED_SIDE,
    SWEEP_LAST_MOVER,
    TOTAL,
    GameState,
    Rules,
    apply_move,
    initial_state,
    is_terminal,
    legal_moves,
    opposite,
    score,
    validate_state,
)


def test_initial_state() -> None:
    s = initial_state()
    assert s.current_player == 0
    assert not s.game_over
    assert s.winner is None
    assert s.pits[P1_TREASURY] == 0
    assert s.pits[P2_TREASURY] == 0
    for p in P1_PITS:
        assert s.pits[p] == 4
    for p in P2_PITS:
        assert s.pits[p] == 4
    assert sum(s.pits) == 48
    validate_state(s)


def test_validate_state_errors() -> None:
    # Wrong length
    with pytest.raises(ValueError, match="must be a list of 14 integers"):
        validate_state(GameState(pits=[4] * 13, current_player=0))

    # Negative stone count
    pits = [4] * TOTAL
    pits[0] = -1
    pits[1] = 5
    with pytest.raises(ValueError, match="non-negative"):
        validate_state(GameState(pits=pits, current_player=0))

    # Wrong total sum
    pits = [4] * TOTAL
    pits[0] = 5
    with pytest.raises(ValueError, match="exactly 48 stones"):
        validate_state(GameState(pits=pits, current_player=0))

    # Invalid current_player
    s = initial_state()
    with pytest.raises(ValueError, match="current_player must be 0 or 1"):
        validate_state(GameState(pits=list(s.pits), current_player=2))

    # Invalid game_over type
    with pytest.raises(ValueError, match="game_over must be a boolean"):
        validate_state(GameState(pits=list(s.pits), current_player=0, game_over="invalid"))  # type: ignore[arg-type]

    # Invalid winner
    with pytest.raises(ValueError, match="winner must be null, 0, 1 or -1"):
        validate_state(GameState(pits=list(s.pits), current_player=0, winner=5))

    # Invalid Rules variant
    with pytest.raises(ValueError, match="unknown sweep_to variant"):
        Rules(sweep_to="non_existent")


def test_legal_moves() -> None:
    s = initial_state()
    assert legal_moves(s) == P1_PITS

    # Player 2 moves
    s2 = GameState(pits=list(s.pits), current_player=1)
    assert legal_moves(s2) == P2_PITS

    # Exclude empty pits
    pits = list(s.pits)
    pits[0] = 0
    pits[3] = 0
    s_partial = GameState(pits=pits, current_player=0)
    assert legal_moves(s_partial) == [1, 2, 4, 5]

    # Terminal state has no legal moves
    s_term = GameState(pits=list(s.pits), current_player=0, game_over=True)
    assert legal_moves(s_term) == []


def test_opposite_mapping() -> None:
    for i in range(6):
        opp = opposite(i)
        assert opp == 12 - i
        assert opposite(opp) == i


def test_move_leave_one_behind() -> None:
    # Pit has 4 stones: leaves 1 behind, sows 3
    s = initial_state()
    ns, ev = apply_move(s, 0)
    assert ns.pits[0] == 1
    assert ns.pits[1] == 5
    assert ns.pits[2] == 5
    assert ns.pits[3] == 5
    assert ns.pits[4] == 4
    assert ev["capture"] == 0
    assert not ev["extra_turn"]
    assert ns.current_player == 1


def test_move_single_stone_pickup() -> None:
    # Pit has 1 stone: lifts it (becomes 0), sows into next pit.
    # Keep other stones on both sides so the game doesn't end.
    pits = [0] * TOTAL
    pits[0] = 1
    pits[2] = 2  # keeps P1 side non-empty
    pits[8] = 2  # keeps P2 side non-empty
    pits[P1_TREASURY] = 21
    pits[P2_TREASURY] = 22
    s = GameState(pits=pits, current_player=0)
    ns, ev = apply_move(s, 0)
    assert ns.pits[0] == 0
    assert ns.pits[1] == 1
    assert not ns.game_over
    assert not ev["extra_turn"]
    assert ns.current_player == 1


def test_extra_turn_in_own_treasury() -> None:
    # Pit 3 has 4 stones: leaves 1 in pit 3, sows into 4, 5, 6 (treasury)
    s = initial_state()
    ns, ev = apply_move(s, 3)
    assert ns.pits[3] == 1
    assert ns.pits[4] == 5
    assert ns.pits[5] == 5
    assert ns.pits[P1_TREASURY] == 1
    assert ev["extra_turn"]
    assert ns.current_player == 0  # Still Player 1's turn


def test_skip_opponent_treasury() -> None:
    # P1 sows past pit 12 -> should skip 13 and land in 0.
    # Keep other pits non-empty so the game doesn't end.
    pits = [0] * TOTAL
    pits[0] = 2  # keeps P1 non-empty
    pits[5] = 9  # leaves 1, sows 8 -> pits 6, 7, 8, 9, 10, 11, 12, skip 13, land in 0
    pits[8] = 2  # keeps P2 non-empty
    pits[P1_TREASURY] = 17
    pits[P2_TREASURY] = 18
    s = GameState(pits=pits, current_player=0)
    ns, _ = apply_move(s, 5)
    assert ns.pits[5] == 1
    assert ns.pits[P1_TREASURY] == 18
    for p in range(7, 13):
        assert ns.pits[p] >= 1
    assert ns.pits[P2_TREASURY] == 18  # Opponent treasury skipped!
    assert ns.pits[0] == 3             # 2 + 1 landed


def test_regular_capture_even_count() -> None:
    # P1 plays pit 4 with 4 stones -> leaves 1 in 4, sows in 5, 6, 7.
    # Pit 7 has 3 stones -> with sown stone becomes 4 (even) -> captured!
    pits = [0] * TOTAL
    pits[0] = 2   # keeps P1 non-empty
    pits[4] = 4
    pits[7] = 3
    pits[8] = 2   # keeps P2 non-empty
    pits[P1_TREASURY] = 18
    pits[P2_TREASURY] = 19
    s = GameState(pits=pits, current_player=0)
    ns, ev = apply_move(s, 4)
    assert ns.pits[7] == 0  # Captured
    assert ev["capture"] == 4
    assert ns.pits[P1_TREASURY] == 23  # 18 + 1 (treasury 6) + 4 (captured) = 23
    assert not ns.game_over
    assert ns.current_player == 1


def test_regular_capture_odd_count_no_capture() -> None:
    # P1 lands in opponent pit, resulting in odd count -> no capture
    pits = [0] * TOTAL
    pits[0] = 2   # keeps P1 non-empty
    pits[4] = 4
    pits[7] = 2
    pits[8] = 2   # keeps P2 non-empty
    pits[P1_TREASURY] = 18
    pits[P2_TREASURY] = 20
    s = GameState(pits=pits, current_player=0)
    ns, ev = apply_move(s, 4)
    assert ns.pits[7] == 3  # Not even, remains
    assert ev["capture"] == 0
    assert ns.pits[P1_TREASURY] == 19  # 18 + 1 (treasury 6)


def test_empty_hole_capture() -> None:
    # P1 plays pit 0 with 2 stones -> leaves 1 in 0, sows 1 into pit 1 (which was empty).
    # Opposite pit of 1 is 12 - 1 = 11. Pit 11 has 5 stones.
    # Result: captures 1 (from pit 1) + 5 (from pit 11) = 6 stones into P1 treasury.
    pits = [0] * TOTAL
    pits[0] = 2
    pits[1] = 0
    pits[2] = 2   # keeps P1 non-empty
    pits[11] = 5
    pits[8] = 2   # keeps P2 non-empty
    pits[P1_TREASURY] = 18
    pits[P2_TREASURY] = 19
    s = GameState(pits=pits, current_player=0)
    ns, ev = apply_move(s, 0)
    assert ns.pits[1] == 0
    assert ns.pits[11] == 0
    assert ev["capture"] == 6
    assert ns.pits[P1_TREASURY] == 24  # 18 + 6
    assert not ns.game_over
    assert ns.current_player == 1


def test_empty_hole_opposite_empty_no_capture() -> None:
    # Empty-hole rule only applies if opposite pit is non-empty.
    pits = [0] * TOTAL
    pits[0] = 2
    pits[1] = 0
    pits[2] = 2   # keeps P1 non-empty
    pits[11] = 0  # Opposite is empty
    pits[8] = 2   # keeps P2 non-empty
    pits[P1_TREASURY] = 21
    pits[P2_TREASURY] = 21
    s = GameState(pits=pits, current_player=0)
    ns, ev = apply_move(s, 0)
    assert ns.pits[1] == 1  # Stone stays
    assert ns.pits[11] == 0
    assert ev["capture"] == 0
    assert ns.pits[P1_TREASURY] == 21


def test_endgame_sweep_emptied_side() -> None:
    # P1 side empties: P1 gets all remaining opponent stones.
    pits = [0] * TOTAL
    pits[5] = 1  # Last stone on P1 side sows into treasury 6
    pits[7] = 5
    pits[8] = 3
    pits[P1_TREASURY] = 20
    pits[P2_TREASURY] = 19
    s = GameState(pits=pits, current_player=0)
    ns, _ = apply_move(s, 5, Rules(sweep_to=SWEEP_EMPTIED_SIDE))
    assert ns.game_over
    # P1 had 20 + 1 (treasury) + 8 (swept from P2) = 29
    assert ns.pits[P1_TREASURY] == 29
    assert ns.pits[P2_TREASURY] == 19
    assert ns.winner == 0
    assert sum(ns.pits[0:6]) == 0
    assert sum(ns.pits[7:13]) == 0


def test_endgame_sweep_last_mover() -> None:
    # P1 makes move that captures and empties P2 side.
    # Under SWEEP_LAST_MOVER, P1 (last mover) takes P1's remaining stones.
    pits = [0] * TOTAL
    pits[0] = 3
    pits[5] = 3  # Sows into 6, 7 (captures)
    pits[7] = 1  # Becomes 2 -> captured
    pits[P1_TREASURY] = 20
    pits[P2_TREASURY] = 22
    s = GameState(pits=pits, current_player=0)
    ns, _ = apply_move(s, 5, Rules(sweep_to=SWEEP_LAST_MOVER))
    assert ns.game_over
    assert ns.winner == 0


def test_endgame_tie() -> None:
    pits = [0] * TOTAL
    pits[5] = 1
    pits[P1_TREASURY] = 23
    pits[P2_TREASURY] = 24
    s = GameState(pits=pits, current_player=0)
    ns, _ = apply_move(s, 5)
    assert ns.game_over
    assert ns.winner == -1
    p1, p2 = score(ns)
    assert p1 == 24 and p2 == 24
    assert is_terminal(ns)


def test_endgame_player2_wins() -> None:
    pits = [0] * TOTAL
    pits[5] = 1
    pits[P1_TREASURY] = 10
    pits[P2_TREASURY] = 37
    s = GameState(pits=pits, current_player=0)
    ns, _ = apply_move(s, 5)
    assert ns.game_over
    assert ns.winner == 1
    p1, p2 = score(ns)
    assert p1 == 11 and p2 == 37


def test_illegal_move_raises() -> None:
    s = initial_state()
    # Opponent pit
    with pytest.raises(ValueError, match="illegal move"):
        apply_move(s, 7)
    # Empty pit
    pits = list(s.pits)
    pits[0] = 0
    pits[P1_TREASURY] = 4
    s_empty = GameState(pits=pits, current_player=0)
    with pytest.raises(ValueError, match="illegal move"):
        apply_move(s_empty, 0)
