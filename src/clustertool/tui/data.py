"""Panel data, gathered without any reference to the widgets that show it.

Each function returns a plain dataclass so it can be tested without starting an
app, which is where the parsing and failure handling are covered.
"""

import dataclasses
import os
import pwd
import socket

from clustertool import site


@dataclasses.dataclass(frozen=True)
class Identity:
    """Who is running the app, and where."""

    user: str
    full_name: str
    host: str
    cluster: str


def identity() -> Identity:
    """Return the caller's identity from the uid, never from the environment."""
    from clustertool import slurm

    user = pwd.getpwuid(os.getuid()).pw_name
    try:
        full = slurm.user_fullnames([user]).get(user, "")
    except Exception:
        full = ""
    return Identity(
        user=user,
        full_name=full,
        host=socket.gethostname().split(".")[0],
        cluster=site.qos_cluster(),
    )
