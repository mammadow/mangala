"""Unit tests for ASCII board renderer (board.py)."""
from mangala.board import render, render_status
from mangala.engine import GameState, initial_state


def test_render_initial_state() -> None:
    s = initial_state()
    txt = render(s)
    assert "P1" in txt
    assert "P2" in txt
    assert "[ 4]" in txt  # initial pit stones
    assert "<--" in txt  # turn marker for Player 1


def test_render_player2_turn() -> None:
    s = GameState(pits=list(initial_state().pits), current_player=1)
    txt = render(s)
    assert "<--" in txt


def test_render_status() -> None:
    s = initial_state()
    status = render_status(s)
    assert "P1 Hazine:  0" in status
    assert "P2 Hazine:  0" in status
    assert "Player 1's turn" in status


def test_render_status_game_over() -> None:
    pits = [0] * 14
    pits[6] = 28
    pits[13] = 20
    s_win = GameState(pits=pits, current_player=0, game_over=True, winner=0)
    assert "Player 1 wins!" in render_status(s_win)

    s_tie = GameState(pits=pits, current_player=0, game_over=True, winner=-1)
    assert "It's a tie!" in render_status(s_tie)
