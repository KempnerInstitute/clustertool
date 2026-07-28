"""Account commands."""

import click

from cluster_tools.commands.account.adduser import add_user
from cluster_tools.commands.account.fairshare import fairshare
from cluster_tools.commands.account.limits import limits
from cluster_tools.commands.account.members import members
from cluster_tools.commands.account.qos import qos
from cluster_tools.commands.account.removeuser import remove_user
from cluster_tools.commands.account.setfairshare import set_fairshare
from cluster_tools.commands.account.topusers import top_users
from cluster_tools.commands.account.usage import usage
from cluster_tools.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def account() -> None:
    """Account membership, fairshare, usage, and limits."""


account.add_command(members)
account.add_command(fairshare)
account.add_command(usage)
account.add_command(limits)
account.add_command(top_users)
account.add_command(qos)
account.add_command(add_user)
account.add_command(remove_user)
account.add_command(set_fairshare)
