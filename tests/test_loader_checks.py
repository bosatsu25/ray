"""loader_checks.py: ローダーごとの上限と、読み込みが失敗する記述の検出"""

from __future__ import annotations

import capabilities as caps
import loader_checks as lc

ENV = {e.name: e for e in caps.ENVS}


def test_missing_programs_follow_capabilities():
    assert lc.missing_programs(ENV["latest"]) == set()
    assert lc.missing_programs(ENV["mid"]) == set()
    assert lc.missing_programs(ENV["1.7.6"]) == {"shadow_entities", "shadow_block", "gbuffers_lightning"}


def test_unknown_feature_flag_is_reported_per_env():
    line = ["iris.features.required = COMPUTE_SHADERS TEXTURE_FILTERING"]
    assert lc.properties_problems(ENV["latest"], line) == []
    found = lc.properties_problems(ENV["1.7.6"], line)
    assert len(found) == 1 and "TEXTURE_FILTERING" in found[0]


def test_buffer_object_index_limit():
    line = ["bufferObject.9 = 64"]
    assert lc.properties_problems(ENV["latest"], line) == []
    assert len(lc.properties_problems(ENV["mid"], line)) == 1


def test_image_count_limit():
    lines = [f"image.img{i} = sampler{i} RGBA RGBA8 UNSIGNED_BYTE false false 1 1" for i in range(17)]
    found = lc.properties_problems(ENV["latest"], lines)
    assert len(found) == 1 and "17" in found[0]
    assert lc.properties_problems(ENV["latest"], lines[:16]) == []


def test_image_pixel_type_per_env():
    line = ["image.img = s RGB R11F_G11F_B10F UNSIGNED_INT_10F_11F_11F_REV false false 1 1"]
    assert lc.properties_problems(ENV["latest"], line) == []
    assert len(lc.properties_problems(ENV["1.7.6"], line)) == 1


def test_comments_and_blank_lines_are_skipped():
    assert lc.properties_problems(ENV["1.7.6"], ["", "# iris.features.required = NOPE", "   "]) == []


def _scan(env, src: str):
    lines = src.splitlines()
    return lc.program_scan(env, "DEFAULT", "world0/test.fsh", src, [("test.fsh", i + 1) for i in range(len(lines))])


def test_colortex_over_limit_is_reported_for_old_loaders():
    src = "uniform sampler2D colortex16;\n/* RENDERTARGETS: 0,16 */\nvoid main() { vec4 c = texture(colortex16, vec2(0.0)); }\n"
    assert _scan(ENV["latest"], src) == ([], [])
    uses, problems = _scan(ENV["1.7.6"], src)
    assert problems == []
    assert sorted((u.kind, u.index, u.where) for u in uses) == [("書く", 16, "test.fsh:2"), ("読む", 16, "test.fsh:3")]


def test_colortex_in_inactive_branch_is_ignored():
    src = "#ifdef NEVER\n/* RENDERTARGETS: 20 */\nvec4 c = texture(colortex20, vec2(0.0));\n#endif\n"
    assert _scan(ENV["1.7.6"], src) == ([], [])


def test_unknown_internal_format_is_reported():
    _, problems = _scan(ENV["1.7.6"], "const int colortex0Format = RGBA64F;\n")
    assert len(problems) == 1 and "RGBA64F" in problems[0]


def test_rendertargets_spacing(tmp_path):
    (tmp_path / "ok.fsh").write_text("/* RENDERTARGETS: 0,1,2 */\n", encoding="utf-8")
    (tmp_path / "bad.fsh").write_text("\n/* RENDERTARGETS: 0, 1 */\n", encoding="utf-8")
    found = lc.rendertargets_spacing(tmp_path)
    assert len(found) == 1 and found[0].startswith("bad.fsh:2:")


def test_direct_loader_macros(tmp_path):
    (tmp_path / "lib" / "settings").mkdir(parents=True)
    # 生成物の中は許す
    (tmp_path / "lib" / "settings" / "capabilities.glsl").write_text("#if defined MC_VERSION\n#endif\n", encoding="utf-8")
    (tmp_path / "a.fsh").write_text("// MC_VERSION はコメントなら良い\n#ifdef IRIS_INLINE_GLINT\n#endif\n", encoding="utf-8")
    (tmp_path / "shaders.properties").write_text(
        "# BEGIN GENERATED capabilities\n#if IRIS_VERSION >= 10800\n#endif\n# END GENERATED capabilities\n#if MC_VERSION >= 1\n#endif\n",
        encoding="latin-1")
    found = lc.direct_loader_macros(tmp_path)
    assert len(found) == 2
    assert any(p.startswith("a.fsh:2:") and "IRIS_INLINE_GLINT" in p for p in found)
    assert any(p.startswith("shaders.properties:5:") and "MC_VERSION" in p for p in found)
