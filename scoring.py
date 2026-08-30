"""Convert a counting-stat line into fantasy points.

Sources publish their own point totals, but each bakes in its own league
rules — RotoWire and ESPN differ on Puka Nacua by 44 points, most of which
is scoring settings rather than disagreement about Nacua. Averaging those
totals would blend two different rulebooks. So we discard every source's
arithmetic, keep their counting stats, and apply one formula here.

The side benefit is that changing scoring format genuinely re-scores the
board instead of swapping a precomputed column.
"""

from config import NORMALIZE_GAMES, RECEPTION_POINTS, SCORING_RULES

# Stat keys every adapter must speak. Missing means the player doesn't do
# it (a receiver has no pass attempts), which scores as zero.
STAT_KEYS = (
    "pass_yd", "pass_td", "pass_int", "pass_2pt",
    "rush_yd", "rush_td", "rush_2pt",
    "rec", "rec_yd", "rec_td", "rec_2pt",
    "fum_lost",
    "pr_td", "def_kr_td",
)


def points(stats: dict, scoring_key: str, rules: dict = None, reception: dict = None) -> float:
    """Fantasy points for one stat line under one scoring format."""
    rules = SCORING_RULES if rules is None else rules
    reception = RECEPTION_POINTS if reception is None else reception

    if scoring_key not in reception:
        raise ValueError(f"unknown scoring format: {scoring_key}")

    total = sum(weight * (stats.get(key) or 0.0) for key, weight in rules.items())
    return total + reception[scoring_key] * (stats.get("rec") or 0.0)


def rescale(stats: dict, games: float, target=NORMALIZE_GAMES) -> dict:
    """Rescale a stat line to a common season length.

    A no-op when target is None, which is the default — see NORMALIZE_GAMES
    in config.py for why. Kept because a future source may genuinely project
    a different season length, at which point this is the correction.
    """
    if target is None or not games or games <= 0:
        return dict(stats)
    factor = target / games
    return {key: (value or 0.0) * factor for key, value in stats.items()}
