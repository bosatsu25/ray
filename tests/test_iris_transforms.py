"""iris_transforms.py: Iris 26.2 / 26.3 の書き換えが効かない書き方の検出"""

from __future__ import annotations

import iris_transforms as it

DECL = "uniform sampler2D depthtex0;\nuniform sampler2D depthtex1;\nuniform sampler2D colortex0;\n"


def problems(body: str, decl: str = DECL) -> list[str]:
    return it.reverse_z_problems("world0/test.fsh", decl + body)


def test_direct_reads_are_fine():
    assert problems("""
        void main() {
            float a = texelFetch(depthtex0, ivec2(gl_FragCoord.xy), 0).r;
            float b = texture(depthtex1, vec2(0.5)).x;
            vec4 g = textureGather(depthtex0, vec2(0.5));
            float c = textureLod(depthtex0, vec2(0.5), 0.0).r;
        }
    """) == []


def test_size_queries_are_fine():
    assert problems("void main() { ivec2 s = textureSize(depthtex0, 0); }") == []


def test_user_function_with_sampler2d_parameter_is_fine():
    assert problems("""
        float readDepth(sampler2D tex, ivec2 p) { return texelFetch(tex, p, 0).r; }
        float outer(in sampler2D tex, ivec2 p) { return readDepth(tex, p); }
        void main() { float d = outer(depthtex1, ivec2(0)) + readDepth(colortex0, ivec2(0)); }
    """) == []


def test_multiline_call_is_fine():
    assert problems("void main() { float d = texelFetch(\n    depthtex0,\n    ivec2(0), 0).r; }") == []


def test_shadow_sampler_declaration_is_reported():
    found = problems("void main() {}", "uniform sampler2DShadow depthtex0;\n")
    assert len(found) == 1 and "sampler2DShadow" in found[0]


def test_function_without_definition_is_reported():
    found = problems("float readDepth(sampler2D tex);\nvoid main() { float d = readDepth(depthtex0); }")
    assert len(found) == 1 and "readDepth" in found[0]


def test_nested_parameter_misuse_is_reported():
    found = problems("""
        float inner(float x) { return x; }
        float outer(sampler2D tex) { return inner(tex); }
        void main() { float d = outer(depthtex0); }
    """)
    assert len(found) == 1 and "inner" in found[0] and "outer" in found[0]


def test_wrong_argument_position_is_reported():
    found = problems("void main() { vec4 c = texture(colortex0, vec2(0.0), depthtex0); }")
    assert len(found) == 1 and "第 3 引数" in found[0]


def test_color_samplers_are_not_tracked():
    assert problems("float f(float x) { return x; }\nvoid main() { float d = f(colortex0); }") == []


def test_comments_are_ignored():
    assert problems("// float d = broken(depthtex0);\n/* gl_FragDepth += 1.0; */\nvoid main() {}") == []


def test_frag_depth_plain_assignment_is_fine():
    assert problems("void main() { gl_FragDepth = 0.5; }") == []


def test_frag_depth_compound_assignment_is_reported():
    found = problems("void main() { gl_FragDepth = 0.5; gl_FragDepth += 0.1; }")
    assert len(found) == 1 and "gl_FragDepth" in found[0]


def test_frag_depth_read_is_reported():
    assert len(problems("void main() { gl_FragDepth = 0.5; float d = gl_FragDepth; }")) == 1


def test_reserved_identifiers(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "a.glsl").write_text(
        "float iris_value = 1.0;\n// iris_inComment は数えない\nvoid irisMainHelper() {}\nfloat fine_iris_ = 0.0;\n", encoding="utf-8")
    (tmp_path / "b.fsh").write_text("bool mc_hasGlint() { return true; }\nvoid main() { if (mc_hasGlint()) {} }\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("iris_ignored", encoding="utf-8")
    found = it.reserved_identifiers(tmp_path)
    assert len(found) == 3
    assert any("lib/a.glsl:1" in p and "iris_value" in p for p in found)
    assert any("lib/a.glsl:3" in p and "irisMainHelper" in p for p in found)
    assert any("b.fsh:1" in p and "mc_hasGlint" in p for p in found)


def test_pack_uses_no_reserved_identifiers(shaders):
    assert it.reserved_identifiers(shaders) == []
