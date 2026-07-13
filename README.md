# Cluster Tools

Kempner AI Cluster Tools: a single umbrella CLI (`clustertools`) that
centralizes the cluster scripts used by both researchers and the engineering
team, so common tasks live in one place with consistent help and behavior.

Every task is a subcommand under a group (for example `clustertools gpu ...`).
Each command has `--help` explaining what it does, its use cases, and its
inputs.

## Requirements

- [uv](https://docs.astral.sh/uv/) for environment and dependency management.
- Slurm client commands (`squeue`, `sacctmgr`, `scontrol`) available on the
  host, i.e. run these on a cluster login node.

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
```

## Available commands

| Command | Inputs | Description |
| --- | --- | --- |
| `gpu labs-util` | none | Rank every account by live base-partition GPU usage. |
| `gpu lab-util` | `ACCOUNT` | Show one account's live GPU usage, by user and partition. |

## Project layout

```
src/cluster_tools/
  cli.py              # umbrella group, registers command groups
  slurm.py            # read-only Slurm query helpers (shared logic)
  commands/
    gpu.py            # the gpu group and its commands
tests/                # unit tests
```

## Contributing

New commands are added by pull request. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

TBD.
