"""Auction valuation: what a player is worth in *this* league.

The whole model rests on one idea: a player's price comes from his points
above the last startable player at his position, not from his raw points.
That baseline — replacement level — is set entirely by league settings,
which is why a generic cheat sheet misprices a non-generic league.

Every function here is pure. No network, no files, no globals.
"""

from statistics import median

# Positions whose flex eligibility we resolve greedily.
NO_ADP = float("inf")


def allocate_starters(by_position: dict, league) -> dict:
    """Resolve how many of each position actually start league-wide.

    Dedicated slots are fixed by the rules. Flex and superflex slots are
    contested, so we assign them the way managers actually do: each open
    slot goes to whichever eligible position still has the best unclaimed
    player. Where those slots land is what sets replacement level.

    In a 3WR + 2FLEX league most flex spots resolve to wide receivers,
    which pushes WR replacement far deeper than in a 2WR league.
    """
    claimed = {
        position: league.dedicated.get(position, 0) * league.teams
        for position in league.positions
    }

    def best_available(eligible):
        options = [
            p for p in eligible if claimed[p] < len(by_position.get(p, []))
        ]
        if not options:
            return None
        return max(options, key=lambda p: by_position[p][claimed[p]]["pts"])

    for _ in range(league.flex * league.teams):
        winner = best_available(league.flex_eligible)
        if winner is None:
            break
        claimed[winner] += 1

    for _ in range(league.superflex * league.teams):
        winner = best_available(league.superflex_eligible)
        if winner is None:
            break
        claimed[winner] += 1

    return claimed


def replacement_levels(by_position: dict, starters: dict, window: int) -> dict:
    """Points a freely-available player at each position would produce.

    We take the median of a small window of players just past the starter
    cutoff rather than the single next player. One player's projection is
    noisy; the median of six is stable but still sits above any talent
    cliff further down the board.
    """
    levels = {}
    for position, players in by_position.items():
        if not players:
            levels[position] = 0.0
            continue

        cutoff = starters.get(position, 0)
        if cutoff >= len(players):
            levels[position] = players[-1]["pts"]
            continue

        sample = [p["pts"] for p in players[cutoff : cutoff + window]]
        levels[position] = median(sample)
    return levels


def compute_values(players: list, replacement: dict, league) -> list:
    """Convert points above replacement into dollars.

    Only players worth more than a freely-available alternative get real
    money; everyone else is a $1 roster filler. The discretionary pool is
    split in proportion to each player's share of total value, so prices
    sum to exactly the money the league can actually spend on talent.
    """
    pool = []
    for player in players:
        surplus = player["pts"] - replacement.get(player["pos"], 0.0)
        if surplus > 0:
            pool.append({**player, "vorp": surplus})

    total_vorp = sum(p["vorp"] for p in pool)
    if total_vorp <= 0:
        return []

    dollars_per_point = league.discretionary / total_vorp
    for player in pool:
        player["value"] = 1.0 + player["vorp"] * dollars_per_point

    pool.sort(key=lambda p: -p["value"])
    return pool


def price_curve(pool: list) -> list:
    """The descending ladder of dollar values this pool implies."""
    return sorted((p["value"] for p in pool), reverse=True)


def attach_market(pool: list, curve: list = None) -> list:
    """Estimate what the room will pay, then expose the gap.

    We re-deal a price curve in ADP order. The market and we disagree about
    *which* player deserves the third-highest price, not about how steep the
    curve is — so this holds both columns on the same total-dollar scale.

    Pass `curve` to deal a ladder computed elsewhere. That matters once hand
    edits exist: deriving the curve from an edited pool would let your own
    opinion inflate the market anchor, so raising one projection would drag
    unrelated players up with it. An anchor that moves when you pull on it
    is not an anchor.

    Players with no superflex ADP sort last; they are genuinely undrafted in
    most leagues, which is itself the signal.
    """
    if curve is None:
        curve = price_curve(pool)

    by_adp = sorted(
        pool, key=lambda p: (p["adp"] if p["adp"] is not None else NO_ADP, -p["value"])
    )

    # A pool can outgrow the curve when an edit lifts players above
    # replacement. Those extra players sit at the bottom of the ladder.
    tail = curve[-1] if curve else 1.0
    for index, player in enumerate(by_adp):
        price = curve[index] if index < len(curve) else tail
        player["market"] = price
        player["edge"] = player["value"] - price
    return pool


def assign_tiers(pool: list, positions, spread: float = 1.0) -> list:
    """Group each position into tiers, breaking where the drop is unusual.

    A tier break is a gap to the next player larger than mean + spread*sd
    of that position's gaps. Tiers matter more than ranks in an auction:
    within a tier you should chase whoever is cheapest, and the last player
    in a tier is where you stop bidding and wait.
    """
    for position in positions:
        ranked = sorted(
            [p for p in pool if p["pos"] == position], key=lambda p: -p["pts"]
        )
        if not ranked:
            continue

        gaps = [
            ranked[i]["pts"] - ranked[i + 1]["pts"] for i in range(len(ranked) - 1)
        ]
        if gaps:
            mean_gap = sum(gaps) / len(gaps)
            variance = sum((g - mean_gap) ** 2 for g in gaps) / len(gaps)
            threshold = mean_gap + spread * (variance**0.5)
        else:
            threshold = float("inf")

        tier = 1
        for i, player in enumerate(ranked):
            player["pos_rank"] = i + 1
            player["tier"] = tier
            if i < len(gaps) and gaps[i] > threshold:
                tier += 1
    return pool


def keeper_cost(paid: float, multiplier: float = None) -> float:
    """What a kept player actually costs his owner this year."""
    from config import KEEPER_MULTIPLIER

    mult = KEEPER_MULTIPLIER if multiplier is None else multiplier
    return float(paid) * mult


def split_keepers(pool: list, keepers: dict) -> tuple:
    """Partition the priced pool into who is biddable and who is held.

    Returns (biddable, held, unmatched). Unmatched keys are reported
    rather than dropped: a keeper you typed wrong is a keeper the board
    silently fails to account for, and you would not find out until the
    prices were already wrong.
    """
    if not keepers:
        return list(pool), [], []

    held, biddable = [], []
    for player in pool:
        entry = keepers.get(f"{player['pos']}|{player['name']}")
        if entry is None:
            biddable.append(player)
        else:
            held.append({
                **player,
                "paid": float(entry.get("paid", 0.0)),
                "cost": keeper_cost(entry.get("paid", 0.0)),
                "mine": bool(entry.get("mine")),
                "kept": True,
            })

    seen = {f"{p['pos']}|{p['name']}" for p in held}
    unmatched = sorted(k for k in keepers if k not in seen)
    return biddable, held, unmatched


def keeper_inflation(held: list, league, known_only: bool = False) -> dict:
    """How much every remaining price has to rise once keepers are gone.

    Prices are `$1 + surplus`, so the $1 floor is untouchable — every
    roster spot needs one regardless. Inflation therefore acts on the
    surplus only:

        multiplier = money left over the floor / surplus left on the board

    Keeping a bargain removes more surplus than money, which drives the
    ratio above 1. This is why the effect is felt almost entirely at the
    top: a 22% lift is +$12 on a $54 player and +$1 on a $5 one.

    Slots we know nothing about are still counted, using the assumed
    cost/value pair from config, because pretending 22 unknown keepers
    do not exist understates every price on the board. Pass
    known_only=True to model just the keepers actually entered.
    """
    from config import ASSUMED_KEEPER_COST, ASSUMED_KEEPER_VALUE

    total_slots = getattr(league, "keepers_per_team", 0) * league.teams
    known = len(held)
    assumed = 0 if known_only else max(0, total_slots - known)

    # A redraft league has no keepers to model, and no board to inflate.
    if total_slots == 0 and not held:
        return {
            "multiplier": 1.0, "known": 0, "assumed": 0, "slots": 0,
            "money_out": 0.0, "surplus_out": 0.0,
            "money_left": float(league.discretionary),
            "surplus_left": float(league.discretionary),
        }

    money_out = sum(p["cost"] for p in held) + assumed * ASSUMED_KEEPER_COST
    # Surplus, not price: the $1 floor leaves with the roster spot it
    # was reserved for, so it cancels on both sides of the ratio.
    surplus_out = (
        sum(max(0.0, p["price"] - 1.0) for p in held)
        + assumed * max(0.0, ASSUMED_KEEPER_VALUE - 1.0)
    )

    spots_left = league.total_roster_spots - (known + assumed)
    money_left = league.total_money - money_out - spots_left
    surplus_left = league.discretionary - surplus_out

    if surplus_left <= 0 or money_left <= 0:
        multiplier = 1.0
    else:
        multiplier = money_left / surplus_left

    return {
        "multiplier": multiplier,
        "known": known,
        "assumed": assumed,
        "slots": total_slots,
        "money_out": money_out,
        "surplus_out": surplus_out,
        "money_left": money_left,
        "surplus_left": surplus_left,
    }


def apply_inflation(pool: list, multiplier: float) -> list:
    """Re-price the biddable pool for a shrunken auction.

    Affine, not linear: the $1 floor stays put and only the surplus
    above it scales. Value, market and price all move together so that
    Edge keeps meaning the same thing in the same units.
    """
    if multiplier == 1.0:
        return pool
    for player in pool:
        for key in ("value", "market", "price"):
            if key in player:
                player[key] = 1.0 + (player[key] - 1.0) * multiplier
        if "edge" in player:
            player["edge"] = player["value"] - player["market"]
    return pool


def collect_fillers(by_position: dict, pool: list, positions) -> list:
    """Everyone the model prices at exactly $1.

    A player at or below replacement has no surplus, so `compute_values`
    has nothing to say about him. But "worth a dollar" and "does not
    exist" are different claims, and the last third of an auction is
    spent buying these players — 84 of this league's 216 roster spots go
    to them. Dropping them off the board means a nomination you cannot
    look up.

    They carry no tier. Below replacement there is no meaningful gap to
    break on, and inventing tiers there would imply a structure the
    projections do not support.
    """
    priced = {(p["pos"], p["name"]) for p in pool}
    fillers = []

    for position in positions:
        ranked = sorted(
            (p for p in by_position.get(position, [])
             if (position, p["name"]) not in priced),
            key=lambda p: -p["pts"],
        )
        offset = sum(1 for p in pool if p["pos"] == position)
        for i, player in enumerate(ranked, start=offset + 1):
            fillers.append({
                **player,
                "vorp": 0.0,
                "value": 1.0,
                "market": 1.0,
                "price": 1.0,
                "edge": 0.0,
                "pos_rank": i,
                "tier": None,
                "filler": True,
            })

    fillers.sort(key=lambda p: -p["pts"])
    return fillers


def positional_spend(pool: list, positions) -> dict:
    """Total dollars and player count the model assigns to each position.

    This is the budget guide: it says what share of league money the format
    itself pushes toward each position, before anyone starts overbidding.
    Reads the final price, so it reflects the stickiness setting.
    """
    summary = {}
    for position in positions:
        members = [p for p in pool if p["pos"] == position]
        summary[position] = {
            "dollars": sum(p.get("price", p["value"]) for p in members),
            "count": len(members),
        }
    return summary


def apply_stickiness(pool: list, weight: float) -> list:
    """Pull each price toward the market anchor.

    Pure value-based drafting answers an economic question — what is this
    production worth. The market answers a behavioral one — what will people
    bid. Neither is wrong, and a weighted blend beats either alone: it keeps
    your projections in charge while refusing to claim a player costs $42
    when the room will not let him go under $50.

    Both input curves already sum to the same total, so any weighting of
    them sums to it too. No renormalization needed.
    """
    weight = max(0.0, min(1.0, weight))
    for player in pool:
        player["price"] = weight * player["value"] + (1.0 - weight) * player["market"]
    return pool


def build_board(
    by_position: dict,
    league,
    stickiness: float = None,
    market_curve: list = None,
    keepers: dict = None,
) -> dict:
    """Run the full pipeline and return the board plus its diagnostics.

    `market_curve` lets a caller supply the ladder the market column is dealt
    from — pass the curve of an unedited board so hand-edited projections
    cannot move the anchor they are being compared against.

    Keepers are removed *after* replacement level is set, deliberately.
    A kept player is still on a roster and still in a starting lineup, so
    league-wide starter demand — and therefore replacement level — is
    exactly what it would be without keepers. What changes is only which
    players you can bid on and how much money is chasing them.
    """
    from config import DEFAULT_STICKINESS

    weight = DEFAULT_STICKINESS if stickiness is None else stickiness

    starters = allocate_starters(by_position, league)
    replacement = replacement_levels(
        by_position, starters, league.replacement_window
    )

    everyone = [p for bucket in by_position.values() for p in bucket]
    pool = compute_values(everyone, replacement, league)

    # Captured before keepers and before inflation, and handed back so a
    # caller can pin a later board to it. Taking the ladder off a finished
    # board would re-inflate an already-inflated curve — the anchor would
    # drift by the multiplier every time an edit triggered a re-price.
    curve = price_curve(pool)

    pool = attach_market(pool, market_curve)
    pool = apply_stickiness(pool, weight)
    pool = assign_tiers(pool, league.positions)

    # Fillers are resolved before the keeper split so that keeping a $1
    # player works. He is not in the priced pool at all, and searching
    # only that pool would report him as an unmatched name while quietly
    # failing to deduct what he costs his owner.
    fillers = collect_fillers(by_position, pool, league.positions)
    biddable, held, unmatched = split_keepers(pool + fillers, keepers)
    pool = [p for p in biddable if not p.get("filler")]
    fillers = [p for p in biddable if p.get("filler")]

    inflation = keeper_inflation(held, league)
    pool = apply_inflation(pool, inflation["multiplier"])
    apply_inflation(held, inflation["multiplier"])

    pool.sort(key=lambda p: -p["price"])
    held.sort(key=lambda p: -p["price"])

    # Fillers are collected after every dollar figure is settled and are
    # never fed back in. Replacement, the market curve, tiers and spend
    # all stay computed from the priced pool alone, so showing the $1
    # tier cannot move a single price on the board above it.
    return {
        "players": pool,
        "fillers": fillers,
        "curve": curve,
        "keepers": held,
        "unmatchedKeepers": unmatched,
        "inflation": inflation,
        "starters": starters,
        "replacement": replacement,
        "spend": positional_spend(pool, league.positions),
        "stickiness": weight,
    }
