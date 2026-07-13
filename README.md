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
  `jobstats`, and the storage tools (`quota`, `lfs`). A command only needs the
  tools it uses.

## Install

Install as a tool from the repository:

```bash
uv tool install git+https://github.com/KempnerInstitute/ClusterTools
```

Or work from a clone:

```bash
git clone https://github.com/KempnerInstitute/ClusterTools
cd ClusterTools
uv sync
uv run clustertools --help
```

## Usage

```bash
clustertools --help              # list command groups
clustertools gpu --help          # list commands in the gpu group
clustertools gpu labs-util       # rank every account by base-partition GPU usage
clustertools gpu lab-util kempner_sham_lab   # one account's usage, by user and partition
clustertools nodes list kempner_h100         # node names and states in a partition
clustertools account members kempner_dev     # users in a fairshare account
clustertools storage quota kempner_dev       # VAST scratch quota for an account
clustertools jobs stats 1234567              # utilization for a job
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
| `gpu labs-util` | none | Rank every account by live base-partition GPU usage. |
| `gpu lab-util` | `ACCOUNT` | Show one account's live GPU usage, by user and partition. |
| `jobs stats` | `JOBID...` | Show job utilization (via `jobstats`). |
| `account members` | `ACCOUNT` | List the users in a fairshare account. |
| `nodes list` | `PARTITION...` | List node names and states in one or more partitions. |
| `storage quota` | `ACCOUNT [-f vast\|lustre]` | Show an account's VAST or Lustre quota. |
| `diag nccl` | `NODE` | Run a single-node NCCL bandwidth test on a GPU node. |

## Project layout

```
src/cluster_tools/
  cli.py              # umbrella group, registers command groups
  process.py          # subprocess helpers (capture / stream)
  slurm.py            # read-only Slurm query and parse helpers
  storage.py          # storage quota command construction
  commands/           # one module per group
    gpu.py  jobs.py  account.py  nodes.py  storage.py  diag.py
tests/                # unit tests
```

## Contributing

New commands are added by pull request. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Kempner Institute, Harvard
University.
