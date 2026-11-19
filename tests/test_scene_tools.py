"""bench_presets.py と scene_regress.py のうち、ゲームが要らない部分"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

import bench_presets
import gen_settings
import scene_regress
from scene_regress import Limits


def test_profile_variants_cover_every_profile_in_order(shaders):
    variants = bench_presets.profile_variants(shaders)
    names = [v.split("=", 1)[0] for v in variants]
    assert names == list(gen_settings.resolved_profiles(shaders))
    assert names[0] == "LOW" and names[-1] == "EXTREME"


def test_profile_variants_use_iris_option_values(shaders):
    high = next(v for v in bench_presets.profile_variants(shaders) if v.startswith("HIGH="))
    items = dict(item.split("=", 1) for item in high.split("=", 1)[1].split(","))
    # ブールは true / false、値はそのまま。ab_scene.py の parse_variant が読める形
    assert items["LIGHT_SHADOWS"] == "true" and items["POM"] == "false"
    assert items["LIGHT_TRACE_COUNT"] == "4"
    options = gen_settings.parse_settings(shaders)
    assert set(items) <= set(options)


def test_profile_variants_filter_and_unknown(shaders):
    assert [v.split("=", 1)[0] for v in bench_presets.profile_variants(shaders, ["ULTRA", "HIGH"])] == ["HIGH", "ULTRA"]
    with pytest.raises(SystemExit):
        bench_presets.profile_variants(shaders, ["NOPE"])


def test_judge_reports_each_exceeded_limit():
    ok = {"mean": 1.0, "p99": 9.0, "max": 40.0, "over": 2.0, "mean_color": 0.5}
    assert scene_regress.judge(ok, Limits()) == []
    bad = {**ok, "mean": 3.0, "mean_color": 4.0}
    assert len(scene_regress.judge(bad, Limits())) == 2
    assert len(scene_regress.judge(ok, Limits(mean=0.5, over=1.0, mean_color=0.1))) == 3


def _save(path, value: int, patch: int | None = None) -> None:
    img = np.full((32, 48, 3), value, dtype=np.uint8)
    if patch is not None:
        img[:16, :24] = patch
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img).save(path)


def test_compare_dirs(tmp_path):
    base, new = tmp_path / "base", tmp_path / "new"
    _save(base / "same.png", 100)
    _save(new / "same.png", 101)          # 差 1 は見えない
    _save(base / "changed.png", 100)
    _save(new / "changed.png", 100, 180)  # 画面の 1/4 が大きく変わった
    _save(base / "gone.png", 100)
    lines, failures = scene_regress.compare_dirs(base, new, Limits())
    assert len(lines) == 2 + 3
    assert not any(f.startswith("same:") for f in failures)
    assert any(f.startswith("changed:") for f in failures)
    assert any(f.startswith("gone:") and "画像が無い" in f for f in failures)
    # 名前を絞ると、そのシーンだけを見る
    assert scene_regress.compare_dirs(base, new, Limits(), ["same"])[1] == []
