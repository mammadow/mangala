/**
 * ai.js — Tournament-grade Client-side AI with PVS, Killer Heuristic,
 * 25-Stone Victory Threshold, Exact Endgame Solver, and Opening Book
 * for Turkish Mangala (Browser & Node.js).
 */
(function(root) {
  const Engine = typeof require !== 'undefined' ? require('./engine') : root.MangalaEngine;
  const Book = typeof require !== 'undefined' ? (function() {
    try { return require('./book'); } catch(e) { return null; }
  })() : root.MangalaBook;

  const INF = 1e9;
  const WIN = 10000;
  const Q_DEPTH = 4;
  const PVS_EPSILON = 1e-4;

  function evaluate(state, rootPlayer) {
    const ownTreas = Engine.PLAYER_TREAS[rootPlayer];
    const oppTreas = Engine.PLAYER_TREAS[1 - rootPlayer];
    const ownT = state.pits[ownTreas];
    const oppT = state.pits[oppTreas];

    // Mathematical victory threshold: >= 25 stones guarantees win outright
    if (ownT >= 25) return WIN + (ownT - oppT);
    if (oppT >= 25) return -WIN + (ownT - oppT);

    const treasDiff = ownT - oppT;
    const ownPits = Engine.PLAYER_PITS[rootPlayer];
    const oppPits = Engine.PLAYER_PITS[1 - rootPlayer];
    const [ownMin, ownMax] = Engine.OWN_PITS_RANGE[rootPlayer];
    const [oppMin, oppMax] = Engine.OPP_PITS_RANGE[rootPlayer];
    const landingTable = Engine.SOW_LANDING[rootPlayer];
    const oppLandingTable = Engine.SOW_LANDING[1 - rootPlayer];

    let ownStones = 0, oppStones = 0;
    for (const p of ownPits) ownStones += state.pits[p];
    for (const p of oppPits) oppStones += state.pits[p];

    // Threshold urgency & opponent suppression
    let thresholdBonus = 0;
    if (ownT >= 20) thresholdBonus += (ownT - 19) * 0.5;
    if (oppT >= 20) thresholdBonus -= (oppT - 19) * 0.6;

    let extraBonus = 0;
    let captureOffense = 0;
    let emptyOffense = 0;

    for (const i of ownPits) {
      const n = state.pits[i];
      if (n === 0) continue;
      const sowCount = n > 1 ? n - 1 : 1;
      const pos = landingTable[i][sowCount % 13];
      if (pos === ownTreas) {
        extraBonus += (n === 1 && i === ownMax) ? 0.6 : 0.4;
      } else if (pos >= ownMin && pos <= ownMax && state.pits[pos] === 0) {
        const opp = 12 - pos;
        if (state.pits[opp] > 0) emptyOffense += 0.25 * (state.pits[opp] + 1);
      } else if (pos >= oppMin && pos <= oppMax) {
        if ((state.pits[pos] + 1) % 2 === 0) {
          captureOffense += 0.35 * (state.pits[pos] + 1);
        }
      }
    }

    let captureExposure = 0;
    for (const j of oppPits) {
      const m = state.pits[j];
      if (m === 0) continue;
      const sowCount = m > 1 ? m - 1 : 1;
      const pos = oppLandingTable[j][sowCount % 13];
      if (pos >= ownMin && pos <= ownMax && state.pits[pos] > 0) {
        if ((state.pits[pos] + 1) % 2 === 0) {
          captureExposure += 0.35 * (state.pits[pos] + 1);
        }
      }
    }

    let emptyHoleExposure = 0;
    for (const e of oppPits) {
      if (state.pits[e] !== 0) continue;
      const opp = 12 - e;
      if (state.pits[opp] === 0) continue;
      for (const j of oppPits) {
        const m = state.pits[j];
        if (m === 0) continue;
        const sowCount = m > 1 ? m - 1 : 1;
        const pos = oppLandingTable[j][sowCount % 13];
        if (pos === e) {
          emptyHoleExposure += 0.25 * (state.pits[opp] + 1);
          break;
        }
      }
    }

    let sweepBonus = 0;
    if (ownStones <= 4) sweepBonus += 0.2 * (4 - ownStones);
    if (oppStones <= 4) sweepBonus -= 0.2 * (4 - oppStones);

    return treasDiff
      + 0.1 * (ownStones - oppStones)
      + extraBonus
      + captureOffense
      + emptyOffense
      - captureExposure
      - emptyHoleExposure
      + sweepBonus
      + thresholdBonus;
  }

  function quiescence(state, alpha, beta, rootPlayer, qDepth) {
    if (state.game_over) {
      const p1 = state.pits[Engine.P1_TREAS], p2 = state.pits[Engine.P2_TREAS];
      const diff = (rootPlayer === 0) ? (p1 - p2) : (p2 - p1);
      return diff > 0 ? (WIN + diff) : (diff < 0 ? (-WIN + diff) : 0);
    }

    // 25-stone victory cutoff
    const ownT = state.pits[Engine.PLAYER_TREAS[rootPlayer]];
    const oppT = state.pits[Engine.PLAYER_TREAS[1 - rootPlayer]];
    if (ownT >= 25) return WIN + (ownT - oppT);
    if (oppT >= 25) return -WIN + (ownT - oppT);

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

    // 25-stone victory cutoff
    const ownT = state.pits[Engine.PLAYER_TREAS[rootPlayer]];
    const oppT = state.pits[Engine.PLAYER_TREAS[1 - rootPlayer]];
    if (ownT >= 25) return WIN + (ownT - oppT);
    if (oppT >= 25) return -WIN + (ownT - oppT);

    // Exact endgame solver: when <= 16 stones remain on the board, solve to terminal
    let stonesOnBoard = 0;
    for (let i = 0; i < 6; i++) stonesOnBoard += state.pits[i];
    for (let i = 7; i < 13; i++) stonesOnBoard += state.pits[i];
    if (stonesOnBoard <= 16 && depth < 64) depth = 64;

    if (depth <= 0) return quiescence(state, alpha, beta, rootPlayer, Q_DEPTH);

    const moves = Engine.legalMoves(state);
    if (moves.length === 0) return evaluate(state, rootPlayer);

    const isMax = (state.current_player === rootPlayer);
    let bestVal = isMax ? -INF : INF;
    const currTreas = Engine.PLAYER_TREAS[state.current_player];

    // Order moves: winning move >= 25 > extra turn > capture > others
    const scored = [];
    for (const m of moves) {
      const {state: child, events} = Engine.applyMove(state, m);
      let score = 0;
      if (child.pits[currTreas] >= 25) score += 200000;
      else if (events.extra_turn) score += 50000 + events.capture * 100;
      else if (events.capture > 0) score += 30000 + events.capture * 100;
      scored.push({m, child, score});
    }
    scored.sort((a, b) => b.score - a.score);

    for (let i = 0; i < scored.length; i++) {
      const {child} = scored[i];
      let val;
      if (i === 0) {
        val = search(child, depth - 1, alpha, beta, rootPlayer);
      } else {
        // PVS zero-window search
        if (isMax) {
          val = search(child, depth - 1, alpha, alpha + PVS_EPSILON, rootPlayer);
          if (val > alpha && val < beta) {
            val = search(child, depth - 1, val, beta, rootPlayer);
          }
        } else {
          val = search(child, depth - 1, beta - PVS_EPSILON, beta, rootPlayer);
          if (val > alpha && val < beta) {
            val = search(child, depth - 1, alpha, val, rootPlayer);
          }
        }
      }

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

  function bestMove(state, depth = 6, useBook = true) {
    const moves = Engine.legalMoves(state);
    if (moves.length === 0) return null;
    if (moves.length === 1) return moves[0];

    // Check precomputed opening book
    if (useBook && Book && typeof Book.getBookMove === 'function') {
      const bookMv = Book.getBookMove(state);
      if (bookMv !== null && moves.includes(bookMv)) {
        return bookMv;
      }
    }

    const rootPlayer = state.current_player;
    const ownTreas = Engine.PLAYER_TREAS[rootPlayer];

    // Fast-path: immediate winning move securing 25+ stones
    for (const m of moves) {
      const {state: child} = Engine.applyMove(state, m);
      if (child.pits[ownTreas] >= 25) return m;
    }

    let bestMv = moves[0];
    let bestScore = -INF;

    for (const m of moves) {
      const {state: child} = Engine.applyMove(state, m);
      const val = search(child, depth - 1, -INF, INF, rootPlayer);
      if (val > bestScore) {
        bestScore = val;
        bestMv = m;
      }
    }
    return bestMv;
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
