"""
tools/ のスクリプトの単体テストと、パックの不変条件のテスト

- glslang が要るテストは `glslang` のフィクスチャを受け、見つからない時は skip する (RAY_GLSLANG / PATH / tools/glslang の順に探す)
- ゲームと GPU は要らない。ドライバでの compile + link は tools/gl_compile_check.py (CI では Mesa の llvmpipe) が受け持つ
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


def _find_glslang() -> str | None:
    env = os.environ.get("RAY_GLSLANG")
    if env and Path(env).exists():
        return env
    for name in ("glslangValidator", "glslang"):
        if p := shutil.which(name):
            return p
    fallback = ROOT / "tools" / "glslang" / "bin" / "glslang.exe"
    return str(fallback) if fallback.exists() else None


@pytest.fixture(scope="session")
def glslang() -> str:
    path = _find_glslang()
    if path is None:
        pytest.skip("glslang が見つからない (RAY_GLSLANG を設定する)")
    return path


@pytest.fixture(scope="session")
def shaders() -> Path:
    return ROOT / "shaders"
