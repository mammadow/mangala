# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

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
