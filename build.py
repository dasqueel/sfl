#!/usr/bin/env python3
"""Build the auction cheat sheet.

    python3 build.py              # use cached projections
    python3 build.py --refresh    # pull fresh numbers (do this draft morning)
"""

import argparse
from pathlib import Path

import blend
import fetch
import rankings
import render
import value
from config import LEAGUE, SEASON

OUT = Path(__file__).parent / "out"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh", action="store_true", help="re-pull projections from Sleeper"
    )
    parser.add_argument("--season", type=int, default=SEASON)
    args = parser.parse_args()

    store = rankings.load(season=args.season)
    data = fetch.load_board(args.season, LEAGUE, refresh=args.refresh)
    players, coverage = data["players"], data["coverage"]
    players = blend.apply_overrides(players, store["projections"])
    by_position = fetch.group_by_position(players, LEAGUE.positions)
    board = value.build_board(by_position, LEAGUE)

    render.write_html(board, LEAGUE, args.season, OUT / "sheet.html", store=store)
    render.write_csv(board, OUT / "values.csv")

    print(f"{LEAGUE.describe()}  |  {args.season}")
    print(
        f"{len(players)} projected players -> {len(board['players'])} worth over $1"
        f", {len(board['fillers'])} at $1\n"
    )

    print("SOURCES")
    for name, count in coverage["per_source"].items():
        print(f"  {name:<10} {count:>4} players")
    print(f"  {'blended':<10} {coverage['blended']:>4} players in both")
    for name, count in coverage["single_source"].items():
        print(f"  {'only ' + name:<10} {count:>4} players")

    lonely = [p for p in board["players"] if p["n_sources"] < 2]
    if lonely:
        print(f"\n  ! {len(lonely)} priced players are single-sourced:")
        for player in lonely[:6]:
            print(f"      {player['name']} ({player['pos']}) ${player['value']:.0f}")
    print()

    print(f"{'POS':<5}{'STARTS':>7}{'REPL':>8}{'$POOL':>8}{'SHARE':>8}")
    for position in LEAGUE.positions:
        spend = board["spend"][position]
        share = spend["dollars"] / LEAGUE.total_money * 100
        print(
            f"{position:<5}{board['starters'][position]:>7}"
            f"{board['replacement'][position]:>8.1f}"
            f"{spend['dollars']:>8.0f}{share:>7.1f}%"
        )

    print(f"\n{'':<4}{'PLAYER':<24}{'POS':<5}{'MY$':>5}{'MKT$':>6}{'EDGE':>7}")
    for i, player in enumerate(board["players"][:15], 1):
        edge = round(player["value"]) - round(player["market"])
        print(
            f"{i:<4}{player['name']:<24}"
            f"{player['pos'] + str(player['pos_rank']):<5}"
            f"{player['value']:>5.0f}{player['market']:>6.0f}{edge:>+7.0f}"
        )

    bargains = sorted(board["players"], key=lambda p: -p["edge"])[:8]
    print("\nBIGGEST BARGAINS (worth more than the room will pay)")
    for player in bargains:
        edge = round(player["value"]) - round(player["market"])
        print(
            f"  {player['name']:<24}{player['pos'] + str(player['pos_rank']):<5}"
            f"my ${player['value']:>3.0f} vs mkt ${player['market']:>3.0f}  {edge:>+3.0f}"
        )

    traps = sorted(board["players"], key=lambda p: p["edge"])[:8]
    print("\nBIGGEST TRAPS (room will overpay — let them)")
    for player in traps:
        edge = round(player["value"]) - round(player["market"])
        print(
            f"  {player['name']:<24}{player['pos'] + str(player['pos_rank']):<5}"
            f"my ${player['value']:>3.0f} vs mkt ${player['market']:>3.0f}  {edge:>+3.0f}"
        )

    print(f"\nwrote {OUT / 'sheet.html'}")
    print(f"wrote {OUT / 'values.csv'}")


if __name__ == "__main__":
    main()
