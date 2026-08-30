"""Tests for the valuation math.

Wrong replacement levels don't crash — they produce plausible-looking
prices that are quietly wrong, which is the worst kind of bug for a
cheat sheet. These tests pin the invariants that would catch that.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import ASSUMED_KEEPER_VALUE, League  # noqa: E402
import value  # noqa: E402


def make_players(position, count, top, step):
    """Synthetic players on a linear decline, best first."""
    return [
        {
            "name": f"{position}{i + 1}",
            "pos": position,
            "team": "AAA",
            "pts": top - step * i,
            "adp": float(i + 1),
            "injury": "",
        }
        for i in range(count)
    ]


@pytest.fixture
def by_position():
    # Curves chosen so QBs clearly out-score flex options in the middle
    # rounds, which is what makes superflex behave like superflex.
    return {
        "QB": make_players("QB", 80, 360, 5),
        "RB": make_players("RB", 80, 330, 6),
        "WR": make_players("WR", 120, 310, 3),
        "TE": make_players("TE", 60, 250, 7),
    }


@pytest.fixture
def league():
    return League()


@pytest.fixture
def redraft():
    """The same league with keepers switched off.

    Keeper inflation scales every price by a constant, which would drown
    out the invariants below without saying anything about whether the
    underlying valuation is right. The keeper arithmetic gets its own
    class further down.
    """
    return League(keepers_per_team=0)


def all_money_accounted(board, league):
    """Every dollar in the league, wherever it ended up.

    Priced players, $1 for each roster spot they don't fill, and whatever
    the keepers cost their owners. This has to come to exactly the league
    total whether or not keepers are in play.
    """
    keepers = board.get("keepers", [])
    inflation = board.get("inflation") or {}
    slots_kept = inflation.get("known", 0) + inflation.get("assumed", 0)

    priced = sum(p["price"] for p in board["players"])
    spots_left = league.total_roster_spots - slots_kept
    floors = spots_left - len(board["players"])
    kept_cost = inflation.get("money_out", 0.0)
    return priced + floors + kept_cost


class TestAllocateStarters:
    def test_total_matches_league_starting_slots(self, by_position, league):
        starters = value.allocate_starters(by_position, league)
        assert sum(starters.values()) == league.total_starters == 120

    def test_superflex_absorbs_quarterbacks(self, by_position, league):
        """The 12 SF slots should go to QBs when QB13+ outscores the flex pool."""
        starters = value.allocate_starters(by_position, league)
        assert starters["QB"] == 24

    def test_without_superflex_qb_demand_halves(self, by_position):
        one_qb = League(superflex=0)
        starters = value.allocate_starters(by_position, one_qb)
        assert starters["QB"] == 12

    def test_every_position_meets_its_dedicated_minimum(self, by_position, league):
        starters = value.allocate_starters(by_position, league)
        for position, per_team in league.dedicated.items():
            assert starters[position] >= per_team * league.teams

    def test_three_wr_drives_deeper_wr_demand_than_two(self, by_position, league):
        """The format itself, not the players, sets how deep WR runs."""
        two_wr = League(dedicated={"QB": 1, "RB": 2, "WR": 2, "TE": 1})
        deep = value.allocate_starters(by_position, league)["WR"]
        shallow = value.allocate_starters(by_position, two_wr)["WR"]
        assert deep > shallow


class TestReplacementLevels:
    def test_uses_median_of_window_past_cutoff(self, by_position, league):
        starters = {"QB": 24, "RB": 30, "WR": 53, "TE": 13}
        levels = value.replacement_levels(by_position, starters, window=6)
        # QB25..QB30 are 360-5*24 .. 360-5*29 -> median of 240..215
        window = [360 - 5 * i for i in range(24, 30)]
        expected = (window[2] + window[3]) / 2
        assert levels["QB"] == pytest.approx(expected)

    def test_deeper_starter_demand_lowers_replacement(self, by_position):
        shallow = value.replacement_levels(by_position, {"WR": 24}, window=6)
        deep = value.replacement_levels(by_position, {"WR": 53}, window=6)
        assert deep["WR"] < shallow["WR"]

    def test_handles_cutoff_past_end_of_pool(self, league):
        tiny = {"TE": make_players("TE", 3, 100, 10)}
        levels = value.replacement_levels(tiny, {"TE": 99}, window=6)
        assert levels["TE"] == 80  # last player's points

    def test_handles_empty_position(self):
        levels = value.replacement_levels({"TE": []}, {"TE": 12}, window=6)
        assert levels["TE"] == 0.0


class TestComputeValues:
    def test_excludes_players_at_or_below_replacement(self, league):
        players = [
            {"name": "Good", "pos": "WR", "pts": 200.0, "adp": 1.0, "team": "A", "injury": ""},
            {"name": "Exactly", "pos": "WR", "pts": 150.0, "adp": 2.0, "team": "A", "injury": ""},
            {"name": "Below", "pos": "WR", "pts": 100.0, "adp": 3.0, "team": "A", "injury": ""},
        ]
        pool = value.compute_values(players, {"WR": 150.0}, league)
        assert [p["name"] for p in pool] == ["Good"]

    def test_prices_exhaust_the_discretionary_pool(self, by_position, redraft):
        """Every discretionary dollar is allocated, plus $1 floor per player.

        Combined with $1 for each unvalued roster spot, this makes the board
        sum to exactly the money in the league.
        """
        board = value.build_board(by_position, redraft)
        pool = board["players"]
        total = sum(p["value"] for p in pool)
        assert total == pytest.approx(len(pool) + redraft.discretionary)

    def test_board_plus_dollar_fillers_equals_all_league_money(
        self, by_position, redraft
    ):
        board = value.build_board(by_position, redraft)
        pool = board["players"]
        fillers = redraft.total_roster_spots - len(pool)
        assert sum(p["value"] for p in pool) + fillers == pytest.approx(
            redraft.total_money
        )

    def test_no_player_priced_below_one_dollar(self, by_position, league):
        pool = value.build_board(by_position, league)["players"]
        assert min(p["value"] for p in pool) >= 1.0

    def test_bigger_budget_scales_prices_up(self, by_position, league):
        rich = League(budget=400)
        cheap_top = value.build_board(by_position, league)["players"][0]["value"]
        rich_top = value.build_board(by_position, rich)["players"][0]["value"]
        assert rich_top > cheap_top


class TestMarket:
    def test_market_and_value_share_a_total(self, by_position, league):
        """Same curve, re-dealt — so Edge is a like-for-like comparison."""
        pool = value.build_board(by_position, league)["players"]
        assert sum(p["market"] for p in pool) == pytest.approx(
            sum(p["value"] for p in pool)
        )

    def test_edges_net_to_zero(self, by_position, league):
        pool = value.build_board(by_position, league)["players"]
        assert sum(p["edge"] for p in pool) == pytest.approx(0.0, abs=1e-6)

    def test_players_without_adp_sort_last(self, league):
        pool = [
            {"name": "Known", "pos": "WR", "pts": 200.0, "value": 50.0, "adp": 5.0},
            {"name": "Unknown", "pos": "WR", "pts": 199.0, "value": 40.0, "adp": None},
        ]
        value.attach_market(pool)
        unknown = next(p for p in pool if p["name"] == "Unknown")
        assert unknown["market"] == 40.0  # got the lower slot on the curve


class TestStickiness:
    def test_full_weight_is_pure_projection(self, by_position, league):
        pool = value.build_board(by_position, league, stickiness=1.0)["players"]
        for player in pool:
            assert player["price"] == pytest.approx(player["value"])

    def test_zero_weight_is_pure_market(self, by_position, league):
        pool = value.build_board(by_position, league, stickiness=0.0)["players"]
        for player in pool:
            assert player["price"] == pytest.approx(player["market"])

    def test_partial_weight_lands_between(self, by_position, league):
        pool = value.build_board(by_position, league, stickiness=0.7)["players"]
        for player in pool:
            low, high = sorted((player["value"], player["market"]))
            assert low - 1e-9 <= player["price"] <= high + 1e-9

    def test_blending_preserves_the_league_total(self, by_position, redraft):
        """Both curves sum to the same money, so any blend of them does too."""
        for weight in (0.0, 0.3, 0.7, 1.0):
            pool = value.build_board(by_position, redraft, stickiness=weight)["players"]
            assert sum(p["price"] for p in pool) == pytest.approx(
                len(pool) + redraft.discretionary
            )

    def test_weight_is_clamped_not_rejected(self, by_position, league):
        high = value.build_board(by_position, league, stickiness=5.0)["players"]
        low = value.build_board(by_position, league, stickiness=-3.0)["players"]
        assert high[0]["price"] == pytest.approx(high[0]["value"])
        assert low[0]["price"] == pytest.approx(low[0]["market"])

    def test_default_comes_from_config(self, by_position, league):
        from config import DEFAULT_STICKINESS

        board = value.build_board(by_position, league)
        assert board["stickiness"] == DEFAULT_STICKINESS


class TestTiers:
    def test_ranks_are_dense_and_ordered(self, by_position, league):
        pool = value.build_board(by_position, league)["players"]
        for position in league.positions:
            ranks = sorted(p["pos_rank"] for p in pool if p["pos"] == position)
            assert ranks == list(range(1, len(ranks) + 1))

    def test_tiers_never_decrease_down_the_board(self, by_position, league):
        pool = value.build_board(by_position, league)["players"]
        for position in league.positions:
            ranked = sorted(
                [p for p in pool if p["pos"] == position],
                key=lambda p: p["pos_rank"],
            )
            tiers = [p["tier"] for p in ranked]
            assert tiers == sorted(tiers)

    def test_obvious_cliff_creates_a_tier_break(self, league):
        cliff = [
            {"name": "Elite", "pos": "TE", "pts": 260.0},
            {"name": "AlsoElite", "pos": "TE", "pts": 255.0},
            {"name": "Fine", "pos": "TE", "pts": 160.0},
            {"name": "AlsoFine", "pos": "TE", "pts": 158.0},
        ]
        value.assign_tiers(cliff, ("TE",))
        assert cliff[0]["tier"] == cliff[1]["tier"]
        assert cliff[2]["tier"] > cliff[1]["tier"]


class TestPositionalSpend:
    def test_spend_covers_every_position_and_totals_the_board(
        self, by_position, league
    ):
        board = value.build_board(by_position, league)
        spend = board["spend"]
        assert set(spend) == set(league.positions)
        assert sum(s["dollars"] for s in spend.values()) == pytest.approx(
            sum(p["value"] for p in board["players"])
        )


class TestKeepers:
    """Keeper removal and the inflation it causes.

    A wrong multiplier here misprices the entire board at once, so these
    lean on conservation: whatever leaves the auction has to show up
    somewhere else in the accounting.
    """

    KEEPERS = {
        "QB|QB8": {"paid": 4, "mine": True},
        "WR|WR25": {"paid": 4, "mine": True},
    }

    def test_redraft_league_is_not_inflated(self, by_position, redraft):
        board = value.build_board(by_position, redraft)
        assert board["inflation"]["multiplier"] == 1.0
        assert board["keepers"] == []

    def test_all_money_is_accounted_for_without_keepers(self, by_position, redraft):
        board = value.build_board(by_position, redraft)
        assert all_money_accounted(board, redraft) == pytest.approx(
            redraft.total_money
        )

    def test_all_money_is_accounted_for_when_every_keeper_is_known(
        self, by_position, league
    ):
        """Fully informed, the accounting closes to the dollar."""
        every = {}
        for i in range(5, 17):
            every[f"QB|QB{i}"] = {"paid": 5}
            every[f"RB|RB{i}"] = {"paid": 5}
        assert len(every) == league.teams * league.keepers_per_team

        board = value.build_board(by_position, league, keepers=every)
        assert board["inflation"]["assumed"] == 0
        assert all_money_accounted(board, league) == pytest.approx(
            league.total_money
        )

    def test_assumed_keepers_leave_a_known_overhang(self, by_position, league):
        """The one place the board knowingly does not balance.

        22 unknown keepers are still *listed*, because we cannot name
        which players they are. Their surplus is therefore counted twice:
        once as money removed from the auction, and once as a player you
        can still see a price for. The gap is exactly that surplus, and
        it shrinks to nothing as real keepers are entered.
        """
        board = value.build_board(by_position, league, keepers=self.KEEPERS)
        inflation = board["inflation"]
        overhang = all_money_accounted(board, league) - league.total_money

        expected = (
            inflation["assumed"]
            * (ASSUMED_KEEPER_VALUE - 1.0)
            * inflation["multiplier"]
        )
        assert overhang == pytest.approx(expected, rel=1e-6)
        assert overhang > 0

    def test_kept_players_leave_the_biddable_pool(self, by_position, league):
        board = value.build_board(by_position, league, keepers=self.KEEPERS)
        biddable = {p["name"] for p in board["players"] + board["fillers"]}
        assert "QB8" not in biddable and "WR25" not in biddable
        assert {p["name"] for p in board["keepers"]} == {"QB8", "WR25"}

    def test_keeper_cost_is_double_what_was_paid(self, by_position, league):
        board = value.build_board(by_position, league, keepers=self.KEEPERS)
        for player in board["keepers"]:
            assert player["cost"] == player["paid"] * 2

    def test_unknown_slots_are_assumed_not_ignored(self, by_position, league):
        board = value.build_board(by_position, league, keepers=self.KEEPERS)
        inflation = board["inflation"]
        assert inflation["known"] == 2
        assert inflation["assumed"] == league.teams * league.keepers_per_team - 2
        assert inflation["multiplier"] > 1.0

    def test_entering_a_keeper_replaces_an_assumed_one(self, by_position, league):
        """The fitted portion must shrink as real information arrives."""
        none_known = value.build_board(by_position, league)["inflation"]
        two_known = value.build_board(
            by_position, league, keepers=self.KEEPERS
        )["inflation"]
        assert none_known["assumed"] == league.teams * league.keepers_per_team
        assert two_known["assumed"] == none_known["assumed"] - 2
        assert two_known["slots"] == none_known["slots"]

    def test_inflation_lands_on_the_expensive_players(self, by_position, league):
        """+22% on the surplus is +$12 at the top and +$1 at the bottom."""
        flat = value.build_board(by_position, redraft_league())["players"]
        rich = value.build_board(by_position, league)["players"]
        before = {p["name"]: p["price"] for p in flat}

        top = max(rich, key=lambda p: p["price"])
        cheap = min(rich, key=lambda p: p["price"])
        top_rise = top["price"] - before[top["name"]]
        cheap_rise = cheap["price"] - before[cheap["name"]]
        assert top_rise > 8.0
        assert cheap_rise < 1.0

    def test_the_dollar_floor_never_inflates(self, by_position, league):
        board = value.build_board(by_position, league, keepers=self.KEEPERS)
        assert min(p["price"] for p in board["players"]) >= 1.0
        assert all(p["price"] == 1.0 for p in board["fillers"])

    def test_unmatched_keepers_are_reported_not_swallowed(self, by_position, league):
        board = value.build_board(
            by_position, league, keepers={"RB|Nobody At All": {"paid": 5}}
        )
        assert board["unmatchedKeepers"] == ["RB|Nobody At All"]

    def test_a_keeper_below_replacement_is_still_found(self, by_position, league):
        """Someone can keep a $1 player — it removes cash but no surplus.

        He lives in the filler list, not the priced pool, so a keeper
        lookup that only searched the priced pool would call him a typo.
        """
        cheap = value.build_board(
            by_position, league, keepers={"WR|WR119": {"paid": 1}}
        )
        assert cheap["unmatchedKeepers"] == []
        assert [p["name"] for p in cheap["keepers"]] == ["WR119"]
        assert cheap["keepers"][0]["cost"] == 2.0
        assert "WR119" not in {p["name"] for p in cheap["fillers"]}
        # He carries no surplus, so he shifts the money side only.
        assert cheap["inflation"]["known"] == 1
        assert cheap["inflation"]["surplus_out"] == pytest.approx(
            (league.teams * league.keepers_per_team - 1)
            * (ASSUMED_KEEPER_VALUE - 1.0)
        )

    def test_replacement_level_is_unchanged_by_keepers(self, by_position, league):
        """A kept player still starts, so league-wide demand is identical."""
        plain = value.build_board(by_position, league)
        kept = value.build_board(by_position, league, keepers=self.KEEPERS)
        assert kept["replacement"] == plain["replacement"]
        assert kept["starters"] == plain["starters"]

    def test_market_curve_is_handed_back_uninflated(self, by_position, league):
        """Re-deriving it from finished prices would double-inflate."""
        board = value.build_board(by_position, league)
        assert max(board["curve"]) < max(p["value"] for p in board["players"])

    def test_pinned_curve_survives_a_reprice(self, by_position, league):
        """The anchor must not drift by the multiplier on every edit."""
        first = value.build_board(by_position, league)
        second = value.build_board(by_position, league, market_curve=first["curve"])
        before = {p["name"]: p["market"] for p in first["players"]}
        for player in second["players"]:
            assert player["market"] == pytest.approx(before[player["name"]])


def redraft_league():
    return League(keepers_per_team=0)


class TestFillers:
    """The $1 tier.

    Its whole reason for being a separate list is that it must be
    inert: you can show every player without a single price moving.
    """

    def test_nobody_is_lost_between_the_two_lists(self, by_position, league):
        board = value.build_board(by_position, league)
        everyone = {(p["pos"], p["name"]) for b in by_position.values() for p in b}
        shown = {(p["pos"], p["name"]) for p in board["players"] + board["fillers"]}
        assert shown == everyone

    def test_no_player_appears_in_both_lists(self, by_position, league):
        board = value.build_board(by_position, league)
        priced = {(p["pos"], p["name"]) for p in board["players"]}
        filler = {(p["pos"], p["name"]) for p in board["fillers"]}
        assert priced & filler == set()

    def test_every_filler_is_at_or_below_replacement(self, by_position, league):
        board = value.build_board(by_position, league)
        for player in board["fillers"]:
            assert player["pts"] <= board["replacement"][player["pos"]]

    def test_fillers_all_cost_exactly_one_dollar(self, by_position, league):
        board = value.build_board(by_position, league)
        assert board["fillers"], "fixture should produce sub-replacement players"
        for player in board["fillers"]:
            assert player["value"] == 1.0
            assert player["price"] == 1.0
            assert player["market"] == 1.0
            assert player["vorp"] == 0.0

    def test_fillers_carry_no_tier(self, by_position, league):
        board = value.build_board(by_position, league)
        assert all(p["tier"] is None for p in board["fillers"])

    def test_deeper_projections_do_not_change_any_price(self, by_position, league):
        """The invariant the separate list exists to protect.

        Adding more players below replacement must move nothing. Note the
        test appends rather than removes: replacement is the median of the
        six players just past the cutoff, so deleting sub-replacement
        players genuinely *should* re-price the board. Only players below
        that window are inert.
        """
        board = value.build_board(by_position, league)
        priced = {(p["pos"], p["name"]): p["price"] for p in board["players"]}

        deeper = {
            position: bucket + make_players(f"deep{position}", 40, 20, 0.5)
            for position, bucket in by_position.items()
        }
        for position, bucket in deeper.items():
            for player in bucket:
                player["pos"] = position

        again = value.build_board(deeper, league)

        assert again["starters"] == board["starters"]
        assert again["replacement"] == board["replacement"]
        assert again["spend"] == board["spend"]
        assert len(again["players"]) == len(board["players"])
        for player in again["players"]:
            assert player["price"] == pytest.approx(
                priced[(player["pos"], player["name"])]
            )
        assert len(again["fillers"]) == len(board["fillers"]) + 40 * 4

    def test_spend_excludes_fillers(self, by_position, league):
        board = value.build_board(by_position, league)
        counted = sum(s["count"] for s in board["spend"].values())
        assert counted == len(board["players"])

    def test_pos_rank_continues_from_the_priced_players(self, by_position, league):
        board = value.build_board(by_position, league)
        for position in league.positions:
            ranks = sorted(
                p["pos_rank"]
                for p in board["players"] + board["fillers"]
                if p["pos"] == position
            )
            assert ranks == list(range(1, len(ranks) + 1))

    def test_fillers_are_ordered_by_points(self, by_position, league):
        board = value.build_board(by_position, league)
        points = [p["pts"] for p in board["fillers"]]
        assert points == sorted(points, reverse=True)

    def test_no_fillers_when_everyone_clears_replacement(self, league):
        # Exactly the starters and the replacement window, nobody spare.
        tiny = {
            "QB": make_players("QB", 30, 360, 5),
            "RB": make_players("RB", 40, 330, 6),
            "WR": make_players("WR", 60, 310, 3),
            "TE": make_players("TE", 18, 250, 7),
        }
        board = value.build_board(tiny, league)
        assert all(
            p["pts"] <= board["replacement"][p["pos"]] for p in board["fillers"]
        )
