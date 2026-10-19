"""Browser front end. Runs under Pyodide, with an xterm.js terminal as the
screen and keyboard. index.html loads this module and calls start()."""
import asyncio
import collections

from pyodide.ffi import create_proxy

from . import engine
from .console import Console
from .game import run


class WebIO(Console):
    def __init__(self, term):
        # Console.__init__ is skipped: it sets up the Windows console.
        self.term = term
        self.fast = False
        self.interactive = True
        self.keys = collections.deque()
        self.waiter = None

    def feed(self, data, *_):
        """Called by xterm.js with every keypress or paste. xterm.js passes a
        second, unused argument, so extra arguments are ignored."""
        if data.startswith("\x1b"):
            return  # arrow and function keys
        self.keys.extend(data)
        if self.waiter is not None and not self.waiter.done():
            self.waiter.set_result(None)

    def write(self, text):
        self.term.write(text)

    async def read_key(self):
        while not self.keys:
            self.waiter = asyncio.get_running_loop().create_future()
            await self.waiter
        return self.keys.popleft()

    def poll_key(self):
        return self.keys.popleft() if self.keys else None


async def start(term):
    io = WebIO(term)
    term.onData(create_proxy(io.feed))
    term.focus()
    await run(io, engine.Rng())
    io.write("\nFair winds, Taipan. Reload the page to sail again.\n")
