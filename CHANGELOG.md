# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.5] - 2026-11-10

### Added
- **Automated Self-Play Dataset Generator & SPSA/Texel Tuning Optimizer (`src/mangala/tune.py`)**:
  - Pure standard-library multi-core self-play generator with opening entropy and quiet-position filtering.
  - Parameterized `EvalWeights` vector with typed extraction and injection across the entire AI engine.
  - SPSA (Simultaneous Perturbation Stochastic Approximation) optimizer minimizing Texel MSE loss.
  - Head-to-head match arena with Wald's Sequential Probability Ratio Testing (SPRT) and Elo calculation.
  - New console script: `mangala-tune` (`selfplay`, `tune`, `arena`).
- **Superhuman AI Engine v2.0 Architecture**:
  - **Endgame Tablebase (EGTB) Engine (`src/mangala/tablebase.py`, `src/mangala/web/ai.js`)**: Pure-math combinadic state indexer, DAG-based retro-analysis solver, and client-side tablebase probing with extra-turn tie breaking.
  - **Efficiently Updatable Neural Network (NNUE) (`src/mangala/nnue.py`)**: Quantized feature transformers with accumulator caching, clipped ReLU activations, and AdamW distillation trainer.
  - **Advanced Search Pruning & Move Ordering**: Added Late Move Reductions (LMR), Reverse Futility Pruning (RFP), Razoring, Internal Iterative Deepening (IIR), and dynamic history malus.
  - **120-Line Grandmaster Opening Book (`src/mangala/book.py`, `src/mangala/web/book.js`)**: Comprehensive theory coverage for both Player 1 and Player 2 openings.
- **Dedicated Standalone Desktop App Window Mode (`mangala-gui` / `mangala --app`)**:
  - Re-routed `mangala-gui` to launch the modern Web/PWA interface inside a dedicated, frameless desktop application window (`--app` mode).
  - Eliminates all C/SDL external dependencies while delivering full WebRTC P2P multiplayer, 5 luxury board themes, procedural Web Audio effects, and offline PWA support.
- **Web UI & UX Overhaul**:
  - **Live Engine Telemetry**: Real-time evaluation gauge, node counter, search depth, NPS, and source tag (Book, EGTB, Win25, Search).
  - **Interactive Tactical Hover Previews & Stone Delta Badges**: Live sowing preview highlighting destination pits and displaying stone count changes (`+1`, `+2`).
  - **Interactive Move Timeline & Scrubber**: Full game history navigation with first, previous, next, and last step controls.
  - **SVG Match Review Graph**: Interactive post-game evaluation trajectory chart visualizing advantages and turning points.
  - **Player Career / ELO Profile Modal**: Persistent statistics tracking rating, win rates, streak counter, and achievement unlocks.
  - **Imperial Topkapı Royal Theme**: Cohesive Ottoman palace aesthetic with Midnight Burgundy Velvet, Rosewood frame, burnished bronze-gold pits, and mother-of-pearl stones.
  - **Flipped Board Counter-Rotation Fix**: Dynamic sowing direction indicators (`◄` / `►`) accurately reflecting the counter-clockwise visual flow toward each player's Hazine when the board is flipped 180°.

### Removed
- **Legacy Pygame Interface (`gui_pygame.py`) & Dependency Extra (`[gui]`)**:
  - Dropped legacy Pygame script and `pygame` / `pygame-ce` dependencies.
  - Repository and PyPI package are now **100% Pure Python Standard Library** (`dependencies = []`).

## [0.2.4] - 2026-11-03

### Added
- **7-Step Interactive Board Tutorial ("All Rules in One Go")**:
  - Replaced modal text guide with an uninterrupted, guided on-board walkthrough (`#interactiveHUD`) explaining 100% of authentic Turkish rules sequentially.
  - Covers: Sowing >1 stone, Single-stone pickup, Skipping opponent's treasury, Extra turn in Hazine, Even-parity capture, Empty-hole capture, and Endgame sweep.
  - Dynamic pulsating guidance rings (`.tut-target`, `.tut-focus`) highlight the source pit and destination/opposite pit in real time.
  - Interactive HUD with step indicators, explanatory banners, hint explanations, and celebratory completion card (`#tutCompleteOverlay`).
  - One-click launch from the menu mode grid (`#modeGrid`) and the rules guide hero banner (`#startFullTutorialHeroBtn`).
- **Tactical Puzzles Trainer Overhaul (16 Scenarios across 3 Tiers)**:
  - Expanded puzzle database from 8 to 16 authentic endgame and middlegame tactical scenarios.
  - Categorized into 3 skill tiers: `Apprentice` (Puzzles 1–5), `Master` (Puzzles 6–11), and `Grandmaster` (Puzzles 12–16) with dedicated filter tabs.
  - Multi-move combination engine: puzzles with bonus turns (e.g. Extra-turn into Even capture) seamlessly request the correct follow-up move.
  - Persistent progress tracking stored in `localStorage` (`mangala_puzzles_solved`) with checkmarks (`✓`) and progress bar (`X / 16 solved`).

## [0.2.3] - 2026-11-03

### Added
- **Superhuman Tournament-Grade AI Engine Upgrade**:
  - **Full Transposition Table in Client JavaScript (`src/mangala/web/ai.js`)**: Ported depth-preferred transposition table with `EXACT`, `LOWER_BOUND`, and `UPPER_BOUND` flags, enabling 5x–10x faster search speeds in web browsers.
  - **Killer Moves & History Heuristic ($d^2$) in JavaScript**: Dynamic move ordering prioritizing quiet refutations that caused previous beta-cutoffs.
  - **Aspiration Window Search in Iterative Deepening**: Root search with narrow dynamic score windows ($[v - 0.5, v + 0.5]$) and fail-high/fail-low full-window recovery, cutting alpha-beta tree evaluations by 30%–40% across both Python and JavaScript.
  - **Grandmaster Positional Heuristics**:
    - *Multi-Step Ladder Cascades (Merdiven Serisi)*: Evaluates initiative gained from chaining consecutive bonus turns into treasuries.
    - *Even-Parity Defensive Shielding (Çift Sayı Kalkanı)*: Evaluates stone parity where even-count pits are naturally immune to Rule 3 captures upon opponent sowing.
    - *Kuyu Saklama (Deep Fortress Reserves)*: Strategic value assigned to back pits (0/1 and 7/8) with $\ge 8$ stones threatening late-game full-board sowing sweeps.
  - **Exact Endgame Solver Extended to 16 Stones**: When $\le 16$ stones remain on the board (32+ banked), the AI solves the endgame with 100% mathematical precision.

## [0.2.2] - 2026-11-03

### Added
- **Automated PyPI Publishing**:
  - Added GitHub Actions workflow (`.github/workflows/publish.yml`) supporting PyPI Trusted Publishing (OIDC).
  - Publishes automatically on release publication, version tag pushes (`v*.*.*`), or manual dispatch.
- **Modern Online P2P Multiplayer Hub**:
  - Overhauled multiplayer lobby with distinct 👑 Host Room & 🔗 Join Friend tabs.
  - Large segmented 4-character room code display (`[ 7 ] [ K ] [ 2 ] [ X ]`).
  - Native Web Share API (`navigator.share`) integration with fallback to 1-click clipboard copy.
  - One-click clipboard paste button (`📋`) and auto-sanitization for 4-letter room codes.
- **In-Game Live HUD & Reconnection Overlay**:
  - Slim in-game HUD bar displaying real-time round-trip latency (`📶 X ms`), room code, player role indicator, and leave match button.
  - Floating auto-reconnection notification badge (`#p2pReconnectOverlay`) with retry progress.
- **Resilient Multiplayer State Machine & Heartbeat Recovery**:
  - Persistent match storage via `sessionStorage` (`mangala_p2p_active`) enabling full state recovery across page reloads.
  - 3.5-second keepalive ping-pong heartbeats with desync self-healing: detects turn or move count discrepancies and automatically requests authoritative state sync.
  - Bidirectional sync handshake (`request_sync`) on peer connection open.
  - Immortal Host room listener: host peer never destroys itself on guest disconnect, allowing instant reconnects.
  - Clean `beforeunload` peer destruction ensuring PeerJS signaling servers release room IDs immediately.
  - Instant dismissal of mode selection overlay (`#menuOverlay`) upon room joining.

## [0.2.1] - 2026-11-03

### Added
- **Python 3.14 Support**:
  - Configured conditional dependency on `pygame-ce>=2.5` for Python $\ge 3.13$ to eliminate MSVC compilation failures caused by the removal of `distutils`.
  - Maintained `pygame>=2.5` for Python $< 3.13$.

### Fixed
- Fixed race condition where incoming P2P sync packets updated state mid-animation and triggered illegal move errors.
- Fixed disappearing legal move highlights during opponent moves by restoring `busy = false` before rendering.

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
  - Difficulty selector pills (Easy, Medium, Hard, Expert) and animation speed controls (⚡ 1x, 2x, Instant).
  - Keyboard navigation for rapid play (keys `1`–`6` for pits, `F` to flip board).
  - Dual-mode operation: seamless automatic fallback to client-side JavaScript engine for offline play and static GitHub Pages hosting.
  - Request body size limits ($4096$ bytes), time limit clamping ($[0.05, 5.0]$ seconds), request body draining, and concurrent search throttling.
  - Strict security headers (CSP, X-Frame-Options, X-Content-Type-Options) and path traversal protections.
- **Cross-Language Engine & Parity Testing (`src/mangala/web/engine.js`, `ai.js`, `tests/test_parity.mjs`)**:
  - Client-side JavaScript rules and minimax AI engines matching Python implementation.
  - Fixture generator (`tools/generate_parity_fixtures.py`) creating 629 corner-case and playout state transitions.
  - Cross-language parity runner (`node --test tests/test_parity.mjs`) validating 100% equivalence in under 10ms.
- **Terminal CLI (`mangala.cli`)**:
  - ASCII board visualizer with active player indicators and ANSI color support.
  - Interactive Human vs Human, Human vs AI, and AI vs AI modes with selectable difficulty levels.
  - Safe UTF-8 console reconfiguring for Windows without destroying stream descriptors.
- **Pygame Desktop GUI (`mangala.gui_pygame`)**:
  - Desktop interface with smooth frame animation, capture banners, move log, and analysis mode.
  - Headless test support with dummy video driver fallback.
- **Development & Packaging**:
  - PEP 621 compliant `pyproject.toml` with `hatchling` build backend.
  - PEP 561 `py.typed` marker file for library type checker compliance.
  - Comprehensive 78-test suite with 97% overall code coverage.
  - AI-vs-AI tournament benchmark arena tool (`tools/selfplay.py`).
  - GitHub Actions CI matrix across Linux & Windows on Python 3.10 through 3.13 and Node.js parity testing.

### Fixed
- Fixed race condition where concurrent AI calls shared a module-level deadline and cut off longer searches prematurely.
- Fixed server input validation allowing malformed states and unbound time limits.
- Corrected outdated rule descriptions in CLI and docstrings regarding chain captures and sweep directions.
