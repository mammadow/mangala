"""
ai.py - Tournament-grade, thread-safe AI for Turkish Mangala.

Search features:
  - Alpha-beta minimax with explicit min/max keyed on the root player, so
    extra turns (same player moves again) need no sign flips.
  - Principal Variation Search (PVS): zero-window scout search on non-PV
    branches to aggressively prune suboptimal subtrees.
  - Killer Move Heuristic: stores quiet refutations per ply to trigger
    immediate beta-cutoffs in sister branches.
  - History Heuristic Table: tracks depth-squared cutoff frequency per pit
    to dynamically optimize move ordering outside the transposition table.
  - Transposition table (TT): caches (depth, value, flag, best_move) per
    position with EXACT / LOWER_BOUND / UPPER_BOUND flags and depth-preferred
    retention. The PV move from the TT is tried first.
  - Precomputed Opening Book: instant grandmaster-level play for opening plies.
  - Iterative deepening with a time budget: searches depth 1, 2, 3, ...
    and keeps the last completed iteration's result.
  - Quiescence search: at depth-0 leaves, extends captures and extra-turn
    moves (up to _Q_DEPTH extra plies) to kill the horizon effect.
  - Endgame exact solver: with <= 12 stones left on the board the search
    runs to the end of the game.
  - Evaluation: treasury diff + mobility + tactical capture offense/exposure +
    ladder/chain extra turn potential + endgame sweep proximity.

All search state lives in a ``Searcher`` instance, so concurrent searches
(web server threads, GUI hint thread) never interfere with each other.

Public API:
    best_move(state, depth=None, time_limit=2.5, rules=DEFAULT_RULES) -> int
    analyse(...) -> SearchResult
    LEVELS / best_move_for_level(state, level)
"""
from __future__ import annotations

import math
import time as _time
from collections.abc import Sequence
from dataclasses import dataclass, field

from .book import get_book_move
from .engine import (
    DEFAULT_RULES,
    OPP_PITS_RANGE,
    OWN_PITS_RANGE,
    P1_PITS,
    P1_TREASURY,
    P2_PITS,
    P2_TREASURY,
    SOW_LANDING,
    TOTAL,
    GameState,
    Rules,
    apply_move,
    legal_moves,
    score,
)
from .nnue import DEFAULT_NNUE
from .tablebase import DEFAULT_EGTB_STONES, probe_egtb, probe_egtb_move

_OWN_PITS_TUPLE: tuple[tuple[int, ...], tuple[int, ...]] = (tuple(P1_PITS), tuple(P2_PITS))
_OPP_PITS_TUPLE: tuple[tuple[int, ...], tuple[int, ...]] = (tuple(P2_PITS), tuple(P1_PITS))
_OWN_TREAS_TUPLE: tuple[int, int] = (P1_TREASURY, P2_TREASURY)
_OPP_TREAS_TUPLE: tuple[int, int] = (P2_TREASURY, P1_TREASURY)

_INF = math.inf
_MAX_PLY = 64
_PVS_EPSILON = 1e-4

# ---------------------------------------------------------------------------
# Transposition table flags
# ---------------------------------------------------------------------------

_EXACT       = 0   # stored value is the exact minimax value
_LOWER_BOUND = 1   # stored value is a lower bound (failed high / beta cutoff)
_UPPER_BOUND = 2   # stored value is an upper bound (failed low)

_WIN = 10_000.0           # terminal scores are +/- (_WIN + stone difference)
_Q_DEPTH = 4              # maximum extra plies in quiescence
_ENDGAME_STONES = 16      # solve exactly when 16 or fewer stones remain on board
_ENDGAME_DEPTH = 64
_TIME_CHECK_MASK = 0x7F   # check the clock every 128 nodes
_ASPIRATION_WINDOW = 0.5  # initial aspiration search half-window

DEFAULT_TIME_LIMIT = 2.5


class _TimeUp(Exception):
    """Raised inside the search when the time budget is exhausted."""
    __slots__ = ()


@dataclass
class SearchResult:
    move: int                 # best pit index for the side to move
    score: float              # evaluation from the mover's perspective
    depth: int                # deepest fully completed iteration
    nodes: int                # nodes visited (main search + quiescence)
    elapsed: float            # seconds
    pv: list[int] = field(default_factory=list)  # principal variation

    @property
    def is_forced_result(self) -> bool:
        """True if the search proved a win or loss."""
        return abs(self.score) >= _WIN


# ---------------------------------------------------------------------------
# Evaluation Weights Dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class EvalWeights:
    """Configurable weights for the Turkish Mangala heuristic evaluation."""
    w_mobility: float = 0.10
    w_extra_single: float = 0.60
    w_extra_multi: float = 0.40
    w_ladder_cascade: float = 0.35
    w_capture_offense: float = 0.35
    w_empty_hole_offense: float = 0.25
    w_capture_exposure: float = 0.35
    w_empty_hole_exposure: float = 0.25
    w_parity_own_even: float = 0.08
    w_parity_own_odd: float = -0.06
    w_parity_opp_odd: float = 0.06
    w_parity_opp_even: float = -0.08
    w_fortress: float = 0.20
    w_sweep: float = 0.20
    w_threshold_own: float = 0.50
    w_threshold_opp: float = 0.60

    def to_dict(self) -> dict[str, float]:
        return {
            "w_mobility": self.w_mobility,
            "w_extra_single": self.w_extra_single,
            "w_extra_multi": self.w_extra_multi,
            "w_ladder_cascade": self.w_ladder_cascade,
            "w_capture_offense": self.w_capture_offense,
            "w_empty_hole_offense": self.w_empty_hole_offense,
            "w_capture_exposure": self.w_capture_exposure,
            "w_empty_hole_exposure": self.w_empty_hole_exposure,
            "w_parity_own_even": self.w_parity_own_even,
            "w_parity_own_odd": self.w_parity_own_odd,
            "w_parity_opp_odd": self.w_parity_opp_odd,
            "w_parity_opp_even": self.w_parity_opp_even,
            "w_fortress": self.w_fortress,
            "w_sweep": self.w_sweep,
            "w_threshold_own": self.w_threshold_own,
            "w_threshold_opp": self.w_threshold_opp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, float]) -> EvalWeights:
        return cls(**{k: float(v) for k, v in d.items() if k in cls.__dataclass_fields__})


DEFAULT_WEIGHTS = EvalWeights()


# ---------------------------------------------------------------------------
# Terminal value / evaluation (pure functions)
# ---------------------------------------------------------------------------

def _terminal_value(state: GameState, root: int) -> float:
    """Score a finished game from root player's perspective."""
    p1, p2 = score(state)
    diff = (p1 - p2) if root == 0 else (p2 - p1)
    if diff > 0:
        return _WIN + diff
    if diff < 0:
        return -_WIN + diff
    return 0.0


def _evaluate(state: GameState, root: int, weights: EvalWeights = DEFAULT_WEIGHTS) -> float:
    """Tournament-grade heuristic score from root player's perspective."""
    p1, p2 = score(state)
    treasury_diff = (p1 - p2) if root == 0 else (p2 - p1)

    own_pits  = _OWN_PITS_TUPLE[root]
    opp_pits  = _OPP_PITS_TUPLE[root]
    own_treas = _OWN_TREAS_TUPLE[root]
    opp_treas = _OPP_TREAS_TUPLE[root]
    own_min, own_max = OWN_PITS_RANGE[root]
    opp_min, opp_max = OPP_PITS_RANGE[root]
    landing_table = SOW_LANDING[root]
    opp_landing_table = SOW_LANDING[1 - root]

    pits = state.pits
    own_t = pits[own_treas]
    opp_t = pits[opp_treas]

    # Mathematical win threshold: >= 25 stones in treasury guarantees victory (48 - 25 = 23 max for opp)
    if own_t >= 25:
        return _WIN + (own_t - opp_t)
    if opp_t >= 25:
        return -_WIN + (own_t - opp_t)

    own_stones = sum(pits[i] for i in own_pits)
    opp_stones = sum(pits[i] for i in opp_pits)

    # Threshold urgency: escalating value when closing in on 25 stones, and high alert if opponent is
    threshold_bonus = 0.0
    if own_t >= 20:
        threshold_bonus += (own_t - 19) * weights.w_threshold_own
    if opp_t >= 20:
        threshold_bonus -= (opp_t - 19) * weights.w_threshold_opp

    # Extra-turn potential, ladder cascades, regular capture offense & empty-hole offense
    extra_bonus = 0.0
    own_ladders = 0
    opp_ladders = 0
    capture_offense = 0.0
    empty_hole_offense = 0.0

    for i in own_pits:
        n = pits[i]
        if n == 0:
            continue
        sow_count = n - 1 if n > 1 else 1
        pos = landing_table[i][sow_count % 13]
        if pos == own_treas:
            # Extra turn into treasury; bonus higher for direct single-step ladder
            extra_bonus += weights.w_extra_single if n == 1 and i == own_max else weights.w_extra_multi
            own_ladders += 1
        elif own_min <= pos <= own_max and pits[pos] == 0 and sow_count < 13:
            # Rule 4: Empty pit capture on own side (including wrap-around sow_count >= 8)
            opposite = 12 - pos
            opp_after = pits[opposite] + (1 if sow_count >= 8 else 0)
            if opp_after > 0:
                empty_hole_offense += weights.w_empty_hole_offense * (opp_after + 1)
        elif opp_min <= pos <= opp_max and (pits[pos] + 1) % 2 == 0:
            # Rule 3: Regular capture on opponent's side (lands on odd pit, making it even)
            capture_offense += weights.w_capture_offense * (pits[pos] + 1)

    # Threat exposure: check if opponent's moves threaten capture or extra turns
    capture_exposure = 0.0
    for j in opp_pits:
        m = pits[j]
        if m == 0:
            continue
        sow_count = m - 1 if m > 1 else 1
        pos = opp_landing_table[j][sow_count % 13]
        if pos == opp_treas:
            opp_ladders += 1
        elif own_min <= pos <= own_max and pits[pos] > 0 and (pits[pos] + 1) % 2 == 0:
            # Opponent landing in our pit makes count even if it was odd
            capture_exposure += weights.w_capture_exposure * (pits[pos] + 1)

    # Exact Exponential Binary Merdiven Cascade (Theorem 3: 2^k - 1 consecutive bonus turns)
    own_stair = 0
    for d in range(1, 7):
        if pits[own_max + 1 - d] == d:
            own_stair += 1
        else:
            break
    opp_stair = 0
    for d in range(1, 7):
        if pits[opp_max + 1 - d] == d:
            opp_stair += 1
        else:
            break

    ladder_cascade_bonus = 0.0
    if own_stair >= 2:
        ladder_cascade_bonus += weights.w_ladder_cascade * ((1 << own_stair) - 1 - own_stair)
    elif own_ladders >= 2:
        ladder_cascade_bonus += weights.w_ladder_cascade * (own_ladders - 1)

    if opp_stair >= 2:
        ladder_cascade_bonus -= weights.w_ladder_cascade * ((1 << opp_stair) - 1 - opp_stair)
    elif opp_ladders >= 2:
        ladder_cascade_bonus -= weights.w_ladder_cascade * (opp_ladders - 1)

    # Empty-hole exposure: check if opponent lands in their own empty pit opposite our stones
    empty_hole_exposure = 0.0
    for e in opp_pits:
        if pits[e] != 0:
            continue
        opposite = 12 - e
        if pits[opposite] == 0:
            continue
        for j in opp_pits:
            m = pits[j]
            if m == 0:
                continue
            sow_count = m - 1 if m > 1 else 1
            pos = opp_landing_table[j][sow_count % 13]
            if pos == e:
                empty_hole_exposure += weights.w_empty_hole_exposure * (pits[opposite] + 1)
                break

    # Even-parity defensive shield (Çift Sayı Kalkanı):
    # Pits with even counts cannot be captured under Rule 3 when sown into (+1 makes them odd)
    parity_shield = 0.0
    for i in own_pits:
        n = pits[i]
        if n > 0:
            parity_shield += weights.w_parity_own_even if n % 2 == 0 else weights.w_parity_own_odd
    for j in opp_pits:
        m = pits[j]
        if m > 0:
            parity_shield += weights.w_parity_opp_odd if m % 2 != 0 else weights.w_parity_opp_even

    # Deep fortress reserves (Kuyu Saklama):
    # Back pits (0/1 for P1, 7/8 for P2) with >= 8 stones threaten full-board sowing sweeps
    fortress_bonus = 0.0
    for i in (own_min, own_min + 1):
        if pits[i] >= 8:
            fortress_bonus += weights.w_fortress
    for j in (opp_min, opp_min + 1):
        if pits[j] >= 8:
            fortress_bonus -= weights.w_fortress

    # Endgame sweep ("kuyu kurutma") proximity:
    # Under Turkish rules, player whose side empties first takes all opponent stones
    sweep_bonus = 0.0
    if own_stones <= 4:
        sweep_bonus += weights.w_sweep * (4 - own_stones)
    if opp_stones <= 4:
        sweep_bonus -= weights.w_sweep * (4 - opp_stones)

    return (treasury_diff
            + weights.w_mobility * (own_stones - opp_stones)
            + extra_bonus
            + ladder_cascade_bonus
            + capture_offense
            + empty_hole_offense
            - capture_exposure
            - empty_hole_exposure
            + parity_shield
            + fortress_bonus
            + sweep_bonus
            + threshold_bonus)


# ---------------------------------------------------------------------------
# State key
# ---------------------------------------------------------------------------

def _key(state: GameState) -> tuple:
    return (tuple(state.pits), state.current_player)


# ---------------------------------------------------------------------------
# Searcher
# ---------------------------------------------------------------------------

class Searcher:
    """One search context (TT, clock, counters, heuristics). Not shared between threads."""

    def __init__(
        self,
        rules: Rules = DEFAULT_RULES,
        weights: EvalWeights = DEFAULT_WEIGHTS,
        use_nnue: bool = False,
    ) -> None:
        self.rules = rules
        self.weights = weights
        self.use_nnue = use_nnue
        self.tt: dict = {}
        self.nodes = 0
        self._deadline = _INF
        self.killer_moves: list[list[int]] = [[] for _ in range(_MAX_PLY)]
        self.history_table: list[list[int]] = [[0] * TOTAL for _ in range(2)]
        self.counter_moves: list[list[int]] = [[-1] * TOTAL for _ in range(2)]

    def _eval_state(self, state: GameState, root: int) -> float:
        """Evaluate *state* from *root* perspective using heuristic (and optional NNUE blend)."""
        base_ev = _evaluate(state, root, self.weights)
        if not self.use_nnue or abs(base_ev) >= _WIN:
            return base_ev
        return 0.75 * base_ev + 0.25 * DEFAULT_NNUE.evaluate(state, root)

    # -- move generation & ordering ----------------------------------------

    def _record_cutoff(
        self,
        player: int,
        move: int,
        ply: int,
        depth: int,
        prev_move: int = -1,
        quiet_tried: Sequence[int] = (),
    ) -> None:
        """Update killer moves, countermove table, and history heuristic (with malus) upon a cutoff."""
        if ply < len(self.killer_moves):
            killers = self.killer_moves[ply]
            if move not in killers:
                killers.insert(0, move)
                if len(killers) > 2:
                    killers.pop()
        bonus = depth * depth
        self.history_table[player][move] += bonus
        for qm in quiet_tried:
            if qm != move:
                self.history_table[player][qm] = max(-65536, self.history_table[player][qm] - bonus)
        if 0 <= prev_move < TOTAL:
            self.counter_moves[player][prev_move] = move

    def _ordered_children(
        self,
        state: GameState,
        pv_move: int = -1,
        ply: int = 0,
        prev_move: int = -1,
    ) -> list[tuple[int, GameState]]:
        """Legal (move, child) pairs sorted best-first.

        Ordering priority:
          1. Immediate 25-stone threshold win (20,000,000)
          2. PV move from transposition table (10,000,000)
          3. Extra-turn moves (5,000,000 + capture bonus)
          4. Tactically capturing moves (3,000,000 + capture bonus)
          5. Killer moves for this search ply (1,000,000 / 900,000)
          6. Countermove refutation for previous move (800,000)
          7. Quiet moves sorted by history heuristic score
        """
        scored = []
        killers = self.killer_moves[ply] if ply < len(self.killer_moves) else []
        curr_p = state.current_player
        curr_treas = _OWN_TREAS_TUPLE[curr_p]
        counter_m = self.counter_moves[curr_p][prev_move] if 0 <= prev_move < TOTAL else -1

        for m in legal_moves(state):
            child, ev = apply_move(state, m, self.rules)
            if child.pits[curr_treas] >= 25:
                # Immediate forced win: securing 25+ stones wins outright
                priority = 20_000_000
            elif m == pv_move:
                priority = 10_000_000
            elif ev['extra_turn']:
                priority = 5_000_000 + ev['capture'] * 10_000
            elif ev['capture'] > 0:
                priority = 3_000_000 + ev['capture'] * 10_000
            elif m in killers:
                priority = 1_000_000 - (killers.index(m) * 100_000)
            elif m == counter_m:
                priority = 800_000
            else:
                priority = self.history_table[curr_p][m]
            scored.append((priority, m, child))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [(m, child) for _, m, child in scored]

    # -- quiescence --------------------------------------------------------

    def _quiescence(self, state: GameState, alpha: float, beta: float,
                    root: int, q_depth: int) -> float:
        """Extend noisy positions (captures / extra turns) past the main horizon."""
        self.nodes += 1
        if state.game_over:
            return _terminal_value(state, root)

        pits = state.pits
        own_t = pits[_OWN_TREAS_TUPLE[root]]
        opp_t = pits[_OPP_TREAS_TUPLE[root]]
        if own_t >= 25:
            return _WIN + (own_t - opp_t)
        if opp_t >= 25:
            return -_WIN + (own_t - opp_t)

        stand_pat = self._eval_state(state, root)

        if q_depth == 0:
            return stand_pat

        # Collect and sort noisy moves (extra turns and high captures first)
        noisy_children: list[tuple[int, GameState]] = []
        for m in legal_moves(state):
            child, ev = apply_move(state, m, self.rules)
            if ev['capture'] > 0 or ev['extra_turn']:
                noisy_score = (1000 if ev['extra_turn'] else 0) + ev['capture']
                noisy_children.append((noisy_score, child))
        noisy_children.sort(key=lambda t: t[0], reverse=True)

        if state.current_player == root:
            # Maximiser: stand_pat is a lower bound (can always stand pat).
            if stand_pat >= beta:
                return stand_pat
            alpha = max(alpha, stand_pat)
            best = stand_pat
            for _, child in noisy_children:
                val = self._quiescence(child, alpha, beta, root, q_depth - 1)
                if val > best:
                    best = val
                if best > alpha:
                    alpha = best
                if alpha >= beta:
                    break
            return best
        else:
            # Minimiser: stand_pat is an upper bound.
            if stand_pat <= alpha:
                return stand_pat
            beta = min(beta, stand_pat)
            best = stand_pat
            for _, child in noisy_children:
                val = self._quiescence(child, alpha, beta, root, q_depth - 1)
                if val < best:
                    best = val
                if best < beta:
                    beta = best
                if alpha >= beta:
                    break
            return best

    # -- alpha-beta / PVS with TT ------------------------------------------

    def _search(
        self,
        state: GameState,
        depth: int,
        alpha: float,
        beta: float,
        root: int,
        ply: int = 0,
        prev_move: int = -1,
        extra_streak: int = 0,
    ) -> float:
        """Principal Variation Search (PVS) with TT, EGTB, Fractional-Ply Extensions, LMR, and RFP."""
        self.nodes += 1
        # Time guard — checked every 128 nodes to keep overhead negligible.
        if (self.nodes & _TIME_CHECK_MASK) == 0 and _time.monotonic() >= self._deadline:
            raise _TimeUp

        if state.game_over:
            return _terminal_value(state, root)

        # Immediate threshold win: 25+ stones in treasury is unassailable
        pits = state.pits
        own_t = pits[_OWN_TREAS_TUPLE[root]]
        opp_t = pits[_OPP_TREAS_TUPLE[root]]
        if own_t >= 25:
            return _WIN + (own_t - opp_t)
        if opp_t >= 25:
            return -_WIN + (own_t - opp_t)

        stones_on_board = sum(pits[0:6]) + sum(pits[7:13])

        # Instant O(1) Retrograde Endgame Tablebase lookup when stones <= DEFAULT_EGTB_STONES
        if stones_on_board <= DEFAULT_EGTB_STONES and ply > 0:
            egtb_diff = probe_egtb(state, max_stones=DEFAULT_EGTB_STONES, rules=self.rules)
            if egtb_diff is not None:
                root_diff = egtb_diff if state.current_player == root else -egtb_diff
                if root_diff > 0:
                    return _WIN + root_diff
                if root_diff < 0:
                    return -_WIN + root_diff
                return 0.0

        # Endgame exact solver: when few stones remain the tree is tiny;
        # override depth and search all the way to terminal for competitive modes.
        if stones_on_board <= _ENDGAME_STONES and depth >= 4 and depth < _ENDGAME_DEPTH:
            depth = _ENDGAME_DEPTH

        if depth <= 0:
            return self._quiescence(state, alpha, beta, root, _Q_DEPTH)

        # --- Reverse Futility Pruning & Razoring at shallow depths ---
        if depth <= 2 and stones_on_board > _ENDGAME_STONES and extra_streak == 0:
            eval_margin = 1.5 * depth
            static_eval = self._eval_state(state, root)
            if state.current_player == root:
                if static_eval - eval_margin >= beta:
                    return static_eval - eval_margin
                if depth == 1 and static_eval + 2.5 <= alpha:
                    return self._quiescence(state, alpha, beta, root, _Q_DEPTH)
            else:
                if static_eval + eval_margin <= alpha:
                    return static_eval + eval_margin
                if depth == 1 and static_eval - 2.5 >= beta:
                    return self._quiescence(state, alpha, beta, root, _Q_DEPTH)

        # --- Transposition table lookup ---
        key        = _key(state)
        tt_entry   = self.tt.get(key)
        pv_move    = -1

        if tt_entry is not None:
            tt_depth, tt_val, tt_flag, tt_best = tt_entry
            pv_move = tt_best                       # always use PV for ordering
            if tt_depth >= depth:
                if tt_flag == _EXACT:
                    return tt_val
                elif tt_flag == _LOWER_BOUND:
                    alpha = max(alpha, tt_val)
                else:                               # _UPPER_BOUND
                    beta  = min(beta,  tt_val)
                if alpha >= beta:
                    return tt_val

        # Internal Iterative Reduction (IIR) on deep unvisited nodes
        if depth >= 4 and pv_move == -1 and stones_on_board > _ENDGAME_STONES and extra_streak == 0:
            depth -= 1

        alpha_orig = alpha
        beta_orig  = beta

        children = self._ordered_children(state, pv_move, ply, prev_move)
        if not children:
            return self._eval_state(state, root)

        maximising = state.current_player == root
        best_val   = -_INF if maximising else _INF
        best_here  = children[0][0]
        quiet_tried: list[int] = []

        if maximising:
            for i, (m, child) in enumerate(children):
                is_extra = child.current_player == state.current_player
                is_quiet = (
                    not is_extra
                    and child.pits[_OWN_TREAS_TUPLE[root]] == pits[_OWN_TREAS_TUPLE[root]]
                )
                next_streak = (extra_streak + 1) if is_extra else 0
                # Turn-conserving extension on the first bonus turn of a cascade at depth >= 3
                ext = 1 if (is_extra and extra_streak == 0 and 3 <= depth < _ENDGAME_DEPTH) else 0
                next_d = depth - 1 + ext

                if i == 0:
                    val = self._search(child, next_d, alpha, beta, root, ply + 1, m, next_streak)
                else:
                    # Late Move Reduction (LMR) on quiet, non-capture moves ordered late
                    do_lmr = i >= 3 and depth >= 3 and is_quiet
                    reduction = 1 if do_lmr else 0

                    val = self._search(
                        child, next_d - reduction, alpha, alpha + _PVS_EPSILON,
                        root, ply + 1, m, next_streak,
                    )
                    if reduction > 0 and val > alpha:
                        val = self._search(
                            child, next_d, alpha, alpha + _PVS_EPSILON,
                            root, ply + 1, m, next_streak,
                        )

                    if alpha < val < beta:
                        val = self._search(child, next_d, alpha, beta, root, ply + 1, m, next_streak)

                if val > best_val:
                    best_val  = val
                    best_here = m
                if best_val > alpha:
                    alpha = best_val
                if alpha >= beta:
                    self._record_cutoff(state.current_player, m, ply, depth, prev_move, quiet_tried)
                    break   # beta cutoff
                if is_quiet:
                    quiet_tried.append(m)
        else:
            for i, (m, child) in enumerate(children):
                is_extra = child.current_player == state.current_player
                is_quiet = (
                    not is_extra
                    and child.pits[_OPP_TREAS_TUPLE[root]] == pits[_OPP_TREAS_TUPLE[root]]
                )
                next_streak = (extra_streak + 1) if is_extra else 0
                ext = 1 if (is_extra and extra_streak == 0 and 3 <= depth < _ENDGAME_DEPTH) else 0
                next_d = depth - 1 + ext

                if i == 0:
                    val = self._search(child, next_d, alpha, beta, root, ply + 1, m, next_streak)
                else:
                    # Late Move Reduction (LMR) on quiet, non-capture moves ordered late
                    do_lmr = i >= 3 and depth >= 3 and is_quiet
                    reduction = 1 if do_lmr else 0

                    val = self._search(
                        child, next_d - reduction, beta - _PVS_EPSILON, beta,
                        root, ply + 1, m, next_streak,
                    )
                    if reduction > 0 and val < beta:
                        val = self._search(
                            child, next_d, beta - _PVS_EPSILON, beta,
                            root, ply + 1, m, next_streak,
                        )

                    if alpha < val < beta:
                        val = self._search(child, next_d, alpha, beta, root, ply + 1, m, next_streak)

                if val < best_val:
                    best_val  = val
                    best_here = m
                if best_val < beta:
                    beta = best_val
                if alpha >= beta:
                    self._record_cutoff(state.current_player, m, ply, depth, prev_move, quiet_tried)
                    break   # alpha cutoff
                if is_quiet:
                    quiet_tried.append(m)

        # --- Depth-preferred transposition table replacement ---
        if best_val <= alpha_orig:
            flag = _UPPER_BOUND
        elif best_val >= beta_orig:
            flag = _LOWER_BOUND
        else:
            flag = _EXACT

        existing = self.tt.get(key)
        if existing is None or depth >= existing[0]:
            self.tt[key] = (depth, best_val, flag, best_here)

        return best_val

    # -- root --------------------------------------------------------------

    def _search_root(self, state: GameState, depth: int,
                     pv_move: int, alpha: float = -_INF, beta: float = _INF) -> tuple[int, float]:
        """Search every root move at *depth*; return (best_move, value)."""
        root = state.current_player
        best_val = -_INF
        best_m = -1
        children = self._ordered_children(state, pv_move, ply=0)

        for i, (m, child) in enumerate(children):
            is_extra = child.current_player == root
            next_streak = 1 if is_extra else 0
            ext = 1 if (is_extra and 3 <= depth < _ENDGAME_DEPTH) else 0
            next_d = depth - 1 + ext

            if i == 0:
                val = self._search(
                    child, next_d, alpha, beta, root, ply=1, prev_move=m, extra_streak=next_streak,
                )
            else:
                # Scout search
                scout_alpha = max(alpha, best_val)
                val = self._search(
                    child, next_d, scout_alpha, scout_alpha + _PVS_EPSILON,
                    root, ply=1, prev_move=m, extra_streak=next_streak,
                )
                if val > scout_alpha and val < beta:
                    val = self._search(
                        child, next_d, scout_alpha, beta,
                        root, ply=1, prev_move=m, extra_streak=next_streak,
                    )

            if val > best_val or best_m == -1:
                best_val = val
                best_m = m
            if best_val >= beta:
                break
        return best_m, best_val

    def _extract_pv(self, state: GameState, first: int, max_len: int) -> list[int]:
        pv = [first]
        s, _ = apply_move(state, first, self.rules)
        seen = {_key(state)}
        while len(pv) < max_len and not s.game_over:
            k = _key(s)
            entry = self.tt.get(k)
            if entry is None or k in seen or entry[3] not in legal_moves(s):
                break
            seen.add(k)
            pv.append(entry[3])
            s, _ = apply_move(s, entry[3], self.rules)
        return pv

    def analyse(self, state: GameState, depth: int | None = None,
                time_limit: float = DEFAULT_TIME_LIMIT,
                use_book: bool = False) -> SearchResult:
        """Search *state* and return the best move with statistics.

        depth      : If given, fixed-depth alpha-beta with no time limit.
        time_limit : Seconds budget for iterative deepening (when depth is None).
        use_book   : If True, uses the precomputed opening book when available.
        """
        moves = legal_moves(state)
        if not moves:
            raise ValueError("no legal moves: the game is over")

        # Validate search bounds upfront
        if depth is not None:
            if depth < 1:
                raise ValueError("depth must be >= 1")
        else:
            if not time_limit > 0:
                raise ValueError("time_limit must be > 0")

        # Fast-path 1: Single legal move
        if len(moves) == 1:
            return SearchResult(moves[0], self._eval_state(state, state.current_player),
                                0, 0, 0.0, [moves[0]])

        # Fast-path 2: Opening book (when enabled and running time-budget search)
        if use_book and depth is None:
            book_mv = get_book_move(state)
            if book_mv is not None and book_mv in moves:
                return SearchResult(
                    move=book_mv,
                    score=self._eval_state(state, state.current_player),
                    depth=16,
                    nodes=1,
                    elapsed=0.0,
                    pv=[book_mv],
                )

        # Fast-path 3: Exact Retrograde EGTB lookup at root when <= DEFAULT_EGTB_STONES remain
        stones_on_board = sum(state.pits[0:6]) + sum(state.pits[7:13])
        if stones_on_board <= DEFAULT_EGTB_STONES:
            egtb_res = probe_egtb_move(state, max_stones=DEFAULT_EGTB_STONES, rules=self.rules)
            if egtb_res is not None:
                egtb_mv, egtb_diff = egtb_res
                egtb_score = (
                    (_WIN + egtb_diff) if egtb_diff > 0
                    else ((-_WIN + egtb_diff) if egtb_diff < 0 else 0.0)
                )
                return SearchResult(
                    move=egtb_mv,
                    score=egtb_score,
                    depth=_ENDGAME_DEPTH,
                    nodes=1,
                    elapsed=0.0,
                    pv=[egtb_mv],
                )

        start = _time.monotonic()
        self.tt = {}                      # fresh table for each search
        self.nodes = 0
        self.killer_moves = [[] for _ in range(_MAX_PLY)]
        self.history_table = [[0] * TOTAL for _ in range(2)]
        self.counter_moves = [[-1] * TOTAL for _ in range(2)]

        root_key = _key(state)

        if depth is not None:
            # ---- Fixed-depth mode ----
            self._deadline = _INF
            best_m, best_val = self._search_root(state, depth, -1)
            done_depth = depth
        else:
            # ---- Iterative deepening with time budget ----
            self._deadline = start + time_limit
            best_m, best_val = moves[0], -_INF   # always have a fallback
            done_depth = 0
            d = 1
            while True:
                if _time.monotonic() >= self._deadline:
                    break
                try:
                    # Root ordering uses the best move of the previous iteration.
                    pv = self.tt[root_key][3] if root_key in self.tt else -1
                    if d >= 3 and abs(best_val) < _WIN:
                        # Aspiration search with narrow window around previous score
                        asp_alpha = best_val - _ASPIRATION_WINDOW
                        asp_beta = best_val + _ASPIRATION_WINDOW
                        cand_m, cand_val = self._search_root(state, d, pv, asp_alpha, asp_beta)
                        if cand_val <= asp_alpha or cand_val >= asp_beta:
                            # Re-search with full window (-inf, +inf) if aspiration window failed
                            cand_m, cand_val = self._search_root(state, d, pv, -_INF, _INF)
                    else:
                        cand_m, cand_val = self._search_root(state, d, pv)
                except _TimeUp:
                    break   # keep the result of the last completed iteration
                # Full iteration completed — commit the result.
                best_m, best_val, done_depth = cand_m, cand_val, d
                self.tt[root_key] = (d, cand_val, _EXACT, cand_m)
                # Forced win/loss found, or the whole tree was solved.
                if abs(cand_val) >= _WIN or d >= _ENDGAME_DEPTH:
                    break
                d += 1

        if best_val == -_INF:            # no iteration completed (tiny budget)
            best_val = _evaluate(state, state.current_player, self.weights)
        return SearchResult(
            move=best_m,
            score=best_val,
            depth=done_depth,
            nodes=self.nodes,
            elapsed=_time.monotonic() - start,
            pv=self._extract_pv(state, best_m, max(1, min(done_depth, 16))),
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse(state: GameState, depth: int | None = None,
            time_limit: float = DEFAULT_TIME_LIMIT,
            rules: Rules = DEFAULT_RULES,
            use_book: bool = False,
            weights: EvalWeights = DEFAULT_WEIGHTS,
            use_nnue: bool = False) -> SearchResult:
    """Search *state* and return a :class:`SearchResult`."""
    return Searcher(rules, weights=weights, use_nnue=use_nnue).analyse(
        state, depth=depth, time_limit=time_limit, use_book=use_book,
    )


def best_move(state: GameState, depth: int | None = None,
              time_limit: float = DEFAULT_TIME_LIMIT,
              rules: Rules = DEFAULT_RULES,
              use_book: bool = True,
              weights: EvalWeights = DEFAULT_WEIGHTS,
              use_nnue: bool = False) -> int:
    """Return the pit index of the best move for the current player.

    Parameters
    ----------
    depth      : If given, use classic fixed-depth alpha-beta (no time limit).
                 TT and quiescence are active; iterative deepening is not used.
    time_limit : Seconds budget for iterative-deepening search. Only used
                 when depth is None. Default 2.5 s.
    rules      : Rule variants (see :class:`mangala.engine.Rules`).
    use_book   : If True, uses the precomputed opening book when available.
    weights    : Custom or tuned heuristic evaluation weights.
    use_nnue   : If True, blends heuristic evaluation with the quantized NNUE.
    """
    res = analyse(
        state,
        depth=depth,
        time_limit=time_limit,
        rules=rules,
        use_book=use_book,
        weights=weights,
        use_nnue=use_nnue,
    )
    return res.move


# Difficulty presets: keyword arguments for best_move / analyse.
LEVELS: dict[str, dict] = {
    "easy":   {"depth": 2, "use_book": False},
    "medium": {"depth": 5, "use_book": False},
    "hard":   {"time_limit": 1.0, "use_book": True},
    "expert": {"time_limit": DEFAULT_TIME_LIMIT, "use_book": True},
}


def best_move_for_level(state: GameState, level: str = "expert",
                        rules: Rules = DEFAULT_RULES) -> int:
    """Best move using one of the :data:`LEVELS` presets."""
    try:
        preset = LEVELS[level]
    except KeyError:
        raise ValueError(f"unknown level {level!r}; choose from {list(LEVELS)}") from None
    return best_move(state, rules=rules, **preset)
