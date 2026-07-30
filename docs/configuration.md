# Site configuration

clustertools ships tuned for the Kempner AI Cluster, but the cluster-specific
values (partition names, per-GPU limits, GPU type map, account conventions, and
storage paths) live in a config file, not in the command code. Another center
runs the same commands by supplying its own file.

## Where the config comes from

The active configuration is the packaged default (the Kempner profile),
deep-merged with the first file found in this order:

1. the path in `$CLUSTERTOOLS_SITE_CONFIG`
2. `~/.config/clustertools/site.toml`
3. `/etc/clustertools/site.toml`

Because the override is deep-merged over the default, a site file only needs the
keys that differ. A center typically deploys one `/etc/clustertools/site.toml`,
so every user on that cluster gets the right values with no per-user setup.

## Keys

The packaged default lists every key with Kempner values; it is the reference:
`src/cluster_tools/data/site.default.toml`. The sections are:

- `[site]` `name`: shown in the top-level `--help`.
- `[partitions]` `base`, `requeue`, `priority_pattern`: the base GPU partitions
  that count toward the cap, the partition spanning every GPU node, and the
  regex identifying priority partitions.
- `[partitions.limits.<name>]` `cpus_per_gpu`, `mem_per_gpu_mb`: the enforced
  per-GPU limits used to size sessions and flag over-requests.
- `[qos]` `base`, `default_cap`: the QoS whose MaxTRESPA holds the per-account
  GPU cap, and a fallback cap.
- `[gpu_types]`: the `session` / `jobs new` GPU-type to partition map.
- `[gpu_status]` `types`: GPU node types in display order, each a `label` and
  the Slurm node `feature` tag that identifies it.
- `[accounts]` `roster_partition`, `lab_prefix`: the partition whose
  AllowAccounts enumerates lab accounts, and the prefix identifying them.
- `[storage]` `path_prefix`, `scratch`, `scratch_purge_days`: the prefix a bare
  name expands to, the default scratch path, and its auto-purge age.

## Example: a second cluster

```toml
[site]
name = "Example HPC"

[partitions]
base = ["gpu", "gpu-shared"]
requeue = "gpu"
priority_pattern = "priority"

[partitions.limits.gpu]
cpus_per_gpu = 8
mem_per_gpu_mb = 100000

[gpu_types]
a100 = "gpu"

[storage]
path_prefix = "/scratch"
scratch = "/scratch/tmp"
scratch_purge_days = 30
```

Point clustertools at it with `export CLUSTERTOOLS_SITE_CONFIG=/path/site.toml`,
or install it to `/etc/clustertools/site.toml` for everyone. Commands whose data
the file does not define keep the packaged defaults, so start small and add keys
as needed.
