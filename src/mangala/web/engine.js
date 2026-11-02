/**
 * engine.js — Client-side Turkish Mangala rules engine.
 * Exact behavioral mirror of Python src/mangala/engine.py.
 */
(function(root) {
  const TOTAL = 14;
  const P1_PITS = [0, 1, 2, 3, 4, 5];
  const P1_TREAS = 6;
  const P2_PITS = [7, 8, 9, 10, 11, 12];
  const P2_TREAS = 13;
  const PLAYER_PITS = [P1_PITS, P2_PITS];
  const PLAYER_TREAS = [P1_TREAS, P2_TREAS];
  const OPP_TREAS = [P2_TREAS, P1_TREAS];

  function initialState() {
    const pits = Array(TOTAL).fill(4);
    pits[P1_TREAS] = 0;
    pits[P2_TREAS] = 0;
    return {
      pits: pits,
      current_player: 0,
      game_over: false,
      winner: null,
      legal: P1_PITS.slice()
    };
  }

  function legalMoves(state) {
    if (state.game_over) return [];
    return PLAYER_PITS[state.current_player].filter(i => state.pits[i] > 0);
  }

  function applyMove(state, pit) {
    const player = state.current_player;
    const ownPits = PLAYER_PITS[player];
    const oppPits = PLAYER_PITS[1 - player];
    const ownTreas = PLAYER_TREAS[player];
    const oppTreas = OPP_TREAS[player];
    const ownPitsSet = new Set(ownPits);
    const oppPitsSet = new Set(oppPits);

    if (state.game_over || !ownPitsSet.has(pit) || state.pits[pit] === 0) {
      throw new Error(`Illegal move: pit ${pit}`);
    }

    const pits = state.pits.slice();
    const ownEmptyBefore = new Set(ownPits.filter(i => pits[i] === 0));

    const stones = pits[pit];
    let toSow;
    if (stones > 1) {
      pits[pit] = 1;
      toSow = stones - 1;
    } else {
      pits[pit] = 0;
      toSow = 1;
    }

    let idx = pit;
    for (let s = 0; s < toSow; s++) {
      idx = (idx + 1) % TOTAL;
      if (idx === oppTreas) idx = (idx + 1) % TOTAL;
      pits[idx] += 1;
    }
    const last = idx;
    const extraTurn = (last === ownTreas);

    let captured = 0;

    // Rule 1: Regular capture (lands on opp side and makes it even)
    if (oppPitsSet.has(last) && pits[last] % 2 === 0 && pits[last] > 0) {
      captured = pits[last];
      pits[ownTreas] += captured;
      pits[last] = 0;
    }
    // Rule 2: Empty-hole capture (lands in own empty pit, opposite has stones)
    else if (ownPitsSet.has(last) && ownEmptyBefore.has(last) && pits[last] === 1) {
      const opposite = 12 - last;
      if (pits[opposite] > 0) {
        captured = pits[last] + pits[opposite];
        pits[ownTreas] += captured;
        pits[last] = 0;
        pits[opposite] = 0;
      }
    }

    // End-of-game sweep: emptying side takes remaining opponent stones
    let gameOver = false;
    let winner = null;
    for (let p = 0; p < 2; p++) {
      if (PLAYER_PITS[p].every(i => pits[i] === 0)) {
        const other = 1 - p;
        for (const i of PLAYER_PITS[other]) {
          pits[PLAYER_TREAS[p]] += pits[i];
          pits[i] = 0;
        }
        gameOver = true;
        const s0 = pits[P1_TREAS], s1 = pits[P2_TREAS];
        if (s0 > s1) winner = 0;
        else if (s1 > s0) winner = 1;
        else winner = -1;
        break;
      }
    }

    let nextPlayer;
    if (gameOver || extraTurn) nextPlayer = player;
    else nextPlayer = 1 - player;

    const nextState = {
      pits: pits,
      current_player: nextPlayer,
      game_over: gameOver,
      winner: winner,
      legal: []
    };
    nextState.legal = legalMoves(nextState);

    const events = {
      capture: captured,
      extra_turn: extraTurn && !gameOver
    };
    return { state: nextState, events: events };
  }

  const MangalaEngine = {
    TOTAL,
    P1_PITS,
    P1_TREAS,
    P2_PITS,
    P2_TREAS,
    PLAYER_PITS,
    PLAYER_TREAS,
    initialState,
    legalMoves,
    applyMove
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = MangalaEngine;
  } else {
    root.MangalaEngine = MangalaEngine;
  }
})(typeof window !== 'undefined' ? window : this);
