"""Panel data, gathered without any reference to the widgets that show it.

Each function returns a plain dataclass so it can be tested without starting an
app, which is where the parsing and failure handling are covered.
"""

import dataclasses
import os
import pwd
import socket

from clustertool import site
from clustertool.process import CommandError


@dataclasses.dataclass(frozen=True)
class Identity:
    """Who is running the app, and where."""

    user: str
    full_name: str
    host: str
    site_name: str


def identity() -> Identity:
    """Return the caller's identity from the uid, never from the environment.

    The site name rather than the QoS cluster, which the site config documents as
    the cluster the admin qos commands write to and which would label every
    deployment with the packaged default.
    """
    from clustertool import slurm

    user = pwd.getpwuid(os.getuid()).pw_name
    try:
        full = slurm.user_fullnames([user]).get(user, "")
    except CommandError:
        full = ""
    return Identity(
        user=user,
        full_name=full,
        host=socket.gethostname().split(".")[0],
        site_name=site.site_name(),
    )
