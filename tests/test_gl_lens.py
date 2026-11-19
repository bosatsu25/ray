"""
レンズの再投影 (lib/post/lens_optics.glsl) を、実際の GLSL として動かして確かめる

tools/pass_preview.py で試験用の全画面パスを 1 回描き、出力の画素ごとに「元画像の位置」と「そこから出力へ戻した位置」を読む
OpenGL のコンテキストが要るので、DISPLAY が無ければ skip する。GPU の無い Linux では Mesa のソフトウェア描画で動く:
    MESA_GL_VERSION_OVERRIDE=4.6COMPAT MESA_GLSL_VERSION_OVERRIDE=460 xvfb-run -a uv run pytest -q tests/test_gl_lens.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

import gen_includes

ROOT = Path(__file__).resolve().parent.parent
WIDTH, HEIGHT = 320, 180
ASPECT = WIDTH / HEIGHT

BODY = """
in vec2 texcoord;
/* RENDERTARGETS: 0 */
layout(location = 0) out vec4 outColor;
void main() {
    float rho;
    vec2 src = lensProjectUv(texcoord, rho);
    outColor = vec4(src, lensForwardUv(src));
}
"""


def _run(tmp_path: Path, glslang: str, fov: float, settings: dict[str, str]) -> np.ndarray:
    """試験用のパスを描いて (高さ, 幅, 4) の配列を返す。rg = 元画像の uv、ba = 出力へ戻した uv。行 0 が画面の下 (v = 0 の側)"""
    if not os.environ.get("DISPLAY"):
        pytest.skip("DISPLAY が無い (xvfb-run で回す)")
    order: list[str] = []
    gen_includes.Includes().order("lib/post/lens_optics.glsl", [set()], order)
    source = "#version 460 compatibility\n" + "".join(f'#include "/{rel}"\n' for rel in order) + BODY
    shader = tmp_path / "lens_roundtrip.fsh"
    shader.write_text(source, encoding="utf-8")
    cmd = [sys.executable, str(ROOT / "tools" / "pass_preview.py"), str(shader), "--size", f"{WIDTH}x{HEIGHT}", "--fov", str(fov),
           "--out", str(tmp_path / "out")]
    for key, value in settings.items():
        cmd += ["--set", f"{key}={value}"]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env={**os.environ, "RAY_GLSLANG": glslang}, cwd=ROOT)
    if "コンテキスト" in proc.stdout + proc.stderr or "glfw" in proc.stderr.lower():
        pytest.skip("OpenGL 4.6 のコンテキストが作れない: " + (proc.stderr.strip().splitlines() or ["?"])[-1])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # 保存された配列は画像の向き (行 0 が上) なので、uv の向きに戻す
    return np.load(tmp_path / "out_colortex0.npy")[::-1]


def _uv() -> tuple[np.ndarray, np.ndarray]:
    u = (np.arange(WIDTH) + 0.5) / WIDTH
    v = (np.arange(HEIGHT) + 0.5) / HEIGHT
    return np.meshgrid(u, v)


PANINI = {"LENS_PRESET": "0", "LENS_C_PROJECTION": "2", "LENS_C_PANINI": "1.0"}


def test_panini_round_trip(tmp_path, glslang):
    out = _run(tmp_path, glslang, 110.0, PANINI)
    u, v = _uv()
    assert np.abs(out[..., 2] - u).max() < 2e-4
    assert np.abs(out[..., 3] - v).max() < 2e-4


def test_panini_reads_inside_the_source_and_reaches_its_corners(tmp_path, glslang):
    out = _run(tmp_path, glslang, 110.0, PANINI)
    src = out[..., :2]
    assert src.min() >= 0.0 and src.max() <= 1.0
    # 出力の四隅の画素は元画像の四隅の近くを読む (隅が黒くならず、描いた範囲を捨てない)
    half_texel = np.array([0.5 / WIDTH, 0.5 / HEIGHT])
    assert np.all(src[0, 0] < 4 * half_texel) and np.all(src[-1, -1] > 1.0 - 4 * half_texel)
    # 上下の端は、中央ほど元画像の内側を読む
    assert src[0, WIDTH // 2, 1] > src[0, 0, 1] + 0.05


def test_panini_keeps_vertical_lines_straight(tmp_path, glslang):
    """出力の同じ列は元画像でも同じ列 (元画像の x が出力の y に依らない)"""
    out = _run(tmp_path, glslang, 110.0, PANINI)
    assert np.ptp(out[..., 0], axis=0).max() < 1e-4


def test_panini_compresses_the_edges(tmp_path, glslang):
    """直線写像の端の横への引き伸ばしを詰める: 出力の 1 画素が読む元画像の幅は、端のほうが中央より広い"""
    out = _run(tmp_path, glslang, 110.0, PANINI)
    row = out[HEIGHT // 2, :, 0]
    step = np.diff(row)
    assert np.all(step > 0.0)
    assert step[0] > 2.0 * step[WIDTH // 2]


def test_panini_strength_zero_point_25_is_closer_to_rectilinear(tmp_path, glslang):
    weak = _run(tmp_path, glslang, 110.0, {**PANINI, "LENS_C_PANINI": "0.25"})
    strong = _run(tmp_path, glslang, 110.0, PANINI)
    u, _ = _uv()
    assert np.abs(weak[..., 0] - u).max() < np.abs(strong[..., 0] - u).max()


@pytest.mark.parametrize("settings", [
    {"LENS_PRESET": "0", "LENS_C_PROJECTION": "1", "LENS_C_FISHEYE_K": "0.5"},   # 魚眼 (等立体角)
    {"LENS_PRESET": "0", "LENS_C_PROJECTION": "1", "LENS_C_FISHEYE_K": "-0.5"},  # 魚眼 (立体射影)
    {"LENS_PRESET": "0", "LENS_C_PROJECTION": "0", "LENS_C_DISTORTION": "0.1"},  # 樽型の歪曲
    {"LENS_PRESET": "11"},                                                        # Flektogon (陣笠型)
], ids=["fisheye-equisolid", "fisheye-stereographic", "barrel", "flektogon"])
def test_existing_projections_round_trip(settings, tmp_path, glslang):
    """パニーニを足した時に、前からある写像の往復を壊していないこと"""
    out = _run(tmp_path, glslang, 100.0, settings)
    u, v = _uv()
    assert np.abs(out[..., 2] - u).max() < 5e-4
    assert np.abs(out[..., 3] - v).max() < 5e-4


def test_panini_preset_round_trip(tmp_path, glslang):
    """レンズのプリセット 19 (広角) がパニーニ投影になっている"""
    out = _run(tmp_path, glslang, 100.0, {"LENS_PRESET": "19"})
    u, v = _uv()
    assert np.abs(out[..., 2] - u).max() < 2e-4 and np.abs(out[..., 3] - v).max() < 2e-4
    # 直線写像のままなら元画像の位置は出力と同じ。左右の端の手前で差が出る
    assert np.abs(out[..., 0] - u).max() > 0.02
