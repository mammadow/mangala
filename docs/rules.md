# Turkish Mangala — Complete Rules Guide

Turkish Mangala is an ancient, strategic two-player board game belonging to the Mancala family. Unlike many other Mancala variants (such as Kalah or Oware), Turkish Mangala features unique rules for piece distribution, captures, and endgame scoring.

---

## 1. Board Layout and Equipment

- **Total Wells**: 14 slots arranged in two rows.
  - **Player 1 (Bottom Row)**: Pits `0`, `1`, `2`, `3`, `4`, `5`
  - **Player 1 Treasury (*Hazine*)**: Slot `6` (Right side from P1's view)
  - **Player 2 (Top Row)**: Pits `7`, `8`, `9`, `10`, `11`, `12`
  - **Player 2 Treasury (*Hazine*)**: Slot `13` (Left side from P1's view)
- **Stones**: 48 identical game stones (often called *saka* or seeds).
- **Initial Setup**: 4 stones in each of the 12 small pits. Both treasuries start with 0 stones.

```text
               Player 2 Wells (Top Row)
           12    11    10     9     8     7
  P2 [ 0]  [ 4]  [ 4]  [ 4]  [ 4]  [ 4]  [ 4]  [ 0] P1
           [ 4]  [ 4]  [ 4]  [ 4]  [ 4]  [ 4]
            0     1     2     3     4     5
               Player 1 Wells (Bottom Row)
```

---

## 2. Direction of Play and Sowing

Play proceeds **counterclockwise** around the board:
- P1 pits (`0` -> `5`) -> P1 Treasury (`6`) -> P2 pits (`7` -> `12`) -> P2 Treasury (`13`) -> P1 pits...

### Distribution Rules
On your turn, choose one non-empty pit on your side of the board:

1. **If the pit contains MORE THAN 1 stone**:
   - Pick up all stones, leave **one stone** in the starting pit.
   - Sow the remaining stones one by one into subsequent pits counterclockwise.
2. **If the pit contains EXACTLY 1 stone**:
   - Pick up the single stone (the starting pit becomes empty `0`).
   - Sow that stone into the next adjacent pit counterclockwise.
3. **Skipping Opponent's Treasury**:
   - You **always sow into your own treasury** when your distribution path reaches it.
   - You **always skip the opponent's treasury**. No stones are ever placed directly into the opponent's treasury during sowing.

---

## 3. Special Rules & Captures

### Rule A: Extra Turn (*Hazine* Rule)
If the **last stone** of your sowing lands directly inside **your own treasury**:
- You earn an immediate **extra turn**.
- If your subsequent move also lands its last stone in your treasury, you earn another extra turn (unlimited chain as long as the condition is satisfied).

### Rule B: Regular Capture (Even Count Rule)
If the **last stone** of your sowing lands in an **opponent's pit** and makes the total stone count of that pit **EVEN** ($2, 4, 6, 8, \dots$):
- You capture **all stones** in that pit.
- The captured stones are immediately placed into your treasury.
- Unlike ancient chain variants, in modern Turkish Mangala, this applies only to the single landing pit.

### Rule C: Empty-Hole Capture (Opposite Capture Rule)
If the **last stone** of your sowing lands in one of **your own pits that was empty before the turn** (so it now has exactly $1$ stone):
- Look directly across the board at the opposite opponent pit (`12 - i`).
- **If the opposite pit contains stones**:
  - You capture your $1$ stone **plus** all stones from the opposite pit.
  - All captured stones are moved to your treasury.
- **If the opposite pit is empty ($0$ stones)**:
  - No capture occurs. Your stone remains in the pit.

#### Opposite Pit Index Mapping
$$\text{opposite}(i) = 12 - i$$

| Player 1 Pit | Opposite Player 2 Pit |
|:---:|:---:|
| `0` | `12` |
| `1` | `11` |
| `2` | `10` |
| `3` | `9` |
| `4` | `8` |
| `5` | `7` |

---

## 4. Game End and Scoring

The game ends immediately when **all six pits on either player's side become empty**.

### The Turkish Endgame Sweep
In traditional Turkish Mangala:
- The player who **emptied their own side first** captures **all remaining stones on the opponent's side**.
- Those stones are swept into that player's treasury.

*(Note: In the engine, `Rules(sweep_to="last_mover")` is available as a configurable option for tournament or house rule variants where the last player to move collects the remaining stones).*

### Victory Condition
Each player counts the stones in their treasury:
- Player with $\ge 25$ stones wins.
- If both players have exactly $24$ stones, the game is a **Tie**.
