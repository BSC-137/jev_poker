"""CLI: python -m jev_poker.sim --hands 10 --seed 1"""

from __future__ import annotations

import argparse

from jev_poker.sim.tournament import format_summary, play_tournament


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Play rock, shark, caller, and maniac for a fixed number of hands.")
    parser.add_argument("--hands", type=int, default=10, help="maximum hands to play (default: 10)")
    parser.add_argument("--seed", type=int, default=1, help="shuffle seed for the tournament (default: 1)")
    args = parser.parse_args(argv)
    if args.hands < 1:
        parser.error("--hands must be at least 1")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    result = play_tournament(args.hands, args.seed)
    print(format_summary(result["summary"]))


if __name__ == "__main__":
    main()
