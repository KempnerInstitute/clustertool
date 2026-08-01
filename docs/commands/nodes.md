# nodes

Node and partition status, load, and reservations. Run `clustertool nodes --help` to list these commands.

At a site whose `slurm.conf` sets `PrivateData` to include `nodes` or
`reservations`, Slurm hides that information from ordinary users, and these
commands then report less than the truth rather than a permission error.

## `nodes list PARTITION...`

List node names and states for one or more partitions.

States are Slurm's own short codes: `idle` is free, `mix` partly allocated,
`alloc` full, `comp` finishing a job, `resv` held by a reservation, `drain` and
`drng` take no new work, `down` is offline, `inval` registered resources that do
not match its configuration, and `plnd` is reserved by the backfill scheduler for
a higher-priority job. Two flags can follow: `*` means the node is not
responding, and `-` that backfill has planned it for a higher-priority job.
`man sinfo` documents seven more, covering power, reboot, and
maintenance-reservation states.

An unknown partition name is an error rather than an empty list.

**Use cases**
- See which nodes make up a partition.
- Check node states before targeting a node for a job.

**Inputs**
- `PARTITION...`: One or more Slurm partition names.

## `nodes partitions [-f TEXT]`

List partitions with their cores, GPUs, average memory, node counts, and time
limits, via the tool named by `[tools].partitions` in the site config (`spart`
with the packaged Kempner profile).

**Use cases**
- See which partitions exist and how big their nodes are.
- Find GPU partitions (filter by name, e.g. `-f kempner`).

**Inputs**
- `-f, --filter`: Only show rows containing this text (the header is kept).

## `nodes down [-p PARTITION]`

List nodes not accepting work, with the scheduler's reason (via `sinfo -R`).
Covers down, drained, draining and failing nodes. The reason is shown to 60
characters; `sinfo -R`'s default format truncates it to 20.

**Use cases**
- See which nodes are out, and why, before blaming your job.
- Spot a partition losing capacity to failures.

**Inputs**
- `-p, --partition`: Limit to one partition.

## `nodes load [-f TEXT]`

Show per-node load and free CPU, GPU, and memory, via the tool named by
`[tools].node_load` in the site config (`lsload` with the packaged Kempner
profile).

**Use cases**
- Find nodes with spare capacity.
- Check how busy a specific node is.

**Inputs**
- `-f, --filter`: Only show rows containing this text (the header is kept).

## `nodes frag [-p PARTITION] [--cpus-per-gpu N] [--mem-per-gpu MiB]`

Show free GPU shards per partition and how many N-GPU jobs could start now (via
one `scontrol` pass over the GPU nodes). Prints the free-GPU distribution
(0/1/2/3/4+ per node) and how many 1-, 2-, and 4-GPU jobs of the given shape
could start right now.

A node that cannot take a new job is excluded: down, drained, reserved, in
maintenance, completing, failing, powered down, not responding, or registered
with invalid resources. A node the backfill scheduler has planned for a
higher-priority job is kept, though its free capacity may only admit a job short
enough to finish first. Partitions with no GPU nodes are not listed.

With `--partition`, the job shape defaults to that partition's per-GPU CPU and
memory policy from `[partitions.limits]` in the site config, so the fit counts
describe a job that partition would actually accept. Across partitions, or for a
partition with no configured ratio, it falls back to 8 CPU and 65536 MiB per GPU.
Either value can be overridden. The header states the shape in force and whether
it came from the partition's policy.

**Use cases**
- See where a multi-GPU job can actually land.
- Spot fragmentation: many free GPUs but few whole-node slots.

**Inputs**
- `-p, --partition`: Limit to one partition.
- `--cpus-per-gpu`: CPUs per GPU in the job shape.
- `--mem-per-gpu`: Memory per GPU in MiB in the job shape.

## `nodes reservations`

List the cluster's reservations and the nodes they hold (via `scontrol show
reservation`). Shows every reservation Slurm knows about, current and scheduled:
`State=ACTIVE` is holding nodes now, `State=INACTIVE` starts at its `StartTime`.

**Use cases**
- See time-boxed reserved compute and the nodes it holds.
- Find a reservation name to submit into with `--reservation`.
- Check for upcoming maintenance windows before planning a long run.

## `nodes resume [NODE...] [-p PARTITION]`

Return drained or down nodes to service (via `scontrol update ... State=RESUME`).
Give explicit node names, or `--partition` to sweep a whole partition. The sweep
covers every state `man scontrol` lists `RESUME` as accepting: DRAIN, DRAINING,
DOWN and REBOOT, plus a node whose registration Slurm marked `INVALID_REG`,
which is normally also DOWN and DRAIN. Each node is listed with its state and the scheduler's
reason before you confirm, whether you named it or the sweep found it. Prompts for
confirmation unless `-y`.

Slurm or system admin only: `scontrol update node` needs
`AdminLevel=Administrator` (or root/SlurmUser), not merely operator rights.

**Use cases**
- Bring auto-drained requeue nodes back after a transient issue.

**Inputs**
- `NODE...`: One or more node names to resume.
- `-p, --partition`: Resume every resumable node in this partition.
- `-y, --yes`: Skip the confirmation prompt.
