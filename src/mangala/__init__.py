"""Turkish Mangala — rules engine, strong AI, and web / terminal / desktop front-ends."""
from __future__ import annotations

__version__ = "0.2.0"

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
    "OPENING_BOOK",
    "GameState",
    "Rules",
    "__version__",
    "apply_move",
    "get_book_move",
    "initial_state",
    "is_terminal",
    "legal_moves",
    "score",
    "validate_state",
]
