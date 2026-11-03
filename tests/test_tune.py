"""Tests for the Automated Self-Play Dataset Generator, Texel Tuning & SPSA Optimization (tune.py)."""
from __future__ import annotations

import math

from mangala.ai import DEFAULT_WEIGHTS, EvalWeights, _evaluate
from mangala.engine import TOTAL, GameState, initial_state
from mangala.tune import (
    ArenaResult,
    TrainingPosition,
    _clamp_param,
    _is_quiet_position,
    _sigmoid,
    extract_linear_features,
    generate_selfplay_dataset,
    run_adam_tuning,
    run_sprt_arena,
    run_spsa_tuning,
    texel_loss,
)


def test_eval_weights_to_from_dict() -> None:
    w = EvalWeights(
        w_mobility=0.15,
        w_extra_single=0.85,
        w_capture_offense=0.42,
    )
    d = w.to_dict()
    assert d["w_mobility"] == 0.15
    assert d["w_extra_single"] == 0.85
    assert d["w_capture_offense"] == 0.42

    w2 = EvalWeights.from_dict(d)
    assert w2 == w


def test_eval_weights_impact() -> None:
    # Baseline eval for initial state
    ev_initial = _evaluate(initial_state(), root=0, weights=DEFAULT_WEIGHTS)
    assert isinstance(ev_initial, float)

    # Custom weights with huge mobility weight
    w_skewed = EvalWeights(w_mobility=10.0)
    # Give P0 more stones
    pits = [4] * TOTAL
    pits[0] = 6
    pits[7] = 2
    s_skew = GameState(pits=pits, current_player=0)
    ev_default = _evaluate(s_skew, root=0, weights=DEFAULT_WEIGHTS)
    ev_skewed = _evaluate(s_skew, root=0, weights=w_skewed)
    assert ev_skewed > ev_default


def test_sigmoid_numerical_stability() -> None:
    assert _sigmoid(0.0) == 0.5
    assert _sigmoid(100.0) == 1.0
    assert _sigmoid(-100.0) == 0.0
    assert 0.0 < _sigmoid(1.0) < 1.0


def test_clamp_param() -> None:
    # Test bounding logic
    assert _clamp_param("w_mobility", 10.0) == 0.50
    assert _clamp_param("w_mobility", -1.0) == 0.01
    assert _clamp_param("w_mobility", 0.25) == 0.25


def test_is_quiet_position() -> None:
    # Initial state has extra turn move (pit 2: 4 stones -> lands in pit 6 hazine)
    s = initial_state()
    assert not _is_quiet_position(s)

    # State with only 1 stone far from treasury or opponent
    pits = [0] * TOTAL
    pits[0] = 1  # sows into pit 1 (no capture, no extra turn)
    pits[6] = 23
    pits[13] = 24
    s_quiet = GameState(pits=pits, current_player=0)
    assert _is_quiet_position(s_quiet)


def test_texel_loss_calculation() -> None:
    pits = [4] * TOTAL
    pos1 = TrainingPosition(pits=pits, current_player=0, result=1.0)
    pos2 = TrainingPosition(pits=pits, current_player=1, result=0.0)

    loss = texel_loss(DEFAULT_WEIGHTS, [pos1, pos2])
    assert loss > 0.0
    assert not math.isnan(loss)
    assert not math.isinf(loss)

    assert texel_loss(DEFAULT_WEIGHTS, []) == 0.0


def test_spsa_tuning_iterations() -> None:
    # Small synthetic position set
    pits1 = [4] * TOTAL
    pits2 = [2] * TOTAL
    positions = [
        TrainingPosition(pits=pits1, current_player=0, result=1.0),
        TrainingPosition(pits=pits2, current_player=0, result=0.0),
    ]

    steps_recorded: list[int] = []

    def cb(k: int, tot: int, cur_l: float, best_l: float) -> None:
        steps_recorded.append(k)

    tuned_w, losses = run_spsa_tuning(
        DEFAULT_WEIGHTS,
        positions,
        iterations=3,
        seed=123,
        callback=cb,
    )

    assert len(steps_recorded) == 3
    assert len(losses) == 4  # initial + 3 iterations
    assert isinstance(tuned_w, EvalWeights)
    # Check that tuned weights remain within valid numerical bounds
    for _k_name, val in tuned_w.to_dict().items():
        assert not math.isnan(val)


def test_sprt_arena_execution() -> None:
    # Run a tiny 1-pair arena (2 games) at depth 1 with single worker
    w1 = DEFAULT_WEIGHTS
    w2 = EvalWeights(w_mobility=0.15)
    res = run_sprt_arena(w1, w2, num_pairs=1, depth=1, num_workers=1)

    assert isinstance(res, ArenaResult)
    assert res.games_played == 2
    assert res.wins_a + res.wins_b + res.draws == 2
    assert 0.0 <= res.win_rate_a <= 1.0


def test_generate_selfplay_dataset_small() -> None:
    # Generate 2 games with single worker to test dataset generator logic
    positions = generate_selfplay_dataset(
        num_games=2,
        max_moves=20,
        time_limit=0.005,
        num_workers=1,
        seed=42,
    )
    assert isinstance(positions, list)
    for p in positions:
        assert len(p.pits) == TOTAL
        assert p.current_player in (0, 1)
        assert p.result in (0.0, 0.5, 1.0)


def test_extract_linear_features_and_adam_tuning() -> None:
    pits1 = [4, 4, 4, 4, 4, 4, 0, 4, 4, 4, 4, 4, 4, 0]
    pits2 = [2, 5, 1, 3, 4, 2, 10, 3, 2, 4, 1, 5, 2, 4]
    positions = [
        TrainingPosition(pits=pits1, current_player=0, result=1.0),
        TrainingPosition(pits=pits2, current_player=1, result=1.0),
    ]

    extracted = extract_linear_features(positions)
    assert len(extracted) == 2

    # Verify exact affine decomposition: b0 + sum(w_k * phi_k) == _evaluate(st, 0, w)
    w_test = EvalWeights(w_mobility=0.22, w_ladder_cascade=0.55, w_fortress=0.31)
    w_dict = w_test.to_dict()
    for pos, (b0, phi, _res) in zip(positions, extracted, strict=True):
        st = GameState(pits=pos.pits, current_player=pos.current_player)
        exact_ev = _evaluate(st, root=0, weights=w_test)
        linear_ev = b0 + sum(w_dict[k] * phi[k] for k in w_dict)
        assert abs(exact_ev - linear_ev) < 1e-9

    # Verify AdamW analytical tuning reduces or preserves loss cleanly
    tuned_w, losses = run_adam_tuning(DEFAULT_WEIGHTS, positions, iterations=15, lr=0.03)
    assert len(losses) == 16
    assert min(losses) <= losses[0] + 1e-12
    assert isinstance(tuned_w, EvalWeights)
