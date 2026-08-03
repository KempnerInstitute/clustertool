"""How a panel emphasizes a figure, and what that becomes when color is off.

Two levels, because that is all the panels distinguish: a figure worth a second
look, and one that has already cost the caller something. Both are redundant by
design, since the number is always printed beside the color; the emphasis only
says where to look first.
"""

WARN = "warn"
"""Approaching a limit: a fairshare under half, a quota over the warning mark."""

ALARM = "alarm"
"""At a limit, or past it: nothing new starts, or nothing more can be written."""

COLORED = {WARN: "yellow", ALARM: "bold red"}
"""Both are ANSI names rather than hex, which is what makes them work on a light
terminal as well as a dark one. Textual maps an ANSI name through a palette chosen
for the current theme's lightness, so yellow is #fd971f on the dark theme and
#cb9000 on the light one. A hex value would be one or the other and wrong on the
rest."""

MONOCHROME = {WARN: "bold", ALARM: "bold underline"}
"""What the same two become for a terminal that asked for no color.

Textual answers NO_COLOR by mapping every color to its luminance, and the alarm
red went to a darker gray than the dim label beside it: the figure that mattered
most became the hardest of the line to see. Bold and underline pass through that
filter untouched.
"""


def resolve(emphasis: str, color: bool = True) -> str:
    """Return the style for an emphasis, in attributes alone when color is off."""
    if not emphasis:
        return ""
    return (COLORED if color else MONOCHROME).get(emphasis, emphasis)
