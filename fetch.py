"""Load projections from every active source and blend them.

This module is deliberately thin: adapters live in sources.py, the scoring
rulebook in scoring.py, and the join in blend.py. What remains here is the
orchestration and the player-dict shape that value.py consumes.
"""

import blend
import sources
from config import ACTIVE_SOURCES


def load_players(season: int, league, refresh: bool = False, names=None) -> list:
    """Blended, scored players ready for valuation."""
    return load_board(season, league, refresh, names)["players"]


def load_board(season: int, league, refresh: bool = False, names=None) -> dict:
    """Blended players plus coverage diagnostics."""
    names = names or ACTIVE_SOURCES
    by_source = {
        name: sources.load(name, season, league.positions, refresh) for name in names
    }
    return blend.blend(by_source, league.scoring_key)


def group_by_position(players: list, positions) -> dict:
    """Bucket players by position, each bucket sorted best-first."""
    grouped = {position: [] for position in positions}
    for player in players:
        if player["pos"] in grouped:
            grouped[player["pos"]].append(player)
    for bucket in grouped.values():
        bucket.sort(key=lambda p: -p["pts"])
    return grouped
