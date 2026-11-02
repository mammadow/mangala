# Mangala Project — Context & Progress Log

## Project Overview
Turkish Mangala (a variant of Mancala) built in Python with modern Web, Pygame, and CLI interfaces.

---

## Files

| File | Purpose |
|------|---------|
| `game.py` | Pure game logic — rules engine, state, move application |
| `ai.py` | Minimax AI with alpha-beta pruning |
| `board.py` | ASCII board renderer (used by `main.py`) |
| `main.py` | Terminal / CLI entry point |
| `gui.py` | Pygame graphical interface (legacy desktop GUI) |
| `server.py` | Stdlib HTTP backend — serves the web UI + JSON API, reuses `game.py`/`ai.py` |
| `web/index.html` | Modern web GUI (single file: HTML/CSS/JS) |
| `requirements.txt` | `pygame>=2.5` (only needed for the legacy `gui.py`) |

---

## Game Rules Implemented (Turkish Mangala)

### Board Layout
- 14 slots total: pits 0–5 (P1), pit 6 (P1 treasury), pits 7–12 (P2), pit 13 (P2 treasury)
- Each pit starts with 4 stones; treasuries start empty

### Sowing
- Player picks a non-empty own pit
- If >1 stone: leave 1 behind, sow the rest counterclockwise
- If exactly 1 stone: pick it up and sow that 1 stone
- Opponent's treasury is always skipped during sowing

### Special Rules
1. **Extra turn** — last sown stone lands in own treasury → play again
2. **Regular capture** — last stone lands on opponent's side and makes that pit's count **even** → capture all stones from that pit into own treasury
3. **Empty-hole capture** — last stone lands in player's **own previously-empty pit** → capture that 1 stone + all stones in the directly-opposite opponent pit (pit `12 - i`), but **only if the opposite pit is non-empty**
4. **End-game sweep** — when a player's side empties, that player takes all remaining opponent stones (Turkish rule: emptying player takes opponent's remaining, NOT the other way around)

### End Condition
Game ends when all small holes are empty. Most stones in treasury wins.

---

## Bugs Found and Fixed

### Bug 1 — Chain capture (wrong)
- **Problem**: Original code walked backwards from capture pit, collecting every adjacent even pile (chain). Turkish rules only capture the single pit where the last stone landed.
- **Fix**: Replaced the `while` loop chain-capture with a single `if` capture in `game.py`.

### Bug 2 — Missing empty-hole capture rule
- **Problem**: The empty-hole capture rule was completely absent.
- **Fix**: Added tracking of `own_empty_before` (own pits with 0 stones at start of turn). After sowing, if last stone lands in own empty pit (now has exactly 1 stone) and opposite pit is non-empty → capture both.
- **Opposite pit formula**: `12 - pit_index` works for both P1 and P2 pits due to board symmetry.

### Bug 3 — End-game sweep direction (wrong)
- **Problem**: Remaining stones were given to the player who **still had stones** (Kalah variant rule).
- **Fix**: Changed to give remaining stones to the player whose side **emptied** (Turkish rule).

### Bug 4 — Chain capture animation still running
- **Problem**: After fixing game logic, `gui.py`'s `_animate` method still had the old chain-capture `while` loop, causing visual discrepancy.
- **Fix**: Replaced the loop with two separate animation blocks matching the actual rules (regular capture + empty-hole capture).

### Bug 5 — Empty-hole capture firing when opposite is empty
- **Problem**: When last stone landed in own empty pit but the opposite pit had 0 stones, the 1 stone was still moved to treasury.
- **Fix**: Added `pits[opposite] > 0` guard — if opposite is empty, the stone stays in the pit and nothing is captured.

---

## AI Improvements (`ai.py`)

### Original AI (v1)
- Depth-limited alpha-beta minimax
- Move ordering: extra-turn > capture > other
- Evaluation: treasury diff + 0.1 × mobility diff
- Public API: `best_move(state, depth=8)`

### Improved AI (v2)
All improvements maintain backwards-compatible API: `best_move(state, depth=None, time_limit=1.0)` *(time_limit raised to 2.5 in v3)*

#### 1. Transposition Table (TT)
- Key: `(tuple(state.pits), state.current_player)`
- Value: `(depth, value, flag, best_move)` where flag ∈ `{EXACT, LOWER_BOUND, UPPER_BOUND}`
- PV move from TT tried first at every node (major pruning improvement)
- TT cleared at the start of each `best_move` call
- Lookup: EXACT → return; LOWER_BOUND → tighten alpha; UPPER_BOUND → tighten beta

#### 2. Iterative Deepening with Time Budget
- Searches depth 1, 2, 3, … until time budget exhausted (default 1.0 s)
- Always keeps the last **completed** iteration's result (any-time algorithm)
- Each new depth is fast because TT is warm from the previous pass
- Fixed-depth mode still available: `best_move(state, depth=8)`

#### 3. Quiescence Search
- At depth-0 leaves, extends **noisy moves only** (captures + extra turns) up to `Q_DEPTH=4` extra plies
- Eliminates horizon effect where a capture just past the depth limit causes tactical blunders
- Uses stand-pat floor/ceiling (maximiser/minimiser can always "do nothing")

#### 4. Richer Evaluation Function
- **Treasury difference** (primary signal, unchanged)
- **Mobility** (0.1 × own_stones − opp_stones, unchanged)
- **Extra-turn potential** (+0.4 per own pit whose last stone would land in own treasury)
- **Capture exposure** (−0.3 per own even-count pit, immediately capturable by opponent)

#### 5. PV-First Move Ordering
- After a TT hit, the stored best move is tried first regardless of cutoff
- Remaining moves ordered by existing priority (extra-turn > capture > other)

#### Performance
- Typical search depth: ~12–14 plies (vs. old depth-8 fixed)
- Move time: ~1 second (time-limited) or fast for `depth=` mode
- First move chosen by AI: **pit 5** (not the "beginner" pit 3 extra-turn tip — the AI found that pit 5 sets up a follow-up extra turn after P2 responds, yielding better long-term position)

### AI v3 — Full Rule Coverage + Deeper Search
`best_move(state, depth=None, time_limit=2.5)`

#### Rule Coverage Gap Fixed — Empty-Hole in Evaluation
Previously `_evaluate` had no term for the empty-hole capture rule (though the search itself already applied the rule correctly via `apply_move`). Two symmetric terms added:

- **Empty-hole offense** (+): while simulating each own pit's sowing path (the loop already present for extra-turn potential), if the landing pit is an own currently-empty pit AND the directly opposite opponent pit has stones → `+0.25 × (opposite_stones + 1)`. AI now seeks empty-hole captures even beyond the main horizon.
- **Empty-hole exposure** (−): for each own empty pit `e` whose opposite has stones, simulate each opponent pit's sowing to see if it would land in `e`; if yes → `-0.25 × (opposite_stones + 1)`. AI now defends against opponent empty-hole captures.

Weight kept at 0.25 so deeper search still dominates over the static signal.

#### Endgame Exact Solver
In `_search`, when `sum of all pit stones ≤ 12`, depth is overridden to 64 (effectively unbounded). With so few stones the game tree is tiny and the TT collapses it further — cost is a few ms, gain is perfect play in the endgame where every stone is decisive.

```python
stones_on_board = sum(state.pits[i] for i in P1_PITS) + sum(state.pits[i] for i in P2_PITS)
if stones_on_board <= 12 and depth < 64:
    depth = 64
```

#### Time Budget Raised to 2.5 s
`time_limit` default changed from 1.0 → 2.5 seconds. GUI inherits automatically. Expected typical depth: ~14–16 plies (up from ~12–14).

#### Rule Coverage Summary (v3)
| Rule | In search (`apply_move`) | In `_evaluate` heuristic |
|------|--------------------------|--------------------------|
| Sow CCW, skip opp treasury | Yes | N/A |
| Leave-one-behind (>1 stone) | Yes | N/A |
| Extra turn (own treasury) | Yes | Yes — extra-turn potential |
| Regular capture (opp side, even) | Yes | Yes — capture exposure |
| Empty-hole capture (own empty + opp non-empty) | Yes | Yes — offense + exposure terms (new) |
| Empty-hole → nothing if opposite empty | Yes | N/A |
| End-game sweep to emptying player | Yes | Yes — terminal value |

---

## GUI Improvements (`gui.py`)

### Visual Layout
- Window: 980 × 730 px (expanded from 960 × 600)
- Panels from top to bottom:
  - Title bar (56 px)
  - Board (56–548 px, 492 px tall)
  - Status bar (548–620 px, 72 px)
  - Move log (620–730 px, 110 px) ← new

### Animation Speed (slowed down for readability)
| Constant | Old | New |
|----------|-----|-----|
| `STONE_DELAY` | 140 ms | 240 ms |
| `CAPTURE_DELAY` | 320 ms | 580 ms |
| `AI_PAUSE_AIAI` | 350 ms | 850 ms |
| `AI_PAUSE_HUMAN` | 120 ms | 400 ms |
| `EVENT_BANNER` | — | 1100 ms (new) |

### Visual Enhancements
- Bigger pits: semi-axes 44×35 → 50×42; treasury 46×80 → 54×98
- Stone radius: 6 → 7 px
- Shadow under each pit for depth
- Centre stripe between P1/P2 rows
- Score difference indicator ("P1 +4") in board centre
- "Stones in hand: N" subtitle during sowing animation
- Event banners: large semi-transparent overlay for captures/extra turns
- Green treasury highlight after capture (distinct from gold legal-move ring)
- Last-move source pit highlighted red

### Move Log Panel
- Shows last 5 moves, newest at top
- Format: `P1  pit 5   captured 6   extra turn`
- P1 entries: blue; P2 entries: red
- Older entries fade (alpha reduced by 38 per row)
- Resets on new game

### AI Call
- GUI uses `ai_module.best_move(state)` (no depth arg) → iterative deepening with 2.5 s budget (raised from 1 s)

### Analysis Mode (new)
- 4th game mode selectable from the start screen
- Both players are human-controlled (you click pits for both sides)
- At the start, choose which player "you are" — the AI highlights its best-move suggestion on that player's turns only
- **AI hint**: runs in a background daemon thread (board stays responsive); suggested pit gets a cyan glow ring; status bar shows "AI suggests: pit N" once ready, "AI is thinking..." while computing
- **Undo** (button or Ctrl+Z): reverts to the previous state; move log entry removed; works all the way back to start
- **Redo** (button or Ctrl+Y): re-applies an undone move; cleared when a new move is made
- **Pass** (button): skips the current player's turn without moving stones; logged as "P{N}  passed"; can be undone
- History stored as list of `(GameState, log_snapshot)` pairs; `hist_idx` tracks current position
- Undo/Redo buttons dim when unavailable (at start or no redo future)
- New colour constant: `C_HINT = (0, 210, 200)` (cyan)
- Thread pattern: each new hint request creates a fresh container `[pit, ready]` passed by reference to the thread; replacing the container discards stale results cleanly

---

## Key Design Decisions

### Pure Game Engine
`game.py` uses only plain data + pure functions (`apply_move` returns new state, never mutates). This lets the AI call the rules engine freely inside the search loop without side effects.

### Extra-Turn Handling in Search
Alpha-beta uses explicit min/max keyed on `root` player (not negamax). When `apply_move` returns the same `current_player` (extra turn), the same maximiser/minimiser branch continues naturally without sign flips.

### Animation vs Rules Engine
`gui.py`'s `_animate` mirrors the sowing/capture logic visually for display, but always calls authoritative `apply_move` at the end to get the true new state. Animation cannot desync from rules.

### Stone Offset Cache
`_OFF_CACHE` dict caches (pit_index, stone_count) → list of (dx, dy) offsets so stones don't jitter between frames when re-drawing the same pit count.

---

## Opposite Pit Mapping

For the empty-hole capture rule, the "directly opposite" pit across the board:

```
P2 display:  12  11  10   9   8   7
P1 display:   0   1   2   3   4   5
```

`opposite(i) = 12 - i` works for **both** P1 pits (0–5) and P2 pits (7–12).

---

## Web GUI (`server.py` + `web/index.html`)

A modern browser-based front-end. No new dependencies — `server.py` uses only
the Python standard library (`http.server`) and reuses the **exact** same
`game.py` rules engine and `ai.py` search. The browser never re-implements the
rules: it animates the sowing visually, then calls `/api/move` for the
authoritative new state.

### Architecture
- **`server.py`** — stateless JSON API + static file server:
  - `GET  /` → `web/index.html`
  - `GET  /api/new` → fresh `GameState`
  - `POST /api/move` `{state, pit}` → `{state, events}` (validates legality)
  - `POST /api/ai` `{state, time_limit?}` → `{pit}` (calls `ai.best_move`)
  - `ThreadingHTTPServer` so a 2.5 s AI search doesn't block other requests.
- **`web/index.html`** — single self-contained file (inline CSS + JS):
  - Felt-and-wood themed board, gradient stone tokens, drop shadows.
  - Legal pits pulse gold; hover lifts them; capture pits shake red; treasury
    glows green on capture; cyan ring for the analysis hint.
  - Stone-by-stone sowing animation (`sowPath` mirrors the sow order only;
    final state always reconciled to the server).
  - Event banners (capture / extra turn), live scoreboard with active-player
    highlight, last-3 move log.
  - Modes: Human vs Human, Human vs AI (pick side), AI vs AI, Analysis.
  - Analysis tools: Undo (Ctrl+Z), Redo (Ctrl+Y), Pass, Hint (cyan glow).
  - **Board flip (180°)**: toolbar `⟲ Flip` button or the `F` key rotates the
    board so the other player's pits sit at the bottom (easier to play as P2).

### Board Flip Feature (`web/index.html`)
A purely visual 180° rotation — no game logic, pit indices, or API change.

- **Toggle**: `⟲ Flip` button in the header toolbar, or press `F` (works in any
  mode, even mid-game). The button gets a gold `.on` highlight while flipped.
- **Auto-orient**: when the human picks **Player 2** in Human-vs-AI, or coaches
  Player 2 in Analysis (`side===1` in `chooseMode`), the board flips
  automatically so your pits start at the bottom. Player 1 / hvh / ava default
  to un-flipped. Manual toggling still works afterward.
- **How it works**: a `.flipped` class on `.board` applies
  `transform:rotate(180deg)` to the `.felt`; every text element inside
  (`.count`, `.pid`, `.tlabel`, `.tcount`, `.rowlabel`, `.stones`) is
  counter-rotated 180° so labels and counts stay upright and readable. A
  `.4s` transition on `.felt` animates the flip smoothly.
- **State**: a single `flipped` boolean + `applyFlip()` / `toggleFlip()` helpers.
  Because it is presentation-only, it survives New Game / Undo / Redo untouched
  and never needs to round-trip to the server.

### Windows note
`server.py` prints ASCII only (no `→`/`…`) because the default Windows console
codepage is cp1252 and would raise `UnicodeEncodeError` on those glyphs.

### Web GUI Bugs Found and Fixed

#### Web Bug 1 — P2 side rendered blank
- **Problem**: `renderPit()` unconditionally called `el.querySelector('.count').textContent = n` for every pit. Treasuries have no `.count` element (they use `.tcount`), so the call returned `null` and threw a `TypeError` at index 6 (P1 treasury). The render loop (`for i in 0..13`) died mid-iteration, so pits 7–12 (the P2 row) were never drawn — the whole P2 side appeared empty.
- **Fix**: Branch on pit type — treasuries write to `.tcount`, regular pits to `.count`:
  ```js
  const isTreas = (idx===P1_TREAS || idx===P2_TREAS);
  if(isTreas) el.querySelector('.tcount').textContent = n;
  else        el.querySelector('.count').textContent = n;
  ```

## Running the Game

```bash
# Web GUI (recommended) — opens http://localhost:8000 automatically
python server.py

# Legacy desktop GUI (Pygame)
python gui.py

# Terminal / CLI
python main.py

# Dependencies: none for the web GUI; pygame only for gui.py
pip install pygame
```
