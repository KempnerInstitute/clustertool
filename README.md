<p align="center">
  <img src="_static/ct-repo-image.png" alt="Cluster Tools" width="100%">
</p>

# Cluster Tools

Kempner AI Cluster Tools: a single umbrella CLI (`clustertools`) that
centralizes the cluster scripts used by both researchers and the engineering
team, so common tasks live in one place with consistent help and behavior.

Every task is a subcommand under a group (for example `clustertools gpu ...`).
Each command has `--help` explaining what it does, its use cases, and its
inputs.

## Requirements

- [uv](https://docs.astral.sh/uv/) for environment and dependency management.
- Run on a cluster login node. Commands shell out to the host's own tools:
  Slurm (`squeue`, `sacctmgr`, `sinfo`, `sshare`, `scontrol`, `srun`),
  `jobstats`, the FASRC `quota` tool, and `getent`. A command only needs
  the tools it uses.
- Some commands need more: the live monitors and `diag ib` need passwordless
  `ssh` to nodes running `nvidia-smi`; `gpu nvtop` needs `tmux` and `nvtop`;
  `diag nvlink` needs `nvcc` and NCCL; `diag nccl` needs `torch`.

## Install

Install as a tool from the repository:

```bash
uv tool install git+https://github.com/KempnerInstitute/cluster-tools
```

Or work from a clone:

```bash
git clone https://github.com/KempnerInstitute/cluster-tools
cd cluster-tools
uv sync
uv run clustertools --help
```

## Usage

```bash
clustertools --help              # list command groups
clustertools gpu --help          # list commands in the gpu group
clustertools gpu usage           # rank every account by base-partition GPU usage
clustertools gpu usage kempner_sham_lab      # one account's usage, by user and partition
clustertools nodes list kempner_h100         # node names and states in a partition
clustertools account members kempner_dev     # users in a fairshare account
clustertools storage quota holylfs06 -g kempner_dev  # lab quota on Lustre (or VAST)
clustertools jobs stats 1234567              # utilization for a job
clustertools gpu avail kempner_h100          # nodes with allocatable GPUs (ratio-capped)
clustertools jobs violators kempner_h100     # jobs over the per-GPU norm
clustertools gpu monitor-job 1234567         # live per-node GPU/CPU/mem/net table
```

## Command groups

Commands are classified into groups. Run `clustertools <group> --help` to list
a group's commands.

| Group | Scope |
| --- | --- |
| `gpu` | GPU usage and availability |
| `jobs` | Job queue and history |
| `account` | Account membership, limits, fairshare |
| `nodes` | Node status and health |
| `storage` | Filesystem quotas |
| `diag` | Diagnostics and benchmarks |

## Commands

| Command | Inputs | Description |
| --- | --- | --- |
| `gpu usage` | `[ACCOUNT]` | Rank all labs by GPU usage, or break one lab down by user and partition. |
| `gpu avail` | `PARTITION [--cpu-per-gpu] [--mem-per-gpu]` | List nodes with allocatable GPUs (free GPUs capped by the enforced per-GPU CPU/mem ratio). |
| `gpu monitor-partition` | `PARTITION [--interval] [--filter]` | Live per-node GPU/CPU/mem/network table for a partition. |
| `gpu monitor-job` | `JOBID [--interval]` | Live per-node GPU/CPU/mem/network table for a job. |
| `gpu nvtop` | `JOBID [--no-attach]` | tmux session running nvtop on each of a job's nodes. |
| `jobs stats` | `JOBID...` | Show job utilization (via `jobstats`). |
| `jobs violators` | `PARTITION [--cpu-per-gpu] [--mem-per-gpu]` | List running jobs over the per-GPU CPU/memory norm. |
| `account members` | `ACCOUNT` / `--all` | List users in an account, or all lab accounts as CSV. |
| `nodes list` | `PARTITION...` | List node names and states in one or more partitions. |
| `storage quota` | `PATH [-g\|-u]` | Show a storage quota on any filesystem (VAST, Lustre, home) via the FASRC `quota` tool. |
| `storage home` | `[--scan] [--top N] [--ncdu]` | Home directory usage (`df ~`); with `--scan`, the largest subdirectories. |
| `diag ib` | `PARTITION... [--parallel]` | Report nodes with InfiniBand ports DOWN. |
| `diag nccl` | `[--python] [--timeout]` | Multi-node FSDP NCCL sanity check inside a Slurm job. |
| `diag nvlink` | `[BYTES] [WARMUP] [REPORT] [--gpus] [--nvcc]` | Saturate a node's NVLink (2-8 GPUs) with NCCL all-reduce. |

## Project layout

```
src/cluster_tools/
  cli.py              # umbrella group, registers command groups
  process.py          # subprocess helpers (capture / stream)
  slurm.py            # read-only Slurm query and parse helpers
  storage.py          # storage quota command construction
  monitor.py          # shared live per-node monitor (monitor-partition/-job)
  data/               # bundled payloads (monitor sample, nccl test, nvlink .cu)
  commands/           # one package per group; one file per command
    gpu/              # usage, avail, monitor_partition, monitor_job, nvtop
    jobs/             # stats, violators
    account/          # members
    nodes/            # list
    storage/          # quota, home
    diag/             # ib, nccl, nvlink
tests/                # unit tests
```

## Contributing

New commands are added by pull request. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Kempner Institute, Harvard
University.
