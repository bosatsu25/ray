"""
# bench_presets
品質プリセットごとのフレーム時間を、同じ場面に立ったまま順に測る (README の「重さの目安」と、プリセットの割り当ての見直しに使う)

プリセット (shaders.properties の profile.*) を設定の組に展開して ab_scene.py に渡すだけで、撮影・再読み込み・frame_ms の記録は
ab_scene.py が行う。結果は --out の report.md (プリセットごとの frame_ms と中央値、同じプリセットの 2 回の画像の差)

### 使い方
- uv run tools/bench_presets.py noon cave_torch --out bench_out            # 全プリセット
- uv run tools/bench_presets.py noon --profiles HIGH,ULTRA --fps 8          # 選んだプリセットだけ、fps を 8 回読む
- uv run tools/bench_presets.py --print                                     # 渡す --variant を表示するだけ (ゲームは要らない)

ゲームと Minescript の用意は tools/README.md の「ゲーム内で撮影する」。測るのは手元の GPU なので、結果には GPU・解像度・描画距離を添える
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_settings  # noqa: E402
from lib.paths import SHADERS  # noqa: E402

ROOT = Path(__file__).resolve().parent


def option_text(value: str | bool) -> str:
    """Ray.txt (Iris の設定ファイル) に書く値。ブールは true / false"""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def profile_variants(shaders: Path = SHADERS, only: list[str] | None = None) -> list[str]:
    """
    ### profile_variants
    プリセットを ab_scene.py の --variant の指定 (`名前=KEY=V,KEY=V`) に展開する。並びは shaders.properties の順 (軽い順)

    @param shaders - シェーダーのフォルダ
    @param only - このプリセットだけ (順番は shaders.properties のまま)。None は全部
    @returns --variant に渡す文字列の一覧
    """
    profiles = gen_settings.resolved_profiles(shaders)
    unknown = [n for n in (only or []) if n not in profiles]
    if unknown:
        raise SystemExit(f"プリセットが無い: {', '.join(unknown)} (候補: {', '.join(profiles)})")
    out = []
    for name, values in profiles.items():
        if only and name not in only:
            continue
        items = ",".join(f"{key}={option_text(value)}" for key, value in sorted(values.items()))
        if "," in name or "=" in name or any("," in option_text(v) for v in values.values()):
            raise SystemExit(f"--variant に書けない文字がある: {name}")
        out.append(f"{name}={items}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="品質プリセットごとのフレーム時間を測る")
    ap.add_argument("scenes", nargs="*", help="tools/scenes.json のシーン名")
    ap.add_argument("--profiles", help="測るプリセット (カンマ区切り。既定は全部)")
    ap.add_argument("--fps", type=int, default=4, help="プリセットごとに fps を読む回数 (1 回 1 秒)")
    ap.add_argument("--rounds", type=int, default=2, help="周の数 (2 周目は逆順。温度などの偏りを打ち消す)")
    ap.add_argument("--tag", default="bench")
    ap.add_argument("--out", type=Path, help="report.md の置き場 (既定 ./ab_<tag>)")
    ap.add_argument("--print", action="store_true", help="--variant の一覧を表示して終わる")
    args = ap.parse_args()

    variants = profile_variants(only=args.profiles.split(",") if args.profiles else None)
    if args.print:
        print("\n".join(variants))
        return 0
    if len(variants) < 2:
        raise SystemExit("プリセットは 2 つ以上 (ab_scene.py は版を比べる)")
    if not args.scenes:
        raise SystemExit("シーン名を指定する (tools/scenes.json)")
    cmd = [sys.executable, str(ROOT / "ab_scene.py"), *args.scenes, "--tag", args.tag, "--rounds", str(args.rounds), "--fps", str(args.fps)]
    for v in variants:
        cmd += ["--variant", v]
    if args.out:
        cmd += ["--out", str(args.out)]
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
