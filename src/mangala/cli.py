"""
cli.py - Terminal front-end for Turkish Mangala.
Run with: mangala-cli   (or: python -m mangala.cli)

Modes:
  1) Human vs Human  (hotseat)
  2) Human vs AI
  3) AI vs AI        (watch the computer play itself)
"""
from __future__ import annotations

import contextlib
import sys
import time
from typing import Any

from . import ai as ai_module
from .board import render, render_status
from .engine import GameState, apply_move, initial_state, is_terminal, legal_moves

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

def _ai_move(state: GameState, level: str) -> int:
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

def _play_turn(state: GameState, players: list[str], level: str) -> tuple[GameState, bool]:
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
    elif state.winner is not None:
        p1, p2 = state.pits[6], state.pits[13]
        print(f"\n  Congratulations, Player {state.winner + 1} wins!  ({p1} vs {p2})")
    print()


# ---------------------------------------------------------------------------
# Mancala Universal Interface (MUI / UCI) Protocol
# ---------------------------------------------------------------------------

def run_mui_protocol(in_stream: Any = sys.stdin, out_stream: Any = sys.stdout) -> None:
    """Mancala Universal Interface (MUI / UCI) standard protocol loop.

    Allows connecting the Turkish Mangala engine to external tournament managers,
    chess GUIs, and bot arenas via standard text protocol.
    """
    state = initial_state()

    for raw_line in in_stream:
        line = raw_line.strip()
        if not line:
            continue
        tokens = line.split()
        cmd = tokens[0].lower()

        if cmd in ("mui", "uci"):
            out_stream.write("id name Turkish Mangala\n")
            out_stream.write("id author mammadow\n")
            opt_line = (
                "option name Level type combo default expert "
                "var easy var medium var hard var expert\n"
            )
            out_stream.write(opt_line)
            out_stream.write(f"{cmd}ok\n")
            out_stream.flush()
        elif cmd == "isready":
            out_stream.write("readyok\n")
            out_stream.flush()
        elif cmd in ("muinewgame", "ucinewgame"):
            state = initial_state()
        elif cmd == "position":
            if len(tokens) > 1 and tokens[1] == "startpos":
                state = initial_state()
                if "moves" in tokens:
                    move_idx = tokens.index("moves") + 1
                    for mv_str in tokens[move_idx:]:
                        with contextlib.suppress(ValueError):
                            mv = int(mv_str)
                            if mv in legal_moves(state):
                                state, _ = apply_move(state, mv)
        elif cmd == "go":
            depth = None
            time_limit = 2.5
            if "depth" in tokens:
                with contextlib.suppress(ValueError, IndexError):
                    depth = int(tokens[tokens.index("depth") + 1])
            if "movetime" in tokens:
                with contextlib.suppress(ValueError, IndexError):
                    time_limit = float(tokens[tokens.index("movetime") + 1]) / 1000.0

            if is_terminal(state) or not legal_moves(state):
                out_stream.write("bestmove none\n")
            else:
                res = ai_module.analyse(state, depth=depth, time_limit=time_limit, use_book=True)
                score_cp = int(res.score * 100)
                elapsed_ms = int(res.elapsed * 1000)
                pv_str = " ".join(str(p) for p in res.pv)
                info_line = (
                    f"info depth {res.depth} score cp {score_cp} "
                    f"nodes {res.nodes} time {elapsed_ms} pv {pv_str}\n"
                )
                out_stream.write(info_line)
                out_stream.write(f"bestmove {res.move}\n")
            out_stream.flush()
        elif cmd == "eval":
            ev = ai_module._evaluate(state, state.current_player)
            out_stream.write(f"eval {ev:.2f}\n")
            out_stream.flush()
        elif cmd == "quit":
            break


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    # Handle standard tournament protocol flag
    if any(arg in sys.argv for arg in ("--mui", "--uci", "-m", "-u")):
        run_mui_protocol()
        return

    # Ensure UTF-8 output on Windows consoles without closing or replacing the stream
    if hasattr(sys.stdout, "reconfigure"):
        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
