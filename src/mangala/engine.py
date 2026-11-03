"""
engine.py — Pure game logic for Turkish Mangala.

No I/O here: everything is plain data + pure functions so the minimax AI
(and any front-end) can call ``legal_moves`` / ``apply_move`` freely.

Pit layout (counterclockwise sowing order)::

    Index 0-5  : Player 1 pits
    Index 6    : Player 1 treasury (hazine)
    Index 7-12 : Player 2 pits
    Index 13   : Player 2 treasury (hazine)

Opposite pits (used by the empty-hole capture)::

    P2 display:  12  11  10   9   8   7
    P1 display:   0   1   2   3   4   5        opposite(i) = 12 - i
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

P1_PITS = list(range(0, 6))
P1_TREASURY = 6
P2_PITS = list(range(7, 13))
P2_TREASURY = 13
TOTAL = 14

STONES_PER_PIT = 4
TOTAL_STONES = STONES_PER_PIT * 12  # 48

PLAYER_PITS = [P1_PITS, P2_PITS]
PLAYER_TREASURY = [P1_TREASURY, P2_TREASURY]
OPP_TREASURY = [P2_TREASURY, P1_TREASURY]

# Precomputed pit boundaries for O(1) zero-allocation range checks
OWN_PITS_RANGE: tuple[tuple[int, int], tuple[int, int]] = ((0, 5), (7, 12))
OPP_PITS_RANGE: tuple[tuple[int, int], tuple[int, int]] = ((7, 12), (0, 5))


def _compute_landing(player: int, pit: int, to_sow: int) -> int:
    opp_treas = OPP_TREASURY[player]
    pos = pit
    for _ in range(to_sow):
        pos = (pos + 1) % TOTAL
        if pos == opp_treas:
            pos = (pos + 1) % TOTAL
    return pos


# Precomputed O(1) landing table: SOW_LANDING[player][pit][to_sow % 13]
# Sowing tracks contain 13 active holes (opponent treasury is skipped).
# Advancing 13 steps around the 13 active holes returns to the origin pit.
SOW_LANDING: tuple[tuple[tuple[int, ...], ...], ...] = tuple(
    tuple(
        tuple(_compute_landing(p, pit, k) for k in range(13))
        for pit in range(TOTAL)
    )
    for p in range(2)
)


def _splitmix64(seed: int) -> tuple[int, int]:
    """Deterministic 64-bit PRNG (SplitMix64) for cross-language Zobrist parity."""
    z = (seed + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    val = (z ^ (z >> 31)) & 0xFFFFFFFFFFFFFFFF
    return val, (seed + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF


def _init_zobrist() -> tuple[tuple[tuple[int, ...], ...], int]:
    state = 0x4D414E47414C415F  # "MANGALA_" in ASCII hex
    pit_table: list[tuple[int, ...]] = []
    for _pit in range(TOTAL):
        row: list[int] = []
        for _cnt in range(TOTAL_STONES + 1):
            val, state = _splitmix64(state)
            row.append(val)
        pit_table.append(tuple(row))
    side_val, _ = _splitmix64(state)
    return tuple(pit_table), side_val


# Precomputed 64-bit Zobrist hash tables: ZOBRIST_PIT[14][49] and ZOBRIST_SIDE
ZOBRIST_PIT, ZOBRIST_SIDE = _init_zobrist()

# End-game sweep variants (see Rules.sweep_to).
SWEEP_EMPTIED_SIDE = "emptied_side"
SWEEP_LAST_MOVER = "last_mover"


@dataclass(frozen=True)
class Rules:
    """Optional rule variants.

    sweep_to:
        Who collects the stones left on the board when one side runs empty.

        * ``"emptied_side"`` (default, traditional Turkish rule): the player
          whose side is empty takes all of the opponent's remaining stones.
        * ``"last_mover"``: the player who made the final move takes them
          (some house rules; matters when a capture empties the opponent's side).
    """
    sweep_to: str = SWEEP_EMPTIED_SIDE

    def __post_init__(self) -> None:
        if self.sweep_to not in (SWEEP_EMPTIED_SIDE, SWEEP_LAST_MOVER):
            raise ValueError(f"unknown sweep_to variant: {self.sweep_to!r}")


DEFAULT_RULES = Rules()


@dataclass(frozen=True)
class GameState:
    pits: list[int]               # length 14, index layout described above
    current_player: int           # 0 or 1
    game_over: bool = False
    winner: int | None = None  # 0, 1, or -1 for tie


class MoveEvents(TypedDict):
    capture: int      # stones captured this turn (0 if none)
    extra_turn: bool  # True if the same player moves again


def initial_state() -> GameState:
    pits = [STONES_PER_PIT] * TOTAL
    pits[P1_TREASURY] = 0
    pits[P2_TREASURY] = 0
    return GameState(pits=pits, current_player=0)


def validate_state(state: GameState) -> None:
    """Raise ``ValueError`` if *state* is not a well-formed Mangala position."""
    pits = state.pits
    if not isinstance(pits, list) or len(pits) != TOTAL:
        raise ValueError(f"pits must be a list of {TOTAL} integers")
    for n in pits:
        if isinstance(n, bool) or not isinstance(n, int) or n < 0:
            raise ValueError("pit counts must be non-negative integers")
    if sum(pits) != TOTAL_STONES:
        raise ValueError(f"board must contain exactly {TOTAL_STONES} stones")
    if state.current_player not in (0, 1) or isinstance(state.current_player, bool):
        raise ValueError("current_player must be 0 or 1")
    if not isinstance(state.game_over, bool):
        raise ValueError("game_over must be a boolean")
    if state.winner not in (None, 0, 1, -1) or isinstance(state.winner, bool):
        raise ValueError("winner must be null, 0, 1 or -1")


def opposite(pit_index: int) -> int:
    """The pit directly across the board (works for both rows)."""
    return 12 - pit_index


def legal_moves(state: GameState) -> list[int]:
    """Return list of pit indices the current player may choose."""
    if state.game_over:
        return []
    return [i for i in PLAYER_PITS[state.current_player] if state.pits[i] > 0]


def is_terminal(state: GameState) -> bool:
    return state.game_over


def score(state: GameState) -> tuple[int, int]:
    """Return (p1_treasury, p2_treasury)."""
    return state.pits[P1_TREASURY], state.pits[P2_TREASURY]


def zobrist_hash(state: GameState) -> int:
    """Compute the 64-bit Zobrist hash of *state*."""
    pits = state.pits
    h = ZOBRIST_SIDE if state.current_player == 1 else 0
    for i in range(TOTAL):
        c = pits[i]
        if 0 <= c <= TOTAL_STONES:
            h ^= ZOBRIST_PIT[i][c]
        else:
            h ^= ZOBRIST_PIT[i][TOTAL_STONES] ^ (c << (i * 3))
    return h & 0xFFFFFFFFFFFFFFFF


def lexicographic_potential(state: GameState) -> tuple[int, int]:
    """Compute the strictly decreasing DAG potential (K(P), Phi(P)) (Theorem 2).

    K(P)   : Total active stones on the 12 small pits.
    Phi(P) : Intra-row treasury distance sum:
             sum_{i=0..5} (6 - i) * pits[i] + sum_{j=7..12} (13 - j) * pits[j]

    Every legal move in Turkish Mangala strictly decreases (K, Phi) lexicographically.
    """
    pits = state.pits
    k = (
        pits[0] + pits[1] + pits[2] + pits[3] + pits[4] + pits[5]
        + pits[7] + pits[8] + pits[9] + pits[10] + pits[11] + pits[12]
    )
    phi = (
        6 * pits[0] + 5 * pits[1] + 4 * pits[2] + 3 * pits[3] + 2 * pits[4] + 1 * pits[5]
        + 6 * pits[7] + 5 * pits[8] + 4 * pits[9] + 3 * pits[10] + 2 * pits[11] + 1 * pits[12]
    )
    return k, phi


def apply_move(state: GameState, pit_index: int,
               rules: Rules = DEFAULT_RULES) -> tuple[GameState, MoveEvents]:
    """
    Apply a move and return ``(new_state, events)``. Never mutates *state*.

    Raises ``ValueError`` if *pit_index* is not a legal move.

    Turkish Mangala rules applied:
      - If the pit has >1 stone: leave 1 behind, sow the rest counterclockwise.
      - If the pit has exactly 1 stone: pick it up (pit becomes empty), sow it.
      - The opponent's treasury is skipped during sowing.
      - Extra turn if the last stone lands in your own treasury.
      - Regular capture: the last stone lands in an opponent pit and makes its
        count even -> capture that single pit (no chain captures).
      - Empty-hole capture: the last stone lands in one of your own pits that
        was empty at the start of the turn, and the directly opposite opponent
        pit is non-empty -> capture both. If the opposite pit is empty,
        nothing is captured.
      - The game ends as soon as either side's six pits are all empty. The
        remaining stones are swept according to ``rules.sweep_to`` (by default
        the player whose side emptied takes them). Most stones wins.
    """
    player = state.current_player
    own_min, own_max = OWN_PITS_RANGE[player]
    if (state.game_over or not (own_min <= pit_index <= own_max)
            or state.pits[pit_index] == 0):
        raise ValueError(f"illegal move: pit {pit_index} for player {player + 1}")

    pits = state.pits[:]
    own_treasury  = PLAYER_TREASURY[player]
    opp_treasury  = OPP_TREASURY[player]
    opp_min, opp_max = OPP_PITS_RANGE[player]

    stones = pits[pit_index]
    if stones > 1:
        pits[pit_index] = 1
        to_sow = stones - 1
    else:
        pits[pit_index] = 0
        to_sow = 1

    # Sow counterclockwise, skipping opponent's treasury
    idx = pit_index
    for _ in range(to_sow):
        idx = (idx + 1) % TOTAL
        if idx == opp_treasury:
            idx = (idx + 1) % TOTAL
        pits[idx] += 1
    last = idx

    extra_turn = (last == own_treasury)

    # Capture rules (mutually exclusive — last stone is either on own or opp side)
    captured = 0

    # Rule 1 — Regular capture:
    #   Last stone lands on opponent's side and makes that pit's count even
    #   → take all stones from that pit.
    if opp_min <= last <= opp_max and pits[last] % 2 == 0 and pits[last] > 0:
        captured = pits[last]
        pits[own_treasury] += captured
        pits[last] = 0

    # Rule 2 — Empty-hole capture:
    #   Last stone lands in one of the player's OWN pits that was empty at
    #   the start of this turn (so the pit now has exactly 1 stone).
    #   → take that 1 stone PLUS all stones in the directly opposite opponent pit.
    #   The opposite of pit i is pit (12 − i) for both rows (board is symmetric).
    elif (own_min <= last <= own_max
          and state.pits[last] == 0
          and pits[last] == 1):
        opp_pit = opposite(last)
        # Only capture when the opposite opponent pit actually has stones.
        # If it's empty the stone stays and nothing is taken.
        if pits[opp_pit] > 0:
            captured = pits[last] + pits[opp_pit]
            pits[own_treasury] += captured
            pits[last] = 0
            pits[opp_pit] = 0

    # Check end-of-game: any side fully empty?
    # Traditional Turkish rule: the player whose side empties takes the
    # opponent's remaining stones (opposite of the Kalah variant).
    game_over = False
    winner = None
    for p in range(2):
        p_min, p_max = OWN_PITS_RANGE[p]
        if all(pits[i] == 0 for i in range(p_min, p_max + 1)):
            other = 1 - p
            collector = p if rules.sweep_to == SWEEP_EMPTIED_SIDE else player
            o_min, o_max = OWN_PITS_RANGE[other]
            for i in range(o_min, o_max + 1):
                pits[PLAYER_TREASURY[collector]] += pits[i]
                pits[i] = 0
            game_over = True
            s0, s1 = pits[P1_TREASURY], pits[P2_TREASURY]
            if s0 > s1:
                winner = 0
            elif s1 > s0:
                winner = 1
            else:
                winner = -1
            break

    if game_over or extra_turn:
        next_player = player
    else:
        next_player = 1 - player

    new_state = GameState(pits=pits, current_player=next_player,
                          game_over=game_over, winner=winner)
    events: MoveEvents = {'capture': captured,
                          'extra_turn': extra_turn and not game_over}
    return new_state, events
