"""Drive the dashboard through a series of terminal sizes and report the screen.

tmux cannot resize a single-pane window on older versions, and stripping escape
codes from a raw pty stream glues screen rows together, so neither can measure a
redraw after a resize. A terminal emulator interprets the stream into a real
screen buffer, which is what alignment has to be judged against.
"""

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


def _drain(fd, stream, seconds):
    end = time.time() + seconds
    while time.time() < end:
        ready, _, _ = select.select([fd], [], [], 0.2)
        if ready:
            try:
                stream.feed(os.read(fd, 65536).decode("utf-8", "replace"))
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
    _resize(fd, *first)
    _drain(fd, stream, settle + 1)
    for cols, rows in sizes:
        screen.resize(rows, cols)
        _resize(fd, cols, rows)
        os.kill(pid, signal.SIGWINCH)
        _drain(fd, stream, settle)
        lines = [line.rstrip() for line in screen.display]
        over = [len(line) for line in lines if len(line) > cols]
        opened = sum(1 for line in lines if line.startswith("╭"))
        closed = sum(1 for line in lines if line.startswith("╰"))
        status = lines[rows - 1] if len(lines) >= rows else ""
        print(f"=== {cols}x{rows}")
        print(f"  overflow={over or 'none'}  borders opened={opened} closed={closed}")
        print(f"  last row: {status[:cols]!r}")
        for line in lines[:6]:
            print("  |" + line)
    os.kill(pid, signal.SIGKILL)


if __name__ == "__main__":
    pairs = [tuple(int(n) for n in arg.split("x")) for arg in sys.argv[2:]]
    run(sys.argv[1], pairs or [(100, 26)])
