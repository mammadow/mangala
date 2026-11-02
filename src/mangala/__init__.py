"""Turkish Mangala — rules engine, strong AI, and web / terminal / desktop front-ends."""
from __future__ import annotations

__version__ = "0.1.0"

from .engine import (  # noqa: E402
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
    "__version__",
    "DEFAULT_RULES",
    "GameState",
    "Rules",
    "apply_move",
    "initial_state",
    "is_terminal",
    "legal_moves",
    "score",
    "validate_state",
]
