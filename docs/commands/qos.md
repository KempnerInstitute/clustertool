# qos

Slurm QoS: who holds them, and (admin) provisioning their limits. Run
`clustertool qos --help` to list these commands, or `clustertool qos <command>
--help` for one.

The admin write commands are dry run by default: they print the exact `sacctmgr`
commands and change nothing. Re-run with `--execute` to apply, confirming unless
`-y`. Every `sacctmgr` call carries `-i`, so this tool's dry-run gate, not
`sacctmgr`, is what guards against accidental changes.

They need two different privilege levels. Changing a QoS *definition* (`create`,
`modify`, `delete`, `retire`) requires a Slurm or system admin, that is
`AdminLevel=Administrator` or root/SlurmUser. *Assigning* an existing QoS
(`grant`, `revoke`, `sync`) only edits associations, so an operator or a
coordinator of the account can do it.

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
`sacctmgr`). Slurm or system admin only.

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

Change an existing QoS's limits (via `sacctmgr`). Slurm or system admin only.

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
Slurm or system admin only.

Dry run by default. Refuses if any association still lists the QoS; remove it
from those associations first. A QoS that does not exist is a no-op.

**Use cases**
- Retire a QoS definition that is no longer assigned to anyone.

**Inputs**
- `QOS_NAME`: Name of the QoS to delete.
- `-x, --execute`: Apply the change instead of previewing it.
- `-y, --yes`: Skip the confirmation prompt.

## `qos grant QOS_NAME -u USERS -p PART [-d DEFAULT] [-c CLUSTER] [-r REGEX] [-x] [-y]`

Grant a priority QoS to users across their matching accounts on a partition (via
`sacctmgr`). Operator or a coordinator of the account only.

For each user, adds the QoS to every association whose account matches the regex,
sets the default QoS, and strips the catch-all and partition-named QoS so the
granted one takes effect. Missing associations are created. Dry run by default.

**Use cases**
- Give a set of users a priority QoS on a GPU partition.

**Inputs**
- `QOS_NAME`: The QoS to grant.
- `-u, --users`: Users (repeatable, comma-separated).
- `-p, --partition`: Partition to grant the QoS on.
- `-d, --default-qos`: Default QoS to set (default: the granted QoS).
- `-c, --cluster`: Slurm cluster (default: the site cluster).
- `-r, --account-regex`: Only accounts matching this regex (default: all).
- `-x, --execute` / `-y, --yes`: Apply, and skip the prompt.

## `qos revoke QOS_NAME -u USERS|all -p PART|all [-c CLUSTER] [-r REGEX] [-x] [-y]`

Remove a priority QoS from users on a partition (via `sacctmgr`). Operator or a
coordinator of the account only.

Removes the QoS from each matching association, moving the default off it first
when needed and deleting the association if the QoS was its only entry. Pass
`all` for `--users` or `--partition` to act on every current holder. Dry run by
default.

**Use cases**
- Revoke a priority QoS from users who no longer need it.
- Clear a QoS off every holder with `-u all -p all`.

**Inputs**
- `QOS_NAME`: The QoS to remove.
- `-u, --users`: Users, or `all` (repeatable, comma-separated).
- `-p, --partition`: Partition, or `all`.
- `-c, --cluster`: Slurm cluster (default: the site cluster).
- `-r, --account-regex`: Only accounts matching this regex (default: all).
- `-x, --execute` / `-y, --yes`: Apply, and skip the prompt.

## `qos retire QOS_NAME -p PART|all [-c CLUSTER] [-r REGEX] [-x] [-y]`

Remove a QoS from all its holders on a partition, then delete it (via
`sacctmgr`). Slurm or system admin only, because it deletes the definition.

Revokes the QoS from every holder, then deletes the QoS definition. The delete
runs only if every revoke succeeded, so a QoS still held elsewhere (an
account-level or out-of-scope association) is left in place. Dry run by default.

**Use cases**
- Fully decommission a priority QoS in one step.

**Inputs**
- `QOS_NAME`: The QoS to retire.
- `-p, --partition`: Partition to clear, or `all`.
- `-c, --cluster`: Slurm cluster (default: the site cluster).
- `-r, --account-regex`: Only accounts matching this regex (default: all).
- `-x, --execute` / `-y, --yes`: Apply, and skip the prompt.

## `qos sync QOS_NAME -a ACCOUNT -p PART [-c CLUSTER] [-x] [-y]`

Reconcile a QoS's holders to an account's current membership (via `sacctmgr`).
Operator or a coordinator of the account only.

Grants the QoS to account members who lack it and revokes it from holders no
longer in the account, on the given partition. Idempotent and cron-friendly. Dry
run by default.

**Use cases**
- Keep a lab's priority QoS aligned with its Slurm account membership.

**Inputs**
- `QOS_NAME`: The QoS to reconcile.
- `-a, --account`: Account whose membership drives the QoS.
- `-p, --partition`: Partition to reconcile on.
- `-c, --cluster`: Slurm cluster (default: the site cluster).
- `-x, --execute` / `-y, --yes`: Apply, and skip the prompt.
