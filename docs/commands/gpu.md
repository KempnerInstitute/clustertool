# gpu

Inspect GPU usage on the cluster. Run `clustertools gpu --help` to list these
commands, or `clustertools gpu <command> --help` for one.

## `gpu usage [ACCOUNT]`

Show live base-partition GPU usage, for all labs or one lab.

Without ACCOUNT, rank every account by base-partition GPU usage (the usage that
counts toward each account's cap), highest first. With ACCOUNT, break that
account's usage down by user and partition, plus additive priority and
kempner_requeue usage that does not count toward the cap.

**Use cases**
- See which labs are the heaviest GPU users right now (no argument).
- See who in a lab is using its cap and why jobs pend (with ACCOUNT).

**Inputs**
- `ACCOUNT` — Slurm account name (e.g. `kempner_sham_lab`). Omit for all labs.

## `gpu avail PARTITION [--cpu-per-gpu N] [--mem-per-gpu MB]`

List nodes with GPUs you can actually allocate, most first.

Available GPUs per node are the free GPUs, capped by how many the free CPU and
memory support at the enforced per-GPU ratio (kempner: 16 CPU / 240 GB;
kempner_h100: 24 / 360; kempner_h200: 16 / 360; kempner_rtx: 16 / 180). Other
partitions show raw free GPUs unless `--cpu-per-gpu` / `--mem-per-gpu` are given.

**Use cases**
- Find where you can actually place a GPU job.
- See spare CPU and memory alongside usable GPUs.

**Inputs**
- `PARTITION` — Slurm partition name (e.g. `kempner_h100`).
- `--cpu-per-gpu` — Cores per GPU (overrides the per-partition default).
- `--mem-per-gpu` — Memory per GPU in MB (overrides the per-partition default).

## `gpu monitor-partition PARTITION [--interval S] [--filter PREFIX]`

Live GPU/CPU/memory/InfiniBand monitor for a partition's nodes.

Refreshes a colored per-node table in place until Ctrl+C. Requires passwordless
ssh to the nodes, which must expose `nvidia-smi`.

**Use cases**
- Watch utilization across a partition during a large run.
- Spot idle or network-starved nodes live.

**Inputs**
- `PARTITION` — Slurm partition name (e.g. `kempner_h100`).
- `--interval` — Refresh interval in seconds (default 5).
- `--filter` — Only include nodes whose name starts with this prefix.

## `gpu monitor-job JOBID [--interval S]`

Live GPU/CPU/memory/InfiniBand monitor for a running job's nodes.

Refreshes a colored per-node table in place until Ctrl+C. Requires passwordless
ssh to the job's nodes, which must expose `nvidia-smi`.

**Use cases**
- Watch GPU and network utilization across a multi-node job.
- Confirm every node of a job is actually busy.

**Inputs**
- `JOBID` — Slurm job id of a running job.
- `--interval` — Refresh interval in seconds (default 5).

## `gpu nvtop JOBID [--attach/--no-attach]`

Open a tmux session running nvtop on each of a job's nodes.

Creates a tiled tmux session `nvtop_<jobid>` with one pane per node, each ssh-ing
to the node and launching nvtop. Requires tmux locally and passwordless ssh to
the nodes.

**Use cases**
- Watch per-node GPU activity for a multi-node job at a glance.

**Inputs**
- `JOBID` — Slurm job id of a running job.
- `--attach/--no-attach` — Attach after creating the session (default attach).
