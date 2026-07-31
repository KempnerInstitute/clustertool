"""Shared limit options and spec resolution for qos create and modify."""

from collections.abc import Callable

import click

from cluster_tools import qos as qoslib


def limit_options(func: Callable) -> Callable:
    """Attach the five QoS limit options (-g/-n/-G/-j/-J) to a command."""
    options = [
        click.option(
            "-J",
            "--jobs-per-user",
            type=int,
            default=None,
            help="Per-user running-job cap (MaxJobsPU); -1 clears.",
        ),
        click.option(
            "-j",
            "--job-gpu",
            type=int,
            default=None,
            help="Per-job GPU cap (MaxTRES gres/gpu); -1 clears.",
        ),
        click.option(
            "-G",
            "--group-gpu",
            type=int,
            default=None,
            help="Total GPU cap for the QoS (GrpTRES gres/gpu); -1 clears.",
        ),
        click.option(
            "-n",
            "--node-per-user",
            type=int,
            default=None,
            help="Per-user node cap (MaxTRESPU node); -1 clears.",
        ),
        click.option(
            "-g",
            "--gpu-per-user",
            type=int,
            default=None,
            help="Per-user GPU cap (MaxTRESPU gres/gpu); -1 clears.",
        ),
    ]
    for option in options:
        func = option(func)
    return func


def resolve_specs(
    gpu_per_user: int | None,
    node_per_user: int | None,
    group_gpu: int | None,
    job_gpu: int | None,
    jobs_per_user: int | None,
) -> list[str]:
    """Validate the limit flags and build the sacctmgr set specs.

    Raises UsageError when no limit is given or a value is neither a positive
    integer nor -1 (the clear sentinel).
    """
    values = [gpu_per_user, node_per_user, group_gpu, job_gpu, jobs_per_user]
    if all(value is None for value in values):
        raise click.UsageError("give at least one limit (for example -g 4)")
    for value in values:
        if value is not None and value != -1 and value < 1:
            raise click.UsageError("limit values must be a positive integer, or -1 to clear")
    return qoslib.build_limit_specs(
        gpu_per_user=gpu_per_user,
        node_per_user=node_per_user,
        group_gpu=group_gpu,
        job_gpu=job_gpu,
        jobs_per_user=jobs_per_user,
    )
