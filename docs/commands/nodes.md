# nodes

Inspect cluster nodes. Run `clustertools nodes --help` to list these commands.

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

## `nodes reservations`

List active reservations on the cluster (via `scontrol show reservation`).

**Use cases**
- See time-boxed reserved compute and the nodes it holds.
- Find a reservation name to submit into with `--reservation`.
