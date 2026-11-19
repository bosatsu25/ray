"""
Iris が本文に掛ける書き換え (tools/capabilities.py の TRANSFORM_*) が効かない書き方を探す静的検査。validate_shaders.py から呼ぶ

ゲームを起動しないと分からない壊れ方を、書き換えの規則から先に見つけるためのもの。規則の出典は Iris のソース
(26.3 ブランチの pipeline/transform/transformer/DepthTransformer.java と TransformPatcher.java)

- 逆 Z (TRANSFORM_REVERSE_Z): Iris は深度のサンプラー (DEPTH_SAMPLERS) を名前で探し、組み込みのテクスチャ関数の第 1 引数に
  直接書かれた読み出しを `1.0 - 値` に変える。自作の関数に渡した時は、その引数が sampler2D の定義を複製して中の読み出しを変える。
  それ以外の使い方 (複製できない関数に渡す、sampler2D 以外の型で宣言する) では書き換えが掛からず、逆 Z の生の値を読む
- gl_FragDepth: 単純な代入 (`gl_FragDepth = 式`) だけが反転される。複合代入と読み出しは反転されない
- 予約された名前: `iris_`・`irisMain`・`moj_import` で始まる識別子は読み込みが失敗する。mc_hasGlint / mc_sampleGlint は
  Iris が定義を差し込むので、パックが定義すると二重定義になる
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import include_deps

# DepthTransformer.DEPTH_SAMPLERS (vx* は別の MOD 用なので見ない)
DEPTH_SAMPLERS = frozenset({"depthtex0", "depthtex1", "depthtex2", "gdepthtex", "dhDepthTex", "dhDepthTex0", "dhDepthTex1"})
DEPTH_NAME_RE = re.compile(r"\b(" + "|".join(sorted(DEPTH_SAMPLERS)) + r")\b")

# DepthTransformer.TEXTURE_READ_FUNCTIONS のうち GLSL 4.60 の core にあるもの (パックは #version 460 で書く)
TEXTURE_READ_FUNCTIONS = frozenset({
    "texture", "textureProj", "textureLod", "textureOffset", "textureProjOffset", "textureLodOffset", "textureProjLod",
    "textureProjLodOffset", "textureGrad", "textureGradOffset", "textureProjGrad", "textureProjGradOffset", "texelFetch",
    "texelFetchOffset", "textureGather", "textureGatherOffset", "textureGatherOffsets",
})
# 値を読まない組み込み関数 (反転は要らない)
TEXTURE_QUERY_FUNCTIONS = frozenset({"textureSize", "textureQueryLevels", "textureQueryLod"})

# TransformPatcher の internalPrefixes
RESERVED_PREFIXES = ("iris_", "irisMain", "moj_import")
# GlintTransformer が全ステージに定義を差し込む関数
INJECTED_FUNCTIONS = ("mc_hasGlint", "mc_sampleGlint")

GLSL_SUFFIXES = {".glsl", ".vsh", ".fsh", ".gsh", ".csh", ".tcs", ".tes"}
IDENT_RE = re.compile(r"[A-Za-z_]\w*")
FUNC_DEF_RE = re.compile(r"\b([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s*\(([^()]*)\)\s*\{")
UNIFORM_DECL_RE = re.compile(r"\buniform\s+(\w+)\s+(\w+)\s*;")
FRAG_DEPTH_RE = re.compile(r"\bgl_FragDepth\b")
FRAG_DEPTH_ASSIGN_RE = re.compile(r"\bgl_FragDepth\s*=(?!=)")
NOT_FUNCTIONS = frozenset({"if", "for", "while", "switch", "return", "layout"})


@dataclass(frozen=True)
class Function:
    """自作の関数の定義 1 つ。params は (型, 名前)、body は本文の文字の範囲"""

    name: str
    params: tuple[tuple[str, str], ...]
    body: tuple[int, int]

    def sampler2d_at(self, index: int) -> bool:
        return index < len(self.params) and self.params[index][0] == "sampler2D"


def _functions(text: str) -> list[Function]:
    funcs = []
    for m in FUNC_DEF_RE.finditer(text):
        if m.group(1) in NOT_FUNCTIONS or m.group(2) in NOT_FUNCTIONS:
            continue
        params = []
        for raw in m.group(3).split(","):
            toks = IDENT_RE.findall(raw)
            # `in sampler2D tex` の修飾子は型の前に付く。void だけの引数リストは引数なし
            if len(toks) >= 2:
                params.append((toks[-2], toks[-1]))
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        funcs.append(Function(m.group(2), tuple(params), (m.end(), i)))
    return funcs


def _enclosing_call(text: str, pos: int) -> tuple[str, int] | None:
    """
    pos の識別子を引数に持つ呼び出しの (関数名, 引数の番号)。呼び出しの引数でなければ None
    """
    depth = commas = 0
    i = pos - 1
    while i >= 0:
        c = text[i]
        if c in ")]":
            depth += 1
        elif c in "([":
            if depth == 0:
                if c == "[":
                    return None
                m = re.search(r"([A-Za-z_]\w*)\s*$", text[max(0, i - 128):i])
                return (m.group(1), commas) if m and m.group(1) not in NOT_FUNCTIONS else None
            depth -= 1
        elif c == "," and depth == 0:
            commas += 1
        elif c in ";{}" and depth == 0:
            return None
        i -= 1
    return None


def _is_bare_argument(text: str, start: int, end: int) -> bool:
    """識別子が引数の全体か (`f(depthtex0)` は真、`f(depthtex0 == x)` は偽)"""
    before = text[:start].rstrip()[-1:]
    after = text[end:].lstrip()[:1]
    return before in "(," and after in "),"


def reverse_z_problems(program: str, expanded: str) -> list[str]:
    """
    ### reverse_z_problems
    マクロを展開した本文 (glslang -E の出力) から、Iris の逆 Z の書き換えが掛からない深度の使い方を探す

    @param program - 表示に使うプログラムの名前
    @param expanded - マクロを展開した 1 ステージ分の本文
    @returns 問題の一覧
    """
    text = include_deps.strip_comments(expanded)
    problems: list[str] = []
    for m in UNIFORM_DECL_RE.finditer(text):
        if m.group(2) in DEPTH_SAMPLERS and m.group(1) != "sampler2D":
            problems.append(f"{program}: {m.group(2)} を {m.group(1)} で宣言している (Iris は sampler2D の読み出しだけを逆 Z から戻す)")

    funcs = _functions(text)
    by_name: dict[str, list[Function]] = {}
    for f in funcs:
        by_name.setdefault(f.name, []).append(f)

    # (関数, 引数の番号) -> 深度のサンプラーが渡される引数。呼び出しを辿って増やす (Iris の specializeDepthFunctions と同じ向き)
    depth_params: set[tuple[Function, int]] = set()
    seen: set[tuple[str, int, int]] = set()

    def visit(name: str, lo: int, hi: int, label: str) -> None:
        for m in re.finditer(rf"\b{re.escape(name)}\b", text[lo:hi]):
            start, end = lo + m.start(), lo + m.end()
            key = (name, start, end)
            if key in seen:
                continue
            seen.add(key)
            line_start = text.rfind("\n", 0, start) + 1
            head = text[line_start:start]
            # 宣言 (uniform と、関数の引数の `sampler2D 名前`) は使用ではない
            if re.search(r"\b\w*sampler\w*\s+$", head):
                continue
            call = _enclosing_call(text, start)
            if call is None or not _is_bare_argument(text, start, end):
                problems.append(f"{program}: {label} を関数の引数以外で使っている (Iris の逆 Z の書き換えが掛からない)")
                continue
            callee, index = call
            if callee in TEXTURE_QUERY_FUNCTIONS:
                continue
            if callee in TEXTURE_READ_FUNCTIONS:
                if index != 0:
                    problems.append(f"{program}: {label} を {callee} の第 {index + 1} 引数に渡している")
                continue
            targets = [f for f in by_name.get(callee, []) if f.sampler2d_at(index)]
            if not targets:
                problems.append(f"{program}: {label} を {callee} の第 {index + 1} 引数に渡しているが、その引数が sampler2D の定義が無い "
                                "(Iris が関数を複製できず、中の読み出しが逆 Z のままになる)")
                continue
            for f in targets:
                if (f, index) not in depth_params:
                    depth_params.add((f, index))
                    visit(f.params[index][1], f.body[0], f.body[1], f"{label} (関数 {f.name} の引数 {f.params[index][1]})")

    for name in sorted(DEPTH_SAMPLERS):
        visit(name, 0, len(text), name)

    uses = len(FRAG_DEPTH_RE.findall(text))
    if uses != len(FRAG_DEPTH_ASSIGN_RE.findall(text)):
        problems.append(f"{program}: gl_FragDepth を単純な代入以外で使っている (Iris は `gl_FragDepth = 式` だけを逆 Z に直す)")
    return problems


def expand_macros(glslang: str, src: str, stage: str) -> str | None:
    """glslang -E でマクロを展開した本文。失敗したら None (コンパイルの検査が同じ誤りを報告する)"""
    with tempfile.TemporaryDirectory(prefix="ray_expand_") as tmp:
        path = Path(tmp) / f"source.{stage}"
        path.write_text(src, encoding="utf-8")
        proc = subprocess.run([glslang, "-E", "-S", stage, str(path)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return proc.stdout if proc.returncode == 0 else None


def reserved_identifiers(shaders: Path) -> list[str]:
    """
    ### reserved_identifiers
    Iris が内部で使う名前をパックが使っている箇所 (読み込みが失敗する)。コメントは除く

    @param shaders - シェーダーのフォルダ
    @returns 問題の一覧
    """
    problems = []
    injected = re.compile(r"\b\w+\s+(" + "|".join(INJECTED_FUNCTIONS) + r")\s*\([^()]*\)\s*\{")
    for path in sorted(shaders.rglob("*")):
        if path.suffix not in GLSL_SUFFIXES:
            continue
        rel = path.relative_to(shaders).as_posix()
        code = include_deps.strip_comments(path.read_text(encoding="utf-8"))
        for i, line in enumerate(code.splitlines(), 1):
            for ident in IDENT_RE.findall(line):
                if ident.startswith(RESERVED_PREFIXES):
                    problems.append(f"{rel}:{i}: {ident} は Iris の内部用の名前で始まる (読み込みが失敗する)")
            if m := injected.search(line):
                problems.append(f"{rel}:{i}: {m.group(1)} は Iris が定義を差し込む関数 (パックが定義すると二重定義になる)")
    return problems
