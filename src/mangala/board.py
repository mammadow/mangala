"""
board.py — ASCII rendering for Turkish Mangala.

Visual layout (P2's row is shown reversed so counterclockwise flow
looks natural for both players):

           12   11   10    9    8    7
  P2 [xx]  [xx]  [xx]  [xx]  [xx]  [xx]  [xx]  [xx] P1
           [xx]  [xx]  [xx]  [xx]  [xx]  [xx]
            0    1    2    3    4    5
"""
from __future__ import annotations

from .engine import GameState

# P2 pits displayed left-to-right from P1's perspective
_P2_DISPLAY = [12, 11, 10, 9, 8, 7]

# Indent to align pit cells with the treasury prefix "  P2 [xx]  " = 11 chars
_INDENT = " " * 11


def _cell(n: int) -> str:
    return f"[{n:2}]"


def render(state: GameState) -> str:
    p = state.pits
    sep = "  "

    p2_cells = sep.join(_cell(p[i]) for i in _P2_DISPLAY)
    p1_cells = sep.join(_cell(p[i]) for i in range(6))

    p2_idx = sep.join(f" {i:2} " for i in _P2_DISPLAY)
    p1_idx = sep.join(f" {i:2} " for i in range(6))

    p2_haz = _cell(p[13])
    p1_haz = _cell(p[6])

    # Highlight whose side is active
    p1_marker = " <--" if state.current_player == 0 and not state.game_over else ""
    p2_marker = "<-- " if state.current_player == 1 and not state.game_over else "    "

    lines = [
        f"{_INDENT}{p2_idx}",
        f"  P2 {p2_haz}  {p2_cells}  {p1_haz} P1",
        f"{_INDENT}{p1_cells}",
        f"{_INDENT}{p1_idx}",
    ]
    # Append turn markers on the pit rows
    result = lines[:]
    if not state.game_over:
        if state.current_player == 1:
            result[1] = f"{p2_marker}{result[1][4:]}"
        else:
            result[2] = result[2] + p1_marker
    return "\n".join(result)


def render_status(state: GameState) -> str:
    s1, s2 = state.pits[6], state.pits[13]
    base = f"P1 Hazine: {s1:2}  |  P2 Hazine: {s2:2}"
    if state.game_over:
        if state.winner == -1:
            return f"{base}  |  It's a tie!"
        if state.winner is not None:
            return f"{base}  |  Player {state.winner + 1} wins!"
        return f"{base}  |  Game over"
    return f"{base}  |  Player {state.current_player + 1}'s turn"
