#!/usr/bin/env python3
"""클래스 매핑만 다시 만들 때 사용하는 호환용 보조 명령."""

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import fastcrawl


def parse_args():
    parser = argparse.ArgumentParser(
        description="선수 JSON은 유지하고 공식 클래스 매핑 파일만 다시 생성합니다."
    )
    parser.add_argument("--players", type=Path, default=fastcrawl.DEFAULT_OUTPUT)
    parser.add_argument(
        "--output",
        type=Path,
        default=fastcrawl.DEFAULT_CLASS_MAP_OUTPUT,
    )
    parser.add_argument("--min-ovr", type=int, default=100)
    parser.add_argument("--delay", type=float, default=0.02)
    return parser.parse_args()


def main():
    args = parse_args()
    with args.players.open("r", encoding="utf-8") as f:
        players = json.load(f)
    if not isinstance(players, list):
        raise RuntimeError("선수 JSON 최상위 값은 배열이어야 합니다.")

    class_names, overlaps, class_count = fastcrawl.collect_player_class_names(
        players,
        args.min_ovr,
        max(0, args.delay),
    )
    fastcrawl.write_class_map(
        class_names,
        class_count,
        len(players),
        overlaps,
        args.output,
    )
    print(
        f"완료: {len(class_names)}/{len(players)}명 매핑, "
        f"공식 중복 필터 {len(overlaps)}명, 출력 {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
