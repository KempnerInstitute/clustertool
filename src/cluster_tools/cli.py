"""Command-line entry point for Kempner AI Cluster Tools."""

import importlib.metadata
from typing import ClassVar

import click

from cluster_tools.commands.account import account
from cluster_tools.commands.completion import completion
from cluster_tools.commands.diag import diag
from cluster_tools.commands.gpu import gpu
from cluster_tools.commands.jobs import jobs
from cluster_tools.commands.me import me
from cluster_tools.commands.nodes import nodes
from cluster_tools.commands.search import search
from cluster_tools.commands.storage import storage
from cluster_tools.grouping import SectionedGroup
from cluster_tools.process import CommandError


def _version() -> str:
    """Return the installed package version."""
    try:
        return importlib.metadata.version("cluster-tools")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


class ClusterToolsGroup(SectionedGroup):
    """Group that reports command failures as clean CLI errors."""

    aliases: ClassVar[dict[str, str]] = {"find": "search", "lookup": "search"}

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except CommandError as exc:
            raise click.ClickException(str(exc)) from exc


@click.group(cls=ClusterToolsGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=_version(), prog_name="clustertools")
def main() -> None:
    """Kempner AI Cluster Tools: a single umbrella for cluster scripts."""


main.add_command(gpu)
main.add_command(jobs)
main.add_command(account)
main.add_command(nodes)
main.add_command(storage)
main.add_command(diag)
main.add_command(search)
main.add_command(completion)
main.add_command(me)


if __name__ == "__main__":
    main()
