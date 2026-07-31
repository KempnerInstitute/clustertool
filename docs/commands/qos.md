# qos

Slurm QoS: who holds them, and (admin) provisioning their limits. Run
`clustertools qos --help` to list these commands, or `clustertools qos <command>
--help` for one.

The admin write commands are dry run by default: they print the exact `sacctmgr`
commands and change nothing. Re-run with `--execute` to apply, confirming unless
`-y`. Every `sacctmgr` call carries `-i`, so this tool's dry-run gate, not
`sacctmgr`, is what guards against accidental changes.

## `qos holders QOS_NAME [-p PART] [-c CLUSTER] [-r REGEX] [--by all|user|partition]`

List the users and partitions that hold a QoS (via `sacctmgr`).

Answers the inverse of `account limits`: given a QoS, which user associations
carry it, and on which partitions. Use `--by` to collapse the output to just the
distinct users or partitions, which is handy for scripting a grant or revoke.

**Use cases**
- See who currently holds a priority QoS before changing it.
- List the partitions a QoS is attached to.

**Inputs**
- `QOS_NAME`: The QoS to look up.
- `-p, --partition`: Restrict to one partition.
- `-c, --cluster`: Slurm cluster (default: the site cluster).
- `-r, --account-regex`: Only accounts matching this regex (default: all).
- `--by`: `all` rows, or the distinct `user` or `partition` values.

## `qos create QOS_NAME <limits> [-x] [-y]`

Create a QoS with the given limits, updating it if it already exists (via
`sacctmgr`). Operator only.

Dry run by default. Give at least one limit; a value of `-1` clears that limit.
Per-user node and GPU caps merge into one `MaxTRESPU` limit.

**Use cases**
- Provision a new priority QoS with per-user and total GPU caps.

**Inputs**
- `QOS_NAME`: Name of the QoS to create or update.
- `-g, --gpu-per-user`: Per-user GPU cap (`MaxTRESPU gres/gpu`).
- `-n, --node-per-user`: Per-user node cap (`MaxTRESPU node`).
- `-G, --group-gpu`: Total GPU cap for the QoS (`GrpTRES gres/gpu`).
- `-j, --job-gpu`: Per-job GPU cap (`MaxTRES gres/gpu`).
- `-J, --jobs-per-user`: Per-user running-job cap (`MaxJobsPU`).
- `-x, --execute`: Apply the change instead of previewing it.
- `-y, --yes`: Skip the confirmation prompt.

## `qos modify QOS_NAME <limits> [--per-user-only] [-x] [-y]`

Change an existing QoS's limits (via `sacctmgr`). Operator only.

Dry run by default. Only the limits you pass change; a value of `-1` clears one.
With `--per-user-only` the group and per-job GPU caps are cleared so only the
per-user caps remain. Errors if the QoS does not exist (use `qos create`).

**Use cases**
- Raise or lower a QoS's per-user GPU cap.
- Reduce a QoS to per-user caps only.

**Inputs**
- `QOS_NAME`: Name of an existing QoS.
- `-g/-n/-G/-j/-J`: Limit caps (as for `qos create`; `-1` clears).
- `--per-user-only`: Also clear the group and per-job GPU caps.
- `-x, --execute`: Apply the change instead of previewing it.
- `-y, --yes`: Skip the confirmation prompt.

## `qos delete QOS_NAME [-x] [-y]`

Delete a QoS definition, refusing while it is still referenced (via `sacctmgr`).
Operator only.

Dry run by default. Refuses if any association still lists the QoS; remove it
from those associations first. A QoS that does not exist is a no-op.

**Use cases**
- Retire a QoS definition that is no longer assigned to anyone.

**Inputs**
- `QOS_NAME`: Name of the QoS to delete.
- `-x, --execute`: Apply the change instead of previewing it.
- `-y, --yes`: Skip the confirmation prompt.
