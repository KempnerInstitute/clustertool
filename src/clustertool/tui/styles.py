"""Two levels of emphasis for a figure, and what each becomes without color."""

WARN = "warn"
"""Approaching a limit: a fairshare under half, a quota over the warning mark."""

ALARM = "alarm"
"""At a limit or past it: nothing new starts, or nothing more can be written."""

COLORED = {WARN: "yellow", ALARM: "bold red"}
"""ANSI names rather than hex, so Textual maps them to a palette chosen for the
current theme and they read on a light terminal as well as a dark one."""

MONOCHROME = {WARN: "bold", ALARM: "bold underline"}
"""What the two become when NO_COLOR is set.

Textual answers NO_COLOR by mapping each color to its luminance, which leaves a
saturated color darker than the text beside it. Bold and underline are unaffected.
"""


def resolve(emphasis: str, color: bool = True) -> str:
    """Return the style for an emphasis, in attributes alone when color is off."""
    if not emphasis:
        return ""
    return (COLORED if color else MONOCHROME).get(emphasis, emphasis)
