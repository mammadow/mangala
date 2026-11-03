/**
 * ai.js — Tournament-grade Superhuman Client-side AI with Transposition Table,
 * PVS Scout Search, Killer Heuristic, History Heuristic, Aspiration Windows,
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
  const ASPIRATION_WINDOW = 0.5;

  const EXACT = 0;
  const LOWER_BOUND = 1;
  const UPPER_BOUND = 2;

  // Search context tables (cleared at start of each bestMove / analyse call)
  const tt = new Map();
  let killerMoves = Array.from({ length: 64 }, () => []);
  let historyTable = [new Array(14).fill(0), new Array(14).fill(0)];
  let counterMoves = [new Array(14).fill(-1), new Array(14).fill(-1)];

  function recordCutoff(player, move, ply, depth, prevMove = -1) {
    if (ply < killerMoves.length) {
      const killers = killerMoves[ply];
      if (!killers.includes(move)) {
        killers.unshift(move);
        if (killers.length > 2) killers.pop();
      }
    }
    historyTable[player][move] += depth * depth;
    if (prevMove >= 0 && prevMove < 14) {
      counterMoves[player][prevMove] = move;
    }
  }

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
    const ownRange = Engine.OWN_PITS_RANGE ? Engine.OWN_PITS_RANGE[rootPlayer] : (rootPlayer === 0 ? [0, 5] : [7, 12]);
    const oppRange = Engine.OPP_PITS_RANGE ? Engine.OPP_PITS_RANGE[rootPlayer] : (rootPlayer === 0 ? [7, 12] : [0, 5]);
    const [ownMin, ownMax] = ownRange;
    const [oppMin, oppMax] = oppRange;
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
    let ownLadders = 0;
    let oppLadders = 0;
    let captureOffense = 0;
    let emptyOffense = 0;

    for (const i of ownPits) {
      const n = state.pits[i];
      if (n === 0) continue;
      const sowCount = n > 1 ? n - 1 : 1;
      const pos = landingTable[i][sowCount % 13];
      if (pos === ownTreas) {
        extraBonus += (n === 1 && i === ownMax) ? 0.6 : 0.4;
        ownLadders++;
      } else if (pos >= ownMin && pos <= ownMax && state.pits[pos] === 0 && sowCount < 13) {
        const opp = 12 - pos;
        const oppAfter = state.pits[opp] + (sowCount >= 8 ? 1 : 0);
        if (oppAfter > 0) emptyOffense += 0.25 * (oppAfter + 1);
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
      if (pos === oppTreas) {
        oppLadders++;
      } else if (pos >= ownMin && pos <= ownMax && state.pits[pos] > 0) {
        if ((state.pits[pos] + 1) % 2 === 0) {
          captureExposure += 0.35 * (state.pits[pos] + 1);
        }
      }
    }

    // Exact Exponential Binary Merdiven Cascade (Theorem 3: 2^k - 1 consecutive bonus turns)
    let ownStair = 0;
    for (let d = 1; d <= 6; d++) {
      if (state.pits[ownMax + 1 - d] === d) ownStair++;
      else break;
    }
    let oppStair = 0;
    for (let d = 1; d <= 6; d++) {
      if (state.pits[oppMax + 1 - d] === d) oppStair++;
      else break;
    }

    let ladderCascadeBonus = 0;
    if (ownStair >= 2) ladderCascadeBonus += 0.35 * ((1 << ownStair) - 1 - ownStair);
    else if (ownLadders >= 2) ladderCascadeBonus += 0.35 * (ownLadders - 1);

    if (oppStair >= 2) ladderCascadeBonus -= 0.35 * ((1 << oppStair) - 1 - oppStair);
    else if (oppLadders >= 2) ladderCascadeBonus -= 0.35 * (oppLadders - 1);

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

    // Even-parity defensive shield: even pits are immune to Rule 3 captures
    let parityShield = 0;
    for (const i of ownPits) {
      const n = state.pits[i];
      if (n > 0) parityShield += (n % 2 === 0 ? 0.08 : -0.06);
    }
    for (const j of oppPits) {
      const m = state.pits[j];
      if (m > 0) parityShield += (m % 2 !== 0 ? 0.06 : -0.08);
    }

    // Deep fortress reserves: back pits (0/1 or 7/8) with >= 8 stones
    let fortressBonus = 0;
    for (let i = ownMin; i <= ownMin + 1; i++) {
      if (state.pits[i] >= 8) fortressBonus += 0.20;
    }
    for (let j = oppMin; j <= oppMin + 1; j++) {
      if (state.pits[j] >= 8) fortressBonus -= 0.20;
    }

    let sweepBonus = 0;
    if (ownStones <= 4) sweepBonus += 0.2 * (4 - ownStones);
    if (oppStones <= 4) sweepBonus -= 0.2 * (4 - oppStones);

    return treasDiff
      + 0.1 * (ownStones - oppStones)
      + extraBonus
      + ladderCascadeBonus
      + captureOffense
      + emptyOffense
      - captureExposure
      - emptyHoleExposure
      + parityShield
      + fortressBonus
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
    const noisyChildren = [];
    for (const m of moves) {
      const {state: child, events} = Engine.applyMove(state, m);
      if (events.capture > 0 || events.extra_turn) {
        const noisyScore = (events.extra_turn ? 1000 : 0) + events.capture;
        noisyChildren.push({ child, noisyScore });
      }
    }
    noisyChildren.sort((a, b) => b.noisyScore - a.noisyScore);

    if (state.current_player === rootPlayer) {
      if (standPat >= beta) return standPat;
      alpha = Math.max(alpha, standPat);
      let best = standPat;
      for (const { child } of noisyChildren) {
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
      for (const { child } of noisyChildren) {
        const val = quiescence(child, alpha, beta, rootPlayer, qDepth - 1);
        if (val < best) best = val;
        if (best < beta) beta = best;
        if (alpha >= beta) break;
      }
      return best;
    }
  }

  function search(state, depth, alpha, beta, rootPlayer, ply = 0, prevMove = -1, extraStreak = 0) {
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

    // Transposition Table probe
    const key = `${state.pits.join(',')}:${state.current_player}`;
    const entry = tt.get(key);
    if (entry && entry.depth >= depth) {
      if (entry.flag === EXACT) return entry.val;
      if (entry.flag === LOWER_BOUND && entry.val >= beta) return entry.val;
      if (entry.flag === UPPER_BOUND && entry.val <= alpha) return entry.val;
    }

    const isMax = (state.current_player === rootPlayer);

    // Reverse Futility Pruning (Static Null-Move Pruning) at shallow depths
    if (depth <= 2 && stonesOnBoard > 16 && extraStreak === 0) {
      const evalMargin = 1.5 * depth;
      const staticEval = evaluate(state, rootPlayer);
      if (isMax && staticEval - evalMargin >= beta) return staticEval - evalMargin;
      if (!isMax && staticEval + evalMargin <= alpha) return staticEval + evalMargin;
    }

    const moves = Engine.legalMoves(state);
    if (moves.length === 0) return evaluate(state, rootPlayer);

    const alphaOrig = alpha;
    const betaOrig = beta;
    let bestVal = isMax ? -INF : INF;
    let bestHere = -1;
    const currTreas = Engine.PLAYER_TREAS[state.current_player];
    const currPlayer = state.current_player;

    const pvMove = entry ? entry.bestMove : -1;
    const killers = (ply < killerMoves.length) ? killerMoves[ply] : [];
    const counterM = (prevMove >= 0 && prevMove < 14) ? counterMoves[currPlayer][prevMove] : -1;

    // Order moves: PV move > winning move >= 25 > extra turn > capture > killer > counter > history
    const scored = [];
    for (const m of moves) {
      const {state: child, events} = Engine.applyMove(state, m);
      let score = 0;
      if (m === pvMove) score += 10000000;
      if (child.pits[currTreas] >= 25) score += 20000000;
      else if (events.extra_turn) score += 5000000 + events.capture * 10000;
      else if (events.capture > 0) score += 3000000 + events.capture * 10000;
      else if (killers.includes(m)) score += 1000000 - killers.indexOf(m) * 100000;
      else if (m === counterM) score += 800000;
      score += historyTable[currPlayer][m];
      scored.push({m, child, score});
    }
    scored.sort((a, b) => b.score - a.score);

    for (let i = 0; i < scored.length; i++) {
      const {m, child} = scored[i];
      const isExtra = (child.current_player === currPlayer);
      const nextStreak = isExtra ? (extraStreak + 1) : 0;
      const ext = (isExtra && extraStreak === 0 && depth >= 3 && depth < 64) ? 1 : 0;
      const nextD = depth - 1 + ext;

      let val;
      if (i === 0) {
        val = search(child, nextD, alpha, beta, rootPlayer, ply + 1, m, nextStreak);
      } else {
        // Late Move Reduction (LMR) on quiet moves ordered late
        const doLmr = (i >= 3 && depth >= 3 && child.pits[currTreas] === state.pits[currTreas] && !isExtra);
        const reduction = doLmr ? 1 : 0;

        // PVS zero-window scout search (reduced first if LMR)
        if (isMax) {
          const scoutAlpha = Math.max(alpha, bestVal);
          val = search(child, nextD - reduction, scoutAlpha, scoutAlpha + PVS_EPSILON, rootPlayer, ply + 1, m, nextStreak);
          if (reduction > 0 && val > scoutAlpha) {
            val = search(child, nextD, scoutAlpha, scoutAlpha + PVS_EPSILON, rootPlayer, ply + 1, m, nextStreak);
          }
          if (val > bestVal && val < beta) {
            val = search(child, nextD, val, beta, rootPlayer, ply + 1, m, nextStreak);
          }
        } else {
          val = search(child, nextD - reduction, beta - PVS_EPSILON, beta, rootPlayer, ply + 1, m, nextStreak);
          if (reduction > 0 && val < beta) {
            val = search(child, nextD, beta - PVS_EPSILON, beta, rootPlayer, ply + 1, m, nextStreak);
          }
          if (val < beta && val > alpha) {
            val = search(child, nextD, alpha, val, rootPlayer, ply + 1, m, nextStreak);
          }
        }
      }

      if (isMax) {
        if (val > bestVal || bestHere === -1) {
          bestVal = val;
          bestHere = m;
        }
        if (bestVal > alpha) alpha = bestVal;
        if (alpha >= beta) {
          recordCutoff(currPlayer, m, ply, depth, prevMove);
          break;
        }
      } else {
        if (val < bestVal || bestHere === -1) {
          bestVal = val;
          bestHere = m;
        }
        if (bestVal < beta) beta = bestVal;
        if (alpha >= beta) {
          recordCutoff(currPlayer, m, ply, depth, prevMove);
          break;
        }
      }
    }

    // Depth-preferred Transposition Table replacement
    let flag = EXACT;
    if (bestVal <= alphaOrig) flag = UPPER_BOUND;
    else if (bestVal >= betaOrig) flag = LOWER_BOUND;

    if (!entry || depth >= entry.depth) {
      tt.set(key, { depth, val: bestVal, flag, bestMove: bestHere });
    }

    return bestVal;
  }

  function searchRoot(state, depth, pvMove, alpha, beta, rootPlayer) {
    const moves = Engine.legalMoves(state);
    if (moves.length === 0) return { bestM: -1, bestVal: -INF };
    const currTreas = Engine.PLAYER_TREAS[rootPlayer];

    const scored = [];
    for (const m of moves) {
      const {state: child, events} = Engine.applyMove(state, m);
      let score = 0;
      if (m === pvMove) score += 10000000;
      if (child.pits[currTreas] >= 25) score += 2000000;
      else if (events.extra_turn) score += 50000 + events.capture * 100;
      else if (events.capture > 0) score += 30000 + events.capture * 100;
      score += historyTable[rootPlayer][m];
      scored.push({m, child, score});
    }
    scored.sort((a, b) => b.score - a.score);

    let bestVal = -INF;
    let bestM = scored[0].m;

    for (let i = 0; i < scored.length; i++) {
      const {m, child} = scored[i];
      let val;
      if (i === 0) {
        val = search(child, depth - 1, alpha, beta, rootPlayer, 1);
      } else {
        const scoutAlpha = Math.max(alpha, bestVal);
        val = search(child, depth - 1, scoutAlpha, scoutAlpha + PVS_EPSILON, rootPlayer, 1);
        if (val > bestVal && val < beta) {
          val = search(child, depth - 1, val, beta, rootPlayer, 1);
        }
      }

      if (val > bestVal || bestM === -1) {
        bestVal = val;
        bestM = m;
      }
      if (bestVal >= beta) break;
    }
    return { bestM, bestVal };
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

    // Reset search context
    tt.clear();
    killerMoves = Array.from({ length: 64 }, () => []);
    historyTable = [new Array(14).fill(0), new Array(14).fill(0)];
    counterMoves = [new Array(14).fill(-1), new Array(14).fill(-1)];

    let bestMv = moves[0];
    let bestScore = -INF;
    const rootKey = `${state.pits.join(',')}:${state.current_player}`;

    // Iterative deepening up to depth with aspiration search
    for (let d = 1; d <= depth; d++) {
      const pv = tt.has(rootKey) ? tt.get(rootKey).bestMove : -1;
      let res;
      if (d >= 3 && Math.abs(bestScore) < WIN) {
        const aspAlpha = bestScore - ASPIRATION_WINDOW;
        const aspBeta = bestScore + ASPIRATION_WINDOW;
        res = searchRoot(state, d, pv, aspAlpha, aspBeta, rootPlayer);
        if (res.bestVal <= aspAlpha || res.bestVal >= aspBeta) {
          res = searchRoot(state, d, pv, -INF, INF, rootPlayer);
        }
      } else {
        res = searchRoot(state, d, pv, -INF, INF, rootPlayer);
      }

      bestMv = res.bestM;
      bestScore = res.bestVal;
      tt.set(rootKey, { depth: d, val: bestScore, flag: EXACT, bestMove: bestMv });

      if (Math.abs(bestScore) >= WIN) break; // Forced win/loss reached
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
