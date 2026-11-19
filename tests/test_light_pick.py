"""
光源のくじ (program/light/block_light_trace.csh の LIGHT_PICK_STRATIFIED) の数値の確認

GLSL と同じ手順を Python で書いて、期待値が変わらないことと、時間平均のばらつきが独立な乱数より小さいことを確かめる
シェーダーの式を変えたら、ここの pick_single_uniform / pick_stratified も合わせる
"""

from __future__ import annotations

import numpy as np

R1_STEP = 0.618033988749895
STRATA_MAX = 8
PICK_U_MAX = float(np.nextafter(np.float32(1.0), np.float32(0.0)))


def pick_single_uniform(weights, u: float) -> tuple[int, float]:
    """1 個の一様乱数で引く重み付きリザーバ。戻り値は (選んだ番号, 重みの和)。重み 0 の候補は飛ばす"""
    total, chosen = 0.0, -1
    for i, w in enumerate(weights):
        if w <= 0.0:
            continue
        total += w
        p = w / total
        if u < p:
            chosen = i
            u = u / p
        else:
            u = (u - p) / (1.0 - p)
        u = min(u, PICK_U_MAX)
    return chosen, total


def pick_stratified(weights, frame: int, phase: int, u0: float) -> tuple[int, float]:
    """層別化したくじ。戻り値は (選んだ番号, その光源の寄与に掛ける倍率)。当たりが無いフレームは (-1, 0)"""
    strata = min(max(len(weights), 1), STRATA_MAX)
    stratum = (frame + phase) % strata
    masked = [w if i % strata == stratum else 0.0 for i, w in enumerate(weights)]
    u = (u0 + R1_STEP * (frame // strata)) % 1.0
    chosen, total = pick_single_uniform(masked, u)
    return (chosen, strata * total / weights[chosen]) if chosen >= 0 else (-1, 0.0)


def pick_independent(weights, rng) -> tuple[int, float]:
    """層別化しないくじ (候補ごとに独立な乱数)"""
    total, chosen = 0.0, -1
    for i, w in enumerate(weights):
        total += w
        if rng.random() * total < w:
            chosen = i
    return chosen, total / weights[chosen]


def test_single_uniform_picks_in_proportion_to_weight():
    rng = np.random.default_rng(1)
    weights = [5.0, 1.0, 3.0, 0.5, 2.0, 8.0, 1.0, 1.0]
    counts = np.zeros(len(weights))
    n = 100_000
    for u in rng.random(n):
        counts[pick_single_uniform(weights, float(u))[0]] += 1
    expected = np.array(weights) / sum(weights)
    assert np.allclose(counts / n, expected, atol=0.006)


def test_single_uniform_skips_zero_weights_and_handles_one_candidate():
    assert pick_single_uniform([0.0, 2.0, 0.0], 0.999)[0] == 1
    assert pick_single_uniform([3.0], 0.0) == (0, 3.0)
    assert pick_single_uniform([], 0.5) == (-1, 0.0)


def test_stratified_estimate_is_unbiased():
    """1 周 (strata フレーム) x 乱数の全域で平均すると、残りの光源の寄与の和そのものになる"""
    rng = np.random.default_rng(2)
    weights = list(rng.random(13) ** 2 + 0.05)
    values = list(rng.random(13))  # 光源ごとの影の付いた寄与 / 重み (可視率にあたる)
    truth = sum(w * v for w, v in zip(weights, values))
    total, n = 0.0, 0
    for u0 in rng.random(3000):
        for frame in range(STRATA_MAX):
            chosen, scale = pick_stratified(weights, frame, 0, float(u0))
            total += weights[chosen] * values[chosen] * scale if chosen >= 0 else 0.0
            n += 1
    assert abs(total / n - truth) < 0.01 * truth


def test_few_lights_are_each_traced_once_per_cycle():
    """残りが層の数以下なら、くじではなく順番になる (どの光源も 1 周に 1 回)"""
    weights = [0.3, 2.0, 0.7, 1.1, 0.2]
    seen = [pick_stratified(weights, frame, 3, 0.37)[0] for frame in range(len(weights))]
    assert sorted(seen) == list(range(len(weights)))
    # 1 周の平均は真の和と一致する (ばらつきが無い)
    values = [1.0, 0.0, 1.0, 1.0, 0.0]
    est = [weights[c] * values[c] * s for c, s in (pick_stratified(weights, f, 3, 0.37) for f in range(len(weights)))]
    assert abs(np.mean(est) - sum(w * v for w, v in zip(weights, values))) < 1e-9


def _rms_error(count: int, window: int, trials: int, seed: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    err_ind, err_str = [], []
    for _ in range(trials):
        weights = list(rng.random(count) ** 2 + 0.05)
        values = list((rng.random(count) > 0.5).astype(float))
        total = sum(weights)
        truth = sum(w * v for w, v in zip(weights, values))
        u0, f0, phase = float(rng.random()), int(rng.integers(0, 1000)), int(rng.integers(0, 256))
        ind = st = 0.0
        for n in range(window):
            c, s = pick_independent(weights, rng)
            ind += weights[c] * values[c] * s
            c, s = pick_stratified(weights, f0 + n, phase, u0)
            st += weights[c] * values[c] * s if c >= 0 else 0.0
        err_ind.append((ind / window - truth) / total)
        err_str.append((st / window - truth) / total)
    return float(np.sqrt(np.mean(np.square(err_ind)))), float(np.sqrt(np.mean(np.square(err_str))))


def test_stratified_has_less_temporal_error_than_independent():
    """
    デノイズの履歴にあたる 16 フレームの平均で比べる。残りが少ないほど差が大きく、多くても悪くはならない
    (履歴の長さが 1 周の倍数でない時は半端な周の分が残るので、少ない時も 0 にはならない)
    """
    few_ind, few_str = _rms_error(count=6, window=16, trials=300, seed=3)
    assert few_str < 0.6 * few_ind
    aligned_ind, aligned_str = _rms_error(count=4, window=16, trials=300, seed=6)
    assert aligned_str < 0.01 * aligned_ind
    mid_ind, mid_str = _rms_error(count=12, window=16, trials=300, seed=4)
    assert mid_str < 0.85 * mid_ind
    many_ind, many_str = _rms_error(count=60, window=16, trials=300, seed=5)
    assert many_str < 1.1 * many_ind


def _reuse_vs_independent(count: int, cap: int, frames: int, seed: int) -> tuple[float, float, float]:
    """
    前のフレームで選んだ光源を引き継ぐ再利用 (時間方向だけのリザーバの合成。可視率を重みに掛けて保存し、1 / M で正規化する) と、
    毎フレーム独立に選ぶ方法を比べる。戻り値は (独立の誤差, 再利用の誤差, 再利用の偏り)。誤差は 16 フレームの平均の RMS / 重みの和
    """
    rng = np.random.default_rng(seed)
    weights = rng.random(count) ** 2 + 0.05
    visible = (rng.random(count) < 0.5).astype(float)
    total, truth = weights.sum(), (weights * visible).sum()
    picks = np.searchsorted(np.cumsum(weights) / total, rng.random(frames))
    independent = total * visible[picks]
    reuse = np.zeros(frames)
    kept, kept_w, kept_m = -1, 0.0, 0
    for f in range(frames):
        fresh = picks[f]
        a = total
        b = weights[kept] * kept_w * kept_m if kept >= 0 else 0.0
        chosen = kept if rng.random() * (a + b) < b else fresh
        m = 1 + kept_m
        w = (a + b) / (m * weights[chosen])
        reuse[f] = weights[chosen] * w * visible[chosen]
        kept, kept_w, kept_m = chosen, w * visible[chosen], min(m, cap)
    window = frames // 16 * 16
    rms = lambda x: float(np.sqrt(np.mean((x[:window].reshape(-1, 16).mean(1) - truth) ** 2)) / total)  # noqa: E731
    return rms(independent), rms(reuse), float((reuse.mean() - truth) / total)


def test_temporal_reuse_alone_is_unbiased_but_noisier_after_the_denoiser():
    """
    なぜ時間方向の再利用を入れていないかの記録。期待値は合うが、同じ光源が何フレームも続けて選ばれるので、
    後段のデノイズ (時間方向の平均) に入る独立な標本が減り、16 フレームの平均の誤差は独立に選ぶより大きくなる
    画素の間で標本を回す再利用 (ReSTIR の空間方向) と組にしないと得にならない
    """
    for count in (12, 60):
        results = [_reuse_vs_independent(count, cap=8, frames=3200, seed=s) for s in range(6)]
        independent = np.mean([r[0] for r in results])
        reuse = np.mean([r[1] for r in results])
        bias = np.mean([r[2] for r in results])
        assert abs(bias) < 0.03
        assert reuse > 1.3 * independent
