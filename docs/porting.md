# Porting clustertools to another cluster

clustertools ships tuned for the Kempner AI Cluster, but nothing in the commands
is hardwired to it. Another Slurm site adopts it in a few steps. See
[configuration.md](configuration.md) for the full config reference.

## 1. Install

    uv tool install git+https://github.com/KempnerInstitute/cluster-tools

The generic commands, which are most of the tool, work immediately on any Slurm
cluster.

## 2. Describe your cluster

Create a `site.toml` with the values that differ from the Kempner default and
point clustertools at it:

    export CLUSTERTOOLS_SITE_CONFIG=/path/to/site.toml

or deploy it to `/etc/clustertools/site.toml` so every user picks it up. Only the
keys you set change; the rest keep the packaged defaults. A minimal example:

    [site]
    name = "Example HPC"

    [partitions]
    base = ["gpu", "gpu-shared"]
    requeue = "gpu"

    [partitions.limits.gpu]
    cpus_per_gpu = 8
    mem_per_gpu_mb = 100000

    [gpu_types]
    a100 = "gpu"

    [storage]
    path_prefix = "/scratch"
    scratch = "/scratch/tmp"
    scratch_purge_days = 30

## 3. Map or drop the site tools

Some commands wrap tools that may not exist on your cluster (showq, spart,
lsload, stotal, seff-account, jobstats, the FASRC quota tool). Point each
`[tools]` key at your equivalent binary, or leave it: a command whose tool is
missing simply hides itself.

    [tools]
    queue = "my-queue-tool"

## 4. Turn off commands you do not want

    [commands]
    disable = ["jobs scope", "diag nvlink"]

Disable a whole group by its name, for example `["diag"]`.

## 5. Add your own commands

Ship a small package that declares a `clustertools.commands` entry point for
each command or group you add; clustertools loads them at startup next to the
built-ins:

    [project.entry-points."clustertools.commands"]
    mycmd = "my_package.cli:mycmd"

No fork needed: your site keeps a config file and, optionally, a plugin package,
and pulls core updates as they ship.
