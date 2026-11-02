# -*- coding: utf-8 -*-
"""
cli.py - Terminal front-end for Turkish Mangala.
Run with: mangala-cli   (or: python -m mangala.cli)

Modes:
  1) Human vs Human  (hotseat)
  2) Human vs AI
  3) AI vs AI        (watch the computer play itself)
"""
from __future__ import annotations

import io
import sys
import time

from . import ai as ai_module
from .board import render, render_status
from .engine import apply_move, initial_state, is_terminal, legal_moves

_DIVIDER = "-" * 55

_RULES = f"""
{_DIVIDER}
  TURKISH MANGALA - Rules
{_DIVIDER}
  Board: 2 rows of 6 pits + 2 treasuries (hazine).
  Each pit starts with 4 stones (48 total).

  On your turn pick one of your non-empty pits:
    >1 stone : leave 1 behind, sow the rest counterclockwise.
     1 stone : pick it up and sow it counterclockwise.

  Opponent's treasury is always skipped when sowing.

  Extra turn : last stone lands in YOUR treasury -> play again.
  Capture    : last stone lands in an OPPONENT pit whose count
               becomes EVEN -> capture all stones in that pit.
  Empty hole : last stone lands in one of YOUR pits that was
               empty -> capture it plus the opposite pit
               (only if the opposite pit has stones).

  Game ends when one side is empty; the player whose side
  emptied takes all stones left on the board. Most stones wins!

  Player 1 -> pits 0-5  (bottom row)
  Player 2 -> pits 7-12 (top row)
  Type 'q' at any prompt to quit.
{_DIVIDER}
"""

_DEFAULT_LEVEL = "hard"
_AI_VS_AI_PAUSE = 0.4  # seconds between moves in watch mode


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def _read_line(prompt: str) -> str:
    """Read a line; return empty string on EOF/KeyboardInterrupt."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _prompt_mode() -> int:
    """Ask for game mode. Returns 1/2/3 or 0 to quit."""
    print("\n  Choose a mode:")
    print("    1)  Human vs Human  (hotseat)")
    print("    2)  Human vs AI")
    print("    3)  AI vs AI        (watch)")
    while True:
        raw = _read_line("\n  Enter 1, 2, or 3: ")
        if raw in ("q", "quit", ""):
            return 0
        if raw in ("1", "2", "3"):
            return int(raw)
        print("  Please enter 1, 2, or 3.")


def _prompt_human_side() -> int:
    """Ask which side the human controls. Returns 0 (P1) or 1 (P2)."""
    while True:
        raw = _read_line("  You play as Player 1 or 2? [1/2]: ")
        if raw in ("q", ""):
            return -1
        if raw == "1":
            return 0
        if raw == "2":
            return 1
        print("  Enter 1 or 2.")


def _prompt_level(default: str = _DEFAULT_LEVEL) -> str:
    """Ask for AI difficulty. Returns a key of ai.LEVELS."""
    names = list(ai_module.LEVELS)
    options = "  ".join(f"{i}) {n}" for i, n in enumerate(names, 1))
    raw = _read_line(f"  AI level?  {options}  (default {default}): ").lower()
    if raw in names:
        return raw
    if raw.isdigit() and 1 <= int(raw) <= len(names):
        return names[int(raw) - 1]
    return default


def _prompt_move(player: int, moves: list) -> int:
    """Ask a human player to choose a pit. Returns pit index or -1 to quit."""
    labels = ", ".join(str(m) for m in moves)
    while True:
        raw = _read_line(f"\n  Player {player + 1}, pick a pit [{labels}]: ").lower()
        if raw in ("q", "quit", "exit", ""):
            return -1
        try:
            choice = int(raw)
        except ValueError:
            print("  Please enter a pit number.")
            continue
        if choice not in moves:
            print(f"  '{choice}' is not valid. Choose from: {labels}")
            continue
        return choice


# ---------------------------------------------------------------------------
# AI turn
# ---------------------------------------------------------------------------

def _ai_move(state, level: str) -> int:
    """Compute and announce the AI's move. Returns pit index."""
    player = state.current_player
    print(f"\n  Player {player + 1} (AI) is thinking...", end="", flush=True)
    t0 = time.time()
    pit = ai_module.best_move_for_level(state, level)
    elapsed = time.time() - t0
    print(f"\r  Player {player + 1} (AI) plays pit {pit}  ({elapsed:.2f}s)")
    return pit


# ---------------------------------------------------------------------------
# Shared game-turn logic
# ---------------------------------------------------------------------------

def _play_turn(state, players: list, level: str) -> tuple:
    """
    Execute one turn (human or AI) and return (new_state, aborted).
    `players` is a list of two strings: "human" or "ai".
    """
    kind = players[state.current_player]

    if kind == "ai":
        choice = _ai_move(state, level)
    else:
        moves = legal_moves(state)
        choice = _prompt_move(state.current_player, moves)
        if choice == -1:
            return state, True

    new_state, events = apply_move(state, choice)

    messages = []
    if events['capture'] > 0:
        messages.append(f"Captured {events['capture']} stone(s)!")
    if events['extra_turn']:
        messages.append("Extra turn!")
    if messages:
        print("  >> " + "  ".join(messages))

    return new_state, False


# ---------------------------------------------------------------------------
# Main game loop
# ---------------------------------------------------------------------------

def _game_loop(players: list, level: str, watch_mode: bool) -> None:
    state = initial_state()

    while not is_terminal(state):
        print()
        print(render(state))
        print(render_status(state))

        if watch_mode:
            time.sleep(_AI_VS_AI_PAUSE)

        new_state, aborted = _play_turn(state, players, level)
        if aborted:
            print("\n  Game aborted. Goodbye!")
            return
        state = new_state

    # Final board
    print()
    print(_DIVIDER)
    print(render(state))
    print()
    print(render_status(state))
    print(_DIVIDER)
    if state.winner == -1:
        print("\n  It's a tie! Both players scored equally.")
    else:
        p1, p2 = state.pits[6], state.pits[13]
        print(f"\n  Congratulations, Player {state.winner + 1} wins!  ({p1} vs {p2})")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Ensure UTF-8 output on Windows consoles without closing or replacing the stream
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("\n" + "=" * 55)
    print("           WELCOME TO MANGALA")
    print("=" * 55)
    print(_RULES)

    mode = _prompt_mode()
    if mode == 0:
        print("\n  Goodbye!")
        return

    level = _DEFAULT_LEVEL
    watch_mode = False

    if mode == 1:
        players = ["human", "human"]

    elif mode == 2:
        human_side = _prompt_human_side()
        if human_side == -1:
            print("\n  Goodbye!")
            return
        level = _prompt_level()
        players = ["human", "human"]
        players[1 - human_side] = "ai"

    else:  # mode == 3
        level = _prompt_level()
        players = ["ai", "ai"]
        watch_mode = True
        print(f"\n  AI vs AI at level {level!r}. Press Ctrl+C to stop.\n")

    print()
    try:
        _game_loop(players, level, watch_mode)
    except KeyboardInterrupt:
        print("\n\n  Interrupted. Goodbye!")


if __name__ == "__main__":
    main()
