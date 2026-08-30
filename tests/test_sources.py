"""Integration checks against real cached projection data.

These skip when the cache is cold rather than reaching for the network, so
the suite stays fast and offline-safe. Populate it with:
    python3 build.py --refresh
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blend  # noqa: E402
import scoring  # noqa: E402
import sources  # noqa: E402
from config import LEAGUE, SEASON  # noqa: E402

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"


def cached(name):
    path = RAW / name
    if not path.exists():
        pytest.skip(f"no cached {name}; run build.py --refresh")
    return json.loads(path.read_text())


# The rules RotoWire's own published pts_ppr is computed under, derived by
# fitting their totals. Deliberately NOT this league's rules: this league
# docks 1 for a fumble and scores return touchdowns, neither of which their
# number reflects. Pinning the reference here means the test keeps checking
# our stat *mapping* even as league scoring changes.
ROTOWIRE_RULES = {
    "pass_yd": 0.04, "pass_td": 4.0, "pass_int": -1.0, "pass_2pt": 2.0,
    "rush_yd": 0.10, "rush_td": 6.0, "rush_2pt": 2.0,
    "rec_yd": 0.10, "rec_td": 6.0, "rec_2pt": 2.0,
    "fum_lost": -2.0,
}
FULL_PPR = {"pts_ppr": 1.0}


class TestScoringMatchesTheSource:
    def test_reproduces_rotowire_own_ppr_total(self):
        """Our stat mapping must reproduce the source's own arithmetic.

        If this drifts, a stat key is wrong — which would silently corrupt
        every dollar on the board rather than raising anything.
        """
        checked = worst = 0
        for position in LEAGUE.positions:
            for record in cached(f"{SEASON}_sleeper_{position}.json"):
                stats = record.get("stats") or {}
                theirs = stats.get("pts_ppr")
                if not theirs:
                    continue
                line = {k: stats.get(k) or 0.0 for k in sources.SLEEPER_STATS}
                mine = scoring.points(line, "pts_ppr", ROTOWIRE_RULES, FULL_PPR)
                worst = max(worst, abs(mine - theirs))
                checked += 1

        assert checked > 400, f"only {checked} players checked"
        assert worst < 5.0, f"scoring drifted from source by {worst:.2f} points"

    def test_league_rules_deliberately_differ_from_the_source(self):
        """Guards the two settings this league does not share with RotoWire."""
        from config import SCORING_RULES

        assert SCORING_RULES["fum_lost"] == -1.0
        assert SCORING_RULES["pr_td"] == 6.0
        assert SCORING_RULES["def_kr_td"] == 6.0

    def test_return_touchdowns_are_upside_the_source_total_misses(self):
        """A return man must score higher under our rules than RotoWire's."""
        returners = []
        for position in LEAGUE.positions:
            for record in cached(f"{SEASON}_sleeper_{position}.json"):
                stats = record.get("stats") or {}
                if stats.get("pr_td") or stats.get("def_kr_td"):
                    line = {k: stats.get(k) or 0.0 for k in sources.SLEEPER_STATS}
                    returners.append(
                        scoring.points(line, "pts_ppr")
                        - scoring.points(line, "pts_ppr", ROTOWIRE_RULES, FULL_PPR)
                    )
        assert returners, "no return specialists in the cached data"
        assert all(gain > 0 for gain in returners)


class TestAdapters:
    def test_both_sources_return_the_documented_shape(self):
        cached(f"{SEASON}_sleeper_QB.json")
        cached(f"{SEASON}_espn.json")
        for name in ("sleeper", "espn"):
            records = sources.load(name, SEASON, LEAGUE.positions)
            assert records, f"{name} returned nothing"
            for record in records[:50]:
                assert record["source"] == name
                assert record["pos"] in LEAGUE.positions
                assert record["name"]
                assert isinstance(record["stats"], dict)

    def test_espn_stat_ids_land_on_known_players(self):
        """A wrong stat id yields zeros, not an error — so assert magnitudes."""
        cached(f"{SEASON}_espn.json")
        by_key = {
            blend.key(r): r for r in sources.load("espn", SEASON, LEAGUE.positions)
        }
        allen = by_key.get(("josh allen", "QB"))
        if allen is None:
            pytest.skip("Josh Allen absent from cached ESPN payload")
        assert allen["stats"]["pass_yd"] > 3000
        assert 15 < allen["stats"]["pass_td"] < 60
        assert allen["stats"]["rush_yd"] > 100

    def test_adapters_disagree_but_stay_in_the_same_universe(self):
        """Catches a units error — yards read as attempts, say."""
        cached(f"{SEASON}_espn.json")
        left = {blend.key(r): r for r in sources.load("sleeper", SEASON, LEAGUE.positions)}
        right = {blend.key(r): r for r in sources.load("espn", SEASON, LEAGUE.positions)}
        shared = set(left) & set(right)
        assert len(shared) > 300, f"only {len(shared)} players matched across sources"

        ratios = []
        for k in shared:
            a = scoring.points(left[k]["stats"], "pts_ppr")
            b = scoring.points(right[k]["stats"], "pts_ppr")
            if a > 100 and b > 100:
                ratios.append(b / a)
        ratios.sort()
        median = ratios[len(ratios) // 2]
        assert 0.7 < median < 1.5, f"sources differ by a suspicious factor: {median:.2f}"

    def test_unknown_source_rejected(self):
        with pytest.raises(ValueError, match="unknown source"):
            sources.load("nonsense", SEASON, LEAGUE.positions)


class TestBlendedBoardCoverage:
    def test_every_player_worth_real_money_is_multi_sourced(self):
        """Single-sourced players in the money would be unvetted picks."""
        import fetch
        import value

        cached(f"{SEASON}_espn.json")
        data = fetch.load_board(SEASON, LEAGUE)
        board = value.build_board(
            fetch.group_by_position(data["players"], LEAGUE.positions), LEAGUE
        )
        lonely = [p for p in board["players"] if p["n_sources"] < 2 and p["value"] >= 3]
        assert not lonely, f"single-sourced players priced over $3: {[p['name'] for p in lonely]}"
