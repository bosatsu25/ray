"""lib/cpp.py: #if の式の評価と、前処理の後に残る行の区間"""

from __future__ import annotations

import pytest

from lib import cpp


@pytest.mark.parametrize(("expr", "macros", "expected"), [
    ("defined A", {"A": ""}, True),
    ("defined A", {}, False),
    ("defined(A) && !defined B", {"A": "1"}, True),
    ("!defined A || defined B", {"A": "1"}, False),
    # 未定義の名前は 0、値なしの定義は 1
    ("A", {}, False),
    ("A", {"A": ""}, True),
    ("A >= 260100", {"A": "260300"}, True),
    ("A >= 260100", {"A": "12101"}, False),
    ("defined A && A >= 10800", {}, False),
    ("A == 0x10", {"A": "16"}, True),
    ("A > 1u", {"A": "2"}, True),
    # 値はマクロを展開してから評価する
    ("A == 3", {"A": "B + 1", "B": "2"}, True),
    ("A // 行末のコメント", {"A": "1"}, True),
])
def test_eval_expr(expr, macros, expected):
    assert cpp.eval_expr(expr, macros) is expected


def test_eval_expr_rejects_runaway_expansion():
    with pytest.raises(cpp.ExprError):
        cpp.eval_expr("A", {"A": "A + 1"})


def _active(lines: list[str], macros: dict[str, str] | None = None) -> list[int]:
    ranges = cpp.active_ranges(lines, macros)
    return [i for i in range(len(lines)) if cpp.in_ranges(ranges, i)]


def test_active_ranges_if_else():
    lines = ["a", "#ifdef X", "b", "#else", "c", "#endif", "d"]
    assert _active(lines) == [0, 4, 6]
    assert _active(lines, {"X": ""}) == [0, 2, 6]


def test_active_ranges_elif_takes_first_true_branch():
    lines = ["#if V >= 3", "a", "#elif V >= 2", "b", "#elif V >= 1", "c", "#else", "d", "#endif"]
    assert _active(lines, {"V": "2"}) == [3]
    assert _active(lines, {"V": "0"}) == [7]


def test_active_ranges_define_and_undef_apply_in_order():
    lines = ["#define X 1", "#ifdef X", "a", "#endif", "#undef X", "#ifdef X", "b", "#endif"]
    assert _active(lines) == [2]


def test_active_ranges_inactive_define_is_ignored():
    lines = ["#if 0", "#define X 1", "#endif", "#ifdef X", "a", "#endif", "b"]
    assert _active(lines) == [6]


def test_active_ranges_nested():
    lines = ["#ifdef A", "#ifdef B", "ab", "#else", "a", "#endif", "#endif"]
    assert _active(lines, {"A": ""}) == [4]
    assert _active(lines, {"A": "", "B": ""}) == [2]
    assert _active(lines, {"B": ""}) == []
