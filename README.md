# Taipan (Apple II) → Python

A Python remake of the 1982 Apple II game *Taipan!* that runs in a Windows terminal.
It keeps the original game's rules and formulas, recovered from the disk image, but the code and wording are newly written.

## Playing

```
taipan.bat                 # double-click, or run from a terminal
taipan.bat --fast          # no pauses between messages
taipan.bat --seed 42       # repeatable game
```

Needs Python 3.10 or later and nothing else. Use Windows Terminal or any console that handles ANSI colors (Windows 10 and later do).

- Single-key answers don't need Enter.
- Amount prompts take a number, or `A` for "all".
- The window needs to be at least 40 columns by 24 rows for fights.

### Differences from the original

- **Fights look different but play the same.** They run in real time, as in the original:
  - Press R, F or T at any moment to give an order. It keeps repeating each round until you press another key, and if you never give one the enemy just fires.
  - The screen layout is the same: up to ten ships in two rows of five, a `+` when more wait beyond them, and a guns panel. Shots land, ships sink out of sight and the screen flashes when you're hit.
  - The ship and explosion artwork is new, drawn in text characters with ANSI colors.
  - The screen flash relies on the terminal supporting reverse video. Where it doesn't, the message line still flashes red.
- **Wording:** all on-screen text is new.

Everything else, including the original's quirks, follows `analysis/game-rules.md`. For example, Wu accepts overpayment and you then have negative debt, and buying cargo can overload the ship.

## Tests

```
python -m unittest discover -s tests
```

The tests check the formulas against the rules doc and the combat mechanics. A random robot also plays 300 seeded games to the end, checking after every screen redraw that the hold and warehouse books balance.

## Layout

| Folder | Contents |
|---|---|
| `disk/` | Original disk image `taipan.dsk` (SHA-256 `A13BA886...5DAD`). Never modified. |
| `extracted/` | Files pulled off the disk and carved from them (local analysis only). |
| `analysis/` | Scripts and notes about how the original works. |
| `src/` | The Python game. |
| `tests/` | Tests for the Python game. |

## How the original is built

The disk is DOS 3.3 with two files:

- `HELLO`: a generic disk-menu program, not part of the game.
- `TAIPAN`: a locked binary whose catalog entry claims 144 bytes at `$0300`, but which takes up 117 sectors.
  It is a memory image saved with `BSAVE TAIPAN,A$704,L$73BF`, with a 144-byte loader patched over its start.

Once loaded, memory holds:

| Address | Contents |
|---|---|
| `$0300` | 6502 loader. It points Applesoft at `$0801` and jumps to RUN (`$D566`). |
| `$0801` | One-line BASIC stub. It POKEs the program start to `$4001` and jumps there. |
| `$0823`–`$3FFF` | 6502 helper routines (screen and input), plus the game's text strings. BASIC calls them with `CALL 2200`–`CALL 2680`. |
| `$4001`–`$7AB7` | The game: a 290-line Applesoft BASIC program (lines 10–63999). |

## Reproducing the extraction

```
cp2 extract --raw disk/taipan.dsk TAIPAN        # full 29,696-byte file into extracted/raw/
# carve $4001.. (file offset 4 = $0704) to extracted/GAME_BASIC.bin
python -I analysis/detokenize.py extracted/GAME_BASIC.bin 4001 extracted/GAME_BASIC.txt
```
