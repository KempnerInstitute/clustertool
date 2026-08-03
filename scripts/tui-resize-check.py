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
    """Check the painted headings against what the code says the table may do.

    The settling check alone is not enough: it sees a frame that lands wrong and
    then heals, and is blind to one that lands wrong and stays, because then the
    early and the settled screen agree. This compares what is on the screen with
    what the code says should be there, so a wrong frame is wrong either way.

    Which columns fit is decided by their minimum widths and so can be predicted
    here. How wide each one grows is decided by the values on screen, which this
    script cannot predict: it drives the real dashboard against the live queue, and
    reading the queue again to ask would race with it. So the widths are read off the
    frame and checked against what the code says a width may be, in three ways.

    Their bounds, which catches the failure this was written for: a resize that
    repainted every column at its heading width, narrower than any minimum. That a
    cell fits its column, which is the ellipsis doing its job. And that no column is
    wider than the widest value painted in it, which is the one the bounds check was
    blind to: a column grown to its static ceiling while another was cut to nine
    cells passed a bounds check and was exactly the thing being fixed.
    """
    from clustertool.tui.panels.jobs import CELL_PADDING, COLUMNS, layout

    minimum = {name: low for name, low, _ in COLUMNS}
    ceiling = {name: high for name, _, high in COLUMNS}
    for index, line in enumerate(lines):
        edges = [n for n, char in enumerate(line) if char == "│"]
        if len(edges) < 2 or "ID" not in line:
            continue
        table_width = edges[1] - edges[0] - 3
        want = [name for name, _ in layout(table_width)]
        at = [(name, line.find(name, edges[0])) for name in want]
        missing = [name for name, pos in at if pos < 0]
        if missing:
            return f"MISSING {missing}"
        if [pos for _, pos in at] != sorted(pos for _, pos in at):
            return f"OUT OF ORDER {at}"
        painted = [
            (name, later - pos - CELL_PADDING)
            for (name, pos), (_, later) in zip(at, at[1:], strict=False)
        ]
        wrong = [
            (name, width) for name, width in painted if not minimum[name] <= width <= ceiling[name]
        ]
        if wrong:
            return f"OUT OF BOUNDS {wrong}"
        values = _painted_cells(lines[index + 1 :], at, edges[1])
        loose = [
            (name, width, values[name])
            for name, width in painted
            if values.get(name) and width > max(values[name], minimum[name])
        ]
        if loose:
            return f"WIDER THAN ITS VALUES {loose}"
        return f"ok, {len(want)} columns in {table_width}, widths {dict(painted)}"
    return "no table row found"


def _painted_cells(rows, at, right):
    """Return the widest value painted in each column, over the rows below the heading.

    Read off the screen rather than from the queue, which is the only source this
    script has that cannot disagree with what the app drew.
    """
    from clustertool.tui.panels.jobs import CELL_PADDING

    ends = [start - CELL_PADDING for _, start in at[1:]] + [right]
    widest = {}
    for line in rows:
        if "╍" in line or "╰" in line or "│" not in line:
            break
        for (name, start), end in zip(at, ends, strict=True):
            widest[name] = max(widest.get(name, 0), len(line[start:end].rstrip()))
    return widest


def _steady(line):
    """Return a line with the parts that are meant to change taken out."""
    return re.sub(r"\d+[-:]?[\d:]*", "N", line)


if __name__ == "__main__":
    pairs = [tuple(int(n) for n in arg.split("x")) for arg in sys.argv[2:]]
    run(sys.argv[1], pairs or [(100, 26)])
