# 2026 Superflex Auction Board

Auction dollar values computed for **this** league, not a generic one.

```
12 teams | $200 budget | 18 roster spots | no K/DST
1 QB · 2 RB · 3 WR · 1 TE · 2 FLEX (R/W/T) · 1 SUPERFLEX (Q/R/W/T)
2 keepers per team, held at 2x the price paid
Full PPR · Yahoo online auction
```

## Use it

Two front ends over the same engine.

**Flask app** — league settings are editable and the board re-prices live:

```bash
python3 app.py                # http://127.0.0.1:5000
```

**Static file** — no server, one self-contained HTML file:

```bash
python3 build.py              # build from cached projections
python3 build.py --refresh    # re-pull from Sleeper (do this draft morning)
```

Outputs `out/sheet.html` and `out/values.csv`.

```bash
python3 -m pytest tests/ -q   # 204 tests
```

Both pages filter by position, search by name, sort on any column, and mark
players sold on click — persisted to localStorage, so a mid-draft refresh
doesn't lose the board.

### The $1 tier

All 587 projected players are on the board, not just the 132 the model
prices above a dollar. Everyone at or below replacement is worth exactly
$1 by the math, but "worth a dollar" and "does not exist" are different
claims — and **84 of this league's 216 roster spots get filled with $1
players**, which is most of the back half of the draft. A nomination you
can't look up is a real problem at the table.

They render dim, with a blank tier cell, below the priced players. Uncheck
**show $1** to collapse back to the 132 that cost real money.

The $1 tier is a strictly separate list (`board["fillers"]`), collected
after every dollar figure is settled and never fed back in. Replacement,
the market curve, tiers and spend are all computed from the priced pool
alone, so showing these players cannot move a single price above them —
`tests/test_value.py::TestFillers` pins that.

Tagging works on them, which is the point: a $1 gem is exactly the kind of
thing worth marking. And editing a filler's projection above replacement
promotes him into the real pool automatically — hand edits are applied
before valuation runs, so he picks up a tier, a rank and a genuine price,
and whoever he displaced drops to $1.

### Gems and fades

Each row carries two toggles. `◆` marks a **gem** — someone you expect to
beat his price. `▼` marks a **fade** — someone you don't want, and therefore
someone worth nominating early while the room still has money. They're
mutually exclusive; clicking the active one clears it.

Neither tag touches the valuation. They colour the row and drive the two
filter buttons beside the position filters. If you genuinely think a player
is worth more, edit his projected points instead — that flows through the
real math rather than sitting beside it.

Selecting **Fades** sorts by market price descending, because that is your
nomination order: the most expensive player you don't want, thrown out first.
The header reports the total market value of everything you've faded — how
much opponent money is on the table if the room bids those players up.

### Keepers, and why the top of the board is not $54

Each team holds two players over at twice what they paid. That is the
single largest distortion here, and it is the reason a raw VBD board
reads low at the top: 24 players leave the auction along with the money
that would have bought them, and because people keep **bargains**, the
pool loses more value than it loses money. Whatever is left has to be
absorbed by everyone still available.

```
inflation = money left over the $1 floors / surplus left on the board
```

Prices are `$1 + surplus`, and every roster spot needs its dollar
regardless, so inflation acts on the surplus only. That is why it is felt
almost entirely at the top:

| Board | Inflated | Change |
|---|---|---|
| $54 | $66 | **+$12** |
| $16 | $19 | +$3 |
| $5 | $6 | +$1 |

Which matches what this league actually pays. Against draft-room reports
of Gibbs and Bijan going mid-to-high 60s and Chase and Nacua high 50s,
the modelled multiplier is **x1.219**:

| Player | Raw board | Modelled | Reported |
|---|---|---|---|
| Jahmyr Gibbs | $54 | **$66** | ~$66 |
| Bijan Robinson | $54 | **$65** | ~$66 |
| Puka Nacua | $49 | **$59** | ~$58 |
| Ja'Marr Chase | $47 | **$57** | ~$58 |

This is derived, not fitted to those four players. A "+$10 at the top"
fudge factor would match the same numbers and then be wrong the moment
the league's keeper situation changed.

**Entering keepers.** Click `K` on any row and type what was paid — the
cost is twice that, computed from `KEEPER_MULTIPLIER`. Shift-Enter
records an *opponent's* keeper: it feeds league inflation but leaves your
budget alone. Kept players leave the biddable board, keep a `KEPT $4→$8`
badge, and are filterable with the `K Kept` button. Click `K` again to
release.

The header then reports what you actually have — `$184 for 16 spots`
rather than the league's $200 for 18 — along with the multiplier and how
much of it is still guesswork.

**The 22 you don't know.** Unknown keeper slots are assumed at
`ASSUMED_KEEPER_COST` / `ASSUMED_KEEPER_VALUE` in `config.py`. Those two
numbers are the only fitted values in the project, and every real keeper
you enter replaces one assumed pair, so the fitted portion shrinks as
draft day approaches. Set `keepers=0` (or `League(keepers_per_team=0)`)
to switch the whole mechanism off for a redraft league.

One honest caveat: an unknown keeper is still *listed*, because we cannot
name which player he is. His surplus is therefore counted twice — once as
money removed, once as a player you can still see a price for. The gap is
exactly the assumed surplus, it closes as you enter real keepers, and
`test_assumed_keepers_leave_a_known_overhang` measures it rather than
letting it hide.

### Where your work is stored

`data/rankings.json` holds your tags, hand-edited projections, and keepers,
written on every change. It's the one file here that cannot be recomputed,
so:

- writes are atomic (temp file plus `os.replace`), leaving the previous
  version intact if a write fails mid-flight
- a damaged file is reported, never overwritten, so you can repair it by hand
- a failed save reverts the toggle and shows an error — the board never
  claims to have saved something it didn't
- it sits outside the gitignored `data/raw/`, so you can commit it and get
  version history on your own reads

```json
{
  "season": 2026,
  "updated": "2026-08-18T02:29:15+00:00",
  "tags": { "RB|Jahmyr Gibbs": "gem", "QB|Drake Maye": "fade" },
  "projections": { "WR|Puka Nacua": 350.0 },
  "keepers": {
    "QB|Jaxson Dart":   { "paid": 4, "mine": true },
    "WR|Luther Burden": { "paid": 4, "mine": true }
  }
}
```

Keepers store the **price paid**, not this year's cost, so the doubling
rule lives in one place and a league that changes it needs one edit rather
than a re-entry of every keeper. A keeper key that matches no player is
reported on the board in red, never silently ignored — a swallowed typo
would misprice every player at once.

Because the server owns this, any browser at any address sees the same board.
That matters more than it sounds: `localhost:7575` and `127.0.0.1:7575` are
different browser-storage origins, so anything kept in localStorage is
invisible between them.

**Sold marks stay in localStorage** on purpose — they're per-draft, and
persisting them would mean next week's mock starts with last week's players
crossed off. They are therefore per-browser and per-address.

**The static sheet is a snapshot.** It bakes in whatever was in
`rankings.json` at build time and falls back to localStorage for changes,
because it has no server to save to. The Flask app is the live tool.

Only the Flask app can re-price. Change teams, budget, roster spots, scoring,
or any lineup slot and every value updates in about 2ms — the projections are
memoized per process, so only the math re-runs. Dropping the superflex slot,
for instance, moves QB from 22.5% of league money to 6.1%.

### Endpoints

| Route | Returns |
|-------|---------|
| `GET /` | the board with the settings form |
| `GET /api/board?teams=&budget=&spots=&scoring=&qb=&rb=&wr=&te=&flex=&sf=&keepers=` | priced board as JSON; 400 with a message on bad settings |
| `POST /api/board` | same, but accepts `{settings, overrides, stickiness}` in a JSON body |
| `GET /api/rankings` | your saved tags and projections |
| `POST /api/rankings/tag` | `{key, tag}` — tag is `"gem"`, `"fade"`, or `null` to clear |
| `POST /api/rankings/projection` | `{key, points}` — `null` restores the blend |
| `POST /api/rankings/keeper` | `{key, paid, mine}` — `paid` is the acquisition price; `null` releases him |
| `POST /api/rankings/clear` | `{field}` — `"tags"`, `"projections"` or `"keepers"` |
| `GET /api/health` | liveness |

Any omitted parameter falls back to the configured league, so
`/api/board?wr=4` is valid.

## Where the numbers come from

| Input | Source |
|-------|--------|
| Projections A | **RotoWire**, via Sleeper's public API (every record carries `company: "rotowire"`) |
| Projections B | **ESPN**, via their public fantasy API |
| Superflex ADP | **Sleeper** `adp_2qb` — average draft position from real 2QB/superflex drafts |
| Injury status, team | Sleeper |
| **Points** | **Computed here** from each source's counting stats — see `scoring.py` |
| **Dollar values** | **Computed here** — see `value.py`. No site publishes auction values for this roster shape, which is why this project exists. |

FantasyPros is deliberately absent: their public pages expose only 10 players
per position and `api.fantasypros.com` returns 403 without a key. Adding them
means obtaining a key and writing one more adapter in `sources.py`.

### Why the blend uses counting stats, not published point totals

Each source publishes totals under its own league rules — RotoWire and ESPN
differ on Puka Nacua by 44 points, most of which is scoring settings rather
than disagreement about Nacua. Averaging those totals would blend two
rulebooks. So every adapter returns raw stats (attempts, yards, TDs,
receptions, fumbles) and `scoring.py` applies one formula.

Two things follow. Changing scoring format genuinely re-scores the board
rather than swapping a precomputed column. And the rules in `config.py` are
**Yahoo's defaults**, including the interception penalty of −1 rather than
the −2 most sites assume — verified by reproducing RotoWire's own `pts_ppr`
from their counting stats, exact to 0.000 for nearly all 561 players.
`tests/test_sources.py` keeps that honest.

### What the two sources disagree about

ESPN is systematically more bullish, and not evenly — it likes running backs
considerably more than RotoWire does:

| Money share | RotoWire alone | ESPN alone | Blended |
|-------------|---------------|-----------|---------|
| QB | 22.5% | 18.9% | 22.4% |
| RB | 26.3% | 35.2% | 32.4% |
| WR | 41.6% | 36.0% | 36.1% |
| TE | 6.2% | 6.3% | 5.5% |

ESPN projects more production in *fewer* games — it models near-full-health
outcomes while RotoWire discounts volume for injury and rest risk. That gap
is widest for backs with injury history (Breece Hall: 38 receptions per
RotoWire, 52 per ESPN). The blend splits the difference, which is the point.

Note the season-length trap this creates. ESPN's games field reads 17 and
Sleeper's reads 18, but the 2026 season is 17 games across an 18-week
schedule — those are different fields, not different assumptions. Rescaling
on them would apply a bogus 6% haircut to every RotoWire player, so
`NORMALIZE_GAMES` is off. See the comment in `config.py`.

### Coverage

Of 587 blended players, 406 appear in both sources. **All 132 players priced
above $1 are two-sourced** — a test enforces this. Single-source players are
kept, never silently dropped, and marked `1src` on the board. That flag
matters most in the $1 tier, where a lot of the depth is one-sourced.

## Why not just use a downloaded cheat sheet

Every free auction sheet is priced for 1QB / 2RB / 2WR / 1TE / 1FLEX + K + DST.
Replacement level — the last startable player at a position — is what sets
prices, and this league moves it substantially:

| Pos | Starts league-wide | Replacement | Share of league money |
|-----|-------------------|-------------|----------------------|
| QB  | 24                | ~QB25       | 22.5%                |
| RB  | 30                | ~RB31       | 26.3%                |
| WR  | **53**            | ~WR54       | **41.6%**            |
| TE  | 13                | ~TE14       | 6.2%                 |

Three starting WRs plus two flex spots pull 17 of the 24 league-wide flex
slots into wide receivers. That pushes WR replacement down to WR54 and makes
WR the largest money sink — while holding QB to ~22%, well under the 35–45%
that generic superflex advice prescribes.

## How a price is computed

1. **Allocate starters greedily.** Dedicated slots are fixed; each flex and
   superflex slot goes to whichever eligible position still has the best
   unclaimed player. Where those slots land sets replacement level.
2. **Set replacement level** as the median of the six players just past each
   position's starter cutoff. A single player's projection is noisy; six is
   stable but still above any talent cliff further down.
3. **VORP** = projected points − replacement points. Anyone at or below
   replacement is a $1 roster filler — still listed, just priced at the
   floor and excluded from the dollar split.
4. **Price** = $1 + VORP × (discretionary ÷ total VORP), where discretionary
   is $2,400 − $216, since every roster spot locks up a dollar before bidding.
   Board prices plus $1 fillers sum to exactly the $2,400 in the league.
5. **Keepers leave**, after replacement level is set and never before — a
   kept player still starts, so league-wide starter demand is unchanged.
   What changes is who you can bid on and how much money is chasing them.
6. **Market price** re-deals the same price curve in superflex-ADP order.
   Both columns sit on the same total-dollar scale, so **Edge = My$ − Mkt$**
   is a like-for-like comparison: positive means target him, negative means
   let the room have him.
7. **Tiers** break where the gap to the next player exceeds mean + 1 sd of
   that position's gaps.

## Layout

| File | Role |
|------|------|
| `config.py` | League settings, scoring rules, active sources, param validation |
| `rankings.py` | Durable store for your tags and edited projections |
| `sources.py` | One adapter per projection source; caching and memoization |
| `scoring.py` | Counting stats → points under one rulebook |
| `blend.py` | Name normalization, cross-source join, averaging, coverage |
| `fetch.py` | Thin orchestrator over the adapters |
| `value.py` | Valuation math, pure functions, no I/O |
| `templates/board.html` | The page — shared by both front ends |
| `render.py` | Payload builder, Jinja render, CSV output |
| `build.py` | CLI entry point (static) |
| `app.py` | Flask entry point (live) |
| `tests/test_value.py` | Invariants on the math |
| `tests/test_app.py` | Settings round trip, bad-input rejection |
| `tests/test_blend.py` | Scoring formulas, name matching, blend arithmetic |
| `tests/test_sources.py` | Integration checks against cached real data |

Adding a source means writing one function in `sources.py` that returns
counting stats and adding its name to `ACTIVE_SOURCES`. Nothing downstream
changes.

`value.build_board(by_position, league)` takes the league as an argument and
touches nothing else, so serving it from Flask required no change to the
engine at all — a request just builds a different `League` and re-runs it.
The settings form and the static build render the same template, so the two
front ends cannot drift apart.

## Caveats

- **Two sources, not many.** RotoWire and ESPN. Where the model disagrees
  hard with the market, the market sometimes knows about a job battle the
  projections don't. Treat large Edge values as questions, not answers.
- **Verify the scoring rules in `config.py` against your league.** They are
  Yahoo defaults; a league that scores interceptions at −2 or awards 6-point
  passing touchdowns will price quarterbacks differently.
- **Superflex ADP is a proxy for auction price**, not observed auction data.
  It captures ordering well and absolute dollars less well.
- **The market overpays at the top** in real auctions, more than a re-dealt
  curve implies. Expect elite players to cost a few dollars above Mkt$.
- **Keeper inflation is only as good as the keepers you have entered.**
  With 2 of 24 known, 22 slots are running on an assumption calibrated to
  last year's sale prices. Enter opponents' keepers as you learn them.
- Values assume every team plays the superflex slot with a QB, which is
  correct whenever a rostered QB2 outscores a WR3 — nearly always.
