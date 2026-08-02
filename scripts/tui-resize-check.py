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
import select
import signal
import struct
import sys
import termios
import time

import pyte


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


def run(binary, sizes, settle=2.0):
    """Start the app, walk the sizes, and print each resulting screen."""
    first = sizes[0]
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["TERM"] = "xterm-256color"
        os.execv(binary, [binary, "me"])
    screen = pyte.Screen(first[0], first[1])
    stream = pyte.Stream(screen)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    _resize(fd, *first)
    _drain(fd, stream, settle + 1, decoder)
    for cols, rows in sizes:
        screen.resize(rows, cols)
        _resize(fd, cols, rows)
        os.kill(pid, signal.SIGWINCH)
        _drain(fd, stream, settle, decoder)
        report(screen, cols, rows)
    os.kill(pid, signal.SIGKILL)


def report(screen, cols, rows):
    """Print the whole screen with its geometry checks.

    Every row is printed: a first attempt showed only the top six, which put the
    detail pane, the standing panel and the status bar below its horizon, and the
    two defects it was written to catch were all in that region. Corners are
    counted wherever they fall rather than only at the start of a line, since the
    right-hand panel never starts one.
    """
    lines = [line.rstrip() for line in screen.display]
    over = [(n, len(line)) for n, line in enumerate(lines) if len(line) > cols]
    corners = {glyph: sum(line.count(glyph) for line in lines) for glyph in "╭╮╰╯"}
    balanced = len(set(corners.values())) == 1
    print(f"=== {cols}x{rows}")
    print(f"  overflow={over or 'none'}  corners={corners} balanced={balanced}")
    for n, line in enumerate(lines):
        print(f"  {n:3d}|{line}")


if __name__ == "__main__":
    pairs = [tuple(int(n) for n in arg.split("x")) for arg in sys.argv[2:]]
    run(sys.argv[1], pairs or [(100, 26)])
