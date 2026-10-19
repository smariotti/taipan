"""Game state and rules for Taipan, with no terminal I/O.

Every formula here follows analysis/game-rules.md, which cites the BASIC line
numbers of the 1982 Apple II original it was recovered from.
"""
import math
import random
from dataclasses import dataclass, field

PORTS = ["At sea", "Hong Kong", "Shanghai", "Nagasaki", "Saigon", "Manila",
         "Singapore", "Batavia"]
AT_SEA = 0
HONG_KONG = 1

GOODS = ["Opium", "Silk", "Arms", "General Cargo"]
GOOD_KEYS = "OSAG"

# Base price per port (index 1..7), one row per good.
BASE_PRICES = [
    [11, 16, 15, 14, 12, 10, 13],  # Opium
    [11, 14, 15, 16, 10, 13, 12],  # Silk
    [12, 16, 10, 11, 13, 14, 15],  # Arms
    [10, 11, 12, 13, 14, 15, 16],  # General Cargo
]

CONDITION_NAMES = ["Critical", "Poor", "Fair", "Good", "Prime", "Perfect"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep",
          "Oct", "Nov", "Dec"]
RETIRE_WORTH = 1_000_000
WAREHOUSE_CAPACITY = 10_000
MAX_FIRM_NAME = 22


class Rng:
    """The original's FN R(X) = INT(RND * X): an integer in [0, x)."""

    def __init__(self, seed=None):
        self._random = random.Random(seed)

    def r(self, x):
        return math.floor(self._random.random() * x)


@dataclass
class State:
    firm: str
    cash: float
    debt: float
    guns: int
    hold: int            # free hold space; negative means overloaded
    pirate_odds: int     # 1 in N chance of pirates per voyage
    bank: float = 0
    capacity: int = 60
    damage: float = 0
    ship: list = field(default_factory=lambda: [0, 0, 0, 0])
    warehouse: list = field(default_factory=lambda: [0, 0, 0, 0])
    location: int = HONG_KONG
    month: int = 1
    year: int = 1860
    months: int = 1      # months of trading so far (TI)
    protected: bool = False
    enemy_hp_base: int = 20
    enemy_damage: float = 0.5
    loans: int = 0       # emergency loans taken from Wu
    escorted: bool = False
    run_odds: float = 0  # escape score; carries over between fights
    run_step: int = 1
    base_prices: list = field(default_factory=lambda: [row[:] for row in BASE_PRICES])
    prices: list = field(default_factory=lambda: [0, 0, 0, 0])

    @property
    def warehouse_used(self):
        return sum(self.warehouse)

    @property
    def warehouse_free(self):
        return WAREHOUSE_CAPACITY - self.warehouse_used

    @property
    def net_worth(self):
        return self.cash + self.bank - self.debt

    @property
    def has_any_cargo(self):
        return any(self.ship) or any(self.warehouse)


def new_state(firm, start_with_guns):
    if start_with_guns:
        return State(firm=firm, cash=0, debt=0, guns=5, hold=10, pirate_odds=7)
    return State(firm=firm, cash=400, debt=5000, guns=0, hold=60, pirate_odds=10)


# ---------------------------------------------------------------- display

def fmt_money(value):
    """Whole number below a million, else three figures and a scale word."""
    if value < 1e6:
        return str(math.floor(value))
    digits = math.floor(math.log10(value))
    group = digits // 3 * 3
    step = 10 ** (digits - 2)
    scaled = math.floor(value / step + 0.5) * step / 10 ** group
    word = {3: "Thousand", 6: "Million", 9: "Billion", 12: "Trillion"}.get(group, "")
    return ("%.9g" % scaled)[:4].rstrip(".") + " " + word


def fmt_price(value):
    return str(int(value)) if value == int(value) else "%.1f" % value


def seaworthiness(st, rounded=True):
    """Percent seaworthy. The status panel rounds; the combat sink check
    truncates, so a ship can show 1% on the panel and still be sunk."""
    pct = 100 - math.floor(st.damage / st.capacity * 100 + (0.5 if rounded else 0))
    return max(pct, 0)


def condition_name(pct):
    return CONDITION_NAMES[pct // 20]


def date_text(st):
    return "15 %s %d" % (MONTHS[st.month - 1], st.year)


# ---------------------------------------------------------------- economy

def set_prices(st, rng):
    for g in range(4):
        st.prices[g] = st.base_prices[g][st.location - 1] / 2 * (rng.r(3) + 1) * 10 ** (3 - g)


def price_event(st, rng):
    """1 in 9 per visit. Returns (good, new_price, rose) or None."""
    if rng.r(9):
        return None
    good = rng.r(4)
    rose = rng.r(2) == 1
    if rose:
        st.prices[good] = st.prices[good] * (rng.r(5) + 5)
    else:
        st.prices[good] = math.floor(st.prices[good] / 5)
    return good, st.prices[good], rose


def arrive(st, port):
    """Monthly tick on arrival: interest, calendar, yearly drift."""
    st.bank = math.floor(st.bank + st.bank * 0.005)
    st.debt = math.floor(st.debt + st.debt * 0.1)
    st.months += 1
    st.month += 1
    st.location = port


def new_year_if_due(st, rng):
    if st.month <= 12:
        return False
    st.year += 1
    st.month = 1
    st.enemy_hp_base += 10
    st.enemy_damage += 0.5
    for port in range(7):
        for g in range(4):
            st.base_prices[g][port] += rng.r(2)
    return True


def donation_amount(st, rng):
    if st.months > 12:
        floor = rng.r(1000 * st.months) + 1000 * st.months
        return rng.r(st.cash) + floor
    return rng.r(st.cash / 1.8)


def repair_rate(st, rng):
    t = (st.months + 3) / 4
    return math.floor((rng.r(60 * t) + 25 * t) * st.capacity / 50)


def emergency_loan(st, rng):
    """Returns (amount lent, amount owed)."""
    st.loans += 1
    lend = math.floor(rng.r(1500) + 500)
    owe = rng.r(2000) * st.loans + 1500
    return lend, owe


def ship_offer_cost(st, rng):
    scale = st.capacity // 50 + 1 if st.damage > 0 else 1
    return math.floor(1000 + rng.r(1000 * (st.months + 5) / 6)) * scale


def gun_cost(st, rng):
    return math.floor(rng.r(1000 * (st.months + 5) / 6) + 500)


def score(st):
    return math.floor(st.net_worth / 100 / st.months ** 1.1)


def rating(points):
    if points >= 50000:
        return "Ma Tsu"
    if points >= 8000:
        return "Master Taipan"
    if points >= 1000:
        return "Taipan"
    if points >= 500:
        return "Compradore"
    return "Galley Hand"


# ---------------------------------------------------------------- combat

SLOTS = 10


class Battle:
    """One sea fight. Up to SLOTS enemy ships are engaged at a time; the
    rest wait in reserve and move up as slots empty."""

    def __init__(self, st, rng, count, li_yuen):
        self.st = st
        self.rng = rng
        self.fierce = 2 if li_yuen else 1
        self.remaining = count
        self.start = count
        self.slots = [None] * SLOTS   # each is [hit points, damage taken]
        self.last_order = None
        self.booty = (rng.r(st.months / 4 * 1000 * count ** 1.05)
                      + rng.r(1000) + 250)

    @property
    def engaged(self):
        return sum(s is not None for s in self.slots)

    def refill(self):
        for i in range(SLOTS):
            if self.slots[i] is None and self.remaining > self.engaged:
                self.slots[i] = [self.rng.r(self.st.enemy_hp_base) + 20, 0]

    def _drop(self, n):
        """n ships leave the fight, taken from reserve first, then from the
        highest engaged slots."""
        self.remaining -= n
        excess = self.engaged - self.remaining
        i = SLOTS - 1
        while excess > 0:
            if self.slots[i] is not None:
                self.slots[i] = None
                excess -= 1
            i -= 1

    def run(self):
        st = self.st
        if self.last_order in ("R", "T"):
            st.run_odds += st.run_step
            st.run_step += 1
        else:
            st.run_odds = 3
            st.run_step = 1
        return self.try_escape()

    def try_escape(self):
        """Returns (escaped, ships_left_behind)."""
        if self.rng.r(self.st.run_odds) > self.rng.r(self.remaining):
            return True, 0
        behind = 0
        if self.remaining > 2 and self.rng.r(5) == 0:
            behind = self.rng.r(self.remaining / 2) + 1
            self._drop(behind)
        return False, behind

    def volley(self):
        """Fire every gun in turn, yielding (slot, sunk) after each shot so a
        display can animate it. Afterwards self.fled holds how many ships
        broke off and ran."""
        self.fled = 0
        for _ in range(self.st.guns):
            if self.remaining == 0:
                break
            while True:
                i = self.rng.r(SLOTS)
                if self.slots[i] is not None:
                    break
            target = self.slots[i]
            target[1] += self.rng.r(30) + 10
            sunk = target[1] > target[0]
            if sunk:
                self.slots[i] = None
                self.remaining -= 1
            yield i, sunk
            if sunk and self.engaged == 0:
                self.refill()
        roll = self.rng.r(self.start)
        if not (roll < self.remaining * 0.6 / self.fierce or self.remaining == 0
                or self.remaining == self.start or self.remaining < 3):
            self.fled = self.rng.r(self.remaining / 3 / self.fierce) + 1
            self._drop(self.fled)

    def fire(self):
        """Whole volley at once. Returns (sunk, fled), or None with no guns."""
        if self.st.guns == 0:
            return None
        sunk = sum(s for _, s in self.volley())
        return sunk, self.fled

    def jettison(self, good, amount):
        """Throw cargo overboard. good=None means everything. Returns units."""
        st = self.st
        goods = range(4) if good is None else [good]
        thrown = 0
        for g in goods:
            n = min(amount, st.ship[g])
            st.ship[g] -= n
            st.hold += n
            thrown += n
        if thrown:
            st.run_odds += thrown / 10
        return thrown

    def enemy_fire(self):
        """Returns (gun_destroyed, driven_off_by_li_yuen)."""
        st = self.st
        n = min(self.remaining, 15)
        gun_lost = False
        if st.guns:
            pct = st.damage / st.capacity * 100
            if self.rng.r(100) < pct or pct > 80:
                n = 1
                gun_lost = True
                st.guns -= 1
                st.hold += 10
        st.damage += self.rng.r(st.enemy_damage * n * self.fierce) + n / 2
        driven_off = self.rng.r(20) == 0 and self.fierce == 1
        return gun_lost, driven_off
