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

  const OWN_PITS_RANGE = [[0, 5], [7, 12]];
  const OPP_PITS_RANGE = [[7, 12], [0, 5]];

  function computeLanding(player, pit, toSow) {
    const oppTreas = OPP_TREAS[player];
    let pos = pit;
    for (let s = 0; s < toSow; s++) {
      pos = (pos + 1) % TOTAL;
      if (pos === oppTreas) pos = (pos + 1) % TOTAL;
    }
    return pos;
  }

  // Precomputed O(1) landing table: SOW_LANDING[player][pit][toSow % 13]
  const SOW_LANDING = [0, 1].map(p =>
    Array.from({ length: TOTAL }, (_, pit) =>
      Array.from({ length: 13 }, (_, k) => computeLanding(p, pit, k))
    )
  );

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
    const [ownMin, ownMax] = OWN_PITS_RANGE[player];
    const [oppMin, oppMax] = OPP_PITS_RANGE[player];
    const ownTreas = PLAYER_TREAS[player];
    const oppTreas = OPP_TREAS[player];

    if (state.game_over || pit < ownMin || pit > ownMax || state.pits[pit] === 0) {
      throw new Error(`Illegal move: pit ${pit}`);
    }

    const pits = state.pits.slice();

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
    if (last >= oppMin && last <= oppMax && pits[last] % 2 === 0 && pits[last] > 0) {
      captured = pits[last];
      pits[ownTreas] += captured;
      pits[last] = 0;
    }
    // Rule 2: Empty-hole capture (lands in own empty pit, opposite has stones)
    else if (last >= ownMin && last <= ownMax && state.pits[last] === 0 && pits[last] === 1) {
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
      const [pMin, pMax] = OWN_PITS_RANGE[p];
      let empty = true;
      for (let i = pMin; i <= pMax; i++) {
        if (pits[i] !== 0) { empty = false; break; }
      }
      if (empty) {
        const other = 1 - p;
        const [oMin, oMax] = OWN_PITS_RANGE[other];
        for (let i = oMin; i <= oMax; i++) {
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
    OWN_PITS_RANGE,
    SOW_LANDING,
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
