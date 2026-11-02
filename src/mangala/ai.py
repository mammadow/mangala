"""
ai.py - Strong, thread-safe AI for Turkish Mangala.

Search features:
  - Alpha-beta minimax with explicit min/max keyed on the root player, so
    extra turns (same player moves again) need no sign flips.
  - Transposition table (TT): caches (depth, value, flag, best_move) per
    position with EXACT / LOWER_BOUND / UPPER_BOUND flags.  The PV move from
    the TT is tried first, which dramatically improves pruning.
  - Iterative deepening with a time budget: searches depth 1, 2, 3, ...
    and keeps the last completed iteration's result.  At each new depth the
    TT is already warm from the previous pass, so the search is cheap.
  - Quiescence search: at depth-0 leaves, extends captures and extra-turn
    moves (up to _Q_DEPTH extra plies) to kill the horizon effect.
  - Endgame exact solver: with <= 12 stones left on the board the search
    runs to the end of the game.
  - Evaluation: treasury diff + mobility + extra-turn potential + capture
    exposure + empty-hole offense/exposure.

All search state lives in a ``Searcher`` instance, so concurrent searches
(web server threads, GUI hint thread) never interfere with each other.

Public API:
    best_move(state, depth=None, time_limit=2.5, rules=DEFAULT_RULES) -> int
        depth      : fixed-depth mode (no time limit).
        time_limit : iterative-deepening budget in seconds (used when depth is None).
    analyse(...) -> SearchResult   same arguments, returns move + score + stats.
    LEVELS / best_move_for_level(state, level)  difficulty presets.
"""
from __future__ import annotations

import math
import time as _time
from dataclasses import dataclass, field
from typing import Optional

from .engine import (
    DEFAULT_RULES,
    P1_PITS,
    P1_TREASURY,
    P2_PITS,
    P2_TREASURY,
    TOTAL,
    GameState,
    MoveEvents,
    Rules,
    apply_move,
    legal_moves,
    score,
)

_INF = math.inf

# ---------------------------------------------------------------------------
# Transposition table flags
# ---------------------------------------------------------------------------

_EXACT       = 0   # stored value is the exact minimax value
_LOWER_BOUND = 1   # stored value is a lower bound (failed high / beta cutoff)
_UPPER_BOUND = 2   # stored value is an upper bound (failed low)

_WIN = 10_000.0           # terminal scores are +/- (_WIN + stone difference)
_Q_DEPTH = 4              # maximum extra plies in quiescence
_ENDGAME_STONES = 12      # solve exactly when this few stones remain on board
_ENDGAME_DEPTH = 64
_TIME_CHECK_MASK = 0x7F   # check the clock every 128 nodes

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


def _evaluate(state: GameState, root: int) -> float:
    """Heuristic score from root player's perspective."""
    p1, p2 = score(state)
    treasury_diff = (p1 - p2) if root == 0 else (p2 - p1)

    own_pits  = P1_PITS     if root == 0 else P2_PITS
    opp_pits  = P2_PITS     if root == 0 else P1_PITS
    own_treas = P1_TREASURY if root == 0 else P2_TREASURY
    opp_treas = P2_TREASURY if root == 0 else P1_TREASURY

    pits = state.pits
    own_stones = sum(pits[i] for i in own_pits)
    opp_stones = sum(pits[i] for i in opp_pits)

    # Extra-turn potential: bonus for each own pit whose last sown stone
    # would land in own treasury (free-tempo move).
    # Also compute empty-hole offense along the same sowing simulation.
    extra_bonus = 0.0
    empty_hole_offense = 0.0
    own_pits_set = set(own_pits)
    for i in own_pits:
        n = pits[i]
        if n == 0:
            continue
        sow_count = n - 1 if n > 1 else 1
        pos = i
        for _ in range(sow_count):
            pos = (pos + 1) % TOTAL
            if pos == opp_treas:
                pos = (pos + 1) % TOTAL
        if pos == own_treas:
            extra_bonus += 0.4
        # Empty-hole offense: sowing lands in own pit that is currently empty
        # and the directly opposite opponent pit has stones.
        elif pos in own_pits_set and pits[pos] == 0:
            opposite = 12 - pos
            if pits[opposite] > 0:
                empty_hole_offense += 0.25 * (pits[opposite] + 1)

    # Regular capture exposure: penalty for own even-count pits (immediately
    # capturable by the opponent's last stone).
    exposure = 0.0
    for i in own_pits:
        n = pits[i]
        if n > 0 and n % 2 == 0:
            exposure += 0.3

    # Empty-hole exposure: penalty when opponent can exploit own empty pits.
    # For each own empty pit e whose opposite has stones, check whether any
    # opponent pit's sowing would land exactly in e.
    empty_hole_exposure = 0.0
    for e in own_pits:
        if pits[e] != 0:
            continue
        opposite = 12 - e
        if pits[opposite] == 0:
            continue
        # Check if any opponent pit can land its last stone in e.
        for j in opp_pits:
            m = pits[j]
            if m == 0:
                continue
            sow_count = m - 1 if m > 1 else 1
            pos = j
            for _ in range(sow_count):
                pos = (pos + 1) % TOTAL
                if pos == own_treas:
                    pos = (pos + 1) % TOTAL
            if pos == e:
                empty_hole_exposure += 0.25 * (pits[opposite] + 1)
                break  # one threat per empty pit is enough

    return (treasury_diff
            + 0.1 * (own_stones - opp_stones)
            + extra_bonus
            + empty_hole_offense
            - exposure
            - empty_hole_exposure)


# ---------------------------------------------------------------------------
# Move ordering
# ---------------------------------------------------------------------------

def _move_priority(events: MoveEvents) -> tuple[int, int]:
    """Sort key: extra-turn > big-capture > other."""
    if events['extra_turn']:
        return (0, -events['capture'])
    if events['capture'] > 0:
        return (1, -events['capture'])
    return (2, 0)


def _key(state: GameState) -> tuple:
    return (tuple(state.pits), state.current_player)


# ---------------------------------------------------------------------------
# Searcher
# ---------------------------------------------------------------------------

class Searcher:
    """One search context (TT, clock, counters). Not shared between threads."""

    def __init__(self, rules: Rules = DEFAULT_RULES) -> None:
        self.rules = rules
        self.tt: dict = {}
        self.nodes = 0
        self._deadline = _INF

    # -- move generation ---------------------------------------------------

    def _ordered_children(self, state: GameState,
                          pv_move: int = -1) -> list[tuple[int, GameState]]:
        """Legal (move, child) pairs sorted best-first; PV move (from TT) first.

        Children are generated once here and reused by the search.
        """
        scored = []
        for m in legal_moves(state):
            child, ev = apply_move(state, m, self.rules)
            is_pv = 0 if m == pv_move else 1
            scored.append(((is_pv, _move_priority(ev), m), m, child))
        scored.sort(key=lambda t: t[0])
        return [(m, child) for _, m, child in scored]

    # -- quiescence --------------------------------------------------------

    def _quiescence(self, state: GameState, alpha: float, beta: float,
                    root: int, q_depth: int) -> float:
        """Extend noisy positions (captures / extra turns) past the main horizon."""
        self.nodes += 1
        if state.game_over:
            return _terminal_value(state, root)

        stand_pat = _evaluate(state, root)

        if q_depth == 0:
            return stand_pat

        if state.current_player == root:
            # Maximiser: stand_pat is a lower bound (can always stand pat).
            if stand_pat >= beta:
                return stand_pat
            alpha = max(alpha, stand_pat)
            best = stand_pat
            for m in legal_moves(state):
                child, ev = apply_move(state, m, self.rules)
                if not (ev['capture'] > 0 or ev['extra_turn']):
                    continue  # only noisy moves in quiescence
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
            for m in legal_moves(state):
                child, ev = apply_move(state, m, self.rules)
                if not (ev['capture'] > 0 or ev['extra_turn']):
                    continue
                val = self._quiescence(child, alpha, beta, root, q_depth - 1)
                if val < best:
                    best = val
                if best < beta:
                    beta = best
                if alpha >= beta:
                    break
            return best

    # -- alpha-beta with TT ------------------------------------------------

    def _search(self, state: GameState, depth: int, alpha: float, beta: float,
                root: int) -> float:
        """Alpha-beta minimax.  Explicit min/max handles extra-turn correctly."""
        self.nodes += 1
        # Time guard — checked every 1024 nodes to keep overhead negligible.
        if (self.nodes & _TIME_CHECK_MASK) == 0 and _time.monotonic() >= self._deadline:
            raise _TimeUp

        if state.game_over:
            return _terminal_value(state, root)

        # Endgame exact solver: when few stones remain the tree is tiny;
        # override depth and search all the way to terminal.
        pits = state.pits
        stones_on_board = sum(pits[0:6]) + sum(pits[7:13])
        if stones_on_board <= _ENDGAME_STONES and depth < _ENDGAME_DEPTH:
            depth = _ENDGAME_DEPTH

        if depth == 0:
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

        # The window actually searched (after TT tightening) decides whether
        # the result is exact or only a bound.
        alpha_orig = alpha
        beta_orig  = beta

        children = self._ordered_children(state, pv_move)
        if not children:
            return _evaluate(state, root)

        maximising = state.current_player == root
        best_val   = -_INF if maximising else _INF
        best_here  = children[0][0]

        if maximising:
            for m, child in children:
                val = self._search(child, depth - 1, alpha, beta, root)
                if val > best_val:
                    best_val  = val
                    best_here = m
                if best_val > alpha:
                    alpha = best_val
                if alpha >= beta:
                    break   # beta cutoff
        else:
            for m, child in children:
                val = self._search(child, depth - 1, alpha, beta, root)
                if val < best_val:
                    best_val  = val
                    best_here = m
                if best_val < beta:
                    beta = best_val
                if alpha >= beta:
                    break   # alpha cutoff

        # --- Store result in transposition table ---
        if best_val <= alpha_orig:
            flag = _UPPER_BOUND  # failed low
        elif best_val >= beta_orig:
            flag = _LOWER_BOUND  # failed high
        else:
            flag = _EXACT
        self.tt[key] = (depth, best_val, flag, best_here)

        return best_val

    # -- root --------------------------------------------------------------

    def _search_root(self, state: GameState, depth: int,
                     pv_move: int) -> tuple[int, float]:
        """Search every root move at *depth*; return (best_move, value).

        The best value so far is passed down as alpha, so moves that cannot
        beat it are refuted cheaply.  Ties keep the earlier (better-ordered)
        move, exactly like a plain full-window root loop.
        """
        root = state.current_player
        best_val = -_INF
        best_m = -1
        for m, child in self._ordered_children(state, pv_move):
            val = self._search(child, depth - 1, best_val, _INF, root)
            if val > best_val or best_m == -1:
                best_val = val
                best_m = m
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

    def analyse(self, state: GameState, depth: Optional[int] = None,
                time_limit: float = DEFAULT_TIME_LIMIT) -> SearchResult:
        """Search *state* and return the best move with statistics.

        depth      : If given, fixed-depth alpha-beta with no time limit.
        time_limit : Seconds budget for iterative deepening (when depth is None).
        """
        moves = legal_moves(state)
        if not moves:
            raise ValueError("no legal moves: the game is over")

        start = _time.monotonic()
        self.tt = {}                      # fresh table for each search
        self.nodes = 0

        if len(moves) == 1:               # no search needed
            return SearchResult(moves[0], _evaluate(state, state.current_player),
                                0, 0, 0.0, [moves[0]])

        root_key = _key(state)

        if depth is not None:
            # ---- Fixed-depth mode ----
            if depth < 1:
                raise ValueError("depth must be >= 1")
            self._deadline = _INF
            best_m, best_val = self._search_root(state, depth, -1)
            done_depth = depth
        else:
            # ---- Iterative deepening with time budget ----
            if not time_limit > 0:
                raise ValueError("time_limit must be > 0")
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
            best_val = _evaluate(state, state.current_player)
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

def analyse(state: GameState, depth: Optional[int] = None,
            time_limit: float = DEFAULT_TIME_LIMIT,
            rules: Rules = DEFAULT_RULES) -> SearchResult:
    """Search *state* and return a :class:`SearchResult`."""
    return Searcher(rules).analyse(state, depth=depth, time_limit=time_limit)


def best_move(state: GameState, depth: Optional[int] = None,
              time_limit: float = DEFAULT_TIME_LIMIT,
              rules: Rules = DEFAULT_RULES) -> int:
    """Return the pit index of the best move for the current player.

    Parameters
    ----------
    depth      : If given, use classic fixed-depth alpha-beta (no time limit).
                 TT and quiescence are active; iterative deepening is not used.
    time_limit : Seconds budget for iterative-deepening search.  Only used
                 when depth is None.  Default 2.5 s.
    rules      : Rule variants (see :class:`mangala.engine.Rules`).
    """
    return analyse(state, depth=depth, time_limit=time_limit, rules=rules).move


# Difficulty presets: keyword arguments for best_move / analyse.
LEVELS: dict[str, dict] = {
    "easy":   {"depth": 2},
    "medium": {"depth": 5},
    "hard":   {"time_limit": 1.0},
    "expert": {"time_limit": DEFAULT_TIME_LIMIT},
}


def best_move_for_level(state: GameState, level: str = "expert",
                        rules: Rules = DEFAULT_RULES) -> int:
    """Best move using one of the :data:`LEVELS` presets."""
    try:
        preset = LEVELS[level]
    except KeyError:
        raise ValueError(f"unknown level {level!r}; choose from {list(LEVELS)}") from None
    return best_move(state, rules=rules, **preset)
