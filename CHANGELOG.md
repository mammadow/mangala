# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-11-02

### Added
- **Core Engine (`mangala.engine`)**:
  - Pure, functional rules engine with frozen `GameState` dataclass.
  - Strict input validation via `validate_state()`.
  - Configurable end-game sweep rules (`SWEEP_EMPTIED_SIDE` default, `SWEEP_LAST_MOVER` variant).
  - Complete rule implementation: leave-one-behind, single stone pickup, opponent treasury skipping, extra turns, even captures, and empty-hole captures.
- **AI Search Engine (`mangala.ai`)**:
  - Thread-safe `Searcher` class with isolated transposition table, deadline, and node telemetry.
  - Symmetrical Minimax with Alpha-Beta pruning handling extra-turn branches without negamax inversions.
  - Quiescence search extending captures and extra turns up to 4 plies.
  - Iterative deepening with anytime time budget management (`time_limit`).
  - Endgame exact solver for positions with $\le 12$ stones remaining on the board.
  - Difficulty presets: `easy`, `medium`, `hard`, and `expert`.
  - Comprehensive position analysis API (`analyse()` returning best move, score, depth, node count, and principal variation).
- **Web Front-End & HTTP Backend (`mangala.server`, `src/mangala/web/index.html`)**:
  - Stateless JSON REST API (`GET /api/new`, `POST /api/move`, `POST /api/ai`).
  - Single-file modern web UI featuring felt/wood aesthetics, animated stone sowing, move log, analysis tools (undo, redo, pass, AI hint), and 180° board flip.
  - Request body size limits ($4096$ bytes), time limit clamping ($[0.05, 5.0]$ seconds), and concurrent search throttling.
  - Strict security headers (CSP, X-Frame-Options, X-Content-Type-Options) and path traversal protections.
- **Terminal CLI (`mangala.cli`)**:
  - ASCII board visualizer with active player indicators and ANSI color support.
  - Interactive Human vs Human, Human vs AI, and AI vs AI modes with selectable difficulty levels.
- **Pygame Desktop GUI (`mangala.gui_pygame`)**:
  - Desktop interface with smooth frame animation, capture banners, move log, and analysis mode.
- **Development & Packaging**:
  - PEP 621 compliant `pyproject.toml` with `hatchling` build backend.
  - Comprehensive test suite covering engine rules, AI pruning, property-based hypothesis tests, and REST API endpoints.
  - AI-vs-AI tournament benchmark arena tool (`tools/selfplay.py`).
  - GitHub Actions CI matrix across Linux & Windows on Python 3.10 through 3.13.

### Fixed
- Fixed race condition where concurrent AI calls shared a module-level deadline and cut off longer searches prematurely.
- Fixed server input validation allowing malformed states and unbound time limits.
- Corrected outdated rule descriptions in CLI and docstrings regarding chain captures and sweep directions.
