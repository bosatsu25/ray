"""
パックの不変条件。生成物が表と一致しているか、Iris の読み方の制約を守っているか、ローダーごとの本文が意図どおりか

validate_shaders.py も同じ検査を回すが、ここでは項目ごとに分けて、落ちた時にどの決まりを破ったかが名前で分かるようにする
"""

from __future__ import annotations

import re

import pytest

import capabilities as caps
import check_slots
import gen_block_properties
import gen_includes
import gen_settings
import gen_wrappers
import include_deps
import iris_transforms
import loader_checks
import validate_shaders as vs
from lib import cpp

ENV = {e.name: e for e in caps.ENVS}


@pytest.mark.parametrize("module", [gen_includes, gen_wrappers, gen_settings, gen_block_properties, check_slots],
                         ids=lambda m: m.__name__)
def test_generated_files_are_current(module, shaders):
    assert module.check(shaders) == []


def test_include_declarations_resolve(shaders):
    assert include_deps.Tree(shaders).problems() == []


def test_settings_definitions(shaders):
    assert gen_settings.definition_problems(shaders) == []


def test_static_checks_pass():
    assert vs.static_checks(vs.parse_settings(), vs.parse_profiles()) == []


def test_properties_are_ascii(shaders):
    """Iris は .properties を ISO-8859-1 で読む。日本語はコメントでも前処理を壊す"""
    for path in sorted(shaders.glob("*.properties")):
        assert path.read_bytes().isascii(), path.name


def test_lang_files_have_the_same_keys(shaders):
    def keys(name: str) -> set[str]:
        text = (shaders / "lang" / name).read_text(encoding="utf-8")
        return {ln.split("=", 1)[0].strip() for ln in text.splitlines() if "=" in ln and not ln.lstrip().startswith("#")}

    assert keys("en_US.lang") == keys("ja_JP.lang")


def test_rendertargets_and_loader_macros(shaders):
    assert loader_checks.rendertargets_spacing(shaders) == []
    assert loader_checks.direct_loader_macros(shaders) == []


@pytest.mark.parametrize("env", caps.ENVS, ids=lambda e: e.name)
def test_properties_load_on_every_loader(env, shaders):
    """既定値の shaders.properties が、そのローダーの flag・SSBO の添字・image の数と形式に収まる"""
    options = vs.parse_settings()
    macros = {**vs.IRIS_MACROS, **env.macros, **loader_checks.settings_macros(options, {})}
    props = loader_checks.preprocessed_properties(shaders, macros)
    assert loader_checks.properties_problems(env, props) == []
    assert loader_checks.properties_colortex(env, "DEFAULT", props) == []


def _wrapper(shaders, name: str):
    return shaders / "world0" / name


def _source(shaders, name: str, env_name: str) -> str:
    req, opt = vs.parse_features()
    src, linemap = vs.build_source(_wrapper(shaders, name), {}, vs.parse_settings(), req + opt, ENV[env_name])
    assert len(src.splitlines()) == len(linemap)
    return src


def _active_code(src: str) -> str:
    stripped = include_deps.strip_comments(src).splitlines()
    ranges = cpp.active_ranges(stripped)
    return "\n".join(ln for i, ln in enumerate(stripped) if cpp.in_ranges(ranges, i))


# エンチャントの光沢を本体の中で足すプログラム (MC 26.3 の *_GLINT の描画が割り当てられる 4 つ)
GLINT_PROGRAMS = ["gbuffers_entities.fsh", "gbuffers_hand.fsh", "gbuffers_entities_translucent.fsh", "gbuffers_hand_water.fsh"]


@pytest.mark.parametrize("program", GLINT_PROGRAMS)
def test_inline_glint_is_sampled_on_26_3(program, shaders):
    assert "mc_sampleGlint()" in _active_code(_source(shaders, program, "latest"))


@pytest.mark.parametrize("program", GLINT_PROGRAMS)
@pytest.mark.parametrize("env_name", ["26.1", "mid", "1.7.6"])
def test_inline_glint_is_compiled_out_before_26_3(program, env_name, shaders):
    """Iris が関数を差し込まないローダーで呼ぶと、コンパイルが落ちてパックごと読み込めない"""
    assert "mc_sampleGlint" not in _active_code(_source(shaders, program, env_name))


@pytest.mark.parametrize("program", ["gbuffers_terrain.fsh", "gbuffers_water.fsh", "gbuffers_armor_glint.fsh"])
def test_inline_glint_is_not_sampled_outside_entity_programs(program, shaders):
    code = _active_code(_source(shaders, program, "latest"))
    assert "mc_sampleGlint()" not in code.replace("vec3 mc_sampleGlint();", "").replace("vec3 mc_sampleGlint() {", "")


def test_glint_stubs_are_injected_only_for_26_3(shaders):
    assert vs.INLINE_GLINT_DECLS[0] in _source(shaders, "final.fsh", "latest")
    assert vs.INLINE_GLINT_DECLS[0] not in _source(shaders, "final.fsh", "26.1")


def test_at_mid_block_is_rounded_before_integer_use(shaders):
    """
    Iris 26.3 は at_midBlock を正規化した形式 (SNORM) で持ち、127 倍して戻す。戻した値は整数からわずかにずれるので、
    発光レベルを切り捨てで整数にすると 1 小さくなる
    """
    text = (shaders / "lib" / "light" / "voxel.glsl").read_text(encoding="utf-8")
    assert re.search(r"int\(emissionLevel \+ 0\.5\)", text)
    for path in sorted((shaders / "program").rglob("*.vsh")):
        code = include_deps.strip_comments(path.read_text(encoding="utf-8"))
        assert not re.search(r"\bu?int\(\s*at_midBlock", code), path.name


@pytest.mark.parametrize("env", caps.ENVS, ids=lambda e: e.name)
def test_representative_programs_compile(env, shaders, glslang, tmp_path):
    """全プログラムは validate_shaders.py が回す。ここではローダーで本文が分かれるものだけを見る"""
    req, opt = vs.parse_features()
    options = vs.parse_settings()
    skipped = loader_checks.missing_programs(env)
    for name in [*GLINT_PROGRAMS, "gbuffers_particles.fsh", "shadow.gsh", "composite25.csh"]:
        if name.split(".")[0] in skipped:
            continue
        label, msgs, _ = vs.compile_one(glslang, tmp_path, _wrapper(shaders, name), "DEFAULT", {}, options, req + opt, env=env)
        assert msgs == [], label


@pytest.mark.parametrize("name", ["deferred30.fsh", "composite2.fsh", "composite25.csh", "final.fsh"])
def test_depth_reads_survive_the_reverse_z_transform(name, shaders, glslang):
    src = _source(shaders, name, "latest")
    text = iris_transforms.expand_macros(glslang, src, vs.STAGE_OF_EXT["." + name.rsplit(".", 1)[1]])
    assert text is not None
    # 検査が空振りしていないこと: これらのプログラムは深度を読む
    assert iris_transforms.DEPTH_NAME_RE.search(include_deps.strip_comments(text))
    assert iris_transforms.reverse_z_problems(name, text) == []


# 戻り値の型から始まる行だけを宣言・定義と数える (`return f(x);` は呼び出し)
_DECL_HEAD = r"^[ \t]*(?!return\b|else\b)(?:\w+[ \t]+)+"
_PROTOTYPE_RE = re.compile(_DECL_HEAD + r"(\w+)[ \t]*\([^(){};]*\)\s*;", re.M)


def undefined_prototypes(text: str) -> set[str]:
    """宣言だけで定義が無く、どこかから呼ばれている関数の名前"""
    missing = set()
    for name in set(_PROTOTYPE_RE.findall(text)):
        declared = len(re.findall(_DECL_HEAD + rf"{name}[ \t]*\(", text, re.M))
        called = len(re.findall(rf"\b{name}\s*\(", text)) > declared
        defined = re.search(_DECL_HEAD + rf"{name}[ \t]*\([^(){{}};]*\)\s*\{{", text, re.M)
        if called and not defined:
            missing.add(name)
    return missing


def test_undefined_prototypes_detection():
    assert undefined_prototypes("float f(float x);\nfloat g(float x) { return f(x); }\nvoid main() {}") == {"f"}
    assert undefined_prototypes("float f(float x);\nfloat f(float x) { return x; }\nvoid main() { float y = f(1.0); }") == set()
    # 宣言だけで呼ばれない関数は、どのドライバでもリンクできる
    assert undefined_prototypes("float f(float x);\nvoid main() {}") == set()
    assert undefined_prototypes("void main() { float y = 1.0;\n    return smoothstep(0.0, 1.0, y);\n}") == set()


def test_forward_declared_functions_are_defined(shaders, glslang):
    """
    宣言だけして定義を持たない関数を呼ぶ本文は、NVIDIA では呼ばれない関数の中なら通るが、Mesa ではリンクが失敗する
    (lib 同士の循環を前方宣言でほどいた時に、定義側の lib を本体が include し忘れると起きる)
    """
    options = vs.parse_settings()
    req, opt = vs.parse_features()
    for wrapper in sorted((shaders / "world0").iterdir()):
        if wrapper.suffix not in vs.STAGE_OF_EXT:
            continue
        # Iris が差し込む関数は Iris が定義するので、差し込みの無いローダーの本文で見る
        src, _ = vs.build_source(wrapper, {}, options, req + opt, ENV["26.1"])
        expanded = iris_transforms.expand_macros(glslang, src, vs.STAGE_OF_EXT[wrapper.suffix])
        assert expanded is not None, wrapper.name
        assert undefined_prototypes(include_deps.strip_comments(expanded)) == set(), wrapper.name


# 既定値と違う側の設定。既定値の検証 (validate_shaders.py) は通らない枝を、関係するプログラムだけコンパイルして確かめる
OPTION_VARIANTS = [
    ({"LIGHT_TRANSLUCENT_SHADOWS": True}, ["gbuffers_water.fsh"]),
    ({"LIGHT_PICK_STRATIFIED": False}, ["deferred1.csh"]),
    ({"LIGHT_LIGHTMAP_FILL": True}, ["deferred1.csh"]),
    ({"LIGHT_LIGHTMAP_FILL": True, "LIGHT_TRACE_COUNT": "1"}, ["deferred1.csh"]),
    ({"LIGHT_PICK_STRATIFIED": True, "LIGHT_TRACE_COUNT": "1"}, ["deferred1.csh"]),
    ({"MOD_BLOCK_LIGHTS": False}, ["shadow.vsh", "shadow_solid.vsh", "gbuffers_terrain.vsh"]),
    ({"LENS_PRESET": "0", "LENS_C_PROJECTION": "2"}, ["final.fsh", "composite20.fsh", "composite22.fsh", "composite25.csh"]),
    ({"LENS_PRESET": "19"}, ["final.fsh", "composite20.fsh", "composite22.fsh", "composite24.fsh"]),
    ({"LENS_PRESET": "20"}, ["final.fsh", "composite22.fsh", "composite24.fsh"]),
    ({"LENS_PRESET": "21"}, ["final.fsh", "composite22.fsh", "composite24.fsh"]),
]


@pytest.mark.parametrize(("overrides", "programs"), OPTION_VARIANTS, ids=lambda v: ",".join(f"{k}={x}" for k, x in v.items()) if isinstance(v, dict) else None)
def test_non_default_options_compile(overrides, programs, shaders, glslang, tmp_path):
    req, opt = vs.parse_features()
    options = vs.parse_settings()
    for env in (ENV["latest"], ENV["1.7.6"]):
        for name in programs:
            label, msgs, _ = vs.compile_one(glslang, tmp_path, _wrapper(shaders, name), "VARIANT", overrides, options, req + opt, env=env)
            assert msgs == [], label


def test_mod_light_ids_are_block_lights(shaders):
    """未登録の光るブロックの汎用光源 (8 色) が、ブロック光源の帯の中で連番になっている"""
    import id_tables

    mods = [light for light in id_tables.LIGHTS if light.label.startswith("LIGHT_MOD_FIRST")]
    assert [light.index for light in mods] == list(range(mods[0].index, mods[0].index + 8))
    assert mods[-1].index <= id_tables.LIGHT_BLOCK_LAST
    assert all(light.make.endswith("LT_OCC") and not light.blocks for light in mods)
    text = (shaders / "lib" / "ids" / "id_decode.glsl").read_text(encoding="utf-8")
    # シェーダーが返す番号は LIGHT_MOD_FIRST + 0..7
    assert "LIGHT_MOD_FIRST + k" in text and "? 7 : 1" in text


# Distant Horizons 対応 (DH_SUPPORT)。既定は OFF で、DH の入った環境 (dh) で ON にした時だけ本文が変わる
DH_ON = {"DH_SUPPORT": True}
DH_PROGRAMS = ["dh_terrain.vsh", "dh_terrain.fsh", "dh_water.vsh", "dh_water.fsh", "deferred30.fsh", "deferred20.fsh",
               "composite1_a.csh", "composite12.fsh", "composite19.fsh"]


def _source_with(shaders, world: str, name: str, env_name: str, overrides: dict) -> str:
    req, opt = vs.parse_features()
    return vs.build_source(shaders / world / name, overrides, vs.parse_settings(), req + opt, ENV[env_name])[0]


def test_dh_programs_compile_when_enabled(shaders, glslang, tmp_path):
    req, opt = vs.parse_features()
    options = vs.parse_settings()
    for name in DH_PROGRAMS:
        label, msgs, _ = vs.compile_one(glslang, tmp_path, _wrapper(shaders, name), "DH", DH_ON, options, req + opt, env=ENV["dh"])
        assert msgs == [], label


def test_dh_code_is_active_only_with_the_mod_and_the_setting(shaders):
    """DH の入っていない環境や設定 OFF では、DH の uniform を 1 つも宣言しない (これまでと同じ本文になる)"""
    assert "shadeDhTerrain(" in _active_code(_source_with(shaders, "world0", "deferred30.fsh", "dh", DH_ON))
    for env_name, overrides in (("dh", {}), ("latest", DH_ON), ("1.7.6", DH_ON)):
        code = _active_code(_source_with(shaders, "world0", "deferred30.fsh", env_name, overrides))
        assert "dhDepthTex" not in code and "shadeDhTerrain" not in code, env_name


def test_dh_is_overworld_only(shaders):
    """フォグの式が大気を前提にしているので、ネザーとエンドでは DH の画素を扱わない"""
    for world in ("world-1", "world1"):
        code = _active_code(_source_with(shaders, world, "deferred30.fsh", "dh", DH_ON))
        assert "dhDepthTex" not in code, world


def test_dh_programs_are_disabled_by_default(shaders):
    options = vs.parse_settings()
    for overrides, expected in (({}, True), (DH_ON, False)):
        macros = {**vs.IRIS_MACROS, **ENV["dh"].macros, **loader_checks.settings_macros(options, overrides)}
        disabled = vs.disabled_programs(loader_checks.preprocessed_properties(shaders, macros))
        assert ("world0/dh_terrain" in disabled) is expected
        assert ("world0/dh_water" in disabled) is expected
        # 空の無いディメンションでは設定に依らず止める
        assert "world-1/dh_terrain" in disabled and "world1/dh_water" in disabled


def test_dh_depth_reads_survive_the_reverse_z_transform(shaders, glslang):
    """DH の深度 (dhDepthTex0 / 1) も Iris が逆 Z から戻す対象。書き換えが効く読み方だけをしている"""
    for name in ("deferred30.fsh", "deferred20.fsh", "composite1_a.csh", "composite12.fsh", "composite19.fsh"):
        src = _source_with(shaders, "world0", name, "dh", DH_ON)
        text = iris_transforms.expand_macros(glslang, src, vs.STAGE_OF_EXT["." + name.rsplit(".", 1)[1]])
        assert text is not None, name
        assert "dhDepthTex" in include_deps.strip_comments(text), name
        assert iris_transforms.reverse_z_problems(name, text) == [], name
