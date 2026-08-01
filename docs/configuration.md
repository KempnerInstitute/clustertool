# Site configuration

clustertool ships tuned for the Kempner AI Cluster, but the cluster-specific
values (partition names, per-GPU limits, GPU type map, account conventions, and
storage paths) live in a config file, not in the command code. Another center
runs the same commands by supplying its own file.

## Where the config comes from

The active configuration is the packaged default (the Kempner profile),
deep-merged with the first file found in this order:

1. the path in `$CLUSTERTOOL_SITE_CONFIG`
2. `~/.config/clustertool/site.toml`
3. `/etc/clustertool/site.toml`

Because the override is deep-merged over the default, a site file only needs the
keys that differ. A center typically deploys one `/etc/clustertool/site.toml`,
so every user on that cluster gets the right values with no per-user setup.

Two tables are the exception. `[gpu_types]` and `[partitions.limits]` describe
what a cluster actually has, so defining either one replaces it entirely rather
than merging. List every entry you want under them: a file that sets only
`[partitions.limits.gpu_big]` leaves every other partition with no ratio, and
those jobs then get whatever Slurm defaults to.

## Keys

The packaged default lists every key with Kempner values; it is the reference:
`src/clustertool/data/site.default.toml`. The sections are:

- `[site]` `name`, `slurm_group_prefix`: a label for the cluster, and the prefix
  of the Unix groups that map to Slurm priority tiers, which `me --access` lists.
- `[partitions]` `base`, `requeue`, `priority_pattern`: the base GPU partitions
  that count toward the cap, the partition spanning every GPU node, and the
  regex identifying priority partitions.
- `[partitions.limits.<name>]` `cpus_per_gpu`, `mem_per_gpu_mb`: the per-GPU CPU
  and memory policy used to size sessions and job scripts and to flag
  over-requests. This is a local policy, not something Slurm enforces.
- `[qos]` `base`, `default_cap`, `cluster`, `grant_fairshare`, `grant_strip`:
  `base` is the QoS whose MaxTRESPA holds the per-account GPU cap, which
  `gpu usage` reports each account against. Only a `gres/gpu` entry there counts
  as a GPU cap. `default_cap` is a fallback for a cluster that enforces a cap
  outside that QoS; it defaults to `0`, meaning no cap is assumed, and then
  `gpu usage` reports plain GPU counts with no denominator instead of scoring
  every account against a limit your cluster does not enforce. Then the
  three used by the admin `qos` commands: `cluster` is the Slurm cluster name
  every `sacctmgr` write targets, so **set it before running any `qos` command**
  or you will aim them at a cluster named `odyssey`; `grant_fairshare` is the
  fairshare value given to associations that `qos grant` creates; `grant_strip`
  lists the QoS that `qos grant` removes so the granted one takes effect.
- `[gpu_types]`: the `session` / `jobs new` GPU-type to partition map.
- `[gpu_status]` `types`: GPU node types in display order, each a `label` and
  the Slurm node `feature` tag that identifies it.
- `[accounts]` `roster_partition`, `lab_prefix`: the partition whose
  AllowAccounts enumerates lab accounts, and the prefix identifying them.
- `[storage]` `path_prefix`, `scratch`, `scratch_purge_days`, `lab_roots`: the
  prefix a bare name expands to, the default scratch path, its auto-purge age,
  and the parent directories searched for a lab's directories by
  `storage quota --all`.
- `[pulse]` `remote_venv`: the virtualenv that `gpu pulse --node` activates on a
  remote GPU node. Leave it empty and that flag reports it is not configured.
- `[tools]`: the binary each tool-backed command runs (`queue`, `partitions`,
  `node_load`, `account_usage`, `account_efficiency`, `job_stats`, `quota`,
  `lfs`). A
  command whose tool is not on PATH is hidden from help and search, so a cluster
  without `showq` simply does not show `jobs queue`. Point a key at your
  cluster's equivalent binary, or leave it and the command stays hidden.
- `[commands]` `disable`: command paths to turn off at this site, e.g.
  `["jobs scope", "diag nvlink"]`. Disabled commands vanish from help, search,
  and resolution. Disable a whole group by its name, e.g. `["diag"]`.

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

Point clustertool at it with `export CLUSTERTOOL_SITE_CONFIG=/path/site.toml`,
or install it to `/etc/clustertool/site.toml` for everyone. Commands whose data
the file does not define keep the packaged defaults, so start small and add keys
as needed.

## Adding commands without forking

A site can ship extra commands in its own package that declares a
`clustertool.commands` entry point for each top-level command or group:

    [project.entry-points."clustertool.commands"]
    mycmd = "my_package.cli:mycmd"

clustertool loads them at startup and adds them next to the built-in commands.
A plugin that fails to import is skipped, so a broken one never breaks the CLI.
