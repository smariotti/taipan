"""Tests for the Taipan remake. Run from the project folder:

    python -m unittest discover -s tests
"""
import os
import asyncio
import contextlib
import io
import io as io_module
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from taipan import engine  # noqa: E402
from taipan.console import ALL  # noqa: E402
from taipan.battle_screen import BattleView, ScreenBattleView  # noqa: E402
from taipan.console import Console  # noqa: E402
from taipan.game import Game  # noqa: E402

SCREEN = Console(fast=True)


class FixedRng:
    """Returns queued fractions in place of RND, so r(x) = floor(f * x)."""

    def __init__(self, *fractions):
        self.queue = list(fractions)

    def r(self, x):
        return engine.math.floor(self.queue.pop(0) * x)


class FormulaTests(unittest.TestCase):
    def test_start_options(self):
        a = engine.new_state("A", start_with_guns=False)
        self.assertEqual((a.cash, a.debt, a.guns, a.hold, a.pirate_odds), (400, 5000, 0, 60, 10))
        b = engine.new_state("B", start_with_guns=True)
        self.assertEqual((b.cash, b.debt, b.guns, b.hold, b.pirate_odds), (0, 0, 5, 10, 7))

    def test_prices_scale_by_good(self):
        st = engine.new_state("T", False)
        st.location = 2  # Shanghai
        engine.set_prices(st, FixedRng(0, 0.5, 0.9, 0))  # multipliers 1, 2, 3, 1
        self.assertEqual(st.prices, [16 / 2 * 1000, 14 / 2 * 2 * 100, 16 / 2 * 3 * 10, 11 / 2])

    def test_price_event_crash_and_boom(self):
        st = engine.new_state("T", False)
        st.prices = [8000, 700, 80, 5.5]
        self.assertEqual(engine.price_event(st, FixedRng(0, 0, 0)), (0, 1600, False))
        self.assertEqual(engine.price_event(st, FixedRng(0, 0.3, 0.9, 0.99)), (1, 700 * 9, True))
        self.assertIsNone(engine.price_event(st, FixedRng(0.5)))

    def test_interest_on_arrival(self):
        st = engine.new_state("T", False)
        st.bank = 1000
        engine.arrive(st, 3)
        self.assertEqual((st.bank, st.debt, st.months, st.month, st.location),
                         (1005, 5500, 2, 2, 3))

    def test_new_year(self):
        st = engine.new_state("T", False)
        st.month = 13
        self.assertTrue(engine.new_year_if_due(st, FixedRng(*[0.9] * 28)))
        self.assertEqual((st.month, st.year, st.enemy_hp_base, st.enemy_damage), (1, 1861, 30, 1.0))
        self.assertEqual(st.base_prices[0][0], 12)

    def test_donation(self):
        st = engine.new_state("T", False)
        st.cash = 1800
        self.assertEqual(engine.donation_amount(st, FixedRng(0.5)), 500)
        st.months = 13
        self.assertEqual(engine.donation_amount(st, FixedRng(0, 0.5)), 900 + 13000)

    def test_repair_rate(self):
        st = engine.new_state("T", False)  # months 1 -> t = 1
        self.assertEqual(engine.repair_rate(st, FixedRng(0)), 30)       # 25 * 60/50
        self.assertEqual(engine.repair_rate(st, FixedRng(0.999)), 100)  # INT((59 + 25) * 1.2)

    def test_offers(self):
        st = engine.new_state("T", False)
        self.assertEqual(engine.ship_offer_cost(st, FixedRng(0)), 1000)
        st.damage = 5
        self.assertEqual(engine.ship_offer_cost(st, FixedRng(0)), 2000)  # INT(60/50)+1
        self.assertEqual(engine.gun_cost(st, FixedRng(0.999)), 1499)

    def test_money_format(self):
        self.assertEqual(engine.fmt_money(999999), "999999")
        self.assertEqual(engine.fmt_money(1234567), "1.23 Million")
        self.assertEqual(engine.fmt_money(25_000_000), "25 Million")
        self.assertEqual(engine.fmt_money(987_600_000), "988 Million")
        self.assertEqual(engine.fmt_money(4_560_000_000), "4.56 Billion")

    def test_score_and_rating(self):
        st = engine.new_state("T", False)
        st.cash, st.debt, st.months = 1_005_000, 5000, 12
        self.assertEqual(engine.score(st), engine.math.floor(1_000_000 / 100 / 12 ** 1.1))
        self.assertEqual(engine.rating(50000), "Ma Tsu")
        self.assertEqual(engine.rating(49999), "Master Taipan")
        self.assertEqual(engine.rating(1000), "Taipan")
        self.assertEqual(engine.rating(999), "Compradore")
        self.assertEqual(engine.rating(-5), "Galley Hand")

    def test_seaworthiness(self):
        st = engine.new_state("T", False)
        st.damage = 59.5
        self.assertEqual(engine.seaworthiness(st), 1)
        self.assertEqual(engine.seaworthiness(st, rounded=False), 1)
        st.damage = 60
        self.assertEqual(engine.seaworthiness(st, rounded=False), 0)
        self.assertEqual(engine.condition_name(100), "Perfect")
        self.assertEqual(engine.condition_name(19), "Critical")


class BattleTests(unittest.TestCase):
    def make(self, count, guns=0, li_yuen=False, rng=None):
        st = engine.new_state("T", False)
        st.guns = guns
        return st, engine.Battle(st, rng or engine.Rng(1), count, li_yuen)

    def test_refill_caps_at_ten(self):
        _, b = self.make(25)
        b.refill()
        self.assertEqual((b.engaged, b.remaining), (10, 25))
        self.assertTrue(all(20 <= s[0] < 40 for s in b.slots))

    def test_drop_takes_reserve_then_high_slots(self):
        _, b = self.make(12)
        b.refill()
        b._drop(2)
        self.assertEqual((b.engaged, b.remaining), (10, 10))
        b._drop(3)
        self.assertEqual(b.engaged, 7)
        self.assertEqual([s is None for s in b.slots], [False] * 7 + [True] * 3)

    def test_run_odds_build_on_repeated_runs(self):
        st, b = self.make(2, rng=FixedRng(*[0] * 20))  # escape always fails: 0 > 0 is false
        b.refill()
        b.run()
        self.assertEqual((st.run_odds, st.run_step), (3, 1))
        b.last_order = "R"
        b.run()
        b.run()
        self.assertEqual((st.run_odds, st.run_step), (3 + 1 + 2, 3))
        b.last_order = "F"
        b.run()
        self.assertEqual(st.run_odds, 3)

    def test_guns_sink_ships(self):
        st, b = self.make(1, guns=3)
        b.refill()
        b.slots[0] = [20, 0]
        b.slots[0] = b.slots[0]
        sunk, fled = b.fire()
        self.assertEqual((sunk, fled, b.remaining), (1, 0, 0))

    def test_li_yuen_hits_twice_as_hard(self):
        damages = []
        for li in (False, True):
            st, b = self.make(4, li_yuen=li, rng=FixedRng(0, 0, 0.999, 0.5))
            st.enemy_damage = 1
            b.enemy_fire()
            damages.append(st.damage)
        self.assertEqual(damages, [3 + 2, 7 + 2])

    def test_jettison_frees_hold_and_helps_escape(self):
        st, b = self.make(3)
        st.ship = [10, 20, 0, 5]
        st.hold -= 35
        st.run_odds = 1
        self.assertEqual(b.jettison(None, 10 ** 9), 35)
        self.assertEqual((st.ship, st.hold, st.run_odds), ([0, 0, 0, 0], 60, 4.5))


class RobotBattleView(BattleView):
    """Changes orders now and then mid-fight, like an impatient captain."""

    async def ask_for_orders(self):
        if self.order is None or self.io.rand.random() < 0.3:
            self.order = self.io.rand.choice("RFT")


class QuietScreenView(ScreenBattleView):
    """The real animated screen, minus the delays, drawing into a buffer."""

    def __init__(self, io):
        super().__init__(io)
        self.buffer = io_module.StringIO()

    def out(self, *parts):
        self.buffer.write("".join(parts))

    async def wait(self, seconds, until_order=False):
        pass

    async def ask_for_orders(self):
        await RobotBattleView.ask_for_orders(self)


class RobotIO:
    """Plays by picking random legal-looking answers. Every prompt is
    answered, so a game must run to its end without hanging."""

    interactive = False

    def __init__(self, seed, animated=False):
        self.rand = random.Random(seed)
        self.game = None
        self.prompts = 0
        self.animated = animated

    def battle_view(self):
        if self.animated:
            return QuietScreenView(self)
        return RobotBattleView(self)

    def status(self, st):
        # Draw the real screen into a buffer so display bugs fail the tests.
        with contextlib.redirect_stdout(io.StringIO()):
            SCREEN.status(st)

    def say(self, text=""):
        pass

    async def pause(self, seconds=1.5):
        pass

    async def key(self, prompt, keys, default=None):
        self.prompts += 1
        if self.prompts > 4000:  # long games: retire or sail on
            if "R" in keys and "B" in keys:
                return "R"
        if "B" in keys and "Q" in keys:  # trading menu: lean towards sailing
            return self.rand.choice("BSQQQ" + keys[3:])
        return self.rand.choice(keys)

    async def yes(self, prompt):
        return self.rand.random() < 0.6

    async def amount(self, prompt):
        self.prompts += 1
        roll = self.rand.random()
        if roll < 0.4:
            return ALL
        if roll < 0.6:
            return 0
        return self.rand.randint(0, 3000)

    async def text(self, prompt):
        return "Robot Trading Co"


def check_books(test, st):
    test.assertEqual(st.hold, st.capacity - sum(st.ship) - 10 * st.guns)
    test.assertLessEqual(st.warehouse_used, engine.WAREHOUSE_CAPACITY)
    test.assertGreaterEqual(st.guns, 0)
    test.assertTrue(all(n >= 0 for n in st.ship + st.warehouse))
    test.assertGreaterEqual(st.cash, 0)


class CalendarTests(unittest.TestCase):
    def test_arriving_in_january_redraws_without_error(self):
        # Regression: arriving after a December voyage left month = 13 while
        # the arrival screen was drawn, crashing date_text.
        game = Game(RobotIO(0), engine.Rng(0))
        game.st = engine.new_state("Calendar", False)
        game.st.month, game.st.location = 12, 6
        engine.arrive(game.st, engine.HONG_KONG)
        self.assertEqual(game.st.month, 13)
        asyncio.run(game.in_port(arriving=True))
        self.assertEqual((game.st.month, game.st.year), (1, 1861))


class RetireTests(unittest.TestCase):
    def test_millionaire_can_retire_in_hong_kong(self):
        io = RobotIO(0)

        async def key(prompt, keys, default=None):
            return "R" if "R" in keys and "B" in keys else keys[0]

        io.key = key
        game = Game(io, engine.Rng(0))
        game.st = engine.new_state("Rich", False)
        game.st.bank = 2_000_000
        with self.assertRaises(Exception) as end:
            asyncio.run(game.trade())
        self.assertEqual(end.exception.reason, "retired")

    def test_retire_not_offered_below_a_million(self):
        offered = []
        io = RobotIO(0)

        async def key(prompt, keys, default=None):
            offered.append(keys)
            return "Q" if "Q" in keys else "2"  # sail to Shanghai

        io.key = key
        game = Game(io, engine.Rng(0))
        game.st = engine.new_state("Poor", False)
        asyncio.run(game.trade())
        self.assertNotIn("R", offered[0])


class AnimatedBattleTests(unittest.TestCase):
    def test_animated_games_run_to_the_end(self):
        """Whole games through the real battle screen: drawing, sinking and
        prompts must never crash, and ships on screen must match the fight."""
        fights = 0
        for seed in range(150):
            robot = RobotIO(seed, animated=True)
            game = Game(robot, engine.Rng(seed))
            views = []
            make_view = robot.battle_view

            def tracked(make_view=make_view, views=views):
                view = make_view()
                views.append(view)
                return view

            robot.battle_view = tracked
            original_sync = QuietScreenView.sync

            async def checked_sync(view, fight):
                await original_sync(view, fight)
                self.assertEqual(view.shown, [s is not None for s in fight.slots])

            QuietScreenView.sync = checked_sync
            try:
                asyncio.run(game.play())
            finally:
                QuietScreenView.sync = original_sync
            fights += len(views)
            for view in views:
                self.assertIn("\x1b[?25h", view.buffer.getvalue())  # cursor restored
        self.assertGreater(fights, 50)

    def test_sinking_erases_the_ship(self):
        st = engine.new_state("T", False)
        fight = engine.Battle(st, engine.Rng(5), 3, li_yuen=False)
        view = QuietScreenView(RobotIO(0))
        view.open(fight)
        fight.refill()
        asyncio.run(view.sync(fight))
        self.assertEqual(view.shown, [True, True, True] + [False] * 7)
        asyncio.run(view.sink(1))
        fight.slots[1] = None
        asyncio.run(view.sync(fight))
        self.assertEqual(view.shown, [True, False, True] + [False] * 7)


class PlaythroughTests(unittest.TestCase):
    def test_many_seeded_games_finish_with_consistent_books(self):
        reasons = {}
        for seed in range(300):
            io = RobotIO(seed)
            game = Game(io, engine.Rng(seed))
            original_redraw = game.redraw

            def redraw(game=game, original=original_redraw):
                check_books(self, game.st)
                original()

            game.redraw = redraw
            reason = asyncio.run(game.play())
            check_books(self, game.st)
            reasons[reason] = reasons.get(reason, 0) + 1
        # The robot should meet more than one kind of ending.
        self.assertGreater(len(reasons), 1, reasons)


if __name__ == "__main__":
    unittest.main()
