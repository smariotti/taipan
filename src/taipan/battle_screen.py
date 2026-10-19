"""Animated, real-time sea battles drawn with ANSI escape codes.

The layout and timing follow the Apple II original: a 40-column screen with
up to ten enemy ships in two rows of five, a reserve marker, a guns panel,
and orders that keep repeating until a new key is pressed. The ship and
explosion artwork is new.

All drawing goes through io.write and all keys through io.poll_key, so the
same screen works in a Windows console and in the web page.
"""
import asyncio
import random
import time

from . import engine

ESC = "\x1b["
RESET = ESC + "0m"
HIDE_CURSOR = ESC + "?25l"
SHOW_CURSOR = ESC + "?25h"
CLEAR = ESC + "2J" + ESC + "H"
INVERT_SCREEN = ESC + "?5h"
NORMAL_SCREEN = ESC + "?5l"

WHITE = ESC + "97m"
YELLOW = ESC + "33m"
BLUE = ESC + "34m"
RED = ESC + "91m"
ORANGE = ESC + "93m"
DARK_RED = ESC + "31m"
REVERSE = ESC + "7m"
RED_BAR = ESC + "41;97m"

# A small junk: battened sail, hull, and the water line. 7 columns x 5 rows.
SHIP = [
    "   |\\  ",
    "   |=\\ ",
    " __|__ ",
    " \\___/ ",
    "~~~~~~~",
]
SHIP_COLORS = [WHITE, WHITE, YELLOW, YELLOW, BLUE]
SHIP_W, SHIP_H = 7, 5
SPARKS = "*#@%"

ORDER_NAMES = {"R": "Run", "F": "Fight", "T": "Throw cargo"}
MESSAGE_ROW = 4
STATUS_ROW = 5
PROMPT_ROW = 20

# How long each pause between messages lasts. This is also the window in
# which the player can change orders, as in the original's keyboard poll.
BEAT = 0.8
HURRIED_BEAT = 0.25  # message pause for the rest of a round after orders change


def at(row, col):
    return "%s%d;%dH" % (ESC, row, col)


def slot_origin(slot):
    """Top-left screen cell of an enemy slot (1-based row, column)."""
    return slot // 5 * 6 + 7, slot % 5 * 8 + 1


class BattleView:
    """Silent display that only tracks orders. Tests use it directly; the
    animated screen below fills in the drawing."""

    def __init__(self, io):
        self.io = io
        self.order = None

    def open(self, fight):
        pass

    def close(self):
        pass

    async def sync(self, fight):
        pass

    async def say(self, text, beats=1):
        pass

    def status(self, text):
        pass

    async def ask_for_orders(self):
        if self.order is None:
            self.order = await self.io.key("Orders? (R)un, (F)ight, (T)hrow cargo", "RFT")

    async def hit(self, slot):
        pass

    async def sink(self, slot):
        pass

    async def incoming(self):
        pass

    def show_cargo(self, st):
        pass

    async def ask_key(self, prompt, keys):
        return await self.io.key(prompt, keys)

    async def ask_amount(self, prompt):
        return await self.io.amount(prompt)


class ScreenBattleView(BattleView):
    def __init__(self, io):
        super().__init__(io)
        self.live = io.interactive
        self.shown = [False] * engine.SLOTS
        self.marks = [[] for _ in range(engine.SLOTS)]
        self.fight = None
        # Set when orders change mid-round: the rest of the round plays out
        # quickly so the new order comes into effect without a long wait.
        self.hurry = False

    # ------------------------------------------------------------ plumbing

    def out(self, *parts):
        self.io.write("".join(parts))

    async def wait(self, seconds, until_order=False):
        """Pause, watching the keyboard for new orders the whole time. With
        until_order, a new order ends the pause early, as a keypress did in
        the original's keyboard poll."""
        end = time.monotonic() + seconds
        while True:
            if self.poll_keys() and until_order:
                return
            left = end - time.monotonic()
            if left <= 0:
                return
            await asyncio.sleep(min(0.02, left))

    def poll_keys(self):
        """Read waiting keys. Returns True if the orders changed."""
        if not self.live:
            return False
        changed = False
        while (ch := self.io.poll_key()) is not None:
            ch = ch.upper()
            if ch in ORDER_NAMES:
                self.order = ch
                self.hurry = True
                changed = True
                self.show_order()
        return changed

    def show_order(self):
        name = ORDER_NAMES.get(self.order, "none yet")
        self.out(at(2, 1), "Orders: ", REVERSE, " %-11s" % name, RESET)

    def flush_keys(self):
        while self.live and self.io.poll_key() is not None:
            pass

    # ------------------------------------------------------------ frame

    def open(self, fight):
        self.fight = fight
        self.flush_keys()
        self.out(HIDE_CURSOR, CLEAR)
        self.out(at(1, 31), YELLOW, "|", RESET, " Our guns")
        self.out(at(2, 31), YELLOW, "|", RESET)
        self.out(at(3, 31), YELLOW, "+---------", RESET)
        self.show_order()
        self.counts()

    def close(self):
        self.out(NORMAL_SCREEN, SHOW_CURSOR, RESET, CLEAR)

    def counts(self):
        f = self.fight
        n = f.remaining
        self.out(at(1, 1), "%3d enemy ship%s in sight " % (n, " " if n == 1 else "s"))
        self.out(at(2, 33), "%4d   " % f.st.guns)
        reserve = f.remaining > f.engaged
        self.out(at(12, 40), ORANGE + "+" + RESET if reserve else " ")

    async def say(self, text, beats=1):
        self.out(at(MESSAGE_ROW, 1), ESC, "2K", text)
        await self.wait(HURRIED_BEAT if self.hurry else BEAT * beats, until_order=True)

    def status(self, text):
        self.out(at(STATUS_ROW, 1), ESC, "2K", text)

    async def ask_for_orders(self):
        """The decision window at the top of each round. The original polled
        the keyboard twice here before acting on the standing order."""
        keys = (REVERSE + " R " + RESET + "un  " + REVERSE + " F " + RESET + "ight  "
                + REVERSE + " T " + RESET + "hrow cargo")
        if self.hurry:  # orders just changed: act on them now
            self.hurry = False
            return
        if self.order is None:
            await self.say("What are your orders, Taipan?  " + keys, beats=2)
        else:
            await self.say("Orders stand: %s.  Change: %s"
                           % (ORDER_NAMES[self.order], keys), beats=1.5)
        if self.order is None and not self.live:
            await super().ask_for_orders()  # piped input: block for an answer

    # ------------------------------------------------------------ ships

    def draw_ship(self, slot, sink_by=0):
        row, col = slot_origin(slot)
        for r in range(SHIP_H):
            src = r - sink_by
            if r == SHIP_H - 1:
                line, color = SHIP[-1], SHIP_COLORS[-1]  # the sea stays put
            elif src < 0:
                line, color = " " * SHIP_W, ""
            else:
                line, color = SHIP[src], SHIP_COLORS[src]
            self.out(at(row + r, col), color, line, RESET)
        if not sink_by:
            for r, c in self.marks[slot]:
                self.out(at(row + r, col + c), DARK_RED, "x", RESET)

    def erase_ship(self, slot):
        row, col = slot_origin(slot)
        for r in range(SHIP_H):
            self.out(at(row + r, col), " " * SHIP_W)
        self.shown[slot] = False
        self.marks[slot] = []

    async def sync(self, fight):
        """Bring the picture in line with the fight: new arrivals sail in,
        ships that left vanish."""
        for slot, ship in enumerate(fight.slots):
            if ship is None and self.shown[slot]:
                self.erase_ship(slot)
            elif ship is not None and not self.shown[slot]:
                self.shown[slot] = True
                self.draw_ship(slot)
                await self.wait(0.05)
        self.counts()

    async def hit(self, slot):
        row, col = slot_origin(slot)
        spots = [(random.randrange(SHIP_H - 1), random.randrange(SHIP_W)) for _ in range(2)]
        for frame in range(4):
            color = RED if frame % 2 == 0 else ORANGE
            for r, c in spots:
                self.out(at(row + r, col + c), color, random.choice(SPARKS), RESET)
            await self.wait(0.03 if self.hurry else 0.07)
        self.marks[slot] = (self.marks[slot] + spots)[-6:]
        self.draw_ship(slot)

    async def sink(self, slot):
        delay = random.uniform(0.04, 0.22)  # some go down fast, some slowly
        for depth in range(1, SHIP_H):
            self.draw_ship(slot, sink_by=depth)
            await self.wait(0.03 if self.hurry else delay)
        self.erase_ship(slot)

    async def incoming(self):
        for i in range(10):
            on = i % 2 == 0
            self.out(INVERT_SCREEN if on else NORMAL_SCREEN,
                     at(MESSAGE_ROW, 1), RED_BAR if on else "", " " * 40, RESET)
            await self.wait(0.04)
        self.out(NORMAL_SCREEN)

    # ------------------------------------------------------------ prompts

    def clear_prompt_area(self):
        for r in range(PROMPT_ROW - 1, 25):
            self.out(at(r, 1), ESC, "2K")
        self.out(at(PROMPT_ROW, 1))

    def show_cargo(self, st):
        self.clear_prompt_area()
        self.out(at(PROMPT_ROW - 1, 1), "Aboard: " + ", ".join(
            "%s %d" % (engine.GOODS[g], st.ship[g]) for g in range(4)))
        self.out(at(PROMPT_ROW, 1))

    async def ask_key(self, prompt, keys):
        self.out(SHOW_CURSOR)
        try:
            return await self.io.key(prompt, keys)
        finally:
            self.out(HIDE_CURSOR)

    async def ask_amount(self, prompt):
        self.out(SHOW_CURSOR)
        try:
            return await self.io.amount(prompt)
        finally:
            self.out(HIDE_CURSOR)
            self.clear_prompt_area()
