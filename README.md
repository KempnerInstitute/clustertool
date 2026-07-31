<p align="center">
  <img src="_static/ct-repo-image.png" alt="Cluster Tools" width="60%">
</p>

# Cluster Tools

A single umbrella CLI (`clustertools`) that centralizes the Slurm cluster
scripts used by both researchers and the engineering team, so common tasks live
in one place with consistent help and behavior. It is built at the Kempner
Institute and adapts to other clusters through a site config.

Every task is a subcommand under a group (for example `clustertools gpu ...`).
Each command has `--help` explaining what it does, its use cases, and its
inputs.

## Requirements

- [uv](https://docs.astral.sh/uv/) for environment and dependency management.
- Run on a cluster login node. Commands shell out to the host's own tools:
  Slurm (`squeue`, `sacct`, `sacctmgr`, `sinfo`, `sshare`, `sprio`, `sstat`,
  `sdiag`, `scontrol`, `salloc`, `sbatch`, `scancel`, `srun`), the FASRC wrappers
  (`spart`, `stotal`, `seff-account`, `showq`, `lsload`) and `quota` tool, `lfs`,
  `jobstats`, and `getent`. A command only needs the tools it uses.
- Some commands need more: the live monitors and `diag ib` need passwordless
  `ssh` to nodes running `nvidia-smi`; `gpu nvtop` needs `tmux` and `nvtop`;
  `diag nvlink` needs `nvcc` and NCCL; `diag nccl` needs `torch`;
  `storage home --ncdu` needs `ncdu`. `jobs scope` uses the bundled `jobscope`
  tool (installed automatically); its GPU views also read a Prometheus endpoint,
  auto-discovered from the cluster's jobstats install. `gpu pulse` uses the
  bundled `kempnerpulse`; run it on a GPU node, where by default it reads GPU
  counters via `dcgmi` (or a dcgm-exporter Prometheus endpoint with `--backend
  prometheus`).

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

Enable tab completion for your shell (bash, zsh, fish), then restart it:

```bash
clustertools completion --install
```

## Usage

```bash
# Discover
clustertools --help      # list command groups
clustertools gpu --help  # list a group's commands
clustertools search fairshare  # find a command by keyword (also: find, lookup)
clustertools me                # your jobs, GPUs, and fairshare at a glance

# GPU
clustertools gpu usage                   # rank every lab by base-partition GPU usage
clustertools gpu usage kempner_sham_lab  # one lab's usage, by user and partition
clustertools gpu avail kempner_h100      # nodes with allocatable GPUs (ratio-capped)
clustertools gpu session a100 -A LAB     # interactive single-GPU shell (a100/h100/h200/rtx)
clustertools gpu monitor-job 1234567     # live per-node GPU/CPU/memory/network table
clustertools gpu pulse                   # live per-GPU dashboard (on a GPU node)

# Jobs
clustertools jobs list           # your queued and running jobs
clustertools jobs why 1234567    # why a job is pending, and its priority
clustertools jobs debug 1234567  # why a finished job failed, with a suggested fix
clustertools jobs stats 1234567  # utilization for a job
clustertools jobs scope -D 3     # efficiency of your completed jobs (last 3 days)
clustertools jobs new            # build a correct GPU sbatch script (prompts, or --submit)

# Accounts and nodes
clustertools account fairshare            # your fairshare and priority standing
clustertools account members kempner_dev  # users in a fairshare account
clustertools nodes partitions -f kempner  # partitions, GPUs, and limits
clustertools nodes list kempner_h100      # nodes and states in a partition

# Storage
clustertools storage quota netscratch  # your quota on a filesystem (-g LAB for a lab)
clustertools storage scratch           # netscratch usage and the 90-day purge reminder
clustertools storage home              # home directory usage and quota
```

## Commands

Most commands live in a group; a few are top-level (`search`, `completion`,
`me`). The table below lists each group's commands. For the full reference of
what each does, its use cases, and inputs, see the linked
[`docs/commands/<group>.md`](docs/commands/) file, or run
`clustertools <group> <command> --help`.

A flat, greppable index of every command, with its scope (user or admin) and the
host tool it wraps, is in
[`clustertools-commands-index.md`](clustertools-commands-index.md).

Not sure which command you need? `clustertools search <words>` (also `find` or
`lookup`) ranks commands by relevance, for example `clustertools search
fairshare` or `clustertools search gpu reservation`.

| Group | Commands | Scope |
| --- | --- | --- |
| [`gpu`](docs/commands/gpu.md) | `usage`, `util`, `status`, `avail`, `session`, `monitor-partition`, `monitor-job`, `nvtop`, `pulse` | GPU usage, availability, and sessions |
| [`jobs`](docs/commands/jobs.md) | `list`, `queue`, `show`, `why`, `top`, `stats`, `scope`, `history`, `log`, `script`, `priorities`, `violators`, `wait-times`, `failures`, `cancel`, `hold`, `release`, `requeue`, `set-priority`, `submit`, `new`, `debug` | Job queue, status, history, logs, and control |
| [`account`](docs/commands/account.md) | `members`, `fairshare`, `balance`, `usage`, `limits`, `top-users`, `qos`, `add-user`, `remove-user`, `set-fairshare` | Account membership, fairshare, usage, limits, QOS |
| [`nodes`](docs/commands/nodes.md) | `list`, `partitions`, `down`, `load`, `frag`, `reservations`, `resume` | Node, partition, and reservation status |
| [`storage`](docs/commands/storage.md) | `quota`, `home`, `vast-usage`, `scratch`, `lfs-stripe`, `lfs-inodes` | Filesystem quotas, usage, and striping |
| [`diag`](docs/commands/diag.md) | `ib`, `nccl`, `nvlink`, `scheduler` | Diagnostics and benchmarks |

## Configuration

clustertools defaults to the Kempner AI Cluster. The cluster-specific values
(partitions, per-GPU limits, GPU types, account conventions, storage paths) live
in a config file, so another center runs the same commands by supplying its own.
See [`docs/configuration.md`](docs/configuration.md) for the config reference and
[`docs/porting.md`](docs/porting.md) for a step-by-step adoption guide.

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
    gpu/              # usage, util, status, avail, session, monitor_partition, monitor_job, nvtop, pulse
    jobs/             # list, queue, show, why, top, stats, scope, history, log, script, priorities, violators, wait-times, failures, cancel, hold, release, requeue, set-priority, submit, new, debug
    account/          # members, fairshare, balance, usage, limits, topusers, qos, adduser, removeuser, setfairshare
    nodes/            # list, partitions, down, load, frag, reservations, resume
    storage/          # quota, home, vast-usage, scratch, lfs-stripe, lfs-inodes
    diag/             # ib, nccl, nvlink, scheduler
tests/                # unit tests
docs/commands/        # extended per-group command reference (gpu.md, jobs.md, ...)
```

## Contributing

New commands are added by pull request. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Kempner Institute, Harvard
University.
