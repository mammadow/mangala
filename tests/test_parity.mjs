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
