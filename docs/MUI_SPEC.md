# Mancala Universal Interface (MUI v1.0) Specification

The **Mancala Universal Interface (MUI)** is an open, text-based communication protocol inspired by the Universal Chess Interface (UCI). It enables Turkish Mangala game engines to communicate seamlessly with graphical user interfaces (GUIs), automated tournament directors, and bot arenas via standard input and output streams (`stdin` / `stdout`).

---

## 1. Engine Invocation

An engine supporting MUI can be invoked directly from the CLI:

```bash
mangala --mui
# or:
mangala --uci
# or:
python -m mangala.cli --mui
```

---

## 2. Command Reference (GUI to Engine)

### `mui` / `uci`
Signals the engine to identify itself and initialize the protocol loop.

**Engine Response:**
```text
id name Turkish Mangala
id author mammadow
option name Level type combo default expert var easy var medium var hard var expert
muiok
```

### `isready`
Used to synchronize the engine and GUI. Guarantees that the engine is ready to receive commands.

**Engine Response:**
```text
readyok
```

### `muinewgame` / `ucinewgame`
Resets internal search state, clears transposition tables and history heuristics, and prepares for a new match from the initial position.

### `position startpos [moves m1 m2 ...]`
Sets up the board position.
* `startpos`: Initializes the standard 48-stone Turkish Mangala board ($4$ stones per pit, $0$ in treasuries, Player 0 to move).
* `moves m1 m2 ...`: Applies a sequence of legal pit indices ($0 \dots 12$, excluding treasuries $6$ and $13$).

**Example:**
```text
position startpos moves 4 10 2
```

### `go [depth <d>] [movetime <ms>]`
Starts minimax iterative deepening search on the current position.
* `depth <d>`: Restricts search to a maximum depth of $d$ plies.
* `movetime <ms>`: Imposes a strict search time budget in milliseconds.

**Engine Output during Search:**
```text
info depth 8 score cp 140 nodes 18450 time 120 pv 4 10 5
bestmove 4
```

### `eval`
Requests static board evaluation from the current player's perspective without searching.

**Engine Response:**
```text
eval +1.40
```

### `quit`
Terminates the engine process cleanly.

---

## 3. Notation and Coordinates

* **Player 1 Pits**: `0, 1, 2, 3, 4, 5` (labeled 1 through 6 on physical boards)
* **Player 1 Treasury (Hazine)**: `6`
* **Player 2 Pits**: `7, 8, 9, 10, 11, 12` (labeled 1 through 6 on physical boards)
* **Player 2 Treasury (Hazine)**: `13`
