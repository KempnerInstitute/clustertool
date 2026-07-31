# nodes

Node and partition status, load, and reservations. Run `clustertools nodes --help` to list these commands.

## `nodes list PARTITION...`

List node names and states for one or more partitions.

**Use cases**
- See which nodes make up a partition.
- Check node states before targeting a node for a job.

**Inputs**
- `PARTITION...`: One or more Slurm partition names (e.g. `kempner_h100`).

## `nodes partitions [-f TEXT]`

List partitions with their cores, GPUs, average memory, node counts, and time
limits (via `spart`).

**Use cases**
- See which partitions exist and how big their nodes are.
- Find GPU partitions (filter by name, e.g. `-f kempner`).

**Inputs**
- `-f, --filter`: Only show rows containing this text (the header is kept).

## `nodes down [-p PARTITION]`

List down and drained nodes with the scheduler's reason (via `sinfo -R`).

**Use cases**
- See which nodes are out, and why, before blaming your job.
- Spot a partition losing capacity to failures.

**Inputs**
- `-p, --partition`: Limit to one partition.

## `nodes load [-f TEXT]`

Show per-node load and free CPU, GPU, and memory (via `lsload`).

**Use cases**
- Find nodes with spare capacity.
- Check how busy a specific node is.

**Inputs**
- `-f, --filter`: Only show rows containing this text (the header is kept).

## `nodes frag [-p PARTITION] [--cpus-per-gpu N] [--mem-per-gpu MB]`

Show free GPU shards per partition and how many N-GPU jobs could start now (via
`scontrol`). Reads one pass; nodes in down, drain, or maint states are excluded.
Prints the free-GPU distribution (0/1/2/3/4+ per node) and how many 1-, 2-, and
4-GPU jobs of the given shape could start right now.

**Use cases**
- See where a multi-GPU job can actually land.
- Spot fragmentation: many free GPUs but few whole-node slots.

**Inputs**
- `-p, --partition`: Limit to one partition.
- `--cpus-per-gpu`: CPUs per GPU in the job shape (default 8).
- `--mem-per-gpu`: Memory per GPU in MB in the job shape (default 65536).

## `nodes reservations`

List active reservations on the cluster (via `scontrol show reservation`).

**Use cases**
- See time-boxed reserved compute and the nodes it holds.
- Find a reservation name to submit into with `--reservation`.

## `nodes resume [NODE...] [-p PARTITION]`

Return drained or down nodes to service (via `scontrol update ... State=RESUME`).
Give explicit node names, or `--partition` to resume every drained node in a
partition. Prompts for confirmation unless `-y`. Operator only.

**Use cases**
- Bring auto-drained requeue nodes back after a transient issue.

**Inputs**
- `NODE...`: One or more node names to resume.
- `-p, --partition`: Resume all drained nodes in this partition.
- `-y, --yes`: Skip the confirmation prompt.
