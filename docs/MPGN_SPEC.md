# Mancala Portable Game Notation (MPGN v1.0) Specification

**Mancala Portable Game Notation (MPGN)** is a standardized ASCII text format for recording, archiving, and replaying Turkish Mangala matches, modeled after Chess Portable Game Notation (PGN).

---

## 1. Specification Overview

An MPGN file (`.mpgn`) consists of two main sections:
1. **Tag Pair Section (Metadata)**: Bracketed key-value pairs defining match parameters.
2. **Move Text Section (Play Sequence)**: Numbered turns showing pit selections, special events (captures, extra turns), and final scores.

---

## 2. Example MPGN File

```text
[Event "Turkish Mangala National Championship"]
[Site "mangala.local"]
[Date "2026-11-03"]
[Round "1"]
[Player1 "Human (You)"]
[Player2 "AI (Expert)"]
[Result "26-22"]

1. P1 pit 4 (extra turn) 1. P1 pit 5 (✦ +2) 1. P2 pit 11 2. P1 pit 2 2. P2 pit 12 ... 26-22
```

---

## 3. Metadata Tags

* `[Event "..."]`: Name of the tournament or match format.
* `[Site "..."]`: URL, host, or venue where the game was conducted.
* `[Date "YYYY-MM-DD"]`: Date the match commenced in ISO 8601 format.
* `[Round "..."]`: Round identifier.
* `[Player1 "..."]`: Name or AI profile of Player 1 (first mover, pits 0–5).
* `[Player2 "..."]`: Name or AI profile of Player 2 (second mover, pits 7–12).
* `[Result "P1-P2"]`: Final score tally (e.g. `26-22`, `24-24` for tie, or `*` for ongoing match).

---

## 4. Move Annotations

* `P1 pit <N>`: Player 1 sowed from pit index $N$.
* `P2 pit <N>`: Player 2 sowed from pit index $N$.
* `↺ extra turn`: Indicates the final stone landed in the player's treasury, granting a sequential move.
* `✦ +K`: Indicates a capture of $K$ stones (either even capture or empty-hole opposite capture).
