"""Projection source adapters.

Each adapter returns the same shape — a list of records carrying counting
stats, never points — so the blend can average them and `scoring.py` can
apply one rulebook. Adding a source means adding a function here and a
name to ACTIVE_SOURCES; nothing downstream changes.

Both endpoints are public and unauthenticated. Both reject the default
urllib user-agent, so we present a browser one.
"""

import json
import urllib.request
from pathlib import Path

RAW_DIR = Path(__file__).parent / "data" / "raw"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}

# Sleeper writes 999.0 for "never drafted" rather than omitting the field.
ADP_SENTINEL = 900.0

_MEMO: dict = {}


def _get(url: str, cache_name: str, refresh: bool, headers: dict = None):
    """Fetch JSON, preferring the in-process memo, then disk, then network."""
    if not refresh and cache_name in _MEMO:
        return _MEMO[cache_name]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache = RAW_DIR / cache_name

    if cache.exists() and not refresh:
        data = json.loads(cache.read_text())
    else:
        request = urllib.request.Request(url, headers={**HEADERS, **(headers or {})})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.load(response)
        cache.write_text(json.dumps(data))

    _MEMO[cache_name] = data
    return data


# --------------------------------------------------------------------------
# Sleeper (serving RotoWire projections — every record carries
# company: "rotowire")
# --------------------------------------------------------------------------

SLEEPER_URL = "https://api.sleeper.com/projections/nfl"

SLEEPER_STATS = (
    "pass_yd", "pass_td", "pass_int", "pass_2pt",
    "rush_yd", "rush_td", "rush_2pt",
    "rec", "rec_yd", "rec_td", "rec_2pt",
    "fum_lost",
    "pr_td", "def_kr_td",
)


def sleeper(season: int, positions, refresh: bool = False) -> list:
    out = []
    for position in positions:
        url = (
            f"{SLEEPER_URL}/{season}"
            f"?season_type=regular&position[]={position}&order_by=pts_ppr"
        )
        for record in _get(url, f"{season}_sleeper_{position}.json", refresh):
            stats = record.get("stats") or {}
            info = record.get("player") or {}
            if not stats.get("pts_ppr"):
                continue

            adp = stats.get("adp_2qb")
            if adp is not None and adp >= ADP_SENTINEL:
                adp = None

            name = f"{info.get('first_name', '')} {info.get('last_name', '')}"
            out.append(
                {
                    "source": "sleeper",
                    "name": name.strip(),
                    "pos": position,
                    "team": record.get("team") or info.get("team") or "FA",
                    "games": stats.get("gp") or 0.0,
                    "stats": {k: stats.get(k) or 0.0 for k in SLEEPER_STATS},
                    "adp": adp,
                    "injury": info.get("injury_status") or "",
                }
            )
    return out


# --------------------------------------------------------------------------
# ESPN
# --------------------------------------------------------------------------

ESPN_URL = (
    "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/"
    "{season}/segments/0/leaguedefaults/3?view=kona_player_info"
)

# Verified against known stat lines: Allen 508.7 attempts / 3946.4 yards,
# Nacua 122.9 receptions / 1590.4 yards, Gibbs 283.1 carries.
ESPN_STAT_IDS = {
    "3": "pass_yd",
    "4": "pass_td",
    "20": "pass_int",
    "24": "rush_yd",
    "25": "rush_td",
    "42": "rec_yd",
    "43": "rec_td",
    "53": "rec",
    "72": "fum_lost",
}
ESPN_GAMES_ID = "210"
ESPN_POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE"}

# `limit` selects how many players come back; the stats ride along. Note
# that filterStatsForTopScoringPeriodIds wants an integer, not a list — an
# array there returns a 400 with a Java deserialization message.
ESPN_FILTER = '{"players":{"limit":600,"sortPercOwned":{"sortPriority":1,"sortAsc":false}}}'


def espn(season: int, positions, refresh: bool = False) -> list:
    payload = _get(
        ESPN_URL.format(season=season),
        f"{season}_espn.json",
        refresh,
        headers={"x-fantasy-filter": ESPN_FILTER},
    )
    entries = payload.get("players") if isinstance(payload, dict) else payload

    out = []
    for entry in entries or []:
        player = entry.get("player", entry)
        position = ESPN_POSITIONS.get(player.get("defaultPositionId"))
        if position not in positions:
            continue

        block = next(
            (
                s
                for s in (player.get("stats") or [])
                if s.get("seasonId") == season
                and s.get("statSourceId") == 1        # 1 = projected, 0 = actual
                and s.get("scoringPeriodId") == 0     # 0 = full season
                and (s.get("appliedTotal") or 0) > 0
            ),
            None,
        )
        if block is None:
            continue

        raw = block.get("stats") or {}
        out.append(
            {
                "source": "espn",
                "name": player.get("fullName", "").strip(),
                "pos": position,
                "team": "",  # ESPN gives a numeric team id; Sleeper's is clearer
                "games": raw.get(ESPN_GAMES_ID) or 0.0,
                "stats": {
                    name: raw.get(stat_id) or 0.0
                    for stat_id, name in ESPN_STAT_IDS.items()
                },
                "adp": None,
                "injury": "",
            }
        )
    return out


ADAPTERS = {"sleeper": sleeper, "espn": espn}


def load(name: str, season: int, positions, refresh: bool = False) -> list:
    if name not in ADAPTERS:
        raise ValueError(f"unknown source: {name}")
    return ADAPTERS[name](season, positions, refresh)
