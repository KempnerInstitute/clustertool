# nodes

Inspect cluster nodes. Run `clustertools nodes --help` to list these commands.

## `nodes list PARTITION...`

List node names and states for one or more partitions.

**Use cases**
- See which nodes make up a partition.
- Check node states before targeting a node for a job.

**Inputs**
- `PARTITION...`: One or more Slurm partition names (e.g. `kempner_h100`).
