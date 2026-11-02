#!/usr/bin/env python3
"""selfplay.py — AI-vs-AI tournament and evaluation benchmark for Turkish Mangala.

Runs N games between two AI configurations, alternating starting player
to eliminate first-move advantage. Reports win rates, draw rates, average
game length, and estimated Elo difference.

Usage:
    python tools/selfplay.py --games 50 --p1 hard --p2 medium
    python tools/selfplay.py --games 20 --p1 expert --p2 hard --time 1.0
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from typing import Optional

from mangala.ai import LEVELS, best_move, best_move_for_level
from mangala.engine import GameState, apply_move, initial_state, is_terminal, score


def estimate_elo_diff(score_ratio: float) -> Optional[float]:
    """Estimate Elo difference from score ratio in [0, 1]."""
    if score_ratio <= 0.0:
        return -math.inf
    if score_ratio >= 1.0:
        return math.inf
    return -400.0 * math.log10(1.0 / score_ratio - 1.0)


def play_one_game(p1_conf: dict, p2_conf: dict, p1_is_starter: bool) -> tuple[int, int, int]:
    """Play one game.

    Returns:
        (p1_score, p2_score, move_count)
    """
    state = initial_state()
    # Map player 0 and player 1 to their respective configs
    # If p1_is_starter is True, Player 1 (index 0) is p1_conf, Player 2 is p2_conf
    confs = [p1_conf, p2_conf] if p1_is_starter else [p2_conf, p1_conf]
    move_count = 0

    while not is_terminal(state):
        curr = state.current_player
        conf = confs[curr]
        if "level" in conf:
            chosen_pit = best_move_for_level(state, level=conf["level"])
        else:
            chosen_pit = best_move(state, depth=conf.get("depth"),
                                   time_limit=conf.get("time_limit", 1.0))
        state, _ = apply_move(state, chosen_pit)
        move_count += 1
        if move_count > 1000:
            break

    s0, s1 = score(state)
    if p1_is_starter:
        return s0, s1, move_count
    else:
        return s1, s0, move_count


def run_tournament(p1_conf: dict, p2_conf: dict, games: int) -> None:
    print("=" * 60)
    print(f" Mangala AI Benchmark Arena: {games} Games")
    print(f" Player 1 (Agent A): {p1_conf}")
    print(f" Player 2 (Agent B): {p2_conf}")
    print("=" * 60)

    p1_wins = 0
    p2_wins = 0
    draws = 0
    total_moves = 0
    start_time = time.time()

    for g in range(1, games + 1):
        # Alternate starter each game
        p1_starts = (g % 2 == 1)
        s1, s2, moves = play_one_game(p1_conf, p2_conf, p1_starts)
        total_moves += moves

        if s1 > s2:
            p1_wins += 1
            res = "A won"
        elif s2 > s1:
            p2_wins += 1
            res = "B won"
        else:
            draws += 1
            res = "Draw"

        starter_str = "A started" if p1_starts else "B started"
        print(f"Game {g:3d}/{games}: {res:7s} ({s1:2d} - {s2:2d}) in {moves:3d} moves [{starter_str}]")

    elapsed = time.time() - start_time
    total_score = p1_wins + 0.5 * draws
    score_pct = (total_score / games) * 100.0
    elo_diff = estimate_elo_diff(total_score / games)
    avg_moves = total_moves / games

    print("\n" + "=" * 60)
    print(" Tournament Results:")
    print(f"  Agent A wins : {p1_wins} ({p1_wins / games * 100:.1f}%)")
    print(f"  Agent B wins : {p2_wins} ({p2_wins / games * 100:.1f}%)")
    print(f"  Draws        : {draws} ({draws / games * 100:.1f}%)")
    print(f"  Total Score  : {total_score:.1f} / {games} ({score_pct:.1f}%)")
    if elo_diff is not None and not math.isinf(elo_diff):
        print(f"  Elo Diff     : {elo_diff:+.1f} (Agent A rel to B)")
    print(f"  Avg Moves    : {avg_moves:.1f} moves/game")
    print(f"  Time Taken   : {elapsed:.1f}s ({elapsed / games:.2f}s/game)")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mangala AI Benchmark Arena")
    parser.add_argument("--games", type=int, default=20, help="Number of games to play (default: 20)")
    parser.add_argument("--p1", default="hard", choices=list(LEVELS), help="Agent A preset (default: hard)")
    parser.add_argument("--p2", default="medium", choices=list(LEVELS), help="Agent B preset (default: medium)")
    args = parser.parse_args()

    run_tournament({"level": args.p1}, {"level": args.p2}, games=args.games)


if __name__ == "__main__":
    main()
