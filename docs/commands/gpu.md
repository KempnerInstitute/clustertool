# gpu

GPU usage, availability, sessions, and monitoring. Run `clustertool gpu --help` to list these
commands, or `clustertool gpu <command> --help` for one.

## `gpu usage [ACCOUNT]`

Show live base-partition GPU usage, for all labs or one lab.

Without ACCOUNT, rank every account by base-partition GPU usage (the usage that
counts toward each account's cap), highest first. With ACCOUNT, break that
account's usage down by user and partition, plus additive priority and requeue
usage that does not count toward the cap.

**Use cases**
- See which labs are the heaviest GPU users right now (no argument).
- See who in a lab is using its cap and why jobs pend (with ACCOUNT).

**Inputs**
- `ACCOUNT`: Slurm account name (e.g. `kempner_sham_lab`). Omit for all labs.

## `gpu util [PARTITION...] [-p PARTITION]`

Show GPU occupancy per partition: total, unavailable, used, other, free, and
percent.

`USED` is the GPUs held by jobs submitted to that partition. `TOTAL`, `UNAVAIL`
and `FREE` describe the partition's nodes, read in one `scontrol` pass: the GPUs
those nodes have, those on nodes that cannot take a new job (down, drained,
reserved, in maintenance, completing, failing, powered down, not responding, or
registered with invalid resources), and those still unallocated on nodes that can.

`OTHER` is what jobs from partitions sharing the same nodes hold, which is why
`USED` plus `FREE` need not reach `TOTAL`. On a cluster where a requeue or
priority partition overlaps a base partition, that column is where the rest of the
hardware went. `UTIL` is used over total.

With no PARTITION, reports the site base partitions.

**Use cases**
- See how full each GPU partition is right now.

**Inputs**
- `PARTITION...`: One or more partitions (default: the site base partitions).
- `-p, --partition`: Same, as an option rather than an argument (repeatable).

## `gpu status`

Show GPU node status by type and state (via `sinfo`). Reads the site's requeue
partition, which spans every GPU node, and breaks the nodes down by GPU type and
state. Idle, Mixed, and Alloc nodes are up; Resv is reserved; Drain is draining;
Down is offline. Each column aggregates the related Slurm states: a node planned
by the backfill scheduler counts as Idle, one still completing a job as Alloc, one
held for maintenance as Resv, and one with invalid registered resources as
Down.

**Use cases**
- See how many nodes of each GPU type are up, drained, or down.
- Spot fleet health problems before submitting or debugging jobs.

## `gpu avail PARTITION [--cpus-per-gpu N] [--mem-per-gpu MB]`

List nodes with GPUs you can actually allocate, most first.

Available GPUs per node are the free GPUs, capped by how many the free CPU and
memory support at the per-GPU ratio your site enforces for that partition, from
`[partitions.limits]` in the site config. A partition with no configured ratio
shows raw free GPUs unless `--cpus-per-gpu` / `--mem-per-gpu` are given. Run
`nodes partitions` to see the configured ratios.

Only schedulable nodes are listed: a node that is down, draining, reserved, in
maintenance, completing, failing, powered down, not responding, or registered with
invalid resources keeps its free GPUs but cannot take a new job. A node the
backfill scheduler has planned for a higher-priority job is still listed, since a
job that fits before that one is due to start can run on it.

**Use cases**
- Find where you can actually place a GPU job.
- See spare CPU and memory alongside usable GPUs.

**Inputs**
- `PARTITION`: Slurm partition name.
- `--cpus-per-gpu`: Cores per GPU (overrides the per-partition default).
- `--mem-per-gpu`: Memory per GPU in MB (overrides the per-partition default).

## `gpu session GPU_TYPE -A ACCOUNT [-t TIME] [SALLOC_ARG]...`

Start an interactive single-GPU session on a base partition (via `salloc`).
GPU_TYPE selects the partition, and the session requests one GPU plus the CPU and
memory your site allots per GPU on that partition. Where the site sets
`use_interactive_step` in `LaunchParameters`, as this cluster does, salloc puts
the shell on the allocated node; otherwise it runs on the submitting host. Exit
it (or let the time limit lapse) to release the allocation.

The GPU types come from `[gpu_types]` in the site config, each mapped to a
partition whose per-GPU CPU and memory come from `[partitions.limits]`. With the
packaged Kempner profile that is:

| GPU_TYPE | Partition | CPUs | Memory |
| --- | --- | --- | --- |
| `a100` | `kempner` | 16 | 245760 MiB |
| `h100` | `kempner_h100` | 24 | 368640 MiB |
| `h200` | `kempner_h200` | 16 | 368640 MiB |
| `rtx` | `kempner_rtx` | 16 | 184320 MiB |

Run `gpu avail PARTITION` to see the ratio in force on your cluster. Memory is
passed in MiB, Slurm's default unit for `--mem`, so `--mem=368640` rather than
`360G`; the two are the same amount. When a
partition has no configured ratio, no CPU or memory request is made and Slurm
applies that partition's own defaults.

Any extra arguments are forwarded to `salloc` after these defaults, so you can
override or add flags (salloc uses the last value): for example
`gpu session a100 -A LAB --mem=500000`, `... -J devshell`, or `... --x11`.

**Use cases**
- Grab one GPU for interactive development or debugging.

**Inputs**
- `GPU_TYPE`: A GPU type your site defines under `[gpu_types]`.
- `-A, --account`: Fairshare account to charge (required).
- `-t, --time`: Time limit D-HH:MM (default 0-01:00).
- `--jupyter`: Launch Jupyter Lab on the node and print the SSH tunnel to reach it.
- `--port`: Port for `--jupyter` (default 8888; 1024-65535).
- `[SALLOC_ARG]...`: Extra salloc arguments, forwarded (they override the defaults).

## `gpu monitor-partition PARTITION [--interval S] [--filter PREFIX]`

Live GPU/CPU/memory/InfiniBand monitor for a partition's nodes.

Refreshes a colored per-node table in place until Ctrl+C. Requires passwordless
ssh to the nodes, which must expose `nvidia-smi`.

That means ssh to every node in the partition, not only the ones running your
jobs. Where node login requires an allocation on that node, as `pam_slurm_adopt`
enforces, use `gpu monitor-job JOBID` instead.

**Use cases**
- Watch utilization across a partition during a large run.
- Spot idle or network-starved nodes live.

**Inputs**
- `PARTITION`: Slurm partition name (e.g. `kempner_h100`).
- `--interval`: Refresh interval in seconds (default 5).
- `--filter`: Only include nodes whose name starts with this prefix.

## `gpu monitor-job JOBID [--interval S]`

Live GPU/CPU/memory/InfiniBand monitor for a running job's nodes.

Refreshes a colored per-node table in place until Ctrl+C. Requires passwordless
ssh to the job's nodes, which must expose `nvidia-smi`.

**Use cases**
- Watch GPU and network utilization across a multi-node job.
- Confirm every node of a job is actually busy.

**Inputs**
- `JOBID`: Slurm job id of a running job.
- `--interval`: Refresh interval in seconds (default 5).

## `gpu nvtop JOBID [--attach/--no-attach]`

Open a tmux session running nvtop on each of a job's nodes.

Creates a tiled tmux session `nvtop_<jobid>` with one pane per node, each ssh-ing
to the node and launching nvtop. Requires tmux locally and passwordless ssh to
the nodes.

**Use cases**
- Watch per-node GPU activity for a multi-node job at a glance.

**Inputs**
- `JOBID`: Slurm job id of a running job.
- `--attach/--no-attach`: Attach after creating the session (default attach).

## `gpu pulse [ARG]...`

Live GPU utilization dashboard, via the bundled
[kempnerpulse](https://github.com/KempnerInstitute/kempnerpulse) tool. It shows a
real-time per-GPU view (SM, tensor, and memory activity, real-utilization, and
workload classification) from DCGM metrics. Every argument is forwarded to
kempnerpulse unchanged, so its full option set is available; run `clustertool
gpu pulse --help` for the complete list.

Run this on a GPU node (for example inside a Slurm job); by default it reads the
node's GPU counters directly via `dcgmi dmon` (the `dcgm` backend), or a
dcgm-exporter Prometheus endpoint with `--backend prometheus`. For completed-job
efficiency use `jobs scope`; for a multi-node overview use `gpu
monitor-partition` or `gpu monitor-job`.

To launch it on a remote node from a login node, pass `--node NODE` (or `--job
JOBID` to target a running job's first node): this ssh's in and runs kempnerpulse
from the site's shared install (`[pulse].remote_venv`). `--dry-run` prints the
ssh command instead of running it. Remote launch needs passwordless ssh to the
node.

**Most useful**
- `gpu pulse`: live fleet dashboard (dcgm backend, about 100 ms refresh).
- `gpu pulse --node NODE`: run the dashboard on a remote GPU node.
- `gpu pulse --job 1234567`: run it on a running job's node.
- `gpu pulse --once`: render one snapshot and exit.
- `gpu pulse --focus-gpu 0`: start focused on a single GPU.
- `gpu pulse --gpus 0,1`: limit to specific GPUs (otherwise uses CUDA_VISIBLE_DEVICES or the SLURM GPU env).
- `gpu pulse --backend prometheus --source http://host:9400/metrics`: read from a Prometheus or dcgm-exporter endpoint.
- `gpu pulse --export all --once`: write a one-shot CSV snapshot to stdout.

In the live view, type `:focus <id>`, `:plot`, or `:job` to switch views, and `:exit` (or Ctrl-C) to quit.

**Inputs**
- `--node NODE`: ssh to NODE and run the dashboard there.
- `--job JOBID`: run it on the first node of one of your own running jobs.
  Where node login requires an allocation, as `pam_slurm_adopt` enforces,
  `--node` reaches a node only if you hold one there.
- `--dry-run`: with `--node`/`--job`, print the ssh command instead of running it.
- `[ARG]...`: any kempnerpulse arguments (`--backend`, `--source`, `--poll`, `--focus-gpu`, `--gpus`, `--once`, `--export`, the weight presets, ...), forwarded verbatim.
