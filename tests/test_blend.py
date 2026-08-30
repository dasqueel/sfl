"""Tests for scoring and multi-source blending.

The dangerous failure here is silent: a mistyped stat key or a name that
fails to match produces a plausible board that is quietly wrong. These
tests pin the arithmetic and the join.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import blend  # noqa: E402
import scoring  # noqa: E402
from config import RECEPTION_POINTS, SCORING_RULES  # noqa: E402


def record(source, name, pos, games=17.0, **stats):
    return {
        "source": source,
        "name": name,
        "pos": pos,
        "team": "AAA",
        "games": games,
        "stats": stats,
        "adp": None,
        "injury": "",
    }


class TestScoring:
    def test_receiving_line(self):
        line = {"rec": 100.0, "rec_yd": 1200.0, "rec_td": 10.0}
        # 100 catches + 120 yards-points + 60 TD-points
        assert scoring.points(line, "pts_ppr") == pytest.approx(280.0)
        assert scoring.points(line, "pts_half_ppr") == pytest.approx(230.0)
        assert scoring.points(line, "pts_std") == pytest.approx(180.0)

    def test_passing_line_uses_yahoo_interception_penalty(self):
        """Yahoo docks 1 for a pick; most projection sites assume 2."""
        line = {"pass_yd": 5000.0, "pass_td": 40.0, "pass_int": 10.0}
        assert scoring.points(line, "pts_ppr") == pytest.approx(200 + 160 - 10)

    def test_missing_keys_score_as_zero(self):
        assert scoring.points({}, "pts_ppr") == 0.0
        assert scoring.points({"rush_yd": 100.0}, "pts_ppr") == pytest.approx(10.0)

    def test_unknown_format_rejected(self):
        with pytest.raises(ValueError, match="unknown scoring"):
            scoring.points({}, "pts_bogus")

    def test_every_documented_stat_key_has_a_rule(self):
        """A key in STAT_KEYS with no rule would score as zero forever."""
        priced = set(SCORING_RULES) | {"rec"}
        assert set(scoring.STAT_KEYS) == priced

    def test_rescale_is_off_by_default(self):
        line = {"rush_yd": 1000.0}
        assert scoring.rescale(line, 18.0)["rush_yd"] == 1000.0

    def test_rescale_when_explicitly_targeted(self):
        line = {"rush_yd": 1800.0}
        assert scoring.rescale(line, 18.0, 17)["rush_yd"] == pytest.approx(1700.0)

    def test_rescale_survives_zero_games(self):
        assert scoring.rescale({"rush_yd": 5.0}, 0, 17)["rush_yd"] == 5.0


class TestNormalize:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("Ja'Marr Chase", "jamarr chase"),
            ("Marvin Harrison Jr.", "marvin harrison"),
            ("A.J. Brown", "aj brown"),
            ("Michael Pittman Jr", "michael pittman"),
            ("Amon-Ra St. Brown", "amon ra st brown"),
            ("  Puka   Nacua ", "puka nacua"),
            ("Kenneth Walker III", "kenneth walker"),
        ],
    )
    def test_normalizes_to_a_comparable_key(self, raw, expected):
        assert blend.normalize(raw) == expected

    def test_aliases_resolve_nicknames(self):
        assert blend.normalize("Hollywood Brown") == blend.normalize("Marquise Brown")

    def test_suffix_stripping_does_not_eat_real_names(self):
        """'V' as a suffix must not truncate a name that merely ends in it."""
        assert blend.normalize("Steve Smith") == "steve smith"
        assert blend.normalize("Jeudy") == "jeudy"


class TestBlend:
    def test_averages_matched_players(self):
        data = {
            "a": [record("a", "Puka Nacua", "WR", rec=100.0, rec_yd=1400.0)],
            "b": [record("b", "Puka Nacua", "WR", rec=120.0, rec_yd=1600.0)],
        }
        out = blend.blend(data, "pts_ppr")
        assert len(out["players"]) == 1
        player = out["players"][0]
        # mean line: 110 catches, 1500 yards -> 110 + 150
        assert player["pts"] == pytest.approx(260.0)
        assert player["n_sources"] == 2

    def test_matches_across_spelling_differences(self):
        data = {
            "a": [record("a", "Marvin Harrison Jr.", "WR", rec=80.0)],
            "b": [record("b", "Marvin Harrison", "WR", rec=90.0)],
        }
        out = blend.blend(data, "pts_ppr")
        assert len(out["players"]) == 1
        assert out["players"][0]["n_sources"] == 2

    def test_same_name_different_position_stays_separate(self):
        data = {
            "a": [
                record("a", "Josh Allen", "QB", pass_yd=4000.0),
                record("a", "Josh Allen", "TE", rec=20.0),
            ]
        }
        out = blend.blend(data, "pts_ppr")
        assert len(out["players"]) == 2

    def test_single_source_player_is_kept_and_flagged(self):
        data = {
            "a": [record("a", "Only Mine", "RB", rush_yd=1000.0)],
            "b": [record("b", "Puka Nacua", "WR", rec=100.0)],
        }
        out = blend.blend(data, "pts_ppr")
        lonely = next(p for p in out["players"] if p["name"] == "Only Mine")
        assert lonely["n_sources"] == 1
        assert lonely["sources"] == ["a"]
        assert lonely["pts"] == pytest.approx(100.0)

    def test_blending_is_linear_so_order_does_not_matter(self):
        one = {"a": [record("a", "X", "RB", rush_yd=900.0)],
               "b": [record("b", "X", "RB", rush_yd=1100.0)]}
        two = {"b": one["b"], "a": one["a"]}
        assert blend.blend(one, "pts_ppr")["players"][0]["pts"] == pytest.approx(
            blend.blend(two, "pts_ppr")["players"][0]["pts"]
        )

    def test_metadata_prefers_the_source_that_has_it(self):
        rich = record("sleeper", "Puka Nacua", "WR", rec=100.0)
        rich.update(adp=5.3, injury="Questionable", team="LAR")
        bare = record("espn", "Puka Nacua", "WR", rec=100.0)
        bare.update(team="")
        out = blend.blend({"sleeper": [rich], "espn": [bare]}, "pts_ppr")
        player = out["players"][0]
        assert player["adp"] == 5.3
        assert player["injury"] == "Questionable"
        assert player["team"] == "LAR"

    def test_players_come_back_sorted_by_points(self):
        data = {
            "a": [
                record("a", "Low", "WR", rec=10.0),
                record("a", "High", "WR", rec=100.0),
                record("a", "Mid", "WR", rec=50.0),
            ]
        }
        names = [p["name"] for p in blend.blend(data, "pts_ppr")["players"]]
        assert names == ["High", "Mid", "Low"]

    def test_coverage_counts_are_honest(self):
        data = {
            "a": [record("a", "Both", "WR", rec=50.0), record("a", "OnlyA", "WR", rec=10.0)],
            "b": [record("b", "Both", "WR", rec=60.0)],
        }
        cov = blend.blend(data, "pts_ppr")["coverage"]
        assert cov["total"] == 2
        assert cov["blended"] == 1
        assert cov["single_source"] == {"a": 1}
        assert cov["per_source"] == {"a": 2, "b": 1}

    def test_overrides_replace_the_blend_outright(self):
        data = {
            "a": [record("a", "Puka Nacua", "WR", rec=100.0)],
            "b": [record("b", "Puka Nacua", "WR", rec=120.0)],
        }
        players = blend.blend(data, "pts_ppr")["players"]
        assert players[0]["pts"] == pytest.approx(110.0)

        blend.apply_overrides(players, {"WR|Puka Nacua": 400.0})
        assert players[0]["pts"] == 400.0
        assert players[0]["overridden"] is True

    def test_overrides_leave_other_players_alone(self):
        data = {
            "a": [
                record("a", "Edited", "WR", rec=100.0),
                record("a", "Untouched", "WR", rec=90.0),
            ]
        }
        players = blend.blend(data, "pts_ppr")["players"]
        blend.apply_overrides(players, {"WR|Edited": 10.0})
        untouched = next(p for p in players if p["name"] == "Untouched")
        assert untouched["pts"] == pytest.approx(90.0)
        assert "overridden" not in untouched

    def test_overrides_resort_the_board(self):
        data = {
            "a": [
                record("a", "WasFirst", "WR", rec=100.0),
                record("a", "WasSecond", "WR", rec=50.0),
            ]
        }
        players = blend.blend(data, "pts_ppr")["players"]
        blend.apply_overrides(players, {"WR|WasSecond": 500.0})
        assert players[0]["name"] == "WasSecond"

    def test_empty_overrides_are_a_no_op(self):
        data = {"a": [record("a", "X", "WR", rec=100.0)]}
        players = blend.blend(data, "pts_ppr")["players"]
        assert blend.apply_overrides(players, None)[0]["pts"] == pytest.approx(100.0)
        assert blend.apply_overrides(players, {})[0]["pts"] == pytest.approx(100.0)

    @pytest.mark.parametrize(
        "bad,fragment",
        [
            ({"WR|X": "abc"}, "must be a number"),
            ({"WR|X": -5}, "between 0 and 1000"),
            ({"WR|X": 5000}, "between 0 and 1000"),
            ({"WR|X": None}, "must be a number"),
        ],
    )
    def test_bad_overrides_rejected(self, bad, fragment):
        with pytest.raises(ValueError, match=fragment):
            blend.parse_overrides(bad)

    def test_good_overrides_coerce_to_float(self):
        assert blend.parse_overrides({"WR|X": "250.5"}) == {"WR|X": 250.5}

    def test_single_source_report_is_worst_first(self):
        data = {
            "a": [record("a", "Big", "WR", rec=100.0), record("a", "Small", "WR", rec=5.0)],
            "b": [],
        }
        out = blend.blend(data, "pts_ppr")
        lonely = blend.single_source_players(out["players"])
        assert [p["name"] for p in lonely] == ["Big", "Small"]
