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
