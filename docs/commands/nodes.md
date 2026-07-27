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
