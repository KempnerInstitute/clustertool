# jobs

Inspect Slurm jobs. Run `clustertools jobs --help` to list these commands, or
`clustertools jobs <command> --help` for one.

## `jobs stats JOBID...`

Show utilization for one or more jobs (via `jobstats`).

**Use cases**
- Check a job's CPU, memory, and GPU utilization.
- Review the efficiency of a finished job.

**Inputs**
- `JOBID...`: One or more Slurm job ids (e.g. `1234567`).

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
