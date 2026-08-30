"""Tests for the Flask layer.

The valuation math is covered in test_value.py. What matters here is that
league settings survive the round trip from query string to priced board,
and that bad input is refused rather than quietly priced on nonsense.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
import rankings  # noqa: E402
from app import app as flask_app  # noqa: E402
from config import League  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Point the rankings store at a temp file for every test.

    Without this the suite would read and write the real data/rankings.json
    and quietly destroy hand-entered work.
    """
    monkeypatch.setattr(config, "RANKINGS_PATH", tmp_path / "rankings.json")
    return tmp_path / "rankings.json"


@pytest.fixture
def client():
    flask_app.config.update(TESTING=True)
    return flask_app.test_client()


def share(payload, position):
    """That position's cut of all league money."""
    return payload["spend"][position]["dollars"] / payload["league"]["totalMoney"]


class TestPage:
    def test_index_serves_the_board_with_settings(self, client):
        page = client.get("/").get_data(as_text=True)
        assert page.startswith("<!doctype html>")
        assert 'id="settings"' in page
        assert "const SERVER = true" in page
        assert "Jahmyr Gibbs" in page

    def test_health(self, client):
        body = client.get("/api/health").get_json()
        assert body["status"] == "ok"


class TestBoardApi:
    def test_defaults_match_the_configured_league(self, client):
        payload = client.get("/api/board").get_json()
        assert payload["league"]["teams"] == 12
        assert payload["league"]["budget"] == 200
        assert payload["starters"]["QB"] == 24
        assert len(payload["players"]) > 100

    def test_more_wr_slots_raise_wr_share(self, client):
        two = client.get("/api/board?wr=2").get_json()
        four = client.get("/api/board?wr=4").get_json()
        assert share(four, "WR") > share(two, "WR")

    def test_dropping_superflex_collapses_qb_demand(self, client):
        """The single biggest lever in this format."""
        with_sf = client.get("/api/board?sf=1").get_json()
        without = client.get("/api/board?sf=0").get_json()
        assert with_sf["starters"]["QB"] == 24
        assert without["starters"]["QB"] == 12
        assert share(without, "QB") < share(with_sf, "QB")

    def test_budget_scales_prices(self, client):
        cheap = client.get("/api/board?budget=200").get_json()
        rich = client.get("/api/board?budget=400").get_json()
        assert rich["players"][0]["value"] > cheap["players"][0]["value"]

    def test_scoring_change_reranks_receivers(self, client):
        """Standard scoring should not value a target hog like full PPR does."""
        ppr = client.get("/api/board?scoring=pts_ppr").get_json()
        std = client.get("/api/board?scoring=pts_std").get_json()
        assert share(std, "WR") != share(ppr, "WR")

    def test_partial_query_keeps_other_defaults(self, client):
        payload = client.get("/api/board?teams=10").get_json()
        assert payload["league"]["teams"] == 10
        assert payload["league"]["budget"] == 200

    def test_prices_still_exhaust_the_league(self, client):
        # keepers=0 isolates the valuation math: keeper inflation moves
        # money out of the auction on purpose, so a keeper league is
        # expected not to sum to the raw league total.
        payload = client.get("/api/board?teams=10&budget=300&keepers=0").get_json()
        league = payload["league"]
        spent = sum(p["value"] for p in payload["players"])
        fillers = league["teams"] * league["spots"] - len(payload["players"])
        assert spent + fillers == pytest.approx(league["totalMoney"], abs=len(payload["players"]))


class TestOverridesAndStickiness:
    def post(self, client, **body):
        return client.post("/api/board", json=body)

    def test_override_moves_that_player(self, client):
        base = client.get("/api/board").get_json()
        target = base["players"][5]
        key = f"{target['pos']}|{target['name']}"

        bumped = self.post(client, overrides={key: 600.0}).get_json()
        moved = next(p for p in bumped["players"] if p["name"] == target["name"])
        assert moved["pts"] == 600.0
        assert moved["edited"] is True
        assert moved["price"] > target["price"]

    def test_override_reprices_the_whole_board(self, client):
        """Changing one projection shifts $/point for everyone, by design."""
        base = client.get("/api/board").get_json()
        top = base["players"][0]
        other = base["players"][20]

        bumped = self.post(
            client, overrides={f"{top['pos']}|{top['name']}": 900.0}
        ).get_json()
        after = next(p for p in bumped["players"] if p["name"] == other["name"])
        assert after["price"] != other["price"]

    def test_editing_a_projection_does_not_move_the_market_anchor(self, client):
        """The consensus must not bend to your own opinion.

        Deriving the market curve from an edited pool let a single inflated
        projection drag unrelated players upward — an anchor that moves when
        you pull on it is not an anchor.
        """
        base = client.get("/api/board").get_json()
        top = base["players"][0]
        others = {p["name"]: p for p in base["players"][1:40]}

        bumped = self.post(
            client, overrides={f"{top['pos']}|{top['name']}": 900.0}
        ).get_json()

        for player in bumped["players"]:
            before = others.get(player["name"])
            if before:
                assert player["market"] == before["market"], (
                    f"{player['name']} market moved "
                    f"{before['market']} -> {player['market']}"
                )

    def test_inflating_one_player_cannot_enrich_another(self, client):
        """Raising one projection must not raise anyone else's price."""
        base = client.get("/api/board").get_json()
        top = base["players"][0]
        before = {p["name"]: p["price"] for p in base["players"][1:40]}

        bumped = self.post(
            client, overrides={f"{top['pos']}|{top['name']}": 900.0}
        ).get_json()

        for player in bumped["players"]:
            if player["name"] in before:
                assert player["price"] <= before[player["name"]] + 0.5, (
                    f"{player['name']} rose from {before[player['name']]} "
                    f"to {player['price']}"
                )

    def test_board_still_sums_to_the_league_after_overrides(self, client):
        body = self.post(
            client,
            overrides={"WR|Puka Nacua": 500.0},
            settings={"keepers": 0},
        ).get_json()
        league = body["league"]
        spent = sum(p["price"] for p in body["players"])
        fillers = league["teams"] * league["spots"] - len(body["players"])
        assert spent + fillers == pytest.approx(
            league["totalMoney"], abs=len(body["players"])
        )

    def test_unknown_override_name_is_ignored(self, client):
        body = self.post(client, overrides={"WR|Nobody At All": 300.0}).get_json()
        assert not any(p["edited"] for p in body["players"])

    def test_stickiness_extremes(self, client):
        pure = self.post(client, stickiness=1.0).get_json()["players"]
        market = self.post(client, stickiness=0.0).get_json()["players"]
        assert all(p["price"] == p["value"] for p in pure)
        assert all(p["price"] == p["market"] for p in market)

    def test_stickiness_default_reported_back(self, client):
        from config import DEFAULT_STICKINESS

        body = client.get("/api/board").get_json()
        assert body["league"]["stickiness"] == DEFAULT_STICKINESS

    def test_stickiness_pulls_toward_market(self, client):
        """A player the market likes more than we do gets dearer as we lean market."""
        pure = {p["name"]: p for p in self.post(client, stickiness=1.0).get_json()["players"]}
        leaned = {p["name"]: p for p in self.post(client, stickiness=0.3).get_json()["players"]}
        gap = [n for n, p in pure.items() if p["market"] - p["value"] >= 5]
        assert gap, "expected at least one player the market prices well above us"
        for name in gap:
            assert leaned[name]["price"] > pure[name]["price"]

    def test_settings_and_overrides_combine(self, client):
        body = self.post(
            client, settings={"wr": 2}, overrides={"WR|Puka Nacua": 400.0}, stickiness=1.0
        ).get_json()
        assert body["league"]["params"]["wr"] == 2
        nacua = next(p for p in body["players"] if p["name"] == "Puka Nacua")
        assert nacua["pts"] == 400.0

    @pytest.mark.parametrize(
        "body,fragment",
        [
            ({"overrides": {"WR|X": "abc"}}, "must be a number"),
            ({"overrides": {"WR|X": 9999}}, "between 0 and 1000"),
            ({"stickiness": 4}, "between 0 and 1"),
            ({"stickiness": "nope"}, "must be a number"),
            ({"settings": {"teams": 0}}, "between"),
        ],
    )
    def test_bad_post_bodies_return_400(self, client, body, fragment):
        response = client.post("/api/board", json=body)
        assert response.status_code == 400
        assert fragment in response.get_json()["error"]

    def test_empty_post_body_is_valid(self, client):
        response = client.post("/api/board", json={})
        assert response.status_code == 200
        assert len(response.get_json()["players"]) > 100


class TestRejectsBadInput:
    @pytest.mark.parametrize(
        "query,fragment",
        [
            ("teams=0", "between"),
            ("teams=abc", "whole number"),
            ("budget=-5", "between"),
            ("spots=5", "cannot hold"),
            ("scoring=pts_bogus", "unknown scoring"),
            ("qb=0&rb=0&wr=0&te=0&flex=0&sf=0", "at least one starting slot"),
        ],
    )
    def test_bad_settings_return_400(self, client, query, fragment):
        response = client.get(f"/api/board?{query}")
        assert response.status_code == 400
        assert fragment in response.get_json()["error"]

    def test_error_is_a_message_not_a_traceback(self, client):
        body = client.get("/api/board?teams=0").get_json()
        assert "Traceback" not in body["error"]


class TestKeeperEndpoint:
    """Keepers reach the board through the store, not the query string.

    A keeper is prep work, like a tag — it must survive a reload from any
    browser, and it must re-price the board the moment it lands.
    """

    def keep(self, client, key, paid, mine=True):
        return client.post(
            "/api/rankings/keeper", json={"key": key, "paid": paid, "mine": mine}
        )

    def test_keeper_round_trips_and_persists(self, client, isolated_store):
        saved = self.keep(client, "QB|Jaxson Dart", 4).get_json()
        assert saved["saved"] is True
        assert saved["counts"]["keepers"] == 1
        assert json.loads(isolated_store.read_text())["keepers"] == {
            "QB|Jaxson Dart": {"paid": 4.0, "mine": True}
        }

    def test_a_saved_keeper_leaves_the_biddable_board(self, client):
        before = client.get("/api/board").get_json()
        assert any(p["name"] == "Jaxson Dart" for p in before["players"])

        self.keep(client, "QB|Jaxson Dart", 4)
        after = client.get("/api/board").get_json()

        biddable = {p["name"] for p in after["players"] + after["fillers"]}
        assert "Jaxson Dart" not in biddable
        assert [p["name"] for p in after["keepers"]] == ["Jaxson Dart"]

    def test_keeper_cost_and_your_remaining_budget(self, client):
        self.keep(client, "QB|Jaxson Dart", 4)
        self.keep(client, "WR|Luther Burden", 4)
        body = client.get("/api/board").get_json()

        assert {p["cost"] for p in body["keepers"]} == {8.0}
        assert body["you"] == {
            "spent": 16,
            "budget": 184,
            "spots": 16,
            "keepers": 2,
        }

    def test_opponent_keepers_do_not_touch_your_budget(self, client):
        self.keep(client, "RB|Bijan Robinson", 30, mine=False)
        body = client.get("/api/board").get_json()
        assert body["you"]["budget"] == 200
        assert body["you"]["spots"] == 18
        assert len(body["keepers"]) == 1

    def test_removing_a_keeper_puts_him_back(self, client):
        self.keep(client, "QB|Jaxson Dart", 4)
        client.post(
            "/api/rankings/keeper", json={"key": "QB|Jaxson Dart", "paid": None}
        )
        body = client.get("/api/board").get_json()
        assert body["keepers"] == []
        assert any(p["name"] == "Jaxson Dart" for p in body["players"])

    def test_a_typo_is_reported_not_swallowed(self, client):
        self.keep(client, "QB|Jaxon Dart", 4)  # one 's' short
        body = client.get("/api/board").get_json()
        assert body["unmatchedKeepers"] == ["QB|Jaxon Dart"]

    def test_board_is_inflated_and_the_multiplier_is_reported(self, client):
        body = client.get("/api/board").get_json()
        assert body["inflation"]["multiplier"] > 1.0
        assert body["inflation"]["slots"] == 24

    def test_keepers_off_removes_all_inflation(self, client):
        body = client.get("/api/board?keepers=0").get_json()
        assert body["inflation"]["multiplier"] == 1.0
        assert body["keepers"] == []


class TestRankingsEndpoints:
    def test_starts_empty(self, client):
        body = client.get("/api/rankings").get_json()
        assert body["tags"] == {} and body["projections"] == {}
        assert body["keepers"] == {}

    def test_tag_round_trips_through_the_api(self, client):
        saved = client.post(
            "/api/rankings/tag", json={"key": "RB|Jahmyr Gibbs", "tag": "gem"}
        ).get_json()
        assert saved["saved"] is True
        assert saved["counts"]["gems"] == 1
        assert client.get("/api/rankings").get_json()["tags"] == {
            "RB|Jahmyr Gibbs": "gem"
        }

    def test_tag_survives_on_disk(self, client, isolated_store):
        client.post("/api/rankings/tag", json={"key": "QB|Josh Allen", "tag": "fade"})
        assert isolated_store.exists()
        assert json.loads(isolated_store.read_text())["tags"] == {
            "QB|Josh Allen": "fade"
        }

    def test_clearing_a_tag(self, client):
        client.post("/api/rankings/tag", json={"key": "RB|X", "tag": "gem"})
        client.post("/api/rankings/tag", json={"key": "RB|X", "tag": None})
        assert client.get("/api/rankings").get_json()["tags"] == {}

    def test_projection_round_trips(self, client):
        client.post(
            "/api/rankings/projection", json={"key": "WR|Puka Nacua", "points": 400}
        )
        assert client.get("/api/rankings").get_json()["projections"] == {
            "WR|Puka Nacua": 400.0
        }

    def test_saved_projection_reprices_the_served_board(self, client):
        """The point of persisting: a reload shows the board you left."""
        client.post(
            "/api/rankings/projection", json={"key": "WR|Puka Nacua", "points": 500}
        )
        page = client.get("/").get_data(as_text=True)
        assert '"pts": 500.0' in page or '"pts":500.0' in page

    def test_index_seeds_saved_tags_into_the_page(self, client):
        client.post("/api/rankings/tag", json={"key": "RB|Jahmyr Gibbs", "tag": "gem"})
        page = client.get("/").get_data(as_text=True)
        assert "Jahmyr Gibbs" in page and "gem" in page

    def test_clear_section(self, client):
        client.post("/api/rankings/tag", json={"key": "RB|X", "tag": "gem"})
        client.post("/api/rankings/projection", json={"key": "WR|Y", "points": 300})
        client.post("/api/rankings/clear", json={"field": "projections"})
        body = client.get("/api/rankings").get_json()
        assert body["projections"] == {}
        assert body["tags"] == {"RB|X": "gem"}

    @pytest.mark.parametrize(
        "endpoint,body,fragment",
        [
            ("tag", {"key": "RB|X", "tag": "star"}, "tag must be one of"),
            ("tag", {"key": "nopipe", "tag": "gem"}, "key must look like"),
            ("tag", {}, "key must look like"),
            ("projection", {"key": "WR|X", "points": "abc"}, "must be a number"),
            ("projection", {"key": "WR|X", "points": 9999}, "between 0 and 1000"),
            ("clear", {"field": "everything"}, "field must be one of"),
            ("keeper", {"key": "no-pipe", "paid": 4}, "key must look like"),
            ("keeper", {"key": "QB|X", "paid": "abc"}, "must be a number"),
            ("keeper", {"key": "QB|X", "paid": 9999}, "between 0 and 500"),
        ],
    )
    def test_bad_input_returns_400(self, client, endpoint, body, fragment):
        response = client.post(f"/api/rankings/{endpoint}", json=body)
        assert response.status_code == 400
        assert fragment in response.get_json()["error"]

    def test_damaged_file_reports_rather_than_overwrites(self, client, isolated_store):
        isolated_store.write_text("{ corrupted")
        response = client.post(
            "/api/rankings/tag", json={"key": "RB|X", "tag": "gem"}
        )
        assert response.status_code == 400
        assert "refusing to overwrite" in response.get_json()["error"]
        assert isolated_store.read_text() == "{ corrupted"


class TestLeagueParams:
    def test_params_round_trip(self):
        original = League()
        assert League.from_params(original.params) == original

    def test_market_key_follows_superflex(self):
        assert League.from_params({"sf": "1"}).adp_key == "adp_2qb"
        assert League.from_params({"sf": "0"}).adp_key == "adp_ppr"
        assert League.from_params(
            {"sf": "0", "scoring": "pts_std"}
        ).adp_key == "adp_std"
