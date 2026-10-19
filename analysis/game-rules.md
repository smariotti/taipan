# Taipan (Apple II): recovered game rules

Recovered from `extracted/GAME_BASIC.txt`, the Applesoft program at `$4001`. BASIC line numbers are given as `Lnnnn` so each rule can be checked against the source.
This spec is the reference for `src/taipan/`.

## Conventions

- `R(x)` is the original's `FN R(X) = INT(RND * X)`, a random integer `0 <= n < x` (floor, so `R(0) = 0` and fractional `x` work).
  "1 in N chance" below means `R(N) == 0`.
- Money and cargo are whole numbers, except where a formula produces a fraction (debt and bank interest are truncated with `INT`).
- One voyage takes one month. `TI` counts months played and starts at 1.

## State

| Var | Meaning | Start |
|---|---|---|
| `CA` / `BA` / `DW` | cash / bank / debt to Elder Brother Wu | see start options |
| `SC` | ship capacity | 60 |
| `MW` | free hold space (`SC` − cargo − 10 × guns); can go negative (overloaded) | |
| `GN` | guns (each takes 10 hold units) | |
| `DM` | damage points; seaworthiness % = `100 − INT(DM/SC×100)` | 0 |
| `ST(1,j)` / `ST(2,j)` | warehouse / ship stock of good *j* | 0 |
| `WC` / `WS` | warehouse capacity 10,000 / units stored | |
| `LO` | location: 0 at sea, 1 Hong Kong, 2 Shanghai, 3 Nagasaki, 4 Saigon, 5 Manila, 6 Singapore, 7 Batavia | 1 |
| `MO`, `YE` | month, year | Jan 1860 |
| `LI` | paid Li Yuen for protection (0/1) | 0 |
| `BP` | pirate encounter odds (1 in `BP` per voyage) | see start options |
| `EC` | enemy ship toughness base | 20 |
| `ED` | enemy damage multiplier | 0.5 |
| `BL` | number of emergency loans taken | 0 |
| `BP%(port, good)` | base price table | below |

**Start options (L10150–L10170)**

1. Cash 400, debt 5,000, no guns, 60 free hold, pirates 1 in 10.
2. 5 guns, no cash, no debt, 10 free hold, pirates 1 in 7.

The player names their firm (max 22 characters; L10120–L10130).

## Goods and prices

Goods: 1 Opium, 2 Silk, 3 Arms, 4 General Cargo.

Base price table `BP%` (L10200):

| Good | HK | Shanghai | Nagasaki | Saigon | Manila | Singapore | Batavia |
|---|---|---|---|---|---|---|---|
| Opium | 11 | 16 | 15 | 14 | 12 | 10 | 13 |
| Silk | 11 | 14 | 15 | 16 | 10 | 13 | 12 |
| Arms | 12 | 16 | 10 | 11 | 13 | 14 | 15 |
| General | 10 | 11 | 12 | 13 | 14 | 15 | 16 |

- Each port visit (L2100): `price(j) = BP%(port,j) / 2 × (R(3)+1) × 10^(4−j)`.
  So opium is ×1000, silk ×100, arms ×10 and general cargo ×1, each with a random multiplier of 0.5, 1 or 1.5.
- Each new year (L1020): every `BP%` entry gains `R(2)` (0 or 1).
- Price event, 1 in 9 per visit (L2410–L2440): a random good either crashes to `INT(price/5)` or jumps to `price × (R(5)+5)` (×5 to ×9), 50/50.

## Arriving in port (L1010–L1030)

Only when arriving from a voyage, not at game start:

- Bank: `BA = INT(BA × 1.005)`. Debt: `DW = INT(DW × 1.1)`.
- `TI += 1`, the month advances, and January adds a year.
- New year: `EC += 10`, `ED += 0.5`, and the base prices drift (above).

Hong Kong runs the Hong Kong events and then the port events. Other ports run only the port events.

## Hong Kong events

**Li Yuen's donation (L1040–L1100).** Asked only if not protected and cash > 0.
- Amount: months 1–12: `R(CA/1.8)`. After month 12: `R(CA) + R(1000×TI) + 1000×TI`.
- Pay → protected (`LI = 1`) and cash drops by the amount.
- If that leaves cash ≤ 0: the player is asked whether Wu should cover the gap.
  - Yes: the shortfall is added to debt and cash is set to 0. Protection holds.
  - No: cash is set to 0 *and* protection is lost.

**Ship repair (L1120–L1160).** Offered when damaged.
- Rate `BR = INT((R(60×(TI+3)/4) + 25×(TI+3)/4) × SC/50)` per damage point. A full repair costs `BR×DM + 1`.
- The player names an amount ("all" = full repair, capped at cash). Damage repaired is `INT(amount/BR + 0.5)`, floored at 0.

**Wu's escort (L1210–L1240).** Flavor only: once per game, when debt ≥ 10,000 on arrival, Wu sends 50–149 braves to escort the player.

**Visiting Elder Brother Wu (L1310–L1430).** Optional each Hong Kong stay.
- Emergency loan, if cash, bank, all cargo (ship and warehouse) and guns are all zero: `BL += 1`, loan `INT(R(1500)+500)` against repayment `R(2000)×BL + 1500`. Refusing ends the game. Accepting skips the rest of Wu's business.
- Otherwise repay: allowed if debt and cash are both nonzero. "All" means `min(cash, debt)`. Any amount up to cash is accepted, so overpaying gives *negative* debt (an original quirk).
- Then borrow up to `2 × cash`.

**Cutthroats (L1460).** Checked only after a normal visit to Wu: not if the player declines to visit, and not after an emergency loan. Debt > 20,000 → 1 in 5 chance that 1–3 bodyguards are killed and all cash is stolen.

## Port events (every port, L1610–L2501)

In order:

1. **Bigger ship offer.** Cost `INT(1000 + R(1000×(TI+5)/6)) × (INT(SC/50)+1 if damaged else 1)`. Offered with a 1 in 4 chance if cash ≥ cost. Accepting gives +50 capacity, +50 free hold and repairs all damage.
2. **Gun offer.** Cost `INT(R(1000×(TI+5)/6) + 500)`. Offered with a 1 in 3 chance if cash ≥ cost. It needs 10 free hold.
3. **Opium seizure.** Outside Hong Kong, with opium aboard, 1 in 18: the opium is confiscated and the player is fined `R(CA/1.8)`.
4. **Warehouse theft.** Warehouse non-empty, 1 in 50: each good drops to `R(stock/1.8)`.
5. Prices are set for the visit (above).
6. **Protection lapse.** If protected, 1 in 20 per visit that it lapses.
7. **Li Yuen's summons.** If unprotected and outside Hong Kong, 3 in 4: a flavor message that Li Yuen wants to see the player in Hong Kong.
8. Price event, 1 in 9 (above).
9. **Mugging.** Cash > 25,000, 1 in 20: robbed of `R(CA/1.4)`.

## Trading menu (L2510–L2690)

| Key | Action | Where |
|---|---|---|
| B | Buy | any port |
| S | Sell | any port |
| Q | Quit trading, i.e. set sail | any port |
| T | Transfer cargo | Hong Kong only |
| V | Visit bank | Hong Kong only |
| R | Retire | Hong Kong only, when `CA + BA − DW ≥ 1,000,000` |

- **Buy:** the player can buy any amount they can afford. Hold space is *not* checked when buying, so free hold may go negative.
- **Sell:** up to the amount aboard.
- **Transfer:** for each good, first ship→warehouse (limited by free warehouse space; "all" is capped to that space), then warehouse→ship.
- **Bank:** deposit, then withdraw.
- Amount prompts accept a number, or "A" for all.
- **Sailing** is refused while the ship is overloaded (free hold < 0). The destination must be a different port.

## At sea (L3100–L3350)

In order:

1. **Pirates**, 1 in `BP`: `R(SC/10 + GN) + 1` ships, a normal fight (`F1 = 1`).
2. **Li Yuen's fleet**, 1 in `4 + 8×LI` (1 in 4 unprotected, 1 in 12 protected).
   - Protected: they let the player pass.
   - Otherwise: `R(SC/5 + GN) + 5` ships, a hard fight (`F1 = 2`).
3. **Storm**, 1 in 10.
   - 1 in 30 of those is a near-sinking. The ship then sinks (game over) if `R(DM/SC×3) ≠ 0`, so an undamaged ship never sinks.
   - Surviving a storm: 1 in 3 chance of being blown to a random other port.
4. Arrive at the destination.

After a fight the voyage continues at step 3, except as noted below.

## Combat (L5000–L5940)

**Setup.**
- Booty: `R(TI/4 × 1000 × SN^1.05) + R(1000) + 250`.
- Up to 10 enemy ships are on screen in slots 0–9. Each has hit points `R(EC)+20` and accumulated damage.
- At the top of each round, empty slots are refilled from the ships not yet shown.

**Each round:**

1. Seaworthiness = `100 − INT(DM/SC×100)`. At 0% the player is sunk (game over).
2. The player gives an order: **R**un, **F**ight or **T**hrow cargo.
   The original is real-time. The last order repeats if no key is pressed, and with no order at all the enemy just fires.
3. **Run.**
   - If the previous order was Run or Throw, the escape score `OK` grows by an increasing step `IK` (+1, +2, +3 …). Otherwise it resets to `OK = 3`, `IK = 1`.
   - Escape succeeds if `R(OK) > R(SN)`.
   - On failure, if more than 2 ships remain, 1 in 5 chance that `R(SN/2)+1` of them fall behind (removed).
4. **Fight** (needs guns): each gun fires at a random on-screen ship for `R(30)+10` damage. A ship sinks when damage > its HP.
   - Afterwards, if some but not all ships were sunk, at least 3 remain, and `R(S0) ≥ SN×0.6/F1` (`S0` = starting count): `R(SN/3/F1)+1` ships flee.
5. **Throw cargo:** jettison one good or everything (amount or "all").
   - If anything was thrown: `OK += thrown/10`, then an escape attempt is made straight away with that `OK`. There is no reset, so the leftover `OK` carries over, even from the previous fight's result code.
6. All enemies gone → victory: booty is added to cash.
7. **Enemy fire:** let `I = min(SN, 15)`.
   - If the player has guns and (`R(100)` < damage % or damage % > 80), a gun is destroyed instead (`I = 1`, +10 free hold).
   - Damage `DM += R(ED × I × F1) + I/2`.
   - In a normal fight only: 1 in 20 that Li Yuen's fleet arrives and drives the pirates off. This leads straight into a Li Yuen encounter: passage if protected, otherwise a Li Yuen fight.

**Outcomes.**
- Sunk: game over.
- Victory: booty, then continue to the storm check.
- Escaped: continue to the storm check.
- Driven off: Li Yuen encounter.

## End of game (L20000–L20190)

Ends when the player retires, is sunk, refuses Wu's emergency loan, or sinks in a storm.

- Net worth `= CA + BA − DW`.
- Score `= INT(net / 100 / TI^1.1)`.

| Score | Rating |
|---|---|
| ≥ 50,000 | Ma Tsu |
| 8,000–49,999 | Master Taipan |
| 1,000–7,999 | Taipan |
| 500–999 | Compradore |
| < 500 | Galley Hand |

- Score 0–98 earns a suggestion to find a job on land. A negative score means the crew asks the player to stay ashore.

## Number display (L600–L690)

- Below one million: the integer.
- Otherwise: three significant figures with a scale word, e.g. 1,234,567 → "1.23 Million". The words are Thousand, Million, Billion and Trillion.
