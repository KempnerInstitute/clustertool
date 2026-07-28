# clustertools command index

A single-page reference for every `clustertools` command, grouped by area. Run
each as `clustertools <command>` (for example `clustertools gpu util`). For full
help, use `--help` on any command, or see [docs/commands/](docs/commands/).

Scope: **user** commands need no special privilege; **admin** commands require
Slurm operator rights. The Wraps column names the host tool each command shells
out to.

## gpu

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `gpu usage [ACCOUNT]` | user | squeue, sacctmgr | Rank labs by base-partition GPU usage, or break one lab down by user and partition. |
| `gpu util [PARTITION...]` | user | sinfo, squeue | GPU occupancy per partition: total, down, available, used, and percent. |
| `gpu status` | user | sinfo | Kempner GPU node counts by type (A100/H100/H200/RTX) and state. |
| `gpu avail PARTITION` | user | scontrol, sinfo | Nodes with allocatable GPUs (free GPUs capped by the enforced per-GPU ratio). |
| `gpu session GPU_TYPE -A ACCOUNT` | user | salloc | Interactive single-GPU session (a100/h100/h200/rtx), sized to the per-GPU limits. |
| `gpu monitor-partition PARTITION` | user | ssh, nvidia-smi | Live per-node GPU/CPU/memory/network table for a partition. |
| `gpu monitor-job JOBID` | user | ssh, nvidia-smi | Live per-node GPU/CPU/memory/network table for a running job. |
| `gpu nvtop JOBID` | user | tmux, nvtop, ssh | tmux session running nvtop on each of a job's nodes. |
| `gpu pulse [ARG...]` | user | kempnerpulse | Live per-GPU dashboard (bundled kempnerpulse); all arguments forwarded. |

## jobs

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `jobs list` | user | squeue | Your queued and running jobs (`-t`, `-p`, `-A`, `--start`). |
| `jobs queue PARTITION` | user | showq | A partition's pending jobs in priority order. |
| `jobs show JOBID...` | user | scontrol | Live detail for one or more jobs, including the pending reason. |
| `jobs why JOBID` | user | squeue, sprio | Why a job is pending, plus its priority factor breakdown. |
| `jobs top JOBID` | user | sstat | Live resource use of a running job's steps. |
| `jobs stats JOBID...` | user | jobstats | Utilization for one or more jobs. |
| `jobs scope [ARG...]` | user | jobscope | Completed-job efficiency plus DCGM profiling (bundled jobscope). |
| `jobs history` | user | sacct | Your recent finished jobs (`-d`, `-u`). |
| `jobs log JOBID [-f]` | user | scontrol, tail | Show, or tail, a job's stdout/stderr. |
| `jobs script JOBID` | user | sacct | The batch script a job was submitted with. |
| `jobs priorities PARTITION` | user | sprio | Priority factors for all pending jobs in a partition. |
| `jobs violators PARTITION` | user | squeue, scontrol | Running jobs over the per-GPU CPU/memory norm. |
| `jobs cancel [JOBID...]` | user | scancel | Cancel jobs (`--all`, `--pending`). |
| `jobs hold JOBID...` | user | scontrol | Prevent pending jobs from starting. |
| `jobs release JOBID...` | user | scontrol | Release held jobs. |
| `jobs requeue JOBID...` | user | scontrol | Cancel and re-queue jobs. |
| `jobs setprio JOBID PRIORITY` | admin | scontrol update | Set (pin) a job's scheduling priority. |
| `jobs submit [ARG...]` | user | sbatch | Submit a batch job (passthrough to sbatch). |

## account

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `account members [ACCOUNT]` | user | sacctmgr, getent | Users in an account, or all lab accounts as CSV (`--all`). |
| `account fairshare [ACCOUNT]` | user | sshare | Fairshare standing and priority (yours, or an account's members). |
| `account usage [ACCOUNT]` | user | stotal, seff-account | Cumulative CPU/GPU/TRES-hours, or efficiency (`--efficiency`). |
| `account limits [ACCOUNT]` | user | sacctmgr | Account associations: QOS, partitions, and limits. |
| `account top-users ACCOUNT` | user | sshare | Rank an account's members by RawUsage. |
| `account qos [-f TEXT]` | user | sacctmgr | QOS definitions and their TRES limits. |
| `account add-user USER ACCOUNT` | admin | sacctmgr | Add a user to a fairshare account. |
| `account remove-user USER ACCOUNT` | admin | sacctmgr | Remove a user's association with an account. |
| `account set-fairshare USER ACCOUNT SHARE` | admin | sacctmgr | Set a user's fairshare in an account. |

## nodes

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `nodes list PARTITION...` | user | sinfo, scontrol | Node names and states for one or more partitions. |
| `nodes partitions [-f TEXT]` | user | spart | Partitions with cores, GPUs, memory, and time limits. |
| `nodes down [-p PARTITION]` | user | sinfo | Down and drained nodes with the scheduler's reason. |
| `nodes load [-f TEXT]` | user | lsload | Per-node load and free CPU/GPU/memory. |
| `nodes reservations` | user | scontrol | Active reservations on the cluster. |
| `nodes resume [NODE...] [-p]` | admin | scontrol update | Return drained or down nodes to service. |

## storage

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `storage quota PATH` | user | quota | Storage quota on any filesystem (VAST, Lustre, home). |
| `storage home` | user | df, du, ncdu | Home directory usage; largest subdirectories with `--scan`. |
| `storage usage PATH -g GROUP` | user | quota | Per-user usage for a group on a VAST filesystem. |
| `storage scratch [PATH]` | user | quota | Netscratch usage and the 90-day purge reminder. |
| `storage stripe PATH [-c N]` | user | lfs | Show or set Lustre striping. |
| `storage inodes PATH` | user | lfs | Inode capacity and usage for a Lustre filesystem. |

## diag

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `diag ib PARTITION...` | user | ssh, ip | Nodes with InfiniBand ports DOWN. |
| `diag nccl` | user | srun, torch | Multi-node FSDP NCCL sanity check inside a Slurm job. |
| `diag nvlink` | user | nvcc, NCCL | Saturate a node's NVLink fabric with NCCL all-reduce. |
| `diag scheduler` | user | sdiag | Slurm scheduler diagnostics (cycle, backfill, queue depth). |

---

Keep this index in sync when adding or changing a command (see
[CONTRIBUTING.md](CONTRIBUTING.md)).
