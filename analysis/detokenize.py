"""Detokenize an Applesoft BASIC program image into a text listing.

Usage: python -I detokenize.py <program.bin> <load_address_hex> <out.txt>
"""
import sys

TOKENS = [
    "END", "FOR", "NEXT", "DATA", "INPUT", "DEL", "DIM", "READ", "GR", "TEXT",
    "PR#", "IN#", "CALL", "PLOT", "HLIN", "VLIN", "HGR2", "HGR", "HCOLOR=",
    "HPLOT", "DRAW", "XDRAW", "HTAB", "HOME", "ROT=", "SCALE=", "SHLOAD",
    "TRACE", "NOTRACE", "NORMAL", "INVERSE", "FLASH", "COLOR=", "POP", "VTAB",
    "HIMEM:", "LOMEM:", "ONERR", "RESUME", "RECALL", "STORE", "SPEED=", "LET",
    "GOTO", "RUN", "IF", "RESTORE", "&", "GOSUB", "RETURN", "REM", "STOP", "ON",
    "WAIT", "LOAD", "SAVE", "DEF", "POKE", "PRINT", "CONT", "LIST", "CLEAR",
    "GET", "NEW", "TAB(", "TO", "FN", "SPC(", "THEN", "AT", "NOT", "STEP", "+",
    "-", "*", "/", "^", "AND", "OR", ">", "=", "<", "SGN", "INT", "ABS", "USR",
    "FRE", "SCRN(", "PDL", "POS", "SQR", "RND", "LOG", "EXP", "COS", "SIN",
    "TAN", "ATN", "PEEK", "LEN", "STR$", "VAL", "ASC", "CHR$", "LEFT$",
    "RIGHT$", "MID$",
]


def detokenize(data, load):
    out = []
    addr = load
    while True:
        o = addr - load
        nxt = data[o] | data[o + 1] << 8
        if nxt == 0:
            break
        num = data[o + 2] | data[o + 3] << 8
        body = data[o + 4:nxt - load - 1]
        text = []
        in_quote = in_rem = False
        for b in body:
            if in_quote or in_rem or b < 0x80:
                ch = chr(b & 0x7F)
                if ch == '"':
                    in_quote = not in_quote
                text.append(ch)
            else:
                tok = TOKENS[b - 0x80] if b - 0x80 < len(TOKENS) else "?%02X?" % b
                text.append(" %s " % tok)
                if tok == "REM":
                    in_rem = True
        out.append("%d %s" % (num, "".join(text).strip()))
        addr = nxt
    return out


if __name__ == "__main__":
    src, load, dst = sys.argv[1], int(sys.argv[2], 16), sys.argv[3]
    lines = detokenize(open(src, "rb").read(), load)
    with open(dst, "w", encoding="utf8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("%d lines -> %s" % (len(lines), dst))
