"""Drive the dashboard through a series of terminal sizes and report the screen.

tmux cannot resize a single-pane window on older versions, and stripping escape
codes from a raw pty stream glues screen rows together, so neither can measure a
redraw after a resize. A terminal emulator interprets the stream into a real
screen buffer, which is what alignment has to be judged against.
"""

import codecs
import fcntl
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import time

import pyte

EARLY = float(os.environ.get("TUI_EARLY", "0.35"))
"""How long after a resize the first screen is taken, to catch a frame that heals.

Small on purpose. A frame that lands wrong and is corrected a second later looks
perfect to anything that waits for the screen to settle, so this samples before
the correction can arrive.
"""


def _resize(fd, cols, rows):
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def _drain(fd, stream, seconds, decoder):
    """Feed the emulator for a while, decoding across reads rather than per read.

    A box-drawing glyph is three bytes, and a read boundary can fall inside one.
    Decoding each read on its own turned those into a replacement character and
    reported a redraw as differing from an identical one.
    """
    end = time.time() + seconds
    while time.time() < end:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if ready:
            try:
                stream.feed(decoder.decode(os.read(fd, 65536)))
            except OSError:
                return


FIRST_LOAD = 9.0
"""Time allowed before the walk starts, for every panel to hold real data.

The quota fan-out takes about six seconds cold. Beginning the walk before it lands
makes the panel change during the sample window, and the settling check then
reports that arrival rather than a redraw that went wrong.
"""


def run(binary, sizes, settle=2.0):
    """Start the app, walk the sizes, and print each resulting screen."""
    first = sizes[0]
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        os.execv(binary, [binary, "me"])
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    screen = pyte.Screen(first[0], first[1])
    _resize(fd, *first)
    _drain(fd, pyte.Stream(screen), FIRST_LOAD, decoder)
    for cols, rows in sizes:
        nudge = max(rows - 1, 2)
        _resize(fd, cols, nudge)
        os.kill(pid, signal.SIGWINCH)
        _drain(fd, pyte.Stream(pyte.Screen(cols, nudge)), 0.4, decoder)
        screen = pyte.Screen(cols, rows)
        stream = pyte.Stream(screen)
        _resize(fd, cols, rows)
        os.kill(pid, signal.SIGWINCH)
        _drain(fd, stream, EARLY, decoder)
        early = [line.rstrip() for line in screen.display]
        _drain(fd, stream, max(settle - EARLY, 0.1), decoder)
        report(screen, cols, rows, early)
    os.kill(pid, signal.SIGKILL)


def report(screen, cols, rows, early):
    """Print the whole screen with its geometry checks.

    Every row is printed: a first attempt showed only the top six, which put the
    detail pane, the standing panel and the status bar below its horizon, and the
    two defects it was written to catch were all in that region. Corners are
    counted wherever they fall rather than only at the start of a line, since the
    right-hand panel never starts one.

    The early screen is compared against the settled one, because a resize that
    lands wrong and is corrected a second later looks perfect to anything that
    only waits. Ignore the clock, which is meant to change.
    """
    lines = [line.rstrip() for line in screen.display]
    over = [(n, len(line)) for n, line in enumerate(lines) if len(line) > cols]
    corners = {glyph: sum(line.count(glyph) for line in lines) for glyph in "╭╮╰╯"}
    balanced = len(set(corners.values())) == 1
    paired = enumerate(zip(early, lines, strict=False))
    settling = [n for n, (a, b) in paired if _steady(a) != _steady(b)]
    print(f"=== {cols}x{rows}")
    print(f"  overflow={over or 'none'}  corners={corners} balanced={balanced}")
    print(f"  rows still changing after {EARLY}s: {settling or 'none'}")
    print(f"  table headings: {_headings_verdict(lines)}")
    for n, line in enumerate(lines):
        print(f"  {n:3d}|{line}")


def _headings_verdict(lines):
    """Check the painted heading positions against the widths layout asked for.

    The settling check alone is not enough: it sees a frame that lands wrong and
    then heals, and is blind to one that lands wrong and stays, because then the
    early and the settled screen agree. This compares what is on the screen with
    what the code says should be there, so a wrong frame is wrong either way.
    """
    from clustertool.tui.panels.jobs import layout

    for line in lines:
        edges = [n for n, char in enumerate(line) if char == "│"]
        if len(edges) < 2 or "ID" not in line:
            continue
        table_width = edges[1] - edges[0] - 3
        want = layout(table_width)
        offset, expected = edges[0] + 2, []
        for name, width in want:
            expected.append((name, offset + 1))
            offset += width + 2
        painted = [(name, line.find(name, start - 1)) for name, start in expected]
        wrong = [
            (name, start, at)
            for (name, start), (_, at) in zip(expected, painted, strict=True)
            if at != start
        ]
        return f"ok, {len(want)} columns in {table_width}" if not wrong else f"MISPLACED {wrong}"
    return "no table row found"


def _steady(line):
    """Return a line with the parts that are meant to change taken out."""
    return re.sub(r"\d+[-:]?[\d:]*", "N", line)


if __name__ == "__main__":
    pairs = [tuple(int(n) for n in arg.split("x")) for arg in sys.argv[2:]]
    run(sys.argv[1], pairs or [(100, 26)])
