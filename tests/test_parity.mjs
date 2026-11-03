import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Import the client-side JavaScript engine
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const MangalaEngine = require('../src/mangala/web/engine.js');

test('Cross-Language Parity: Python vs JavaScript Engine', async (t) => {
  const fixturesPath = path.join(__dirname, 'fixtures', 'engine_parity_fixtures.json');
  const fixtures = JSON.parse(fs.readFileSync(fixturesPath, 'utf-8'));

  let verifiedCount = 0;

  for (let i = 0; i < fixtures.length; i++) {
    const { initial, move, expected_state, expected_events } = fixtures[i];

    // Apply move using JavaScript engine
    const { state: actualState, events: actualEvents } = MangalaEngine.applyMove(initial, move);

    // Assert pit counts match identically
    assert.deepEqual(
      actualState.pits,
      expected_state.pits,
      `Pit mismatch at fixture #${i} (move: pit ${move})`
    );

    // Assert current_player matches
    assert.equal(
      actualState.current_player,
      expected_state.current_player,
      `current_player mismatch at fixture #${i}`
    );

    // Assert game_over matches
    assert.equal(
      actualState.game_over,
      expected_state.game_over,
      `game_over mismatch at fixture #${i}`
    );

    // Assert winner matches
    assert.equal(
      actualState.winner,
      expected_state.winner,
      `winner mismatch at fixture #${i}`
    );

    // Assert events (capture and extra_turn) match
    assert.equal(
      actualEvents.capture,
      expected_events.capture,
      `events.capture mismatch at fixture #${i}`
    );
    assert.equal(
      actualEvents.extra_turn,
      expected_events.extra_turn,
      `events.extra_turn mismatch at fixture #${i}`
    );

    // Assert legal moves match
    assert.deepEqual(
      actualState.legal,
      expected_state.legal,
      `legal moves mismatch at fixture #${i}`
    );

    verifiedCount++;
  }

  assert.equal(verifiedCount, fixtures.length);
  console.log(`Verified 100% parity across all ${verifiedCount} test cases!`);
});

test('Client AI Evaluation and Move Search Parity', (t) => {
  const MangalaAI = require('../src/mangala/web/ai.js');

  // Verify engine export integrity
  assert.ok(Array.isArray(MangalaEngine.OPP_PITS_RANGE), 'OPP_PITS_RANGE must be exported');
  assert.ok(Array.isArray(MangalaEngine.OPP_TREAS), 'OPP_TREAS must be exported');
  assert.deepEqual(MangalaEngine.OPP_PITS_RANGE[0], [7, 12]);
  assert.deepEqual(MangalaEngine.OPP_PITS_RANGE[1], [0, 5]);

  const s0 = MangalaEngine.initialState();

  // Verify lexicographicPotential and zobristHash on initial state
  assert.equal(typeof MangalaEngine.lexicographicPotential, 'function');
  assert.equal(typeof MangalaEngine.zobristHash, 'function');
  const [k0, phi0] = MangalaEngine.lexicographicPotential(s0);
  assert.equal(k0, 48);
  assert.equal(phi0, 168);
  const h0 = MangalaEngine.zobristHash(s0);
  assert.equal(typeof h0, 'bigint');
  assert.ok(h0 > 0n);

  // Test evaluation from both player perspectives
  const ev0 = MangalaAI.evaluate(s0, 0);
  const ev1 = MangalaAI.evaluate(s0, 1);
  assert.equal(typeof ev0, 'number');
  assert.equal(typeof ev1, 'number');
  assert.ok(!isNaN(ev0));
  assert.ok(!isNaN(ev1));

  // Test best move from player 0
  const mv0 = MangalaAI.bestMove(s0, 2);
  assert.ok(s0.legal.includes(mv0), `AI move ${mv0} must be in legal moves`);

  // Move to player 1's turn and test best move from player 1
  const { state: s1 } = MangalaEngine.applyMove(s0, 0);
  const [k1, phi1] = MangalaEngine.lexicographicPotential(s1);
  assert.ok(k1 < k0 || (k1 === k0 && phi1 < phi0), 'DAG potential must strictly decrease');
  assert.notEqual(MangalaEngine.zobristHash(s1), h0);
  const evP1 = MangalaAI.evaluate(s1, s1.current_player);
  assert.equal(typeof evP1, 'number');
  assert.ok(!isNaN(evP1));

  const mv1 = MangalaAI.bestMove(s1, 2);
  assert.ok(s1.legal.includes(mv1), `AI move ${mv1} must be in player 1 legal moves`);
});


