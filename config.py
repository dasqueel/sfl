"""League settings — the single source of truth for every price on the sheet.

Change a value here and the whole board re-prices. Nothing else in the
project hardcodes team counts, budgets, or roster shape.
"""

from dataclasses import dataclass, field
from pathlib import Path

SEASON = 2026

# Your own reads on players: gem/fade tags and hand-edited projections.
# Deliberately outside data/raw/ (which is gitignored throwaway cache) so it
# can be committed — this is the one file here that cannot be recomputed.
RANKINGS_PATH = Path(__file__).parent / "data" / "rankings.json"

# Sleeper exposes points and ADP under these keys.
SCORING_KEYS = ("pts_ppr", "pts_half_ppr", "pts_std")

# Transcribed from this league's Yahoo scoring settings page, League Value
# column. Two of these depart from Yahoo's own defaults and from what the
# projection sources assume:
#
#   fumbles lost  -1  (Yahoo default -2, and RotoWire's totals assume -2)
#   receptions     1  (Yahoo default 0.5 — this is a full-PPR league)
#
# Return touchdowns score here and are absent from every source's published
# point total, so they are pure upside the stock numbers miss.
SCORING_RULES = {
    "pass_yd": 0.04,      # 25 yards per point
    "pass_td": 4.0,
    "pass_int": -1.0,
    "pass_2pt": 2.0,
    "rush_yd": 0.10,      # 10 yards per point
    "rush_td": 6.0,
    "rush_2pt": 2.0,
    "rec_yd": 0.10,       # 10 yards per point
    "rec_td": 6.0,
    "rec_2pt": 2.0,
    "fum_lost": -1.0,
    "pr_td": 6.0,         # punt return touchdown
    "def_kr_td": 6.0,     # kick return touchdown
}

# The one rule that varies by format. This league scores full PPR.
RECEPTION_POINTS = {"pts_ppr": 1.0, "pts_half_ppr": 0.5, "pts_std": 0.0}

# Rescale every source to a common season length before blending. Disabled,
# and the reason matters: the 2026 season is 17 games played across an
# 18-week schedule. ESPN's games field reads 17 (games) while Sleeper's reads
# 18 (weeks) — different fields, not different assumptions. Both already
# project the same 17-game season, so normalizing on those numbers would
# apply a bogus ~6% haircut to every Sleeper player.
#
# It would also erase real information: ESPN marks genuinely injured players
# with fewer games, and scaling them back up to a full season would discard
# exactly the discount we want to keep.
#
# Set to an integer only if a future source truly projects a different
# season length.
NORMALIZE_GAMES = None

# Which adapters feed the blend. Order is cosmetic; the average is unweighted.
ACTIVE_SOURCES = ("sleeper", "espn")

# How much the final price trusts our own projections versus the market
# anchor: 1.0 is pure value-based drafting, 0.0 is pure ADP.
#
# Pure VBD systematically underprices stars, because real auctions are
# top-heavy in a way the arithmetic isn't — managers overpay for elite
# production out of roster-construction anxiety. Leaning slightly toward the
# market keeps the board honest about what a player will actually cost
# without surrendering the edge that having your own numbers provides.
DEFAULT_STICKINESS = 0.7

# Keepers. Each team holds two players over at twice what they paid for
# them, which is the single largest distortion on this board: 24 players
# leave the auction along with the money that would have bought them, and
# because people keep bargains the pool loses more value than it loses
# money. What is left over has to be absorbed by everyone still available.
KEEPER_MULTIPLIER = 2.0
KEEPERS_PER_TEAM = 2

# What an unknown keeper is assumed to cost his owner, and what he is
# assumed to actually be worth on this board.
#
# These two numbers are the only fitted values in the project, and they
# are fitted to observed sale prices rather than to taste: at $10 cost /
# $25 value they reproduce a league-wide multiplier of x1.22, which is
# what the 2026 draft-room reports imply (Gibbs and Bijan going mid-to-
# high 60s against a raw board value of ~$54, Chase and Nacua high 50s
# against ~$48). Every real keeper entered replaces one assumed pair, so
# the fitted portion shrinks as draft day approaches.
ASSUMED_KEEPER_COST = 10.0
ASSUMED_KEEPER_VALUE = 25.0

# Without a superflex slot the 2QB ADP no longer describes the market, so
# the market column follows the scoring format instead.
ADP_FOR_SCORING = {
    "pts_ppr": "adp_ppr",
    "pts_half_ppr": "adp_half_ppr",
    "pts_std": "adp_std",
}


@dataclass(frozen=True)
class League:
    teams: int = 12
    budget: int = 200
    roster_spots: int = 18

    # Which Sleeper stat keys to read. pts_ppr is genuinely PPR-scored:
    # verified Nacua at 312.5 ppr vs 205.5 std on 107 receptions.
    scoring_key: str = "pts_ppr"
    adp_key: str = "adp_2qb"  # ADP from real 2QB/superflex drafts

    # Dedicated starting slots per team.
    dedicated: dict = field(
        default_factory=lambda: {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
    )

    # Flex slots per team and what may fill them.
    flex: int = 2
    flex_eligible: tuple = ("RB", "WR", "TE")
    superflex: int = 1
    superflex_eligible: tuple = ("QB", "RB", "WR", "TE")

    # Players each team holds over from last season at twice what they
    # paid. Set to 0 for a redraft league, which turns keeper inflation
    # off entirely rather than assuming slots nobody is going to fill.
    keepers_per_team: int = KEEPERS_PER_TEAM

    # How many players past the starter cutoff to median when setting
    # replacement level. Smooths single-player noise without over-smoothing
    # across a real talent cliff.
    replacement_window: int = 6

    @property
    def positions(self) -> tuple:
        return ("QB", "RB", "WR", "TE")

    @property
    def total_money(self) -> int:
        """Every dollar in the league."""
        return self.teams * self.budget

    @property
    def total_roster_spots(self) -> int:
        return self.teams * self.roster_spots

    @property
    def discretionary(self) -> int:
        """Money that actually bids on talent.

        Every rostered player costs at least $1, so one dollar per roster
        spot is locked up before bidding starts and cannot chase value.
        """
        return self.total_money - self.total_roster_spots

    @property
    def starters_per_team(self) -> int:
        return sum(self.dedicated.values()) + self.flex + self.superflex

    @property
    def total_starters(self) -> int:
        return self.starters_per_team * self.teams

    @property
    def max_opening_bid(self) -> int:
        """Most you can bid while still affording $1 for every other spot."""
        return self.budget - (self.roster_spots - 1)

    def describe(self) -> str:
        slots = ", ".join(f"{n}{p}" for p, n in self.dedicated.items() if n)
        parts = [slots] if slots else []
        if self.flex:
            parts.append(f"{self.flex}FLEX")
        if self.superflex:
            parts.append(f"{self.superflex}SF")
        return (
            f"{self.teams}-team | ${self.budget} | {self.roster_spots} spots | "
            + ", ".join(parts)
        )

    @property
    def params(self) -> dict:
        """Flat form-field view of this league, for round-tripping to the UI."""
        return {
            "teams": self.teams,
            "budget": self.budget,
            "spots": self.roster_spots,
            "scoring": self.scoring_key,
            "qb": self.dedicated.get("QB", 0),
            "rb": self.dedicated.get("RB", 0),
            "wr": self.dedicated.get("WR", 0),
            "te": self.dedicated.get("TE", 0),
            "flex": self.flex,
            "sf": self.superflex,
            "keepers": self.keepers_per_team,
        }

    @classmethod
    def from_params(cls, params) -> "League":
        """Build a league from untrusted form input.

        Anything absent falls back to this league's defaults, so a partial
        query string is valid. Anything present must be sane — bad input
        raises ValueError for the caller to surface, rather than producing
        a board that is quietly priced on nonsense.
        """
        base = cls()

        def whole(key, default, low, high):
            raw = params.get(key)
            if raw is None or raw == "":
                return default
            try:
                number = int(raw)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be a whole number")
            if not low <= number <= high:
                raise ValueError(f"{key} must be between {low} and {high}")
            return number

        scoring = params.get("scoring") or base.scoring_key
        if scoring not in SCORING_KEYS:
            raise ValueError("unknown scoring format")

        superflex = whole("sf", base.superflex, 0, 5)
        league = cls(
            teams=whole("teams", base.teams, 2, 32),
            budget=whole("budget", base.budget, 10, 10000),
            roster_spots=whole("spots", base.roster_spots, 1, 60),
            scoring_key=scoring,
            adp_key="adp_2qb" if superflex else ADP_FOR_SCORING[scoring],
            dedicated={
                "QB": whole("qb", base.dedicated["QB"], 0, 10),
                "RB": whole("rb", base.dedicated["RB"], 0, 10),
                "WR": whole("wr", base.dedicated["WR"], 0, 10),
                "TE": whole("te", base.dedicated["TE"], 0, 10),
            },
            flex=whole("flex", base.flex, 0, 10),
            superflex=superflex,
            keepers_per_team=whole("keepers", base.keepers_per_team, 0, 10),
        )

        if league.starters_per_team == 0:
            raise ValueError("lineup needs at least one starting slot")
        if league.roster_spots < league.starters_per_team:
            raise ValueError(
                f"a {league.roster_spots}-man roster cannot hold "
                f"{league.starters_per_team} starters"
            )
        return league


LEAGUE = League()
