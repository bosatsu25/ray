"""
# scene_regress
定点シーンを撮って、基準の画像と比べる。見た目が変わっていないはずの変更 (リファクタ・ローダーの対応) の後に回す

- save: 今の見た目を基準として保存する (<基準のフォルダ>/<シーン>.png)。基準はワールドと設定に依るのでリポジトリには入れない
- check: 撮り直して基準と比べ、しきい値を超えたシーンがあれば終了コード 1。report.md に差の表を書く

撮影は run_scene.py、差は pixdiff.py と同じ数え方。雲・水・葉は時間で動くので、同じ設定でも差は 0 にならない。
しきい値は「同じ設定で 2 回撮った差」(揺れ) より少し上に置く。揺れは `ab_scene.py` の「揺れ」の行か、save を 2 回して check で測る

### 使い方
- uv run tools/scene_regress.py save --all                       # 基準を撮る (既定の置き場は <game>/screenshots/ray_baseline)
- uv run tools/scene_regress.py check --all                      # 撮り直して比べる
- uv run tools/scene_regress.py check noon --max-mean 1.5 --max-over 3
- uv run tools/scene_regress.py compare a_dir b_dir              # 撮影済みのフォルダ同士を比べる (ゲームは要らない)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pixdiff import VISIBLE_STEP, diff_stats  # noqa: E402

ROOT = Path(__file__).resolve().parent
TAG = "regress"


@dataclass(frozen=True)
class Limits:
    """シーン 1 つの差の上限。mean は画素の差 (0-255) の平均、over は差が VISIBLE_STEP を超える画素の割合 (%)"""

    mean: float = 2.0
    over: float = 5.0
    mean_color: float = 2.0


def judge(stats: dict[str, float], limits: Limits) -> list[str]:
    """
    ### judge
    差の統計 (pixdiff.diff_stats) のうち、上限を超えた項目の説明を返す。空なら合格

    @param stats - diff_stats の戻り値
    @param limits - 上限
    @returns 超えた項目ごとの 1 行
    """
    over = []
    if stats["mean"] > limits.mean:
        over.append(f"平均の差 {stats['mean']:.2f} > {limits.mean:g}")
    if stats["over"] > limits.over:
        over.append(f">{VISIBLE_STEP}/255 の画素 {stats['over']:.2f}% > {limits.over:g}%")
    if stats["mean_color"] > limits.mean_color:
        over.append(f"平均色の差 {stats['mean_color']:.2f} > {limits.mean_color:g}")
    return over


def compare_dirs(base: Path, new: Path, limits: Limits, names: list[str] | None = None) -> tuple[list[str], list[str]]:
    """
    ### compare_dirs
    2 つのフォルダの同じ名前の PNG を比べる

    @param base - 基準のフォルダ
    @param new - 比べるフォルダ
    @param limits - 上限
    @param names - 比べるシーン名 (拡張子なし)。None は基準にある全部
    @returns (report.md の行, 失敗の説明)。基準にあって new に無い画像も失敗に数える
    """
    wanted = names or sorted(p.stem for p in base.glob("*.png"))
    lines = [f"| シーン | mean | p99 | max | >{VISIBLE_STEP}/255 % | 平均色 | 判定 |", "|---|---|---|---|---|---|---|"]
    failures = []
    for name in wanted:
        a, b = base / f"{name}.png", new / f"{name}.png"
        missing = [p.parent.name for p in (a, b) if not p.exists()]
        if missing:
            failures.append(f"{name}: 画像が無い ({', '.join(missing)})")
            lines.append(f"| {name} | - | - | - | - | - | 画像なし |")
            continue
        stats = diff_stats(a, b)
        problems = judge(stats, limits)
        failures += [f"{name}: {p}" for p in problems]
        lines.append(f"| {name} | {stats['mean']:.2f} | {stats['p99']:.1f} | {stats['max']:.0f} | {stats['over']:.2f} | "
                     f"{stats['mean_color']:.2f} | {'NG' if problems else 'OK'} |")
    return lines, failures


def scene_names(args: argparse.Namespace) -> list[str]:
    conf = json.loads((ROOT / "scenes.json").read_text(encoding="utf-8"))
    names = list(conf["scenes"]) if args.all else args.scenes
    if not names:
        raise SystemExit(f"シーン名か --all を指定する。候補: {', '.join(conf['scenes'])}")
    return names


def capture(names: list[str], dest: Path) -> None:
    """run_scene.py で撮って、<game>/screenshots/<tag>_<シーン>.png を dest/<シーン>.png に移す"""
    game = Path(os.environ["RAY_MC_DIR"])
    code = subprocess.call([sys.executable, str(ROOT / "run_scene.py"), *names, "--reload", "--tag", TAG])
    if code:
        raise SystemExit(f"撮影に失敗した (run_scene.py の終了コード {code})")
    dest.mkdir(parents=True, exist_ok=True)
    for name in names:
        shot = game / "screenshots" / f"{TAG}_{name}.png"
        if not shot.exists():
            raise SystemExit(f"撮影が無い: {shot}")
        shutil.move(str(shot), dest / f"{name}.png")


def main() -> int:
    ap = argparse.ArgumentParser(description="定点シーンを撮って基準の画像と比べる")
    ap.add_argument("action", choices=["save", "check", "compare"])
    ap.add_argument("scenes", nargs="*", help="シーン名 (compare は 基準のフォルダ 比べるフォルダ)")
    ap.add_argument("--all", action="store_true", help="scenes.json の全シーン")
    ap.add_argument("--baseline", type=Path, help="基準の置き場 (既定 <game>/screenshots/ray_baseline)")
    ap.add_argument("--out", type=Path, help="check で撮った画像と report.md の置き場 (既定 <game>/screenshots/ray_check)")
    ap.add_argument("--max-mean", type=float, default=Limits.mean)
    ap.add_argument("--max-over", type=float, default=Limits.over)
    ap.add_argument("--max-mean-color", type=float, default=Limits.mean_color)
    args = ap.parse_args()
    limits = Limits(args.max_mean, args.max_over, args.max_mean_color)

    if args.action == "compare":
        if len(args.scenes) != 2:
            raise SystemExit("compare は 基準のフォルダ 比べるフォルダ")
        lines, failures = compare_dirs(Path(args.scenes[0]), Path(args.scenes[1]), limits)
    else:
        if not os.environ.get("RAY_MC_DIR"):
            raise SystemExit("RAY_MC_DIR を指定する")
        shots = Path(os.environ["RAY_MC_DIR"]) / "screenshots"
        baseline = args.baseline or shots / "ray_baseline"
        names = scene_names(args)
        if args.action == "save":
            capture(names, baseline)
            print(f"基準を保存した: {baseline} ({len(names)} シーン)")
            return 0
        out = args.out or shots / "ray_check"
        capture(names, out)
        lines, failures = compare_dirs(baseline, out, limits, names)
        (out / "report.md").write_text("\n".join(lines + [""] + failures) + "\n", encoding="utf-8")
    print("\n".join(lines))
    for f in failures:
        print(f"NG {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
