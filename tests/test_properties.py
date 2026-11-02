"""Property-based tests with Hypothesis for Turkish Mangala."""
import random

from hypothesis import given, settings
from hypothesis import strategies as st

from mangala.engine import (
    PLAYER_PITS,
    TOTAL_STONES,
    apply_move,
    initial_state,
    is_terminal,
    legal_moves,
    validate_state,
)


@settings(max_examples=100, deadline=None)
@given(st.randoms())
def test_stone_conservation_and_invariants(rnd: random.Random) -> None:
    """Verify that throughout any random playout:

    - Total stone count is strictly conserved at 48.
    - No pit count is ever negative.
    - validate_state passes on every intermediate state.
    - apply_move never mutates the previous state.
    - Every legal move is on the current player's side and has stones > 0.
    """
    state = initial_state()
    move_count = 0

    while not is_terminal(state) and move_count < 300:
        moves = legal_moves(state)
        assert len(moves) > 0, "Non-terminal state must have legal moves"

        # Verify legal move constraints
        for m in moves:
            assert m in PLAYER_PITS[state.current_player]
            assert state.pits[m] > 0

        # Snapshot for immutability check
        pits_before = list(state.pits)
        player_before = state.current_player

        chosen_move = rnd.choice(moves)
        next_state, _events = apply_move(state, chosen_move)

        # Immutability
        assert state.pits == pits_before
        assert state.current_player == player_before

        # Conservation of stones
        assert sum(next_state.pits) == TOTAL_STONES
        for p in next_state.pits:
            assert p >= 0

        validate_state(next_state)

        state = next_state
        move_count += 1

    if state.game_over:
        # All small pits must be empty on game over
        assert sum(state.pits[0:6]) == 0
        assert sum(state.pits[7:13]) == 0
        assert state.pits[6] + state.pits[13] == TOTAL_STONES
