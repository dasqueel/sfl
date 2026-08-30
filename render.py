"""Turn a priced board into the page and the CSV.

Both the static build and the Flask app render the same
`templates/board.html`, differing only in whether the settings form is
present. Keeping one template means the two paths cannot drift.

Rows are built through the DOM in that template rather than by string
concatenation — player names contain apostrophes (Ja'Marr Chase, De'Von
Achane) and that is exactly where naive templating breaks.
"""

import csv
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).parent / "templates"

CSV_COLUMNS = [
    "pos", "pos_rank", "tier", "name", "team",
    "pts", "value", "market", "edge", "adp", "injury",
]

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


def _row(p: dict) -> dict:
    """One player as the page consumes him.

    Priced players and $1 fillers go through this same function so the
    two lists cannot drift into different shapes.
    """
    return {
        "name": p["name"],
        "pos": p["pos"],
        "team": p["team"],
        "posRank": p["pos_rank"],
        "tier": p["tier"],
        "pts": round(p["pts"], 1),
        "price": round(p.get("price", p["value"])),
        "value": round(p["value"]),
        "market": round(p["market"]),
        "adp": p["adp"],
        "injury": p["injury"],
        "sources": p.get("n_sources", 1),
        "edited": bool(p.get("overridden")),
        "filler": bool(p.get("filler")),
        "kept": bool(p.get("kept")),
        "paid": p.get("paid"),
        "cost": p.get("cost"),
        "mine": bool(p.get("mine")),
    }


def board_payload(board: dict, league, season: int) -> dict:
    """The JSON shape the page consumes, shared by both render paths.

    Dollar figures are rounded here, once, so that the Edge shown is the
    difference between the two numbers actually on screen rather than a
    third rounding of its own.
    """
    keepers = board.get("keepers", [])
    mine = [p for p in keepers if p.get("mine")]
    inflation = board.get("inflation") or {}

    return {
        "players": [_row(p) for p in board["players"]],
        "fillers": [_row(p) for p in board.get("fillers", [])],
        "keepers": [_row(p) for p in keepers],
        "unmatchedKeepers": board.get("unmatchedKeepers", []),
        "inflation": {
            "multiplier": round(inflation.get("multiplier", 1.0), 4),
            "known": inflation.get("known", 0),
            "assumed": inflation.get("assumed", 0),
            "slots": inflation.get("slots", 0),
            "moneyOut": round(inflation.get("money_out", 0.0)),
            "moneyLeft": round(inflation.get("money_left", 0.0)),
        },
        # Your own keepers are already paid for, so the money and the roster
        # spots they occupy are gone before the first nomination.
        "you": {
            "spent": round(sum(p["cost"] for p in mine)),
            "budget": round(league.budget - sum(p["cost"] for p in mine)),
            "spots": league.roster_spots - len(mine),
            "keepers": len(mine),
        },
        "starters": board["starters"],
        "replacement": {k: round(v, 1) for k, v in board["replacement"].items()},
        "spend": {
            k: {"dollars": round(v["dollars"]), "count": v["count"]}
            for k, v in board["spend"].items()
        },
        "league": {
            "teams": league.teams,
            "budget": league.budget,
            "spots": league.roster_spots,
            "totalMoney": league.total_money,
            "maxBid": league.max_opening_bid,
            "describe": league.describe(),
            "season": season,
            "params": league.params,
            "stickiness": board.get("stickiness"),
        },
    }


def render_page(
    board: dict, league, season: int, server: bool, defaults, store: dict = None
) -> str:
    """Render the board page. `server` decides whether settings are editable.

    `store` seeds the page with saved tags and projections. The static build
    passes whatever was on disk at build time, which makes the file a
    snapshot rather than a live view — it has no server to save back to.
    """
    store = store or {}
    return _env.get_template("board.html").render(
        bootstrap=json.dumps(board_payload(board, league, season)),
        defaults=json.dumps(defaults.params),
        tags=json.dumps(store.get("tags") or {}),
        projections=json.dumps(store.get("projections") or {}),
        keepers=json.dumps(store.get("keepers") or {}),
        server=server,
    )


def write_html(
    board: dict, league, season: int, path: Path, store: dict = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_page(board, league, season, server=False, defaults=league, store=store)
    )


def write_csv(board: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for player in board["players"] + list(board.get("fillers", [])):
            row = dict(player)
            for key in ("pts", "value", "market", "edge"):
                row[key] = round(row[key], 1)
            writer.writerow(row)
