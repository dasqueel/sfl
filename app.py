#!/usr/bin/env python3
"""Flask front end for the auction board.

    python3 app.py                     # http://127.0.0.1:7575
    python3 app.py --port 8080
    python3 app.py --host 0.0.0.0      # reachable from your phone on the LAN

The valuation engine needs nothing from the web layer: a request just
builds a different League and re-runs `value.build_board`. That is the
payoff from keeping value.py pure — changing the roster shape in the
browser re-prices every player with no other moving parts.
"""

import argparse

from flask import Flask, jsonify, request

import blend
import fetch
import rankings
import render
import value
from config import DEFAULT_STICKINESS, LEAGUE, SEASON, League

app = Flask(__name__)


def board_for(
    league: League,
    season: int = SEASON,
    overrides: dict = None,
    stickiness: float = None,
    keepers: dict = None,
) -> dict:
    """Price the whole board for one configuration.

    Overrides are applied to projected points before valuation, so a
    hand-edited player shifts replacement levels and the dollars-per-point
    rate exactly as a real projection change would.

    The market anchor, however, is pinned to an unedited board. Your opinion
    about a player must not move the consensus you are measuring yourself
    against — otherwise raising one projection quietly drags unrelated
    players along with it.
    """
    players = fetch.load_players(season, league)
    by_position = fetch.group_by_position(players, league.positions)

    curve = None
    if overrides:
        baseline = value.build_board(by_position, league, stickiness=stickiness)
        # The board's own pre-inflation ladder, not one re-derived from its
        # finished prices — those already carry the keeper multiplier.
        curve = baseline["curve"]

        players = blend.apply_overrides(
            fetch.load_players(season, league), overrides
        )
        by_position = fetch.group_by_position(players, league.positions)

    return value.build_board(
        by_position,
        league,
        stickiness=stickiness,
        market_curve=curve,
        keepers=keepers,
    )


def parse_stickiness(raw) -> float:
    if raw is None or raw == "":
        return DEFAULT_STICKINESS
    try:
        weight = float(raw)
    except (TypeError, ValueError):
        raise ValueError("stickiness must be a number")
    if not 0.0 <= weight <= 1.0:
        raise ValueError("stickiness must be between 0 and 1")
    return weight


@app.get("/")
def index():
    """Serve the board, priced with whatever rankings are on disk.

    The stored projections are applied here so a reload shows the same board
    you left, from any browser at any address — which is the whole point of
    moving this off localStorage.
    """
    store = rankings.load()
    board = board_for(
        LEAGUE, overrides=store["projections"], keepers=store["keepers"]
    )
    return render.render_page(
        board, LEAGUE, SEASON, server=True, defaults=LEAGUE, store=store
    )


@app.get("/api/rankings")
def api_rankings():
    return jsonify(rankings.load())


@app.post("/api/rankings/tag")
def api_set_tag():
    """Set, change, or clear one player's gem/fade tag."""
    body = request.get_json(silent=True) or {}
    try:
        store = rankings.set_tag(body.get("key"), body.get("tag"))
    except ValueError as bad:
        return jsonify(error=str(bad)), 400
    except OSError as bad:
        return jsonify(error=f"could not write rankings: {bad}"), 500

    return jsonify(saved=True, counts=rankings.counts(store), updated=store["updated"])


@app.post("/api/rankings/projection")
def api_set_projection():
    """Set or clear one hand-edited projection."""
    body = request.get_json(silent=True) or {}
    try:
        store = rankings.set_projection(body.get("key"), body.get("points"))
    except ValueError as bad:
        return jsonify(error=str(bad)), 400
    except OSError as bad:
        return jsonify(error=f"could not write rankings: {bad}"), 500

    return jsonify(saved=True, counts=rankings.counts(store), updated=store["updated"])


@app.post("/api/rankings/keeper")
def api_set_keeper():
    """Record or remove one keeper. `paid=null` removes him."""
    body = request.get_json(silent=True) or {}
    try:
        store = rankings.set_keeper(
            body.get("key"), body.get("paid"), mine=body.get("mine", True)
        )
    except ValueError as bad:
        return jsonify(error=str(bad)), 400
    except OSError as bad:
        return jsonify(error=f"could not write rankings: {bad}"), 500

    return jsonify(saved=True, counts=rankings.counts(store), updated=store["updated"])


@app.post("/api/rankings/clear")
def api_clear_rankings():
    """Empty one section wholesale."""
    body = request.get_json(silent=True) or {}
    try:
        store = rankings.clear(body.get("field"))
    except ValueError as bad:
        return jsonify(error=str(bad)), 400
    except OSError as bad:
        return jsonify(error=f"could not write rankings: {bad}"), 500

    return jsonify(saved=True, counts=rankings.counts(store), updated=store["updated"])


@app.get("/api/board")
def api_board():
    """Re-price for the settings in the query string. No overrides."""
    try:
        league = League.from_params(request.args)
        weight = parse_stickiness(request.args.get("stickiness"))
    except ValueError as bad:
        return jsonify(error=str(bad)), 400

    board = board_for(league, stickiness=weight, keepers=rankings.load()["keepers"])
    return jsonify(render.board_payload(board, league, SEASON))


@app.post("/api/board")
def api_board_with_overrides():
    """Re-price with hand-edited projections carried in the JSON body.

    Overrides go in a body rather than the query string because there can be
    hundreds of them and URLs have limits.
    """
    body = request.get_json(silent=True) or {}
    try:
        league = League.from_params(body.get("settings") or {})
        overrides = blend.parse_overrides(body.get("overrides"))
        weight = parse_stickiness(body.get("stickiness"))
    except ValueError as bad:
        return jsonify(error=str(bad)), 400

    board = board_for(
        league,
        overrides=overrides,
        stickiness=weight,
        keepers=rankings.load()["keepers"],
    )
    return jsonify(render.board_payload(board, league, SEASON))


@app.get("/api/health")
def health():
    return jsonify(status="ok", season=SEASON, league=LEAGUE.describe())


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7575


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="0.0.0.0 to expose on the LAN (phone, tablet) during a draft",
    )
    parser.add_argument("--debug", action="store_true", help="auto-reload on edit")
    args = parser.parse_args()

    app.run(host=args.host, port=args.port, debug=args.debug)
