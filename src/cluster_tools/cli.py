"""Command-line entry point for Kempner AI Cluster Tools."""

import importlib.metadata

import click

from cluster_tools.commands.gpu import gpu
from cluster_tools.slurm import SlurmError


def _version() -> str:
    """Return the installed package version."""
    try:
        return importlib.metadata.version("cluster-tools")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"


class ClusterToolsGroup(click.Group):
    """Group that reports Slurm failures as clean CLI errors."""

    def invoke(self, ctx: click.Context):
        try:
            return super().invoke(ctx)
        except SlurmError as exc:
            raise click.ClickException(str(exc)) from exc


@click.group(cls=ClusterToolsGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=_version(), prog_name="clustertools")
def main() -> None:
    """Kempner AI Cluster Tools: a single umbrella for cluster scripts."""


main.add_command(gpu)


if __name__ == "__main__":
    main()
