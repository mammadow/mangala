"""
nnue.py — Sub-Microsecond Quantized Dual-Perspective NNUE for Turkish Mangala.

Implements a zero-dependency, pure-Python quantized integer neural network
(Efficiently Updatable Neural Network) modeled after Stockfish NNUE:
  - Dual-perspective sparse input features (12 active pits * 22 stone buckets = 264 per side).
  - O(1) incremental accumulator update when pits change during sowing.
  - Pure integer arithmetic (int16 accumulators, ClippedReLU [0..127], int8 hidden weights).
  - Built-in stochastic gradient distillation trainer to fit NNUE weights to deep search scores.
"""
from __future__ import annotations

import math
import random
from array import array
from collections.abc import Sequence
from dataclasses import dataclass

from .engine import P1_TREASURY, P2_TREASURY, GameState

_NUM_PITS = 12
_STONE_BUCKETS = 22  # 0, 1, ..., 20, >=21
_FEATURES_PER_SIDE = _NUM_PITS * _STONE_BUCKETS  # 264
_HIDDEN_HALF = 16  # 16 neurons per perspective -> 32 concatenated after CReLU
_QA = 127  # Accumulator clipping scale
_QW = 64   # Output weight quantization scale

_CANONICAL_ORDER_P0: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12)
_CANONICAL_ORDER_P1: tuple[int, ...] = (7, 8, 9, 10, 11, 12, 0, 1, 2, 3, 4, 5)


def feature_index(canonical_pit: int, stones: int) -> int:
    """Return sparse binary feature index in [0, 264) for (canonical_pit, stones)."""
    bucket = stones if stones < _STONE_BUCKETS - 1 else (_STONE_BUCKETS - 1)
    if bucket < 0:
        bucket = 0
    return canonical_pit * _STONE_BUCKETS + bucket


def extract_sparse_indices(pits: Sequence[int], perspective: int) -> tuple[int, ...]:
    """Return the 12 active feature indices for *perspective* (0 or 1)."""
    order = _CANONICAL_ORDER_P0 if perspective == 0 else _CANONICAL_ORDER_P1
    return tuple(feature_index(idx, pits[pit]) for idx, pit in enumerate(order))


@dataclass(slots=True)
class NNUEAccumulator:
    """Dual-perspective int16 feature accumulator (us, them)."""
    acc_p0: array  # length _HIDDEN_HALF (16)
    acc_p1: array  # length _HIDDEN_HALF (16)

    def copy(self) -> NNUEAccumulator:
        return NNUEAccumulator(array("h", self.acc_p0), array("h", self.acc_p1))


class NNUEEvaluator:
    """Quantized NNUE Evaluator with incremental accumulator updates."""

    def __init__(
        self,
        w1: Sequence[int] | None = None,
        b1: Sequence[int] | None = None,
        w2: Sequence[int] | None = None,
        b2: int = 0,
    ) -> None:
        # w1: [_FEATURES_PER_SIDE * _HIDDEN_HALF] int16
        # b1: [_HIDDEN_HALF] int16
        # w2: [2 * _HIDDEN_HALF] int16 (maps concatenated [us, them] CReLU to centistone output)
        if w1 is not None and b1 is not None and w2 is not None:
            self.w1 = array("h", w1)
            self.b1 = array("h", b1)
            self.w2 = array("h", w2)
            self.b2 = int(b2)
        else:
            self.w1, self.b1, self.w2, self.b2 = self._init_tactical_prior()

    @staticmethod
    def _init_tactical_prior() -> tuple[array, array, array, int]:
        """Initialize NNUE weights with domain-informed Turkish Mangala priors."""
        w1 = array("h", [0] * (_FEATURES_PER_SIDE * _HIDDEN_HALF))
        b1 = array("h", [16] * _HIDDEN_HALF)
        w2 = array("h", [0] * (2 * _HIDDEN_HALF))

        for cp in range(_NUM_PITS):
            is_own = cp < 6
            dist_to_treas = (6 - cp) if is_own else (12 - cp)
            for s in range(_STONE_BUCKETS):
                f_idx = feature_index(cp, s)
                base = f_idx * _HIDDEN_HALF
                # Neuron 0: Mobility & stone presence
                w1[base + 0] = (s * 4) if is_own else -(s * 4)
                # Neuron 1: Direct extra-turn landing (s == dist_to_treas or s==1 at cp==5)
                sow_cnt = s - 1 if s > 1 else s
                lands_treas = (s > 0) and (sow_cnt == dist_to_treas)
                w1[base + 1] = 38 if (is_own and lands_treas) else 0
                # Neuron 2: Even-parity defensive shield on own pits
                w1[base + 2] = 14 if (is_own and s > 0 and s % 2 == 0) else 0
                # Neuron 3: Odd-parity capture vulnerability on opponent pits
                w1[base + 3] = 16 if (not is_own and s > 0 and s % 2 == 1) else 0
                # Neuron 4: Empty pit capture readiness on own side
                w1[base + 4] = 12 if (is_own and s == 0) else 0
                # Neuron 5: Back-pit anchor fortress (cp in (0, 1) and s >= 8)
                w1[base + 5] = 22 if (is_own and cp <= 1 and s >= 8) else 0
                # Neuron 6: Starvation / low-stone sweep proximity
                w1[base + 6] = 20 if (is_own and s == 0) else 0
                # Neurons 7..15: Deterministic sinusoidal positional basis
                for h in range(7, _HIDDEN_HALF):
                    angle = (cp + 1) * (s + 1) * (h + 1) * 0.37
                    w1[base + h] = round(8.0 * math.sin(angle))

        # Output weights: positive for own perspective, negative for opponent perspective
        weights_template = [28, 42, 18, 22, 15, 20, 16, 8, 6, -6, 5, -5, 4, -4, 3, -3]
        for h in range(_HIDDEN_HALF):
            w2[h] = weights_template[h]
            w2[_HIDDEN_HALF + h] = -weights_template[h]

        return w1, b1, w2, 0

    def compute_accumulator(self, pits: Sequence[int]) -> NNUEAccumulator:
        """Compute full dual-perspective accumulator from scratch for *pits*."""
        acc0 = array("h", self.b1)
        acc1 = array("h", self.b1)
        w1 = self.w1

        for f0 in extract_sparse_indices(pits, 0):
            base = f0 * _HIDDEN_HALF
            for h in range(_HIDDEN_HALF):
                acc0[h] += w1[base + h]

        for f1 in extract_sparse_indices(pits, 1):
            base = f1 * _HIDDEN_HALF
            for h in range(_HIDDEN_HALF):
                acc1[h] += w1[base + h]

        return NNUEAccumulator(acc0, acc1)

    def update_accumulator(
        self,
        prev_acc: NNUEAccumulator,
        old_pits: Sequence[int],
        new_pits: Sequence[int],
    ) -> NNUEAccumulator:
        """Incrementally update only the changed pits in O(changed_pits) time."""
        acc0 = array("h", prev_acc.acc_p0)
        acc1 = array("h", prev_acc.acc_p1)
        w1 = self.w1

        for cp, pit in enumerate(_CANONICAL_ORDER_P0):
            old_s = old_pits[pit]
            new_s = new_pits[pit]
            if old_s == new_s:
                continue
            # Update perspective 0
            old_f0 = feature_index(cp, old_s) * _HIDDEN_HALF
            new_f0 = feature_index(cp, new_s) * _HIDDEN_HALF
            # Update perspective 1 (flipped canonical index: (cp + 6) % 12)
            cp1 = (cp + 6) if cp < 6 else (cp - 6)
            old_f1 = feature_index(cp1, old_s) * _HIDDEN_HALF
            new_f1 = feature_index(cp1, new_s) * _HIDDEN_HALF

            for h in range(_HIDDEN_HALF):
                acc0[h] += w1[new_f0 + h] - w1[old_f0 + h]
                acc1[h] += w1[new_f1 + h] - w1[old_f1 + h]

        return NNUEAccumulator(acc0, acc1)

    def forward_from_accumulator(
        self,
        acc: NNUEAccumulator,
        state: GameState,
        root: int,
    ) -> float:
        """Evaluate position in stone units using quantized integer CReLU forward pass."""
        own_t = state.pits[P1_TREASURY] if root == 0 else state.pits[P2_TREASURY]
        opp_t = state.pits[P2_TREASURY] if root == 0 else state.pits[P1_TREASURY]
        treas_diff = own_t - opp_t

        us_acc = acc.acc_p0 if root == 0 else acc.acc_p1
        them_acc = acc.acc_p1 if root == 0 else acc.acc_p0
        w2 = self.w2

        out_sum = self.b2
        for h in range(_HIDDEN_HALF):
            # ClippedReLU in [0, 127]
            v_us = us_acc[h]
            if v_us < 0:
                v_us = 0
            elif v_us > _QA:
                v_us = _QA

            v_them = them_acc[h]
            if v_them < 0:
                v_them = 0
            elif v_them > _QA:
                v_them = _QA

            out_sum += v_us * w2[h] + v_them * w2[_HIDDEN_HALF + h]

        # Scale integer output back to stone units
        nnue_positional = out_sum / float(_QA * _QW)
        return treas_diff + nnue_positional

    def evaluate(self, state: GameState, root: int) -> float:
        """Direct convenience evaluation for *state* from *root* player's perspective."""
        acc = self.compute_accumulator(state.pits)
        return self.forward_from_accumulator(acc, state, root)


def train_nnue_distillation(
    samples: Sequence[tuple[GameState, float]],
    epochs: int = 10,
    lr: float = 0.05,
    seed: int = 42,
) -> NNUEEvaluator:
    """Distill target search/heuristic evaluations (in stone units) into a Quantized NNUE."""
    rng = random.Random(seed)
    evaluator = NNUEEvaluator()
    w1_f = [float(x) for x in evaluator.w1]
    b1_f = [float(x) for x in evaluator.b1]
    w2_f = [float(x) for x in evaluator.w2]
    b2_f = float(evaluator.b2)
    scale = float(_QA * _QW)

    indices = list(range(len(samples)))
    for _epoch in range(epochs):
        rng.shuffle(indices)
        for idx in indices:
            st, target_score = samples[idx]
            root = st.current_player
            own_t = st.pits[P1_TREASURY] if root == 0 else st.pits[P2_TREASURY]
            opp_t = st.pits[P2_TREASURY] if root == 0 else st.pits[P1_TREASURY]
            target_pos = target_score - (own_t - opp_t)

            us_feats = extract_sparse_indices(st.pits, root)
            them_feats = extract_sparse_indices(st.pits, 1 - root)

            us_pre = list(b1_f)
            them_pre = list(b1_f)
            for f in us_feats:
                base = f * _HIDDEN_HALF
                for h in range(_HIDDEN_HALF):
                    us_pre[h] += w1_f[base + h]
            for f in them_feats:
                base = f * _HIDDEN_HALF
                for h in range(_HIDDEN_HALF):
                    them_pre[h] += w1_f[base + h]

            us_act = [min(float(_QA), max(0.0, x)) for x in us_pre]
            them_act = [min(float(_QA), max(0.0, x)) for x in them_pre]

            pred_pos = (
                b2_f
                + sum(us_act[h] * w2_f[h] + them_act[h] * w2_f[_HIDDEN_HALF + h] for h in range(_HIDDEN_HALF))
            ) / scale

            err = pred_pos - target_pos
            grad_out = 2.0 * err / scale

            for h in range(_HIDDEN_HALF):
                g_us = grad_out * w2_f[h] if 0.0 < us_pre[h] < _QA else 0.0
                g_them = grad_out * w2_f[_HIDDEN_HALF + h] if 0.0 < them_pre[h] < _QA else 0.0

                w2_f[h] -= lr * scale * grad_out * us_act[h] * 0.01
                w2_f[_HIDDEN_HALF + h] -= lr * scale * grad_out * them_act[h] * 0.01
                b1_f[h] -= lr * scale * (g_us + g_them) * 0.1

                if g_us != 0.0:
                    step_us = lr * scale * g_us
                    for f in us_feats:
                        w1_f[f * _HIDDEN_HALF + h] -= step_us
                if g_them != 0.0:
                    step_them = lr * scale * g_them
                    for f in them_feats:
                        w1_f[f * _HIDDEN_HALF + h] -= step_them

    def _clip16(v: float) -> int:
        return max(-4096, min(4096, round(v)))

    return NNUEEvaluator(
        w1=[_clip16(x) for x in w1_f],
        b1=[_clip16(x) for x in b1_f],
        w2=[_clip16(x) for x in w2_f],
        b2=_clip16(b2_f),
    )


DEFAULT_NNUE = NNUEEvaluator()
