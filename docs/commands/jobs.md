# jobs

Inspect Slurm jobs. Run `clustertools jobs --help` to list these commands, or
`clustertools jobs <command> --help` for one.

## `jobs stats JOBID...`

Show utilization for one or more jobs (via `jobstats`).

For a richer report across many completed jobs (time windows, DCGM GPU
profiling, terminal plots), see `jobs scope` below.

**Use cases**
- Check a job's CPU, memory, and GPU utilization.
- Review the efficiency of a finished job.

**Inputs**
- `JOBID...`: One or more Slurm job ids (e.g. `1234567`).

## `jobs scope [ARG]...`

Report the efficiency of your completed jobs, via the bundled
[jobscope](https://github.com/KempnerInstitute/jobscope) tool. jobscope reads
the CPU/memory/GPU utilization Slurm records for each finished job (the same
numbers `jobstats` reports, read in one bulk `sacct` query with no per-job cap),
and for the GPU view adds DCGM profiling from Prometheus. Every argument is
forwarded to jobscope unchanged, so all of its views and selectors are
available; run `clustertools jobs scope --help` for the full list.

This is for completed jobs; for live (running) jobs use `gpu monitor-job`. The
GPU views need a Prometheus endpoint, auto-discovered from the cluster's
jobstats install, so no setup is needed on the Kempner AI Cluster (the offline
`--cpu` and `--cgpu` views need nothing).

**Most useful**
- `jobs scope -D 3`: your jobs from the last 3 days (the default view).
- `jobs scope 1234567`: one job by id (pass several ids to compare).
- `jobs scope -N 20`: your most recent 20 jobs.
- `jobs scope --cgpu -D 2`: CPU and GPU summary, fully offline (no Prometheus).
- `jobs scope --diagnose -D 5`: add an advisory GPU-usage diagnosis column.
- `jobs scope detail 1234567`: per-node and per-GPU breakdown for a job.
- `jobs scope dcgm 1234567`: per-GPU DCGM profiling table (`dcgm --ext` for all 28 metrics).
- `jobs scope describe`: plain-English reference for every column and metric.

**Inputs**
- `[ARG]...`: any jobscope arguments (job ids; `-D`/`-N`/`-S`/`-E` time selectors; `-u`/`-A`/`-p` filters; `--cpu`/`--gpu`/`--cgpu` views; `--csv`; the `detail`, `dcgm`, `plot`, and `describe` subcommands), forwarded verbatim.

## `jobs violators PARTITION [--cpu-per-gpu N] [--mem-per-gpu MB]`

List running jobs requesting more CPU or memory per GPU than the norm.

Norms default to the per-partition policy (kempner_h100: 24 CPU / 360000 MB per
GPU; kempner: 16 CPU / 240000 MB per GPU). For other partitions, pass
`--cpu-per-gpu` and `--mem-per-gpu`. Jobs with no GPUs are not evaluated.

**Use cases**
- Find jobs hoarding CPU or memory relative to their GPU count.
- Spot over-requests that block other jobs from a lab's GPUs.

**Inputs**
- `PARTITION`: Slurm partition name (e.g. `kempner_h100`).
- `--cpu-per-gpu`: CPU-per-GPU norm (default: per-partition policy).
- `--mem-per-gpu`: Memory-per-GPU norm in MB (default: per-partition policy).
