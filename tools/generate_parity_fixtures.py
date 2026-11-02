#!/usr/bin/env python3
"""Generate comprehensive test fixtures for cross-language engine parity testing.

Produces `tests/fixtures/engine_parity_fixtures.json`.
"""
import json
import os
import random

from mangala.engine import (
    TOTAL,
    apply_move,
    initial_state,
    legal_moves,
)
from mangala.server import state_to_dict


def generate_fixtures(count: int = 200) -> list[dict]:
    random.seed(42)
    fixtures = []

    # 1. Initial state
    s = initial_state()
    for m in legal_moves(s):
        ns, ev = apply_move(s, m)
        fixtures.append({
            "initial": state_to_dict(s),
            "move": m,
            "expected_state": state_to_dict(ns),
            "expected_events": dict(ev),
        })

    # 2. Random playout states and their legal moves
    seen_keys = set()
    for _ in range(count):
        s = initial_state()
        plies = random.randint(1, 35)
        for _ in range(plies):
            if s.game_over:
                break
            m = random.choice(legal_moves(s))
            s, _ = apply_move(s, m)

        if s.game_over:
            continue

        key = (tuple(s.pits), s.current_player)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        for m in legal_moves(s):
            ns, ev = apply_move(s, m)
            fixtures.append({
                "initial": state_to_dict(s),
                "move": m,
                "expected_state": state_to_dict(ns),
                "expected_events": dict(ev),
            })

    from mangala.engine import GameState
    # 3. Targeted edge cases
    # 3a. Empty-hole capture when opposite has stones
    pits = [0] * TOTAL
    pits[0] = 2; pits[1] = 0; pits[2] = 2; pits[11] = 5; pits[8] = 2
    pits[6] = 18; pits[13] = 19
    s = GameState(pits=pits, current_player=0)
    ns, ev = apply_move(s, 0)
    fixtures.append({
        "initial": state_to_dict(s),
        "move": 0,
        "expected_state": state_to_dict(ns),
        "expected_events": dict(ev),
    })

    # 3b. Empty-hole when opposite is empty
    pits = [0] * TOTAL
    pits[0] = 2; pits[1] = 0; pits[2] = 2; pits[11] = 0; pits[8] = 2
    pits[6] = 21; pits[13] = 21
    s = GameState(pits=pits, current_player=0)
    ns, ev = apply_move(s, 0)
    fixtures.append({
        "initial": state_to_dict(s),
        "move": 0,
        "expected_state": state_to_dict(ns),
        "expected_events": dict(ev),
    })

    # 3c. Large sowing (wrap around multiple times)
    pits = [0] * TOTAL
    pits[5] = 28; pits[2] = 2; pits[8] = 2
    pits[6] = 8; pits[13] = 8
    s = GameState(pits=pits, current_player=0)
    ns, ev = apply_move(s, 5)
    fixtures.append({
        "initial": state_to_dict(s),
        "move": 5,
        "expected_state": state_to_dict(ns),
        "expected_events": dict(ev),
    })

    return fixtures


def main() -> None:
    fixtures = generate_fixtures(count=150)
    out_dir = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "engine_parity_fixtures.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fixtures, f, indent=2)
    print(f"Generated {len(fixtures)} parity test fixtures in {out_path}")


if __name__ == "__main__":
    main()
