# clustertool command index

A single-page reference for every `clustertool` command, grouped by area. Run
each as `clustertool <command>` (for example `clustertool gpu util`). For full
help, use `--help` on any command, or see [docs/commands/](docs/commands/).

Scope: **user** commands need no special privilege; **admin** commands need
elevated rights. Which rights depends on the command, so check its help: editing
accounts or assigning a QoS takes `AdminLevel=Operator` or above, or a
coordinator of the account, while resuming nodes or changing a QoS definition
takes a Slurm or system admin (`AdminLevel=Administrator`, or root/SlurmUser):
slurmdbd gates a QoS object at its super-user level, unlike an association. Two commands are
admin for a different reason: `diag ib` and `gpu monitor-partition` ssh to every
node in a partition, and where node login requires an allocation on that node,
as `pam_slurm_adopt` enforces, only staff can reach them all. The Wraps column
names the host tool each command shells out to.

## top-level

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `search TERMS...` | user | (none) | Find commands by keyword, ranked by relevance (also: find, lookup). |
| `completion [SHELL]` | user | (none) | Set up tab completion for bash, zsh, or fish (--install writes it). |
| `me` | user | squeue, sshare, sacctmgr | Personal overview: jobs, GPUs, fairshare; `--access` adds your accounts, submission map, and tiers. |

## gpu

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `gpu usage [ACCOUNT]` | user | squeue, sacctmgr | Rank labs by base-partition GPU usage, or break one lab down by user and partition. |
| `gpu util [PARTITION...] [-p PARTITION]` | user | scontrol, squeue | GPU occupancy per partition: total, unavailable, used, other, free, and percent. |
| `gpu status` | user | sinfo | GPU node counts by type and state, from the requeue partition. |
| `gpu avail PARTITION` | user | scontrol | Nodes with allocatable GPUs (free GPUs capped by the enforced per-GPU ratio). |
| `gpu session GPU_TYPE -A ACCOUNT` | user | salloc | Interactive single-GPU session (a100/h100/h200/rtx), sized to the per-GPU limits. |
| `gpu monitor-partition PARTITION` | admin | ssh, nvidia-smi | Live per-node GPU/CPU/memory/network table for a partition (needs ssh to every node). |
| `gpu monitor-job JOBID` | user | ssh, nvidia-smi | Live per-node GPU/CPU/memory/network table for a running job. |
| `gpu nvtop JOBID` | user | tmux, nvtop, ssh | tmux session running nvtop on each of a job's nodes. |
| `gpu pulse [ARG...]` | user | kempnerpulse, ssh | Live per-GPU dashboard (bundled kempnerpulse); `--node`/`--job` launch it on a remote node. |

## jobs

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `jobs list [-u USER]` | user | squeue, scontrol, sacctmgr | Your queued and running jobs (`-u`, `-t`, `-p`, `-A`, `--start`). |
| `jobs queue PARTITION` | user | showq | A partition's whole queue, waiting jobs in priority order. |
| `jobs show JOBID...` | user | scontrol | Live detail for one or more jobs, including the pending reason. |
| `jobs why JOBID` | user | squeue, sprio | Why a job is pending, plus its priority factor breakdown. |
| `jobs debug JOBID` | user | sacct, scontrol | Diagnose why a finished job failed, with a suggested fix. |
| `jobs top JOBID` | user | sstat | Live resource use of a running job's steps. |
| `jobs stats JOBID...` | user | jobstats | Utilization for one or more jobs. |
| `jobs scope [ARG...]` | user | jobscope | Completed-job efficiency plus DCGM profiling (bundled jobscope). |
| `jobs history` | user | sacct | Your recent jobs, running or finished (`-d`, `-u`). |
| `jobs log JOBID [-f]` | user | scontrol, sacct, tail | Show, or tail, a job's stdout/stderr. |
| `jobs script JOBID` | user | sacct, scontrol | The batch script a job was submitted with. |
| `jobs priorities PARTITION` | user | sprio, sinfo | Priority factors for the eligible pending jobs in a partition. |
| `jobs violators PARTITION` | user | scontrol, sinfo | Running jobs over the per-GPU CPU/memory norm. |
| `jobs wait-times` | user | sacct | Submit-to-start wait distributions by partition, QOS, GPU count. |
| `jobs failures` | user | sacct | Window failure post-mortem: rate and top exit codes, users, nodes. |
| `jobs cancel [JOBID...] [-y]` | user | scancel | Cancel jobs; `--all` and `--pending` prompt first. |
| `jobs hold JOBID...` | user | scontrol | Prevent pending jobs from starting. |
| `jobs release JOBID...` | user | scontrol | Release held jobs. |
| `jobs requeue JOBID...` | user | scontrol | Cancel and re-queue jobs. |
| `jobs set-priority JOBID PRIORITY [-y]` | admin | scontrol update | Set (pin) a job's scheduling priority (alias: setprio). |
| `jobs submit [ARG...]` | user | sbatch | Submit a batch job (passthrough to sbatch). |
| `jobs new` | user | sbatch | Build (and optionally submit) a GPU sbatch script. |

## account

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `account members [ACCOUNT]` | user | sshare, scontrol, sacctmgr, getent | Users in an account, or all lab accounts as CSV (`--all`). |
| `account fairshare [ACCOUNT]` | user | sshare | Fairshare standing and priority (yours, or an account's members). |
| `account balance [ACCOUNT]` | user | sshare | Rank accounts by over/under-served fair-share ratio. |
| `account usage [ACCOUNT]` | user | stotal, seff-account | Cumulative CPU/GPU/TRES-hours, or efficiency (`--efficiency`). |
| `account limits [ACCOUNT]` | user | sacctmgr | Account associations: QOS, partitions, and limits. |
| `account top-users ACCOUNT` | user | sshare | Rank an account's members by RawUsage. |
| `account qos [-f TEXT] [-l]` | user | sacctmgr | QoS definitions and their TRES limits, per-user, per-account, per-job and total (`--long` adds Flags, Preempt, UsageFactor). |
| `account add-user USER ACCOUNT` | admin | sacctmgr | Add a user to a fairshare account. |
| `account remove-user USER ACCOUNT` | admin | sacctmgr | Remove a user's associations with an account. |
| `account set-fairshare USER ACCOUNT SHARE` | admin | sacctmgr | Set a user's fairshare in an account. |

## nodes

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `nodes list PARTITION...` | user | sinfo, scontrol | Node names and states for one or more partitions. |
| `nodes partitions [-f TEXT]` | user | spart | Partitions with cores, GPUs, memory, and time limits. |
| `nodes down [-p PARTITION]` | user | sinfo, scontrol | Down, drained, draining and failing nodes with the scheduler's reason. |
| `nodes load [-f TEXT]` | user | lsload | Per-node load and free CPU/GPU/memory. |
| `nodes frag [-p PARTITION] [--cpus-per-gpu N] [--mem-per-gpu MiB]` | user | scontrol | Free GPU shards per partition and how many N-GPU jobs fit now. |
| `nodes reservations` | user | scontrol | Reservations on the cluster, active and not. |
| `nodes resume [NODE...] [-p]` | admin | scontrol update | Return drained or down nodes to service. |

## storage

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `storage quota [PATH]` | user | quota | Storage quota on any filesystem; `--all` your labs, `--fleet LAB` a filesystem's labs. |
| `storage home` | user | df, du, ncdu | Home directory usage; largest subdirectories with `--scan`. |
| `storage vast-usage PATH -g GROUP` | user | quota | Per-user usage for a group on a VAST filesystem. |
| `storage scratch [PATH]` | user | quota | Netscratch usage and the 90-day purge reminder. |
| `storage lfs-stripe PATH [-c N] [-y]` | user | lfs | Show or set Lustre striping (setting prompts). |
| `storage lfs-inodes PATH` | user | lfs | Inode capacity and usage for a Lustre filesystem. |

## diag

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `diag gpu-health` | user | nvidia-smi | Node-local GPU health verdict: ECC, throttle, PCIe/NVLink (exit 0 OK, 1 WARN, 3 probe error, 4 FAIL). |
| `diag ib PARTITION...` | admin | ssh, sinfo, scontrol | Nodes with an InfiniBand port that is not ACTIVE, needing ssh to every node (exit 0 clean, 1 unreachable or no IB, 3 no such partition or none visible, 4 a port not ACTIVE). |
| `diag ib-affinity` | user | nvidia-smi | GPU-to-IB-NIC NUMA affinity verdict (exit 0 OK, 1 cross-NUMA, 3 probe error, 4 no NIC reached). |
| `diag ib-counters BEFORE AFTER` | user | (none) | Diff two ib-snapshots for IB error-counter growth (exit 0 clean, 3 unreadable or mismatched snapshots, 4 a counter advanced, reset, saturated, or unreadable). |
| `diag ib-snapshot [OUT]` | user | nvidia-smi, ibdev2netdev | Capture node IB/GPU topology and counters as JSON, for diffing. |
| `diag ib-verify GOLDEN` | user | nvidia-smi, ibdev2netdev | Compare a node's snapshot against a golden one (exit 0 match, 3 setup error, 4 drift). |
| `diag io-probe -d DIR` | user | (none) | Filesystem write/read MiB/s and metadata latency, with optional pass/fail gates (exit 0 report or pass, 3 setup or IO error, 4 a gate missed). |
| `diag nccl` | user | srun, nvidia-smi, torch | Multi-node FSDP NCCL sanity check inside a Slurm job. |
| `diag nvlink` | user | nvcc, NCCL | Saturate a node's NVLink fabric with NCCL all-reduce. |
| `diag scheduler` | user | sdiag | Slurm scheduler diagnostics (cycle, backfill, queue depth). |

## qos

| Command | Scope | Wraps | Description |
| --- | --- | --- | --- |
| `qos holders QOS_NAME` | user | sacctmgr | Users and partitions that hold a QoS (`--by` user/partition). |
| `qos create QOS_NAME` | admin | sacctmgr | Create or update a QoS's TRES limits (dry run unless `--execute`). |
| `qos modify QOS_NAME` | admin | sacctmgr | Change an existing QoS's TRES limits (dry run unless `--execute`). |
| `qos delete QOS_NAME` | admin | sacctmgr | Delete a QoS definition, refusing while it is held (dry run default). |
| `qos grant QOS_NAME` | admin | sacctmgr | Grant a priority QoS to users on a partition (dry run default). |
| `qos revoke QOS_NAME` | admin | sacctmgr | Remove a QoS from users (or all holders) on a partition (dry run default). |
| `qos retire QOS_NAME` | admin | sacctmgr | Revoke a QoS from all holders, then delete it (dry run default). |
| `qos sync QOS_NAME` | admin | sacctmgr | Reconcile a QoS's holders to an account's membership (dry run default). |

---

Keep this index in sync when adding or changing a command (see
[CONTRIBUTING.md](CONTRIBUTING.md)).
