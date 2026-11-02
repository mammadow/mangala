/**
 * ai.js — Client-side Minimax with Alpha-Beta pruning for Turkish Mangala.
 * Enables full offline play and GitHub Pages deployment without Python backend.
 */
(function(root) {
  const Engine = typeof require !== 'undefined' ? require('./engine') : root.MangalaEngine;
  const INF = 1e9;
  const WIN = 10000;
  const Q_DEPTH = 3;

  function evaluate(state, rootPlayer) {
    const p1 = state.pits[Engine.P1_TREAS], p2 = state.pits[Engine.P2_TREAS];
    const treasDiff = (rootPlayer === 0) ? (p1 - p2) : (p2 - p1);

    const ownPits = Engine.PLAYER_PITS[rootPlayer];
    const oppPits = Engine.PLAYER_PITS[1 - rootPlayer];
    const ownTreas = Engine.PLAYER_TREAS[rootPlayer];
    const [ownMin, ownMax] = Engine.OWN_PITS_RANGE[rootPlayer];
    const landingTable = Engine.SOW_LANDING[rootPlayer];

    let ownStones = 0, oppStones = 0;
    for (const p of ownPits) ownStones += state.pits[p];
    for (const p of oppPits) oppStones += state.pits[p];

    let extraBonus = 0;
    let emptyOffense = 0;

    for (const i of ownPits) {
      const n = state.pits[i];
      if (n === 0) continue;
      const sowCount = n > 1 ? n - 1 : 1;
      const pos = landingTable[i][sowCount % 13];
      if (pos === ownTreas) {
        extraBonus += 0.4;
      } else if (pos >= ownMin && pos <= ownMax && state.pits[pos] === 0) {
        const opp = 12 - pos;
        if (state.pits[opp] > 0) emptyOffense += 0.25 * (state.pits[opp] + 1);
      }
    }

    let exposure = 0;
    for (const i of ownPits) {
      const n = state.pits[i];
      if (n > 0 && n % 2 === 0) exposure += 0.3;
    }

    return treasDiff + 0.1 * (ownStones - oppStones) + extraBonus + emptyOffense - exposure;
  }

  function quiescence(state, alpha, beta, rootPlayer, qDepth) {
    if (state.game_over) {
      const p1 = state.pits[Engine.P1_TREAS], p2 = state.pits[Engine.P2_TREAS];
      const diff = (rootPlayer === 0) ? (p1 - p2) : (p2 - p1);
      return diff > 0 ? (WIN + diff) : (diff < 0 ? (-WIN + diff) : 0);
    }
    const standPat = evaluate(state, rootPlayer);
    if (qDepth <= 0) return standPat;

    const moves = Engine.legalMoves(state);
    if (state.current_player === rootPlayer) {
      if (standPat >= beta) return standPat;
      alpha = Math.max(alpha, standPat);
      let best = standPat;
      for (const m of moves) {
        const {state: child, events} = Engine.applyMove(state, m);
        if (!(events.capture > 0 || events.extra_turn)) continue;
        const val = quiescence(child, alpha, beta, rootPlayer, qDepth - 1);
        if (val > best) best = val;
        if (best > alpha) alpha = best;
        if (alpha >= beta) break;
      }
      return best;
    } else {
      if (standPat <= alpha) return standPat;
      beta = Math.min(beta, standPat);
      let best = standPat;
      for (const m of moves) {
        const {state: child, events} = Engine.applyMove(state, m);
        if (!(events.capture > 0 || events.extra_turn)) continue;
        const val = quiescence(child, alpha, beta, rootPlayer, qDepth - 1);
        if (val < best) best = val;
        if (best < beta) beta = best;
        if (alpha >= beta) break;
      }
      return best;
    }
  }

  function search(state, depth, alpha, beta, rootPlayer) {
    if (state.game_over) {
      const p1 = state.pits[Engine.P1_TREAS], p2 = state.pits[Engine.P2_TREAS];
      const diff = (rootPlayer === 0) ? (p1 - p2) : (p2 - p1);
      return diff > 0 ? (WIN + diff) : (diff < 0 ? (-WIN + diff) : 0);
    }
    if (depth <= 0) return quiescence(state, alpha, beta, rootPlayer, Q_DEPTH);

    const moves = Engine.legalMoves(state);
    if (moves.length === 0) return evaluate(state, rootPlayer);

    const isMax = (state.current_player === rootPlayer);
    let bestVal = isMax ? -INF : INF;

    for (const m of moves) {
      const {state: child} = Engine.applyMove(state, m);
      const val = search(child, depth - 1, alpha, beta, rootPlayer);
      if (isMax) {
        if (val > bestVal) bestVal = val;
        if (bestVal > alpha) alpha = bestVal;
        if (alpha >= beta) break;
      } else {
        if (val < bestVal) bestVal = val;
        if (bestVal < beta) beta = bestVal;
        if (alpha >= beta) break;
      }
    }
    return bestVal;
  }

  function bestMove(state, depth = 5) {
    const moves = Engine.legalMoves(state);
    if (moves.length === 0) return null;
    if (moves.length === 1) return moves[0];

    const rootPlayer = state.current_player;
    let bestMove = moves[0];
    let bestScore = -INF;

    for (const m of moves) {
      const {state: child} = Engine.applyMove(state, m);
      const val = search(child, depth - 1, -INF, INF, rootPlayer);
      if (val > bestScore) {
        bestScore = val;
        bestMove = m;
      }
    }
    return bestMove;
  }

  const MangalaAI = {
    bestMove,
    search,
    evaluate
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = MangalaAI;
  } else {
    root.MangalaAI = MangalaAI;
  }
})(typeof window !== 'undefined' ? window : this);
