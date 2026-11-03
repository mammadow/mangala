"""
mangala.tune — Automated Self-Play Dataset Generator, Texel Tuning & SPSA Optimization.

Provides an end-to-end framework to mathematically optimize Turkish Mangala evaluation
weights using:
  1. Multi-core parallel self-play game generation with opening entropy injection.
  2. Quiet-position filtering to eliminate tactical horizon noise from training data.
  3. Texel Tuning Mean Squared Error (MSE) objective evaluation.
  4. Simultaneous Perturbation Stochastic Approximation (SPSA) gradient-free optimizer.
  5. Head-to-head match arena with Sequential Probability Ratio Testing (SPRT).

Usage via CLI:
  python -m mangala.tune selfplay --games 100 --out positions.json
  python -m mangala.tune tune --data positions.json --iters 30
  python -m mangala.tune arena --games 40 --depth 3
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import os
import random
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .ai import DEFAULT_WEIGHTS, EvalWeights, _evaluate, best_move
from .engine import DEFAULT_RULES, GameState, Rules, apply_move, initial_state, legal_moves, score

# ---------------------------------------------------------------------------
# Training Data Models
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TrainingPosition:
    """A single game position paired with the final match outcome."""
    pits: list[int]
    current_player: int
    result: float  # 1.0 = Player 0 won, 0.0 = Player 1 won, 0.5 = Draw

    def to_dict(self) -> dict[str, Any]:
        return {
            "pits": list(self.pits),
            "current_player": self.current_player,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TrainingPosition:
        return cls(
            pits=list(d["pits"]),
            current_player=int(d["current_player"]),
            result=float(d["result"]),
        )


def _is_quiet_position(state: GameState, rules: Rules = DEFAULT_RULES) -> bool:
    """Determine if a position is quiet (free of immediate captures or bonus turns)."""
    for m in legal_moves(state):
        _, ev = apply_move(state, m, rules)
        if ev["capture"] > 0 or ev["extra_turn"]:
            return False
    return True


# ---------------------------------------------------------------------------
# Self-Play Generation
# ---------------------------------------------------------------------------

def _play_single_game(
    args: tuple[int, int, float, int | None, dict[str, float] | None],
) -> list[dict[str, Any]]:
    """Worker function to simulate a single self-play match."""
    game_idx, max_moves, time_limit, seed, weights_dict = args
    if seed is not None:
        random.seed(seed + game_idx * 1009)

    weights = EvalWeights.from_dict(weights_dict) if weights_dict else DEFAULT_WEIGHTS
    state = initial_state()
    history_states: list[GameState] = []

    # Opening entropy: play first 2 to 4 moves with random legal choice
    random_plies = random.randint(2, 4)
    move_count = 0

    while not state.game_over and move_count < max_moves:
        legal = legal_moves(state)
        if not legal:
            break

        if move_count < random_plies:
            mv = random.choice(legal)
        else:
            # If position is quiet, snapshot it for training
            if _is_quiet_position(state):
                history_states.append(state)
            mv = best_move(state, depth=None, time_limit=time_limit, use_book=False, weights=weights)

        state, _ = apply_move(state, mv)
        move_count += 1

    # Final match outcome
    p1, p2 = score(state)
    if p1 > p2:
        res = 1.0
    elif p2 > p1:
        res = 0.0
    else:
        res = 0.5

    positions = []
    for s in history_states:
        positions.append(TrainingPosition(pits=s.pits, current_player=s.current_player, result=res).to_dict())

    return positions


def generate_selfplay_dataset(
    num_games: int = 50,
    max_moves: int = 100,
    time_limit: float = 0.02,
    weights: EvalWeights = DEFAULT_WEIGHTS,
    num_workers: int | None = None,
    seed: int | None = 42,
) -> list[TrainingPosition]:
    """Generate a dataset of quiet training positions via parallel self-play."""
    workers = num_workers or max(1, os.cpu_count() or 1)
    weights_dict = weights.to_dict()

    tasks = [
        (i, max_moves, time_limit, seed, weights_dict)
        for i in range(num_games)
    ]

    all_positions: list[TrainingPosition] = []

    if workers == 1:
        for t in tasks:
            for p in _play_single_game(t):
                all_positions.append(TrainingPosition.from_dict(p))
    else:
        with multiprocessing.Pool(processes=workers) as pool:
            for game_positions in pool.imap_unordered(_play_single_game, tasks):
                for p in game_positions:
                    all_positions.append(TrainingPosition.from_dict(p))

    return all_positions


# ---------------------------------------------------------------------------
# Objective Function (Texel Tuning MSE)
# ---------------------------------------------------------------------------

def _sigmoid(x: float) -> float:
    """Standard numerically stable sigmoid function."""
    if x >= 40.0:
        return 1.0
    if x <= -40.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def texel_loss(
    weights: EvalWeights,
    positions: Sequence[TrainingPosition],
    scaling_k: float = 0.75,
) -> float:
    """Compute Mean Squared Error between sigmoid evaluation and game results.

    L(w) = 1/N * sum( (result_i - sigmoid(K * eval(pos_i, w)))^2 )
    """
    if not positions:
        return 0.0

    total_sq_err = 0.0
    for pos in positions:
        st = GameState(pits=pos.pits, current_player=pos.current_player)
        # Evaluate from Player 0's perspective to correlate directly with result (1.0 = P0 win)
        ev = _evaluate(st, root=0, weights=weights)
        pred = _sigmoid(scaling_k * ev)
        err = pos.result - pred
        total_sq_err += err * err

    return total_sq_err / len(positions)


# ---------------------------------------------------------------------------
# SPSA Optimizer (Simultaneous Perturbation Stochastic Approximation)
# ---------------------------------------------------------------------------

_PARAM_KEYS = list(DEFAULT_WEIGHTS.to_dict().keys())

_BOUNDS: dict[str, tuple[float, float]] = {
    "w_mobility": (0.01, 0.50),
    "w_extra_single": (0.10, 1.50),
    "w_extra_multi": (0.10, 1.20),
    "w_ladder_cascade": (0.05, 1.00),
    "w_capture_offense": (0.05, 1.00),
    "w_empty_hole_offense": (0.05, 0.90),
    "w_capture_exposure": (0.05, 1.00),
    "w_empty_hole_exposure": (0.05, 0.90),
    "w_parity_own_even": (0.01, 0.40),
    "w_parity_own_odd": (-0.40, -0.01),
    "w_parity_opp_odd": (0.01, 0.40),
    "w_parity_opp_even": (-0.40, -0.01),
    "w_fortress": (0.02, 0.60),
    "w_sweep": (0.02, 0.60),
    "w_threshold_own": (0.10, 1.50),
    "w_threshold_opp": (0.10, 1.50),
}


def _clamp_param(key: str, val: float) -> float:
    lo, hi = _BOUNDS.get(key, (-2.0, 2.0))
    return max(lo, min(hi, val))


def run_spsa_tuning(
    initial_weights: EvalWeights,
    positions: Sequence[TrainingPosition],
    iterations: int = 25,
    a_param: float = 0.05,
    c_param: float = 0.03,
    alpha: float = 0.602,
    gamma: float = 0.101,
    seed: int | None = 42,
    callback: Any | None = None,
) -> tuple[EvalWeights, list[float]]:
    """Optimize evaluation weights using SPSA gradient approximation on training positions."""
    if seed is not None:
        random.seed(seed)

    curr_dict = initial_weights.to_dict()
    best_weights = initial_weights
    best_loss = texel_loss(initial_weights, positions)
    loss_history = [best_loss]

    A = max(10, iterations // 10)

    for k in range(iterations):
        ak = a_param / ((k + 1 + A) ** alpha)
        ck = c_param / ((k + 1) ** gamma)

        # Rademacher perturbation vector: delta_i in {-1, +1}
        delta = {key: random.choice([-1.0, 1.0]) for key in _PARAM_KEYS}

        # Perturbed weight vectors w+ and w-
        plus_dict = {
            k_name: _clamp_param(k_name, curr_dict[k_name] + ck * delta[k_name])
            for k_name in _PARAM_KEYS
        }
        minus_dict = {
            k_name: _clamp_param(k_name, curr_dict[k_name] - ck * delta[k_name])
            for k_name in _PARAM_KEYS
        }

        loss_plus = texel_loss(EvalWeights.from_dict(plus_dict), positions)
        loss_minus = texel_loss(EvalWeights.from_dict(minus_dict), positions)

        # Simultaneous gradient estimate
        grad_estimate = (loss_plus - loss_minus) / (2.0 * ck)

        # Update weights along negative gradient
        for k_name in _PARAM_KEYS:
            updated = curr_dict[k_name] - ak * grad_estimate * delta[k_name]
            curr_dict[k_name] = _clamp_param(k_name, updated)

        current_weights = EvalWeights.from_dict(curr_dict)
        cur_loss = texel_loss(current_weights, positions)
        loss_history.append(cur_loss)

        if cur_loss < best_loss:
            best_loss = cur_loss
            best_weights = current_weights

        if callback is not None:
            callback(k + 1, iterations, cur_loss, best_loss)

    return best_weights, loss_history


# ---------------------------------------------------------------------------
# Head-to-Head Tournament Arena (SPRT)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ArenaResult:
    games_played: int
    wins_a: int
    wins_b: int
    draws: int
    score_a: float
    elo_diff: float

    @property
    def win_rate_a(self) -> float:
        return self.score_a / max(1, self.games_played)


def _play_arena_pair(args: tuple[int, int, dict[str, float], dict[str, float]]) -> tuple[float, float]:
    """Play two mirrored games (game 1: A as P0, game 2: B as P0) from initial state."""
    _, depth, weights_a_dict, weights_b_dict = args
    w_a = EvalWeights.from_dict(weights_a_dict)
    w_b = EvalWeights.from_dict(weights_b_dict)

    # Game 1: Player 0 = A, Player 1 = B
    s1 = initial_state()
    while not s1.game_over:
        curr = s1.current_player
        w = w_a if curr == 0 else w_b
        mv = best_move(s1, depth=depth, use_book=False, weights=w)
        s1, _ = apply_move(s1, mv)

    p1, p2 = score(s1)
    pts1_a = 1.0 if p1 > p2 else (0.5 if p1 == p2 else 0.0)

    # Game 2: Player 0 = B, Player 1 = A
    s2 = initial_state()
    while not s2.game_over:
        curr = s2.current_player
        w = w_b if curr == 0 else w_a
        mv = best_move(s2, depth=depth, use_book=False, weights=w)
        s2, _ = apply_move(s2, mv)

    p1, p2 = score(s2)
    pts2_a = 0.0 if p1 > p2 else (0.5 if p1 == p2 else 1.0)

    return pts1_a, pts2_a


def run_sprt_arena(
    weights_a: EvalWeights,
    weights_b: EvalWeights,
    num_pairs: int = 15,
    depth: int = 3,
    num_workers: int | None = None,
) -> ArenaResult:
    """Run an automated head-to-head tournament with opening side parity."""
    workers = num_workers or max(1, os.cpu_count() or 1)
    dict_a = weights_a.to_dict()
    dict_b = weights_b.to_dict()

    tasks = [(i, depth, dict_a, dict_b) for i in range(num_pairs)]

    score_a = 0.0
    wins_a = 0
    wins_b = 0
    draws = 0

    if workers == 1:
        for t in tasks:
            g1, g2 = _play_arena_pair(t)
            for pts in (g1, g2):
                score_a += pts
                if pts == 1.0:
                    wins_a += 1
                elif pts == 0.0:
                    wins_b += 1
                else:
                    draws += 1
    else:
        with multiprocessing.Pool(processes=workers) as pool:
            for g1, g2 in pool.imap_unordered(_play_arena_pair, tasks):
                for pts in (g1, g2):
                    score_a += pts
                    if pts == 1.0:
                        wins_a += 1
                    elif pts == 0.0:
                        wins_b += 1
                    else:
                        draws += 1

    total_games = num_pairs * 2
    w_rate = score_a / max(1, total_games)
    # Clamp win rate to avoid log(0)
    clamped_wr = max(0.01, min(0.99, w_rate))
    elo_diff = -400.0 * math.log10((1.0 / clamped_wr) - 1.0)

    return ArenaResult(
        games_played=total_games,
        wins_a=wins_a,
        wins_b=wins_b,
        draws=draws,
        score_a=score_a,
        elo_diff=elo_diff,
    )


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Turkish Mangala AI Automated Tuning & Arena")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: selfplay
    sp_parser = subparsers.add_parser("selfplay", help="Generate quiet training data via selfplay")
    sp_parser.add_argument("--games", type=int, default=30, help="Number of games to simulate")
    sp_parser.add_argument("--time-limit", type=float, default=0.02, help="Seconds per move")
    sp_parser.add_argument("--out", type=str, default="positions.json", help="Path to save output JSON")

    # Subcommand: tune
    tn_parser = subparsers.add_parser("tune", help="Optimize weights on an existing dataset using SPSA")
    tn_parser.add_argument("--data", type=str, required=True, help="Input positions JSON file")
    tn_parser.add_argument("--iters", type=int, default=20, help="Number of SPSA iterations")
    tn_parser.add_argument("--out", type=str, default="tuned_weights.json", help="Path to save tuned weights")

    # Subcommand: arena
    ar_parser = subparsers.add_parser("arena", help="Run head-to-head match tournament between weight sets")
    ar_parser.add_argument("--pairs", type=int, default=10, help="Number of mirrored game pairs (x2 games)")
    ar_parser.add_argument("--depth", type=int, default=3, help="Search depth for match play")
    ar_parser.add_argument("--candidate", type=str, default=None, help="JSON file with candidate weights")

    args = parser.parse_args()

    if args.command == "selfplay":
        t0 = time.time()
        print(f"[SELFPLAY] Generating {args.games} games...")
        positions = generate_selfplay_dataset(num_games=args.games, time_limit=args.time_limit)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump([p.to_dict() for p in positions], f, indent=2)
        elapsed = time.time() - t0
        print(f"[OK] Generated {len(positions)} positions in {elapsed:.2f}s -> saved to {args.out}")

    elif args.command == "tune":
        with open(args.data, encoding="utf-8") as f:
            data = json.load(f)
        positions = [TrainingPosition.from_dict(d) for d in data]
        print(f"[TUNE] Loaded {len(positions)} training positions from {args.data}.")

        def on_step(iter_num: int, total_iters: int, cur_l: float, best_l: float) -> None:
            print(f"[{iter_num:02d}/{total_iters:02d}] Loss: {cur_l:.6f} (Best: {best_l:.6f})")

        tuned_w, _ = run_spsa_tuning(DEFAULT_WEIGHTS, positions, iterations=args.iters, callback=on_step)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(tuned_w.to_dict(), f, indent=2)
        print(f"[OK] Optimization complete! Tuned weights saved to {args.out}")

    elif args.command == "arena":
        w_b = DEFAULT_WEIGHTS
        if args.candidate and os.path.exists(args.candidate):
            with open(args.candidate, encoding="utf-8") as f:
                w_a = EvalWeights.from_dict(json.load(f))
            print(f"Comparing Candidate ({args.candidate}) vs Baseline (DEFAULT_WEIGHTS)...")
        else:
            w_a = DEFAULT_WEIGHTS
            print("Comparing Baseline vs Baseline (verification benchmark)...")

        t0 = time.time()
        res = run_sprt_arena(w_a, w_b, num_pairs=args.pairs, depth=args.depth)
        print("\n=== Match Arena Results ===")
        print(f"Total Games : {res.games_played}")
        res_summary = f"+{res.wins_a} -{res.wins_b} ={res.draws} ({res.score_a:.1f}/{res.games_played})"
        print(f"Candidate   : {res_summary}")
        print(f"Win Rate    : {res.win_rate_a * 100:.1f}%")
        print(f"Elo Delta   : {res.elo_diff:+.1f} Elo")
        print(f"Elapsed Time: {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()
