"""capabilities.py: ローダーの表と、そこから決まる能力・機能"""

from __future__ import annotations

import re

import pytest

import capabilities as caps
import gen_capabilities
import loader_checks
from lib import cpp

# ローダー -> 持っている能力。表を書き換えた時に、意図しないローダーまで本文が変わるのを止める
EXPECTED_CAPS = {
    "latest": {"CAP_SHADOW_ENTITIES", "CAP_LIGHTNING_PROGRAM", "CAP_SPARKS_TRANSLUCENT", "CAP_CURRENT_PLAYER_ID", "CAP_INLINE_GLINT"},
    "dh": {"CAP_SHADOW_ENTITIES", "CAP_LIGHTNING_PROGRAM", "CAP_SPARKS_TRANSLUCENT", "CAP_CURRENT_PLAYER_ID", "CAP_INLINE_GLINT",
           "CAP_DISTANT_HORIZONS"},
    "26.1": {"CAP_SHADOW_ENTITIES", "CAP_LIGHTNING_PROGRAM", "CAP_SPARKS_TRANSLUCENT", "CAP_CURRENT_PLAYER_ID"},
    "mid": {"CAP_SHADOW_ENTITIES", "CAP_LIGHTNING_PROGRAM", "CAP_CURRENT_PLAYER_ID"},
    "1.7.6": set(),
}


def test_every_env_has_an_expectation():
    assert {e.name for e in caps.ENVS} == set(EXPECTED_CAPS)


@pytest.mark.parametrize("env", caps.ENVS, ids=lambda e: e.name)
def test_caps_per_env(env):
    have = {name for name, on in loader_checks.caps_of(env).items() if on}
    assert have == EXPECTED_CAPS[env.name]


def test_table_is_well_formed():
    assert gen_capabilities.table_problems() == []


def test_generated_files_are_current():
    assert gen_capabilities.check() == []


def test_undefined_macros_mean_no_capability():
    """マクロを 1 つも定義しないローダー (未知の古いローダー) では、どの能力も無い側に倒れる"""
    assert not any(cpp.eval_expr(c.detect, {}) for c in caps.CAPS)


def test_detection_uses_only_loader_macros():
    for c in caps.CAPS:
        idents = set(re.findall(r"[A-Za-z_]\w*", c.detect)) - {"defined"}
        assert idents <= set(caps.LOADER_MACROS), c.name


def test_latest_env_is_first_and_targets_26_3():
    latest = caps.ENVS[0]
    assert latest.name == "latest"
    # Iris の書式は 大 + 中 2 桁 + 小 2 桁
    assert latest.macros["MC_VERSION"] == "260300"
    assert latest.transforms == {caps.TRANSFORM_REVERSE_Z, caps.TRANSFORM_INLINE_GLINT}
    assert "IRIS_INLINE_GLINT" in latest.macros


def test_only_26_3_has_the_inline_glint_transform():
    for env in caps.ENVS:
        assert (caps.TRANSFORM_INLINE_GLINT in env.transforms) == ("IRIS_INLINE_GLINT" in env.macros), env.name


def test_env_limits_never_grow_for_older_loaders():
    """ENVS は新しい順。古いローダーほど資源の上限が小さい (か同じ)"""
    for newer, older in zip(caps.ENVS, caps.ENVS[1:]):
        assert older.colortex_count <= newer.colortex_count
        assert older.buffer_object_max_index <= newer.buffer_object_max_index
        assert older.features <= newer.features


def test_properties_expr_expands_to_settings_and_loader_macros():
    expr = gen_capabilities.properties_expr("FX_SHADOW_NON_TERRAIN")
    assert "CAP_" not in expr and "FX_" not in expr
    assert "IRIS_VERSION" in expr
