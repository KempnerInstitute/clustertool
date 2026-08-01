"""QoS inspection and administration commands."""

import click

from clustertool.commands.qos.create import create
from clustertool.commands.qos.delete import delete
from clustertool.commands.qos.grant import grant
from clustertool.commands.qos.holders import holders
from clustertool.commands.qos.modify import modify
from clustertool.commands.qos.retire import retire
from clustertool.commands.qos.revoke import revoke
from clustertool.commands.qos.sync import sync
from clustertool.grouping import SectionedGroup


@click.group(cls=SectionedGroup)
def qos() -> None:
    """Slurm QoS: who holds them, and (admin) provisioning and assignment."""


qos.add_command(holders)
qos.add_command(create)
qos.add_command(modify)
qos.add_command(delete)
qos.add_command(grant)
qos.add_command(revoke)
qos.add_command(retire)
qos.add_command(sync)
