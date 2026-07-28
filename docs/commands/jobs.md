# jobs

Inspect, submit, and control Slurm jobs. Run `clustertools jobs --help` to list these commands, or
`clustertools jobs <command> --help` for one.

## `jobs list [-t STATE] [-p PARTITION] [-A ACCOUNT] [--start]`

List your queued and running jobs (via `squeue`).

**Use cases**
- See what you have running and pending right now.
- Check why a job is pending (the NODELIST(REASON) column).

**Inputs**
- `-u, --user`: User whose jobs to list (default: current user).
- `-t, --state`: Limit to `running` or `pending` jobs.
- `-p, --partition`: Limit to one partition.
- `-A, --account`: Limit to one account.
- `--start`: Show the estimated start time of pending jobs.

## `jobs show JOBID...`

Show live detail for one or more jobs, including the pending reason (via
`scontrol show job -dd`).

**Use cases**
- Inspect a running job's allocation (nodes, GPUs, TRES).
- See exactly why a job is still pending (the Reason field).

**Inputs**
- `JOBID...`: One or more Slurm job ids.

## `jobs why JOBID`

Explain a job's priority and, if pending, why it is waiting. Prints the state
and reason (from `squeue`), then the priority factor breakdown (from `sprio`):
fairshare, age, partition, QOS, and so on.

**Use cases**
- Understand what is holding a pending job back.
- Compare fairshare and age contributions to a job's priority.

**Inputs**
- `JOBID`: A Slurm job id.

## `jobs priorities PARTITION`

Show priority factors for pending jobs in a partition (via `sprio`): each job's
total priority and its fairshare, age, and other contributions.

**Use cases**
- Compare pending jobs' priorities across a partition.

**Inputs**
- `PARTITION`: Slurm partition name (e.g. `kempner_h100`).

## `jobs queue PARTITION`

Show a partition's pending jobs in priority order (via `showq`). Unlike
`jobs list` (your jobs), this is the whole partition's pending queue, so you can
see where you sit.

**Use cases**
- See how far back your pending job is in a partition.
- Gauge contention before submitting.

**Inputs**
- `PARTITION`: Slurm partition name (e.g. `kempner_h100`).

## `jobs top JOBID`

Show live resource use of a running job's steps (via `sstat`): current CPU and
memory (AveRSS/MaxRSS), which `sacct` and `jobstats` cannot report until the job
finishes. Only jobs with an active step report data.

**Use cases**
- Watch a running job's memory before it hits the limit.

**Inputs**
- `JOBID`: A running Slurm job id.

## `jobs log JOBID [-f]`

Show a job's stdout and stderr paths, or tail its output (via `scontrol`). With
`--follow`, tails the stdout file live. Interactive jobs have no output file, and
only running or recent jobs are in `scontrol`.

**Use cases**
- Find where a job is writing its output.
- Watch a running job's log in real time.

**Inputs**
- `JOBID`: A Slurm job id.
- `-f, --follow`: Tail the stdout file live.

## `jobs script JOBID`

Print the batch script a job was submitted with (via `sacct --batch`).

**Use cases**
- Recover or reproduce exactly how a job was submitted.

**Inputs**
- `JOBID`: A Slurm job id.

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

## `jobs history [-d DAYS] [-u USER]`

List your recent finished jobs (via `sacct`): job id, name, partition, state,
elapsed, peak memory, and nodes.

**Use cases**
- Review what ran over the last few days and how it ended.
- Find a past job's id, runtime, or peak memory.

**Inputs**
- `-d, --days`: How many days back to include (default 7).
- `-u, --user`: User whose history to show (default: current user).

## `jobs cancel [JOBID...] [--all] [--pending]`

Cancel jobs (via `scancel`). Pass explicit ids, or use `--all` / `--pending` to
cancel your own jobs in bulk. This is a direct wrapper: it cancels immediately,
exactly as `scancel` does.

**Use cases**
- Kill a specific job or list of jobs.
- Clear all of your pending jobs at once.

**Inputs**
- `JOBID...`: One or more job ids to cancel.
- `--all`: Cancel every job you own.
- `--pending`: Cancel only your pending jobs.

## `jobs setprio JOBID PRIORITY`

Set a job's scheduling priority (via `scontrol update`). Pins the job to the
given priority, overriding fairshare until it runs. Operator only.

**Use cases**
- Boost a specific job ahead of the queue.

**Inputs**
- `JOBID`: A Slurm job id.
- `PRIORITY`: The integer priority to set.

## `jobs hold JOBID...`

Prevent pending jobs from starting (via `scontrol hold`). Held jobs stay in the
queue but are not scheduled until released with `jobs release`.

**Use cases**
- Pause a pending job you are not ready to run.

**Inputs**
- `JOBID...`: One or more Slurm job ids.

## `jobs release JOBID...`

Release held jobs so they can be scheduled (via `scontrol release`). Undoes
`jobs hold`.

**Use cases**
- Let a previously held job start.

**Inputs**
- `JOBID...`: One or more Slurm job ids.

## `jobs requeue JOBID...`

Cancel and re-queue jobs (via `scontrol requeue`); they return to the pending
queue and run again from the start.

**Use cases**
- Restart a running or failed job without resubmitting it.

**Inputs**
- `JOBID...`: One or more Slurm job ids.

## `jobs submit [ARG]...`

Submit a batch job (passthrough to `sbatch`). All arguments are forwarded to
`sbatch` unchanged, so a script path, `--wrap`, `--array`, `--dependency`, and
mail flags all work. Run `sbatch --help` for the full list.

**Most useful**
- `jobs submit job.sh`: submit a batch script.
- `jobs submit -p kempner_h100 --account=LAB --gres=gpu:1 -t 0-01:00 job.sh`: submit with resources.
- `jobs submit --array=1-10 job.sh`: submit an array job.

**Inputs**
- `[ARG]...`: any sbatch arguments (script path, `--wrap`, directives), forwarded verbatim.

## `jobs new`

Build a Kempner GPU sbatch script and print, save, or submit it. Prompts for the
GPU type and account if not given, sizes CPUs and memory to the partition's
enforced per-GPU limits, and writes a correct sbatch header. Prints the script
by default; `-o` saves it and `--submit` submits it.

**Use cases**
- Generate a correct sbatch header without memorizing the conventions.
- Submit a single-node or multi-node GPU job in one step.

**Inputs**
- `--gpu-type`: One of `a100`, `h100`, `h200`, `rtx` (prompted if omitted).
- `-A, --account`: Fairshare account (prompted if omitted).
- `--gpus`: GPUs per node (default 1).
- `--nodes`: Number of nodes (default 1).
- `-t, --time`: Time limit D-HH:MM (default 0-04:00).
- `-J, --name`: Job name (default `job`).
- `--cpus-per-gpu`, `--mem-per-gpu`: Override the per-GPU CPU or memory.
- `-o, --output`: Write the script to a file.
- `--submit`: Submit the script with `sbatch`.
