# 2026 Draft Plan

12-team superflex auction · 1QB, 2RB, 3WR, 1TE, 2FLEX, 1SF · 18 spots · full PPR
Two keepers per team at 2x the price paid.

Numbers below come from `python3 app.py` (the live board), not from memory.
Re-read them draft morning after `python3 build.py --refresh`.

---

## 1. Where you actually stand

| | |
|---|---|
| Keeper | **Jaxson Dart** — paid $2, costs **$4**, board value **$29** |
| Keeper surplus | **+$25** |
| Second keeper slot | **empty** |
| Auction budget | **$196** for **17 spots** |
| Max opening bid | **$180** |
| League inflation | **x1.227** (1 keeper known, 23 assumed) |

**Dart is the whole plan's foundation.** A QB8 for $4 in a superflex league
means your hardest roster problem is already solved. Everyone else at the
table will spend $25-55 on their second quarterback. You will spend that
money on flex production instead.

Do not let this get lost: the $25 of keeper surplus is real, and it is the
one structural advantage you carry into the room.

---

## 2. The one structural fact about this league

Three dedicated WRs plus two flex pull **17 of the 24 league-wide flex
slots to wide receiver**. That drags WR replacement down to about WR51 and
makes WR the largest money sink, while holding QB to 22% — well under the
35-45% generic superflex advice prescribes.

| Pos | Starts league-wide | Replacement | Share of money | Your share of $196 |
|-----|-------------------|-------------|----------------|--------------------|
| QB  | 24 | 221.1 pts | 22.4% | $44 |
| RB  | 34 | 150.3 pts | 33.8% | $66 |
| WR  | 50 | 156.2 pts | 37.1% | **$73** |
| TE  | 12 | 156.5 pts | 6.7%  | $13 |

**But you should not spend $44 on QB.** Dart covers the superflex slot at
$4. Budget **$18-25 for one more quarterback** and push the freed ~$20
into RB and WR.

Working targets: **QB $22 · RB $75 · WR $85 · TE $14**

---

## 3. The tier structure is the real map

Tiers break where the gap to the next player is unusually large. This
board is violently top-heavy and then completely flat:

| Pos | T1 | T2 | T3 | T4 |
|-----|----|----|----|----|
| RB | 2 players ($65-67) | 1 ($55) | 1 ($50) | **33 players ($2-42)** |
| WR | 1 ($60) | 1 ($57) | 2 ($48-52) | 1 ($43) |
| TE | 2 ($31-33) | **13 players ($2-22)** | — | — |
| QB | 1 ($55) | **25 players ($7-40)** | — | — |

Read that RB row again. **RB4 through RB36 are one undifferentiated
tier** — Travis Etienne at $25 and Jordan Mason at $2 sit in the same
group. There is no cliff to fall off, which means there is no urgency and
no reason to panic-bid into the middle.

The rule this produces:

> **Win one of the top four backs, or wait. Do not pay $35 for the
> 12th-best RB when the tier runs another 24 players deep.**

Same logic at QB: after Josh Allen it is one tier of 25. Same at TE:
after Bowers and McBride it is one tier of 13.

---

## 4. Buy list — where the model disagrees with the room

**Bargains** (board value above market — target these):

| Player | | Board | Market | Edge |
|---|---|---|---|---|
| Amon-Ra St. Brown | WR4 | $48 | $43 | **+7** |
| Derrick Henry | RB9 | $37 | $32 | **+7** |
| Jeremiyah Love | RB12 | $35 | $30 | **+7** |
| Tyler Shough | QB19 | $18 | $13 | **+7** |
| Malik Willis | QB21 | $13 | $8 | **+7** |
| Chase Brown | RB8 | $37 | $33 | +6 |
| Travis Etienne | RB17 | $25 | $21 | +6 |
| Matthew Stafford | QB15 | $24 | $20 | +6 |
| Alec Pierce | WR31 | $11 | $6 | +6 |
| Matthew Golden | WR39 | $6 | $2 | **+6** |

**Traps** (market above board value — let the room have them):

| Player | | Board | Market | Edge |
|---|---|---|---|---|
| Drake Maye | QB3 | $41 | $50 | **-13** |
| Colston Loveland | TE3 | $22 | $29 | -10 |
| Tyler Warren | TE4 | $20 | $27 | -10 |
| Dalton Kincaid | TE13 | $5 | $12 | -10 |
| Josh Allen | QB1 | $55 | $61 | -9 |
| Caleb Williams | QB13 | $29 | $36 | -9 |
| Joe Burrow | QB6 | $34 | $40 | -8 |
| Trey McBride | TE2 | $31 | $37 | -8 |

**Note the conflict in your own tags.** You have Colston Loveland and
Dalton Kincaid marked as gems, and both are among the four biggest traps
on the board (-10 each). That is not automatically wrong — you may know
something about their roles the projections don't — but it is worth
deciding on purpose rather than by accident. If you genuinely believe
them, raise their projected points and let the value flow through the
math instead of sitting beside it.

---

## 5. Three builds, all arithmetic-checked

### A — Two studs, cheap everywhere else

| Player | | $ |
|---|---|---|
| Jahmyr Gibbs | RB1 | 67 |
| Amon-Ra St. Brown | WR4 | 48 |
| Travis Etienne | RB17 | 25 |
| Tyler Shough | QB19 | 18 |
| Alec Pierce | WR31 | 11 |
| Matthew Golden | WR39 | 6 |
| **Total** | | **$175 on 6** |

Leaves **$21 for 11 spots** — only **$10** of real money after the $1
floors. Thin. This build lives or dies on the endgame.

### B — No stud, mid-tier volume

| Player | | $ |
|---|---|---|
| Amon-Ra St. Brown | WR4 | 48 |
| Derrick Henry | RB9 | 37 |
| Jeremiyah Love | RB12 | 35 |
| Matthew Stafford | QB15 | 24 |
| Alec Pierce | WR31 | 11 |
| Matthew Golden | WR39 | 6 |
| **Total** | | **$161 on 6** |

Leaves **$35 for 11 spots** — **$24** of real money. Comfortable.

Worth knowing: adding a *fourth* mid-tier back (Chase Brown $37) to this
build puts you at **$198 on 7 with 10 spots left — over budget.** Three
mid-tier RBs is the ceiling, not four.

### C — Bowers anchor  *(recommended)*

| Player | | $ |
|---|---|---|
| Jahmyr Gibbs | RB1 | 67 |
| Brock Bowers | TE1 | 33 |
| Travis Etienne | RB17 | 25 |
| Malik Willis | QB21 | 13 |
| Alec Pierce | WR31 | 11 |
| Matthew Golden | WR39 | 6 |
| **Total** | | **$155 on 6** |

Leaves **$41 for 11 spots** — **$30** of real money, the most flexible of
the three. Bowers is the only positional edge on the board that lasts all
season: TE1 at $33 against a 12-start position where the tier below him
runs 13 players deep.

The risk is WR. This build needs three receivers out of the $1-11 range,
which is exactly where the format says money should go. Watch that.

---

## 6. Nomination plan — $447 of bait

You have 15 fades. Nominate them **early, in descending market price**,
while the room still has money. Every dollar someone else spends on a
player you don't want is a dollar not bidding against you.

| Order | Player | Market |
|---|---|---|
| 1 | Bijan Robinson | $67 |
| 2 | Puka Nacua | $57 |
| 3 | Christian McCaffrey | $51 |
| 4 | **Drake Maye** | $50 |
| 5 | De'Von Achane | $38 |
| 6 | Jayden Daniels | $38 |
| 7 | Josh Jacobs | $29 |
| 8 | Breece Hall | $28 |

**Drake Maye is the single best nomination on the board.** He is your
fade *and* the largest trap in the data (-$13). Throwing him out early
costs someone $50 for $41 of production, and it drains a superflex rival.

Do not nominate a player you want. Obvious, and still the most common
in-room mistake.

---

## 7. The endgame — 11 spots at roughly $1

You will finish with 10-11 roster spots and single-digit dollars. That is
not a failure state, it is the design: **84 of this league's 216 roster
spots go to $1 players.** Know who you want before you get there.

Best available at $1 (all two-sourced):

| Pos | Targets |
|---|---|
| RB | Blake Corum (148), RJ Harvey (147), Rachaad White (147), Jacory Croskey-Merritt (144) |
| WR | Romeo Doubs (156), Jayden Higgins (154), Rashid Shaheed (145), Denzel Boston (138) |
| TE | Dallas Goedert (156), Brenton Strange (152), Hunter Henry (152) |
| QB | Fernando Mendoza (208), Aaron Rodgers (207), Jacoby Brissett (186) |

Romeo Doubs at $1 projects 156 points — the same as Dallas Goedert and
within a point of WR replacement level. The bottom of this board is not
empty.

---

## 8. Keeper targets for 2027

**Chris Bell** (WR, MIA) and **Elijah Arroyo** (TE, SEA):

| Player | | Pts | ADP | Price now | Keeps 2027 at |
|---|---|---|---|---|---|
| Chris Bell | WR103 | 64.3 | 251 | **$1** | **$2** |
| Elijah Arroyo | TE41 | 66.4 | 278 | **$1** | **$2** |

Both are two-sourced, both sit in the $1 tier, and both have an ADP past
250 — meaning they go undrafted in most leagues. In this one, that makes
them free.

**This is the cheapest keeper the rule permits.** A $1 acquisition keeps
at $2. If either breaks out, you are holding a starter for two dollars —
compare Dart, who at $4 is already the best value on your roster.

The asymmetry is the point: a $1 flier costs you one roster spot and one
dollar. If he busts you drop him. If he hits, you have a multi-year asset
at a price nobody can compete with. Buy both at $1-2 late; do not bid $6
for either, because the keeper option is only worth having while it's
nearly free.

**Reserve two of your last roster spots for this.** Not the last two
picks — spots you consciously protect.

> **Open question — needs your answer.** If you meant Bell and Arroyo as
> candidates for your *empty 2026 keeper slot* rather than 2027 stashes,
> tell me what you paid for each last year and I'll price it. Note that
> the second slot is currently earning you nothing: Dart's slot is worth
> +$25, and an empty one is worth $0.

---

## 9. Draft-morning checklist

- [ ] `python3 build.py --refresh` — re-pull projections
- [ ] `python3 app.py` — open http://127.0.0.1:7575
- [ ] Enter every opponent keeper you have learned (click `K`, Shift-Enter)
- [ ] Fill or consciously abandon your second keeper slot
- [ ] Re-read the tier table — it moves when projections move
- [ ] Resolve the Loveland / Kincaid gem-vs-trap conflict
- [ ] Confirm budget and max bid in the header before the first nomination

**The single highest-value thing you can do between now and draft day is
enter opponents' keepers.** 23 of 24 slots are currently running on an
assumption. Every real one you enter replaces a guess and sharpens every
price on the board.
