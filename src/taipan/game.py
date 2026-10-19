"""Game flow: ports, Hong Kong business, voyages and fights.

Rules come from analysis/game-rules.md; all on-screen wording is new.
"""
import math

from . import engine
from .console import ALL
from .engine import GOODS, GOOD_KEYS, HONG_KONG, PORTS


class GameOver(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class Game:
    def __init__(self, io, rng):
        self.io = io
        self.rng = rng
        self.st = None

    # ------------------------------------------------------------ helpers

    def r(self, x):
        return self.rng.r(x)

    def redraw(self):
        self.io.status(self.st)

    async def tell(self, *lines, wait=1.5):
        for line in lines:
            self.io.say(line)
        await self.io.pause(wait)

    # ------------------------------------------------------------ top level

    async def play(self):
        """One full game. Returns the reason it ended."""
        self.st = await self.setup()
        try:
            arriving = False
            while True:
                await self.in_port(arriving)
                await self.voyage(await self.trade())
                arriving = True
        except GameOver as end:
            self.final_report(end.reason)
            return end.reason

    async def setup(self):
        io = self.io
        io.say("\x1b[2J\x1b[H")
        io.say("T A I P A N  --  trading the China coast, 1860")
        io.say()
        while True:
            name = await io.text("Taipan, what is the name of your firm?")
            if name and len(name) <= engine.MAX_FIRM_NAME:
                break
            io.say("  Give a name of 1 to %d characters." % engine.MAX_FIRM_NAME)
        io.say()
        io.say("How would you like to begin?")
        io.say("  1) With 400 in cash, owing Elder Brother Wu 5,000")
        io.say("  2) With five guns, no cash and no debt")
        choice = await io.key("Choose 1 or 2:", "12")
        return engine.new_state(name, start_with_guns=choice == "2")

    # ------------------------------------------------------------ in port

    async def in_port(self, arriving):
        st = self.st
        engine.new_year_if_due(st, self.rng)  # before any redraw: month may be 13
        if arriving:
            self.redraw()
            await self.tell("Dropping anchor at %s." % PORTS[st.location], wait=0.8)
        self.redraw()
        if st.location == HONG_KONG:
            await self.li_yuen_donation()
            await self.offer_repairs()
            await self.wu_escort(arriving)
            await self.visit_wu()
        await self.offer_bigger_ship()
        await self.offer_gun()
        await self.opium_seizure()
        await self.warehouse_theft()
        engine.set_prices(st, self.rng)
        if st.protected and self.r(20) == 0:
            st.protected = False
        if not st.protected and st.location != HONG_KONG and self.r(4):
            await self.tell("A messenger from Li Yuen says the pirate lord expects",
                      "to see you in Hong Kong. His fleet may not be friendly.")
        await self.price_news()
        await self.mugging()

    async def li_yuen_donation(self):
        st = self.st
        if st.protected or st.cash == 0:
            return
        ask = engine.donation_amount(st, self.rng)
        self.io.say("Li Yuen's agent suggests a gift of %s to the" % engine.fmt_money(ask))
        self.io.say("Tin Hau temple would keep his pirates friendly.")
        if not await self.io.yes("Make the donation?"):
            return
        st.protected = True
        st.cash -= ask
        if st.cash > 0:
            self.redraw()
            return
        self.io.say("Your cash does not cover the gift, Taipan.")
        if await self.io.yes("Ask Elder Brother Wu to make up the shortfall?"):
            st.debt -= st.cash
            st.cash = 0
            await self.tell("Wu pays the balance and adds it to what you owe him.")
        else:
            st.cash = 0
            st.protected = False
            await self.tell("Li Yuen keeps what you had and is not appeased.",
                      "Watch the horizon, Taipan.")
        self.redraw()

    async def offer_repairs(self):
        st = self.st
        if st.damage == 0:
            return
        if not await self.io.yes("The shipyard can repair your hull. Interested?"):
            return
        rate = engine.repair_rate(st, self.rng)
        while True:
            self.redraw()
            full = rate * st.damage + 1
            self.io.say("Your ship is %d%% damaged. A full repair costs %s."
                        % (math.floor(st.damage / st.capacity * 100 + 0.5),
                           engine.fmt_money(full)))
            pay = await self.io.amount("How much will you spend?")
            if pay == ALL:
                pay = min(full, st.cash)
            if pay <= st.cash:
                break
            await self.tell("You don't have that much cash, Taipan.")
        st.damage = max(math.floor(st.damage - math.floor(pay / rate + 0.5)), 0)
        st.cash -= pay
        self.redraw()

    async def wu_escort(self, arriving):
        st = self.st
        if st.debt < 10000 or st.escorted or not arriving:
            return
        st.escorted = True
        await self.tell("%d of Elder Brother Wu's men are waiting on the dock" % (self.r(100) + 50),
                  "to walk you to his house, Taipan.",
                  "Wu reminds you, politely, how much you owe him,",
                  "and how unlucky debtors tend to be.", wait=3)
        self.redraw()

    async def visit_wu(self):
        st = self.st
        if not await self.io.yes("Will you call on Elder Brother Wu, the moneylender?"):
            return
        if not (st.cash or st.bank or st.has_any_cargo or st.guns):
            lend, owe = engine.emergency_loan(st, self.rng)
            self.io.say("Wu sees you have nothing left. He will lend you %d" % lend)
            self.io.say("if you promise to repay %d." % owe)
            if not await self.io.yes("Accept his terms?"):
                raise GameOver("refused_wu")
            st.cash += lend
            st.debt += owe
            await self.tell("Wu nods. May your luck turn, Taipan.")
            self.redraw()
            return
        if st.debt and st.cash:
            while True:
                pay = await self.io.amount("How much will you repay?")
                if pay == ALL:
                    pay = min(st.cash, st.debt)
                if pay <= st.cash:
                    break
                await self.tell("You have only %s in cash." % engine.fmt_money(st.cash))
            st.cash -= pay
            st.debt -= pay  # overpaying leaves Wu owing you, as in the original
            self.redraw()
        while True:
            borrow = await self.io.amount("How much will you borrow?")
            if borrow == ALL:
                borrow = 2 * st.cash
            if borrow <= 2 * st.cash:
                break
            await self.tell("Wu will lend at most twice your cash on hand.")
        st.cash += borrow
        st.debt += borrow
        self.redraw()
        if st.debt > 20000 and self.r(5) == 0:
            await self.tell("Thugs ambush you on the way back from Wu's house!",
                      "%d of your guards are dead and your purse is gone." % (self.r(3) + 1),
                      wait=3)
            st.cash = 0
            self.redraw()

    async def offer_bigger_ship(self):
        st = self.st
        cost = engine.ship_offer_cost(st, self.rng)
        if st.cash < cost or self.r(4):
            return
        state = "damaged" if st.damage else "sound"
        if await self.io.yes("A shipwright offers to take your %s ship in trade for one\n"
                       "with 50 more units of hold, for %s extra. Deal?"
                       % (state, engine.fmt_money(cost))):
            st.cash -= cost
            st.capacity += 50
            st.hold += 50
            st.damage = 0
            self.redraw()

    async def offer_gun(self):
        st = self.st
        cost = engine.gun_cost(st, self.rng)
        if st.cash < cost or self.r(3):
            return
        if not await self.io.yes("A cannon is for sale for %s. Buy it?" % engine.fmt_money(cost)):
            return
        if st.hold < 10:
            await self.tell("There's no room aboard for it, Taipan. A gun needs 10 units.")
            return
        st.cash -= cost
        st.guns += 1
        st.hold -= 10
        self.redraw()

    async def opium_seizure(self):
        st = self.st
        if st.ship[0] == 0 or st.location == HONG_KONG or self.r(18):
            return
        fine = self.r(st.cash / 1.8)
        st.hold += st.ship[0]
        st.ship[0] = 0
        st.cash -= fine
        self.redraw()
        await self.tell("Customs officers board and confiscate your opium,",
                  "and fine you %s on top of it!" % engine.fmt_money(fine), wait=3)

    async def warehouse_theft(self):
        st = self.st
        if st.warehouse_used == 0 or self.r(50):
            return
        for g in range(4):
            st.warehouse[g] = self.r(st.warehouse[g] / 1.8)
        self.redraw()
        await self.tell("Word from Hong Kong: thieves have looted your warehouse!", wait=3)

    async def price_news(self):
        event = engine.price_event(self.st, self.rng)
        if event:
            good, price, rose = event
            what = "soared" if rose else "collapsed"
            await self.tell("Market news, Taipan! %s prices have %s to %s!"
                      % (GOODS[good], what, engine.fmt_money(price)), wait=2.5)

    async def mugging(self):
        st = self.st
        if st.cash > 25000 and self.r(20) == 0:
            loss = self.r(st.cash / 1.4)
            st.cash -= loss
            self.redraw()
            await self.tell("Footpads knock you down in an alley and take %s!"
                      % engine.fmt_money(loss), wait=3)

    # ------------------------------------------------------------ trading

    async def trade(self):
        """Market menu. Returns the chosen destination port."""
        st = self.st
        while True:
            self.redraw()
            self.io.say("Prices in %s today:" % PORTS[st.location])
            for g in range(4):
                self.io.say("    %-14s %s" % (GOODS[g], engine.fmt_price(st.prices[g])))
            options = "BSQ"
            menu = "(B)uy, (S)ell, (Q)uit trading"
            if st.location == HONG_KONG:
                options += "TV"
                menu += ", (T)ransfer cargo, (V)isit bank"
                if st.net_worth >= engine.RETIRE_WORTH:
                    options += "R"
                    menu += ", (R)etire"
            choice = await self.io.key(menu + "?", options)
            if choice == "B":
                await self.buy()
            elif choice == "S":
                await self.sell()
            elif choice == "T":
                await self.transfer()
            elif choice == "V":
                await self.bank()
            elif choice == "R":
                await self.tell("", "*** You are a millionaire, Taipan! ***", "", wait=3)
                raise GameOver("retired")
            elif choice == "Q":
                dest = await self.choose_destination()
                if dest:
                    return dest

    async def pick_good(self, verb):
        key = await self.io.key("%s which? (O)pium, (S)ilk, (A)rms, (G)eneral cargo" % verb,
                          GOOD_KEYS)
        return GOOD_KEYS.index(key)

    async def buy(self):
        st = self.st
        g = await self.pick_good("Buy")
        price = st.prices[g]
        while True:
            most = min(math.floor(st.cash / price), 10 ** 9 - 1)
            self.io.say("You can afford %d." % most)
            n = await self.io.amount("How many units of %s?" % GOODS[g])
            if n == ALL:
                n = most
            if n * price <= st.cash:
                break
            await self.tell("Not enough cash for that.", wait=0.8)
        st.cash -= n * price
        st.ship[g] += n
        st.hold -= n  # not checked here; an overloaded ship just can't sail

    async def sell(self):
        st = self.st
        g = await self.pick_good("Sell")
        while True:
            n = await self.io.amount("How many units of %s?" % GOODS[g])
            if n == ALL:
                n = st.ship[g]
            if n <= st.ship[g]:
                break
            await self.tell("You only have %d aboard." % st.ship[g], wait=0.8)
        st.cash += n * st.prices[g]
        st.ship[g] -= n
        st.hold += n

    async def transfer(self):
        st = self.st
        if not st.has_any_cargo:
            await self.tell("You have no cargo to move, Taipan.")
            return
        for g in range(4):
            for to_warehouse in (True, False):
                source = st.ship if to_warehouse else st.warehouse
                if source[g] == 0:
                    continue
                where = "into the warehouse" if to_warehouse else "aboard ship"
                while True:
                    self.redraw()
                    n = await self.io.amount("How much %s shall I move %s?" % (GOODS[g], where))
                    if n == ALL:
                        n = source[g]
                        if to_warehouse:
                            n = min(n, st.warehouse_free)
                    if to_warehouse and n > 0 and st.warehouse_free == 0:
                        await self.tell("The warehouse is full.")
                    elif to_warehouse and n > st.warehouse_free:
                        await self.tell("The warehouse has room for only %d more." % st.warehouse_free)
                    elif n > source[g]:
                        await self.tell("There are only %d there." % source[g])
                    else:
                        break
                if to_warehouse:
                    st.ship[g] -= n
                    st.warehouse[g] += n
                    st.hold += n
                else:
                    st.warehouse[g] -= n
                    st.ship[g] += n
                    st.hold -= n

    async def bank(self):
        st = self.st
        while True:
            n = await self.io.amount("Deposit how much?")
            if n == ALL:
                n = st.cash
            if n <= st.cash:
                break
            await self.tell("You have only %s in cash." % engine.fmt_money(st.cash))
        st.cash -= n
        st.bank += n
        self.redraw()
        while True:
            n = await self.io.amount("Withdraw how much?")
            if n == ALL:
                n = st.bank
            if n <= st.bank:
                break
            await self.tell("You have only %s in the bank." % engine.fmt_money(st.bank))
        st.bank -= n
        st.cash += n

    async def choose_destination(self):
        st = self.st
        if st.hold < 0:
            await self.tell("The ship is overloaded, Taipan. Lighten her first.")
            return None
        self.io.say("Set a course for:")
        self.io.say("  " + ", ".join("%d) %s" % (i, PORTS[i]) for i in range(1, 8)))
        while True:
            dest = int(await self.io.key("Which port?", "1234567"))
            if dest != st.location:
                return dest
            self.io.say("We're in %s already, Taipan." % PORTS[dest])

    # ------------------------------------------------------------ at sea

    async def voyage(self, dest):
        st = self.st
        st.location = engine.AT_SEA
        self.redraw()
        if self.r(st.pirate_odds) == 0:
            count = self.r(st.capacity / 10 + st.guns) + 1
            await self.tell("Sails on the horizon! %d hostile ship%s closing, Taipan!"
                      % (count, "" if count == 1 else "s"), wait=2)
            if await self.battle(count, li_yuen=False) == "driven_off":
                await self.li_yuen_encounter()
        elif self.r(4 + 8 * st.protected) == 0:
            await self.li_yuen_encounter()
        dest = await self.storm(dest)
        engine.arrive(st, dest)

    async def li_yuen_encounter(self):
        st = self.st
        self.redraw()
        await self.tell("Li Yuen's war junks, Taipan!", wait=1.5)
        if st.protected:
            await self.tell("They recognise our colours and sail on by. The gift paid off!")
            return
        count = self.r(st.capacity / 5 + st.guns) + 5
        await self.tell("%d ships of Li Yuen's fleet bear down on us!" % count, wait=2)
        await self.battle(count, li_yuen=True)

    async def storm(self, dest):
        st = self.st
        if self.r(10):
            return dest
        self.redraw()
        await self.tell("A typhoon, Taipan!")
        if self.r(30) == 0:
            await self.tell("She's taking on water fast...", wait=2)
            if self.r(st.damage / st.capacity * 3):
                await self.tell("She's breaking up! All hands lost!", wait=3)
                raise GameOver("storm")
        await self.tell("We rode it out.")
        if self.r(3) == 0:
            while True:
                port = self.r(7) + 1
                if port != dest:
                    break
            await self.tell("The storm drove us to %s." % PORTS[port])
            return port
        return dest

    # ------------------------------------------------------------ combat

    async def battle(self, count, li_yuen):
        """Fight it out in real time. Returns 'won', 'escaped' or 'driven_off'."""
        fight = engine.Battle(self.st, self.rng, count, li_yuen)
        view = self.io.battle_view()
        view.open(fight)
        try:
            outcome = await self.fight_it_out(fight, view)
        finally:
            view.close()
        return await self.end_battle(outcome, fight.booty if outcome == "won" else 0)

    async def fight_it_out(self, fight, view):
        st = self.st
        while True:
            fight.refill()
            await view.sync(fight)
            fight.last_order = view.order  # the order still standing from last round
            st.damage = math.floor(st.damage)
            pct = engine.seaworthiness(st, rounded=False)
            view.status("Hull: %s (%d%%)" % (engine.condition_name(pct), pct))
            if pct == 0:
                await view.say("She's going down, Taipan! Abandon ship!", beats=3)
                raise GameOver("sunk")
            await view.ask_for_orders()
            order = view.order
            outcome = None
            if order == "R":
                await view.say("Crowd on all sail, we're running!")
                outcome = await self.try_run(fight, view, fight.run)
            elif order == "F":
                await self.open_fire(fight, view)
            elif order == "T":
                outcome = await self.throw_cargo(fight, view)
            if outcome:
                return outcome
            if fight.remaining == 0:
                await view.say("The sea is clear of them, Taipan!", beats=2)
                return "won"
            await view.say("Their guns are run out, Taipan!")
            await view.incoming()
            gun_lost, driven_off = fight.enemy_fire()
            await view.sync(fight)
            if gun_lost:
                await view.say("A ball smashed one of our guns!")
            else:
                await view.say("We're hit, Taipan!")
            if driven_off:
                return "driven_off"

    async def open_fire(self, fight, view):
        if self.st.guns == 0:
            await view.say("We've no guns to answer with!")
            return
        await view.say("Broadside, Taipan! Fire!")
        sunk = 0
        for slot, went_down in fight.volley():
            await view.hit(slot)
            if went_down:
                sunk += 1
                await view.sink(slot)
            await view.sync(fight)
        if sunk:
            await view.say("%d of them sent to the bottom!" % sunk)
        else:
            await view.say("Hits, but they're still afloat.")
        if fight.fled:
            await view.sync(fight)
            await view.say("%d of them have broken off and fled!" % fight.fled)

    async def try_run(self, fight, view, attempt):
        escaped, behind = attempt()
        if escaped:
            return "escaped"
        await view.say("They're keeping pace with us!")
        if behind:
            await view.sync(fight)
            await view.say("...but %d of them have fallen behind." % behind)
        return None

    async def throw_cargo(self, fight, view):
        st = self.st
        view.show_cargo(st)
        key = await view.ask_key("Throw what overboard? (O)pium, (S)ilk, (A)rms, (G)eneral, (*) all",
                           GOOD_KEYS + "*")
        if key == "*":
            good, n = None, 10 ** 9
        else:
            good = GOOD_KEYS.index(key)
            n = await view.ask_amount("How much?")
            if n == ALL:
                n = st.ship[good]
        thrown = fight.jettison(good, n)
        if not thrown:
            await view.say("There's nothing like that aboard!")
            return None
        await view.say("Over the side it goes. Let's hope it slows them down.")
        return await self.try_run(fight, view, fight.try_escape)

    async def end_battle(self, outcome, booty=0):
        st = self.st
        st.run_odds = {"won": 1, "driven_off": 2, "escaped": 3}[outcome]
        st.cash += booty
        self.redraw()
        if outcome == "won":
            await self.tell("Every last one of them is gone, Taipan!",
                      "Their holds yield booty worth %s." % engine.fmt_money(booty), wait=3)
        elif outcome == "escaped":
            await self.tell("We've given them the slip, Taipan!", wait=2)
        else:
            await self.tell("Li Yuen's fleet arrives and scatters the attackers!", wait=2)
        return outcome

    # ------------------------------------------------------------ the end

    def final_report(self, reason):
        st = self.st
        io = self.io
        points = engine.score(st)
        years, months = divmod(st.months, 12)
        io.say()
        io.say("=" * 40)
        io.say("Final accounts of %s" % st.firm)
        io.say("  Net worth:  %s" % engine.fmt_money(st.net_worth))
        io.say("  Ship:       %d units, %d guns" % (st.capacity, st.guns))
        io.say("  Trading:    %d year%s, %d month%s"
               % (years, "" if years == 1 else "s", months, "" if months == 1 else "s"))
        io.say("  Score:      %d" % points)
        io.say("  Rating:     %s" % engine.rating(points))
        for limit, title in ((50000, "Ma Tsu"), (8000, "Master Taipan"), (1000, "Taipan"),
                             (500, "Compradore"), (None, "Galley Hand")):
            mark = "->" if engine.rating(points) == title else "  "
            io.say("   %s %-14s %s" % (mark, title, "%d and up" % limit if limit else "below 500"))
        if 0 <= points < 99:
            io.say("Perhaps a career on dry land would suit you better.")
        elif points < 0:
            io.say("The crew would rather you never set foot on a deck again!")
        io.say("=" * 40)


async def run(io, rng):
    """Play games until the player has had enough."""
    while True:
        await Game(io, rng).play()
        if not await io.yes("Play again?"):
            return


def main(argv=None):
    import argparse
    import asyncio
    from .console import Console

    parser = argparse.ArgumentParser(prog="taipan", description="Trade, fight and get rich on the China coast.")
    parser.add_argument("--seed", type=int, help="fix the random seed")
    parser.add_argument("--fast", action="store_true", help="skip the pauses between messages")
    args = parser.parse_args(argv)
    try:
        asyncio.run(run(Console(fast=args.fast), engine.Rng(args.seed)))
    except (KeyboardInterrupt, EOFError):
        print()
