"""Turkish Mangala — rules engine, strong AI, and web / terminal / desktop front-ends."""
from __future__ import annotations

__version__ = "0.2.4"

from .ai import DEFAULT_WEIGHTS, EvalWeights, SearchResult, analyse, best_move
from .book import OPENING_BOOK, get_book_move
from .engine import (
    DEFAULT_RULES,
    GameState,
    Rules,
    apply_move,
    initial_state,
    is_terminal,
    legal_moves,
    score,
    validate_state,
)

__all__ = [
    "DEFAULT_RULES",
    "DEFAULT_WEIGHTS",
    "OPENING_BOOK",
    "EvalWeights",
    "GameState",
    "Rules",
    "SearchResult",
    "__version__",
    "analyse",
    "apply_move",
    "best_move",
    "get_book_move",
    "initial_state",
    "is_terminal",
    "legal_moves",
    "score",
    "validate_state",
]
