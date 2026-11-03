"""
tablebase.py — Combinadic Retrograde Endgame Tablebase (EGTB) for Turkish Mangala.

Exploits two exact mathematical theorems of Turkish Mangala:
  1. Theorem 1 (Treasury-Invariant Net Yield & 180-deg STM Canonicalization):
     Future net stone yield Delta(P, s) depends solely on the 12 active pits P
     and side-to-move s, and satisfies Delta(P, 1) = -Delta(Rotate180(P), 0).
     Thus only STM = 0 canonical configurations need to be stored (50% reduction).
  2. Theorem 2 (Lexicographic DAG Ordering (K(P), Phi(P))):
     Because each player's treasury sits between their row and the opponent's row,
     any move that keeps total board stones K(P') == K(P) strictly decreases the
     intra-row treasury distance potential:
       Phi(P) = sum_{i=0..5} (6 - i) * P[i] + sum_{j=6..11} (12 - j) * P[j]
     Sorting each k-stone slice by increasing Phi(P) guarantees a 100% single-pass,
     cycle-free retrograde induction.
"""
from __future__ import annotations

import argparse
import math
import zlib
from collections import defaultdict
from collections.abc import Iterator, Sequence

from .engine import (
    DEFAULT_RULES,
    P1_TREASURY,
    P2_TREASURY,
    SWEEP_EMPTIED_SIDE,
    GameState,
    Rules,
    apply_move,
    legal_moves,
)

# Precomputed binomial coefficients BINOM[n][r] for n <= 32, r <= 13
_MAX_N = 33
_MAX_R = 14
BINOM: tuple[tuple[int, ...], ...] = tuple(
    tuple(math.comb(n, r) if n >= r else 0 for r in range(_MAX_R))
    for n in range(_MAX_N)
)

DEFAULT_EGTB_STONES = 6
_OFFSET = 128  # shifts signed int8 delta in [-48..+48] to unsigned byte [80..176]

# In-memory cache of built tablebases keyed by (max_stones, sweep_to)
_EGTB_CACHE: dict[tuple[int, str], tuple[int, bytearray]] = {}


def combinadic_index(pits_12: Sequence[int]) -> int:
    """Map a 12-pit tuple with total stones k = sum(pits_12) bijectively to [0, C(k+12, 12)).

    Uses unified cumulative stars-and-bars combinadics in O(1) time.
    """
    k = (
        pits_12[0] + pits_12[1] + pits_12[2] + pits_12[3] + pits_12[4] + pits_12[5]
        + pits_12[6] + pits_12[7] + pits_12[8] + pits_12[9] + pits_12[10] + pits_12[11]
    )
    idx = BINOM[k + 11][12]
    rem = k
    for j in range(11):
        rem -= pits_12[j]
        if rem <= 0:
            break
        idx += BINOM[rem + 10 - j][11 - j]
    return idx


def canonicalize_pits(state: GameState) -> tuple[int, ...]:
    """Extract the 12 active pits rotated to the current mover's perspective (STM = 0)."""
    p = state.pits
    if state.current_player == 0:
        return (p[0], p[1], p[2], p[3], p[4], p[5], p[7], p[8], p[9], p[10], p[11], p[12])
    return (p[7], p[8], p[9], p[10], p[11], p[12], p[0], p[1], p[2], p[3], p[4], p[5])


def _generate_compositions(k: int, bins: int = 12) -> Iterator[tuple[int, ...]]:
    """Yield all weak compositions of *k* stones into *bins* pits."""
    if bins == 1:
        yield (k,)
        return
    for first in range(k + 1):
        for rest in _generate_compositions(k - first, bins - 1):
            yield (first, *rest)


def _simulate_canonical_move(
    pits_12: tuple[int, ...],
    move: int,
    sweep_emptied: bool,
) -> tuple[tuple[int, ...], int, bool, bool]:
    """Simulate move (0..5) for STM=0 on a 12-pit tuple.

    Returns (child_pits_12, net_gain_stm, extra_turn, game_over).
    """
    # Map 12-pit canonical array to 14-hole board (index 6 = own treasury, 13 = opp treasury)
    b = [
        pits_12[0], pits_12[1], pits_12[2], pits_12[3], pits_12[4], pits_12[5],
        0,
        pits_12[6], pits_12[7], pits_12[8], pits_12[9], pits_12[10], pits_12[11],
        0,
    ]
    stones = b[move]
    if stones > 1:
        b[move] = 1
        to_sow = stones - 1
    else:
        b[move] = 0
        to_sow = 1

    idx = move
    for _ in range(to_sow):
        idx = (idx + 1) % 14
        if idx == 13:  # skip opponent treasury
            idx = 0
        b[idx] += 1
    last = idx
    extra_turn = last == 6

    # Rule 3: Regular capture on opponent side (7..12)
    if 7 <= last <= 12 and b[last] % 2 == 0 and b[last] > 0:
        b[6] += b[last]
        b[last] = 0
    # Rule 4: Empty-hole capture on own side (0..5)
    elif 0 <= last <= 5 and pits_12[last] == 0 and b[last] == 1:
        opp_idx = 12 - last
        if b[opp_idx] > 0:
            b[6] += 1 + b[opp_idx]
            b[last] = 0
            b[opp_idx] = 0

    own_rem = b[0] + b[1] + b[2] + b[3] + b[4] + b[5]
    opp_rem = b[7] + b[8] + b[9] + b[10] + b[11] + b[12]
    game_over = False

    if own_rem == 0:
        # STM=0 emptied own side first: STM=0 sweeps opponent's stones under both rules
        b[6] += opp_rem
        for j in range(7, 13):
            b[j] = 0
        game_over = True
    elif opp_rem == 0:
        # Opponent's side was emptied by STM=0's capture
        if sweep_emptied:
            b[13] += own_rem
        else:
            b[6] += own_rem
        for i in range(6):
            b[i] = 0
        game_over = True

    child_12 = (b[0], b[1], b[2], b[3], b[4], b[5], b[7], b[8], b[9], b[10], b[11], b[12])
    net_gain = b[6] - b[13]
    return child_12, net_gain, (extra_turn and not game_over), game_over


def build_egtb(max_stones: int = DEFAULT_EGTB_STONES, rules: Rules = DEFAULT_RULES) -> bytearray:
    """Build the canonical STM=0 Endgame Tablebase up to *max_stones* via (K, Phi) DAG induction."""
    if max_stones < 0 or max_stones > 16:
        raise ValueError("max_stones must be between 0 and 16")

    cache_key = (max_stones, rules.sweep_to)
    if cache_key in _EGTB_CACHE:
        return _EGTB_CACHE[cache_key][1]

    # If a larger tablebase for the same rule is already cached, slice it
    for (cached_max, cached_rule), (_, cached_tbl) in _EGTB_CACHE.items():
        if cached_rule == rules.sweep_to and cached_max >= max_stones:
            req_size = BINOM[max_stones + 12][12]
            sub_tbl = cached_tbl[:req_size]
            _EGTB_CACHE[cache_key] = (max_stones, sub_tbl)
            return sub_tbl

    total_states = BINOM[max_stones + 12][12]
    table = bytearray(total_states)
    sweep_emptied = rules.sweep_to == SWEEP_EMPTIED_SIDE

    for k in range(max_stones + 1):
        buckets: dict[int, list[tuple[int, ...]]] = defaultdict(list)
        for pits_12 in _generate_compositions(k, 12):
            phi = (
                6 * pits_12[0] + 5 * pits_12[1] + 4 * pits_12[2]
                + 3 * pits_12[3] + 2 * pits_12[4] + 1 * pits_12[5]
                + 6 * pits_12[6] + 5 * pits_12[7] + 4 * pits_12[8]
                + 3 * pits_12[9] + 2 * pits_12[10] + 1 * pits_12[11]
            )
            buckets[phi].append(pits_12)

        for phi in sorted(buckets.keys()):
            for pits_12 in buckets[phi]:
                idx = combinadic_index(pits_12)
                own_sum = pits_12[0] + pits_12[1] + pits_12[2] + pits_12[3] + pits_12[4] + pits_12[5]
                opp_sum = pits_12[6] + pits_12[7] + pits_12[8] + pits_12[9] + pits_12[10] + pits_12[11]

                if own_sum == 0:
                    table[idx] = opp_sum + _OFFSET
                    continue
                if opp_sum == 0:
                    table[idx] = -own_sum + _OFFSET
                    continue

                best_delta = -120
                for move in range(6):
                    if pits_12[move] == 0:
                        continue
                    child_12, gain, extra_turn, game_over = _simulate_canonical_move(
                        pits_12, move, sweep_emptied
                    )
                    if game_over:
                        val = gain
                    elif extra_turn:
                        child_delta = table[combinadic_index(child_12)] - _OFFSET
                        val = gain + child_delta
                    else:
                        rot_child = child_12[6:12] + child_12[0:6]
                        opp_delta = table[combinadic_index(rot_child)] - _OFFSET
                        val = gain - opp_delta

                    if val > best_delta:
                        best_delta = val

                table[idx] = best_delta + _OFFSET

    _EGTB_CACHE[cache_key] = (max_stones, table)
    return table


def probe_egtb(
    state: GameState,
    max_stones: int = DEFAULT_EGTB_STONES,
    rules: Rules = DEFAULT_RULES,
) -> int | None:
    """Return exact final score differential (own_final - opp_final) from current_player's view.

    Returns None if the active stone count on the 12 pits exceeds *max_stones*.
    """
    p = state.pits
    own_t = p[P1_TREASURY] if state.current_player == 0 else p[P2_TREASURY]
    opp_t = p[P2_TREASURY] if state.current_player == 0 else p[P1_TREASURY]
    if state.game_over:
        return own_t - opp_t

    k = (
        p[0] + p[1] + p[2] + p[3] + p[4] + p[5]
        + p[7] + p[8] + p[9] + p[10] + p[11] + p[12]
    )
    if k > max_stones:
        return None

    table = build_egtb(max_stones=max_stones, rules=rules)
    can_pits = canonicalize_pits(state)
    net_future_yield = table[combinadic_index(can_pits)] - _OFFSET
    return (own_t - opp_t) + net_future_yield


def probe_egtb_move(
    state: GameState,
    max_stones: int = DEFAULT_EGTB_STONES,
    rules: Rules = DEFAULT_RULES,
) -> tuple[int, int] | None:
    """Return (best_move, exact_final_diff) for *state* using the EGTB, or None if k > max_stones."""
    if state.game_over:
        return None
    p = state.pits
    k = (
        p[0] + p[1] + p[2] + p[3] + p[4] + p[5]
        + p[7] + p[8] + p[9] + p[10] + p[11] + p[12]
    )
    if k > max_stones:
        return None

    moves = legal_moves(state)
    if not moves:
        return None

    root_player = state.current_player
    best_m = moves[0]
    best_diff = -999

    for m in moves:
        child, _ = apply_move(state, m, rules)
        if child.game_over:
            c_own = child.pits[P1_TREASURY] if root_player == 0 else child.pits[P2_TREASURY]
            c_opp = child.pits[P2_TREASURY] if root_player == 0 else child.pits[P1_TREASURY]
            diff = c_own - c_opp
        else:
            child_diff = probe_egtb(child, max_stones=max_stones, rules=rules)
            assert child_diff is not None
            diff = child_diff if child.current_player == root_player else -child_diff

        if diff > best_diff:
            best_diff = diff
            best_m = m

    return best_m, best_diff


def compress_egtb(max_stones: int = DEFAULT_EGTB_STONES, rules: Rules = DEFAULT_RULES) -> bytes:
    """Return zlib-compressed bytes of the EGTB for *max_stones*."""
    raw = build_egtb(max_stones=max_stones, rules=rules)
    return zlib.compress(raw, level=9)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and verify Turkish Mangala Endgame Tablebase.")
    parser.add_argument("--max-stones", type=int, default=8, help="Maximum board stones K (default: 8)")
    parser.add_argument("--out", type=str, default=None, help="Optional output file path (.egtb.zlib)")
    args = parser.parse_args(argv)

    tbl = build_egtb(max_stones=args.max_stones)
    comp = zlib.compress(tbl, level=9)
    print(
        f"[EGTB] Built K <= {args.max_stones}: {len(tbl):,} canonical states "
        f"({len(tbl) / 1024:.1f} KiB raw, {len(comp) / 1024:.1f} KiB zlib)"
    )
    if args.out:
        with open(args.out, "wb") as f:
            f.write(comp)
        print(f"[OK] Saved compressed tablebase to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
