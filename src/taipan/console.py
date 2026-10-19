"""Terminal input and output. The game talks only to this interface, so tests
can swap in a scripted stand-in and the web page can supply its own
keyboard and screen (see web.py).

Subclasses provide four primitives: write(), read_key(), poll_key() and
the `interactive` flag. Everything else is built on those.
"""
import asyncio
import os
import sys
import time

from . import engine

try:
    import msvcrt
except ImportError:  # not Windows
    msvcrt = None

ALL = "all"
WIDTH = 64

CLEAR = "\x1b[2J\x1b[H"
INVERSE = "\x1b[7m"
NORMAL = "\x1b[0m"


class Console:
    def __init__(self, fast=False):
        self.fast = fast
        self.interactive = msvcrt is not None and sys.stdin.isatty()
        if os.name == "nt":
            os.system("")  # turns on ANSI escape handling in Windows consoles

    # ------------------------------------------------------------ primitives

    def write(self, text):
        sys.stdout.write(text)
        sys.stdout.flush()

    async def read_key(self):
        """Wait for one keypress and return it as a character."""
        while True:
            while not msvcrt.kbhit():
                await asyncio.sleep(0.01)
            ch = msvcrt.getwch()
            if ch in "\x00\xe0":  # arrow and function keys: skip the code byte
                msvcrt.getwch()
                continue
            if ch == "\x03":
                raise KeyboardInterrupt
            return ch

    def poll_key(self):
        """A waiting keypress, or None. Never blocks."""
        if self.interactive and msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch == "\x03":
                raise KeyboardInterrupt
            return ch
        return None

    # ------------------------------------------------------------ output

    def status(self, st):
        """Redraw the full screen: the firm's dashboard, then a blank
        message area below it."""
        pct = engine.seaworthiness(st)
        cond = "%s %d%%" % (engine.condition_name(pct), pct)
        if pct < 40:
            cond = INVERSE + cond + NORMAL
        hold = INVERSE + "OVERLOADED" + NORMAL if st.hold < 0 else "free %d" % st.hold
        rule = "-" * WIDTH
        rows = [
            CLEAR + ("Firm: %s, Hong Kong" % st.firm).center(WIDTH),
            rule,
            " %-12s %-22s Debt: %s" % (engine.date_text(st),
                                       "Port: " + engine.PORTS[st.location],
                                       engine.fmt_money(st.debt)),
            rule,
            " Warehouse  (in use %d, free %d)" % (st.warehouse_used, st.warehouse_free),
        ]
        rows += self._stock_lines(st.warehouse)
        rows.append(" Ship hold  (%s, guns %d)    Condition: %s" % (hold, st.guns, cond))
        rows += self._stock_lines(st.ship)
        rows += [rule,
                 " Cash: %-20s Bank: %s" % (engine.fmt_money(st.cash),
                                             engine.fmt_money(st.bank)),
                 rule]
        self.write("\n".join(rows) + "\n")

    @staticmethod
    def _stock_lines(stock):
        return ["    %-14s %8d     %-14s %8d" % (engine.GOODS[a], stock[a],
                                                  engine.GOODS[b], stock[b])
                for a, b in ((0, 1), (2, 3))]

    def say(self, text=""):
        self.write(text + "\n")

    async def pause(self, seconds=1.5):
        """Wait, but let a keypress cut it short."""
        if self.fast:
            return
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.poll_key() is not None:
                return
            await asyncio.sleep(0.02)

    def battle_view(self):
        from .battle_screen import ScreenBattleView
        return ScreenBattleView(self)

    # ------------------------------------------------------------- input

    async def key(self, prompt, keys, default=None):
        """Read one key from `keys`. Enter picks `default` when given."""
        self.write(prompt + " ")
        while True:
            if self.interactive:
                ch = (await self.read_key()).upper()
            else:
                ch = (input().strip()[:1] or "\r").upper()
            if ch == "\r" and default:
                ch = default
            if ch in keys:
                self.write(ch + "\n")
                return ch

    async def yes(self, prompt):
        return await self.key(prompt + " (Y/N)", "YN") == "Y"

    async def read_line(self, prompt, limit=40):
        """A line of typed text, with backspace."""
        self.write(prompt + " ")
        if not self.interactive:
            return input()
        line = ""
        while True:
            ch = await self.read_key()
            if ch in "\r\n":
                self.write("\n")
                return line
            if ch in "\b\x7f":
                if line:
                    line = line[:-1]
                    self.write("\b \b")
            elif ch.isprintable() and len(line) < limit:
                line += ch
                self.write(ch)

    async def amount(self, prompt):
        """A whole number, or ALL when the reply starts with A."""
        while True:
            reply = (await self.read_line(prompt, limit=12)).strip().lower()
            if reply.startswith("a"):
                return ALL
            if reply.isdigit():
                return int(reply)
            self.write("  A whole number, please (or A for all).\n")

    async def text(self, prompt):
        return (await self.read_line(prompt)).strip()
