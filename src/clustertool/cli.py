"""Command-line entry point for the cluster tools CLI."""

import importlib.metadata
from typing import ClassVar

import click

from clustertool.commands.account import account
from clustertool.commands.completion import completion
from clustertool.commands.diag import diag
from clustertool.commands.gpu import gpu
from clustertool.commands.jobs import jobs
from clustertool.commands.me import me
from clustertool.commands.nodes import nodes
from clustertool.commands.qos import qos
from clustertool.commands.search import search
from clustertool.commands.storage import storage
from clustertool.grouping import SectionedGroup, annotate_paths
from clustertool.process import CommandError


def _version() -> str:
    """Return the installed package version."""
    try:
        return importlib.metadata.version("clustertool")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


class ClusterToolGroup(SectionedGroup):
    """Group that reports command failures as clean CLI errors."""

    aliases: ClassVar[dict[str, str]] = {"find": "search", "lookup": "search"}

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except CommandError as exc:
            raise click.ClickException(str(exc)) from exc


def _register_plugins(group: click.Group) -> None:
    """Add commands published under the clustertool.commands entry point group."""
    for entry in importlib.metadata.entry_points(group="clustertool.commands"):
        try:
            command = entry.load()
        except Exception:
            continue
        if isinstance(command, click.Command):
            group.add_command(command)


@click.group(
    cls=ClusterToolGroup,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="One umbrella CLI for a Slurm cluster: jobs, GPUs, nodes, storage, and health checks.",
)
@click.version_option(version=_version(), prog_name="clustertool")
def main() -> None:
    pass


main.add_command(gpu)
main.add_command(jobs)
main.add_command(account)
main.add_command(nodes)
main.add_command(storage)
main.add_command(diag)
main.add_command(qos)
main.add_command(search)
main.add_command(completion)
main.add_command(me)

_register_plugins(main)
annotate_paths(main)


if __name__ == "__main__":
    main()
