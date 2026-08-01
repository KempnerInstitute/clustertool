"""Account commands."""

import click

from clustertool.commands.account.adduser import add_user
from clustertool.commands.account.balance import balance
from clustertool.commands.account.fairshare import fairshare
from clustertool.commands.account.limits import limits
from clustertool.commands.account.members import members
from clustertool.commands.account.qos import qos
from clustertool.commands.account.removeuser import remove_user
from clustertool.commands.account.setfairshare import set_fairshare
from clustertool.commands.account.topusers import top_users
from clustertool.commands.account.usage import usage
from clustertool.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def account() -> None:
    """Account membership, fairshare, usage, and limits."""


account.add_command(members)
account.add_command(fairshare)
account.add_command(balance)
account.add_command(usage)
account.add_command(limits)
account.add_command(top_users)
account.add_command(qos)
account.add_command(add_user)
account.add_command(remove_user)
account.add_command(set_fairshare)
