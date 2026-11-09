"""Turkish Mangala — rules engine, strong AI, and web / terminal / desktop front-ends."""
from __future__ import annotations

__version__ = "0.2.5"

from .ai import DEFAULT_WEIGHTS, EvalWeights, SearchResult, analyse, best_move
from .book import OPENING_BOOK, get_book_move
from .engine import (
    DEFAULT_RULES,
    ZOBRIST_PIT,
    ZOBRIST_SIDE,
    GameState,
    Rules,
    apply_move,
    initial_state,
    is_terminal,
    legal_moves,
    lexicographic_potential,
    score,
    validate_state,
    zobrist_hash,
)
from .nnue import DEFAULT_NNUE, NNUEAccumulator, NNUEEvaluator, train_nnue_distillation
from .tablebase import build_egtb, combinadic_index, probe_egtb, probe_egtb_move

__all__ = [
    "DEFAULT_NNUE",
    "DEFAULT_RULES",
    "DEFAULT_WEIGHTS",
    "OPENING_BOOK",
    "ZOBRIST_PIT",
    "ZOBRIST_SIDE",
    "EvalWeights",
    "GameState",
    "NNUEAccumulator",
    "NNUEEvaluator",
    "Rules",
    "SearchResult",
    "__version__",
    "analyse",
    "apply_move",
    "best_move",
    "build_egtb",
    "combinadic_index",
    "get_book_move",
    "initial_state",
    "is_terminal",
    "legal_moves",
    "lexicographic_potential",
    "probe_egtb",
    "probe_egtb_move",
    "score",
    "train_nnue_distillation",
    "validate_state",
    "zobrist_hash",
]
