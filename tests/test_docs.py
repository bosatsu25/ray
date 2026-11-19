"""文書の食い違い: 日本語と英語の README、ローダーの表とツールの説明"""

from __future__ import annotations

import re
from pathlib import Path

import capabilities as caps

ROOT = Path(__file__).resolve().parent.parent
CHECKBOX_RE = re.compile(r"^(\s*)- \[([ x])\] ")


def _roadmap(name: str, heading: str) -> list[tuple[int, bool]]:
    """ロードマップの項目の (字下げ, 済みか) の並び"""
    text = (ROOT / name).read_text(encoding="utf-8")
    section = text.split(f"## {heading}\n", 1)[1].split("\n## ", 1)[0]
    return [(len(m.group(1)), m.group(2) == "x") for m in map(CHECKBOX_RE.match, section.splitlines()) if m]


def test_roadmap_matches_between_languages():
    ja = _roadmap("README.md", "ロードマップ")
    en = _roadmap("README.en.md", "Roadmap")
    assert ja and ja == en


def test_roadmap_parent_is_open_while_a_child_is_open():
    items = _roadmap("README.md", "ロードマップ")
    for i, (indent, done) in enumerate(items):
        children = []
        for child_indent, child_done in items[i + 1:]:
            if child_indent <= indent:
                break
            children.append(child_done)
        if children and done:
            assert all(children), f"{i + 1} 番目の項目は子が残っているのに済みになっている"


def test_supported_version_tables_have_the_same_rows():
    def rows(name: str) -> list[str]:
        text = (ROOT / name).read_text(encoding="utf-8")
        return [ln.split("|")[1].strip() + " / " + ln.split("|")[2].strip() for ln in text.splitlines()
                if re.match(r"^\| (Iris|Oculus) ", ln)]

    ja, en = rows("README.md"), rows("README.en.md")
    assert len(ja) == len(en) >= 5
    assert any("26.3" in r for r in ja) and any("26.3" in r for r in en)


def test_every_env_is_documented():
    for name in ("tools/README.md", "docs/architecture.md", "AGENTS.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for env in caps.ENVS:
            assert re.search(rf"(?<![\w.]){re.escape(env.name)}(?![\w.])", text), f"{name} に {env.name} が無い"


# README の品質プリセットの表は手書きなので、プリセットの定義 (shaders.properties の profile.*) からずれやすい
# 値がそのまま表に出る行だけを、定義から作った期待値と比べる (行の順番は日本語と英語で同じ)
PRESET_HEADINGS = {"README.md": "品質プリセット", "README.en.md": "Quality Presets"}
RES = {"1": "Full", "2": "1/2", "4": "1/4"}


def _preset_table(name: str) -> list[list[str]]:
    text = (ROOT / name).read_text(encoding="utf-8")
    section = text.split(f"## {PRESET_HEADINGS[name]}\n", 1)[1]
    rows = []
    for line in section.splitlines():
        if line.startswith("|"):
            rows.append([c.strip().replace("フル", "Full").replace("色付き", "colored") for c in line.strip("|").split("|")])
        elif rows:
            break
    # 見出しと区切りの行、項目名の列を除く
    return [r[1:] for r in rows[2:]]


def _expected_rows() -> dict[int, list[str]]:
    import gen_settings

    shaders = ROOT / "shaders"
    options = gen_settings.parse_settings(shaders)
    profiles = gen_settings.resolved_profiles(shaders)
    lang = dict(ln.split("=", 1) for ln in (shaders / "lang" / "ja_JP.lang").read_text(encoding="utf-8").splitlines() if "=" in ln)

    def column(fn) -> list[str]:
        out = []
        for values in profiles.values():
            def get(key: str):
                v = values.get(key, options[key].default)
                return v if isinstance(v, bool) else str(v)
            out.append(fn(get))
        return out

    on = lambda b: "ON" if b else "OFF"  # noqa: E731
    return {
        1: column(lambda g: lang[f"value.VOXEL_VOLUME.{g('VOXEL_VOLUME')}"]),
        2: column(lambda g: on(g("LIGHT_SHADOWS"))),
        3: column(lambda g: g("LIGHT_TRACE_COUNT") if g("LIGHT_SHADOWS") else "-"),
        4: column(lambda g: RES[g("LIGHT_TRACE_RES")] if g("LIGHT_SHADOWS") else "-"),
        5: column(lambda g: f"{on(g('LIGHT_ENTITY_OCCLUSION'))} / {on(g('LIGHT_PLAYER_OCCLUSION'))}"),
        6: column(lambda g: on(g("HAND_LIGHT_RAYS") and g("HAND_LIGHT_SS_SHADOWS"))),
        7: column(lambda g: on(g("ENTITY_LIGHTS"))),
        8: column(lambda g: f"{g('shadowMapResolution')} / {float(g('shadowDistance')):g}"),
        9: column(lambda g: f"{'PCSS' if g('SHADOW_FILTER') == '2' else 'PCF'} ({g('SHADOW_SAMPLES')})"),
        14: column(lambda g: on(g("POM"))),
        17: column(lambda g: f"ON ({'colored, ' if g('VL_COLORED_SHADOWS') else ''}{RES[g('VL_RES')]})" if g("VL") else "OFF"),
        18: column(lambda g: f"ON ({lang['value.DOF_QUALITY.' + g('DOF_QUALITY')].split()[0]})" if g("DOF") else "OFF"),
        19: column(lambda g: on(g("MOTION_BLUR"))),
        20: column(lambda g: f"{on(g('BLOOM'))} / {on(g('LENS_FLARE'))}"),
    }


def test_quality_preset_table_matches_profiles():
    expected = _expected_rows()
    for name in PRESET_HEADINGS:
        table = _preset_table(name)
        assert len(table) == 22, name
        for index, row in expected.items():
            assert table[index] == row, f"{name} の品質プリセットの表の {index + 1} 行目"


def test_numbered_lists_match_the_settings():
    """ルック・LUT・レンズの番号の表は、設定の値の数と同じ行数"""
    lang = (ROOT / "shaders" / "lang" / "ja_JP.lang").read_text(encoding="utf-8")
    for name in ("README.md", "README.en.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for setting in ("LOOK_PRESET", "LOOK_LUT", "LENS_PRESET"):
            count = len(re.findall(rf"^value\.{setting}\.\d+=", lang, re.M))
            runs = [len(m.group(0).splitlines()) for m in re.finditer(r"(?:^\| \d+ \|.*\n)+", text, re.M)]
            assert count in runs, f"{name}: {setting} ({count} 個) の表が無い"


def test_readme_credits_the_original_pack_first():
    """
    LICENSE の 1.4.a: Fork は README の最初の段落で元のパックを「Based on Ray by kuwacom」と示し、公式の配布先へリンクする
    2.4: 公式の配布物として見せない
    """
    for name, unofficial in (("README.md", "非公式"), ("README.en.md", "unofficial")):
        paragraphs = [p for p in (ROOT / name).read_text(encoding="utf-8").split("\n\n") if not p.startswith("# ")]
        first = paragraphs[0]
        # リンクの記法を外した見た目の文で比べる
        assert "Based on Ray by kuwacom" in re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", first), name
        assert "https://github.com/kuwacom/ray" in first, name
        assert unofficial in first, name
