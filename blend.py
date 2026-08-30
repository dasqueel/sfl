"""Join projection sources by player and average them.

Sources spell players differently ("Marvin Harrison Jr." vs "Marvin
Harrison", "Ja'Marr" vs "JaMarr"), so matching is on a normalized name plus
position rather than raw strings.

Nothing is ever silently dropped. A player only one source knows about
still lands on the board, carrying that source's numbers and a marker
saying so — a player quietly vanishing mid-prep is a far worse failure than
a single-sourced estimate.
"""

import re
from collections import defaultdict

import scoring

# Trailing generational suffixes differ between sources and never disambiguate
# two active players at the same position.
SUFFIX = re.compile(r"\s+(jr|sr|ii|iii|iv|v)$")

# Nicknames one source uses and another doesn't. Keyed by normalized form.
ALIASES = {
    "hollywood brown": "marquise brown",
    "chig okonkwo": "chigoziem okonkwo",
    "gabe davis": "gabriel davis",
    "cam ward": "cameron ward",
    "josh palmer": "joshua palmer",
}


def normalize(name: str) -> str:
    """Reduce a display name to a comparable key."""
    text = name.lower().replace("'", "").replace(".", "").replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = SUFFIX.sub("", text).strip()
    return ALIASES.get(text, text)


def key(record: dict) -> tuple:
    return (normalize(record["name"]), record["pos"])


def _average(stat_lines: list) -> dict:
    """Mean of several stat lines, averaged per key over the sources that
    actually report it.

    Dividing by the total number of sources instead would halve any stat only
    one source publishes. ESPN reports no two-point conversions and no return
    touchdowns; treating those silences as zeros would quietly dock every
    return specialist half their upside. An absent key means "no opinion",
    not "zero".
    """
    names = {key for line in stat_lines for key in line}
    merged = {}
    for name in names:
        values = [line[name] or 0.0 for line in stat_lines if name in line]
        merged[name] = sum(values) / len(values) if values else 0.0
    return merged


def _pick(records: list, field: str, prefer: str = "sleeper"):
    """First non-empty value for a field, preferring one source."""
    ordered = sorted(records, key=lambda r: r["source"] != prefer)
    for record in ordered:
        if record.get(field):
            return record[field]
    return None


def blend(by_source: dict, scoring_key: str, games: int = None) -> dict:
    """Merge every source into one scored player list.

    Each source's stat line is first rescaled to a common season length,
    then averaged, then scored once. Scoring is linear, so averaging stats
    and averaging points agree — but averaging stats keeps the blended line
    inspectable.
    """
    grouped = defaultdict(list)
    for source_name, records in by_source.items():
        for record in records:
            grouped[key(record)].append(record)

    target = games if games is not None else scoring.NORMALIZE_GAMES
    players = []
    for (_, position), records in grouped.items():
        lines = [scoring.rescale(r["stats"], r["games"], target) for r in records]
        merged = _average(lines)
        contributors = sorted(r["source"] for r in records)

        players.append(
            {
                "name": _pick(records, "name") or records[0]["name"],
                "pos": position,
                "team": _pick(records, "team") or "FA",
                "pts": scoring.points(merged, scoring_key),
                "adp": _pick(records, "adp"),
                "injury": _pick(records, "injury") or "",
                "sources": contributors,
                "n_sources": len(contributors),
            }
        )

    players.sort(key=lambda p: -p["pts"])
    return {
        "players": players,
        "coverage": coverage(players, list(by_source)),
    }


def coverage(players: list, source_names: list) -> dict:
    """How many players each source contributed, and how many were matched."""
    counts = {name: 0 for name in source_names}
    for player in players:
        for name in player["sources"]:
            counts[name] = counts.get(name, 0) + 1

    blended = [p for p in players if p["n_sources"] > 1]
    single = [p for p in players if p["n_sources"] == 1]
    by_source = defaultdict(int)
    for player in single:
        by_source[player["sources"][0]] += 1

    return {
        "per_source": counts,
        "blended": len(blended),
        "single_source": dict(by_source),
        "total": len(players),
    }


def override_key(player: dict) -> str:
    """Stable identifier for a player, shared with the browser."""
    return f"{player['pos']}|{player['name']}"


def parse_overrides(raw) -> dict:
    """Validate hand-edited projections coming from the browser."""
    clean = {}
    for name, points in (raw or {}).items():
        try:
            value = float(points)
        except (TypeError, ValueError):
            raise ValueError(f"projection for {name} must be a number")
        if not 0 <= value <= 1000:
            raise ValueError(f"projection for {name} must be between 0 and 1000")
        clean[name] = value
    return clean


def apply_overrides(players: list, overrides: dict) -> list:
    """Replace blended projections with hand-entered ones.

    An override wins outright rather than joining the average — the point of
    typing a number is to assert it, not to be talked partway out of it.
    """
    if not overrides:
        return players

    for player in players:
        replacement = overrides.get(override_key(player))
        if replacement is not None:
            player["pts"] = replacement
            player["overridden"] = True

    players.sort(key=lambda p: -p["pts"])
    return players


def single_source_players(players: list, limit: int = None) -> list:
    """Players only one source knows, worst-case first by points.

    Worth eyeballing before a draft: a high-scoring single-source player is
    either a genuine edge or a name that failed to match.
    """
    lonely = [p for p in players if p["n_sources"] == 1]
    lonely.sort(key=lambda p: -p["pts"])
    return lonely[:limit] if limit else lonely
