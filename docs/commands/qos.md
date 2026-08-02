# qos

Slurm QoS: who holds them, and (admin) provisioning their limits. Run
`clustertool qos --help` to list these commands, or `clustertool qos <command>
--help` for one.

The admin write commands are dry run by default: they print the exact `sacctmgr`
commands and change nothing. Re-run with `--execute` to apply, confirming unless
`-y`. Every `sacctmgr` call carries `-i`, so this tool's dry-run gate, not
`sacctmgr`, is what guards against accidental changes.

They need two different privilege levels.

Changing a QoS *definition* (`create`, `modify`, `delete`, `retire`) needs
`AdminLevel=Administrator`, or root/SlurmUser: slurmdbd gates a QoS object at its
super-user level. Writing an *association* (`grant`, `revoke`, `sync`) needs only
`AdminLevel=Operator`, or a coordinator of the account where `DisableCoordDBD` is
not set. SchedMD's `user_permissions` page describes an operator as able to
"add, modify, and remove any database object", but slurmdbd's own accounting
plugin gates a QoS object at `SLURMDB_ADMIN_SUPER_USER` while gating an
association at `SLURMDB_ADMIN_OPERATOR`, so an operator is refused on the four
definition commands. A coordinator never has QoS-definition rights either, so
`DisableCoordDBD` does not apply to them.

*Assigning* an existing QoS (`grant`, `revoke`, `sync`) only edits associations,
so a Slurm operator or a coordinator of the account can do it, unless the site
sets `DisableCoordDBD` in `slurmdbd.conf`, which restricts it to operators.

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
`sacctmgr`). Needs AdminLevel=Administrator, or root/SlurmUser.

Dry run by default. Give at least one limit; a value of `-1` clears that limit.
Per-user node and GPU caps merge into one `MaxTRESPU` limit.

**Use cases**
- Provision a new priority QoS with per-user and total GPU caps.

**Inputs**
- `QOS_NAME`: Name of the QoS to create or update.
- `-g, --gpu-per-user`: Per-user GPU cap (`MaxTRESPU gres/gpu`).
- `-n, --node-per-user`: Per-user node cap (`MaxTRESPU node`).
- `-A, --account-gpu`: Per-account GPU cap (`MaxTRESPA gres/gpu`). This is the
  cap `gpu usage` reports each account against when the QoS is the site's base
  QoS.
- `-G, --group-gpu`: Total GPU cap for the QoS (`GrpTRES gres/gpu`).
- `-j, --job-gpu`: Per-job GPU cap (`MaxTRES gres/gpu`).
- `-J, --jobs-per-user`: Per-user running-job cap (`MaxJobsPU`).
- `-x, --execute`: Apply the change instead of previewing it.
- `-y, --yes`: Skip the confirmation prompt.

## `qos modify QOS_NAME <limits> [--per-user-only] [-x] [-y]`

Change an existing QoS's limits (via `sacctmgr`). Needs
AdminLevel=Administrator, or root/SlurmUser.

Dry run by default. Only the limits you pass change; a value of `-1` clears one.
With `--per-user-only` the per-account, group, and per-job GPU caps are all
cleared. Any other limit the QoS carries, such as `MaxWall` or a non-GPU
`MaxTRES`, is left as it was. Errors if the QoS does not exist (use
`qos create`).

**Use cases**
- Raise or lower a QoS's per-user GPU cap.
- Reduce a QoS to per-user caps only.
- Set the per-account GPU cap that `gpu usage` reports against, with `-A`.

**Inputs**
- `QOS_NAME`: Name of an existing QoS.
- `-g/-n/-A/-G/-j/-J`: Limit caps (as for `qos create`; `-1` clears).
- `--per-user-only`: Also clear the per-account, group, and per-job GPU caps.
- `-x, --execute`: Apply the change instead of previewing it.
- `-y, --yes`: Skip the confirmation prompt.

## `qos delete QOS_NAME [-x] [-y]`

Delete a QoS definition, refusing while it is still referenced (via `sacctmgr`).
Needs AdminLevel=Administrator, or root/SlurmUser.

Dry run by default. Refuses while the QoS is still in force: if any association
on any cluster still lists it, if a partition's `QoS`, `AllowQos`, or `DenyQos`
setting names it (where it applies without any association mentioning it), or if
any queued or running job carries it. The refusal names the setting, since `QoS`
and `AllowQos` let jobs use it while `DenyQos` bars them. An association that
sets no QoS list of its own inherits its parent's, so a large holder count
usually means one parent sets it. A QoS that does not exist is a no-op.

**Use cases**
- Retire a QoS definition that is no longer assigned to anyone.

**Inputs**
- `QOS_NAME`: Name of the QoS to delete.
- `-x, --execute`: Apply the change instead of previewing it.
- `-y, --yes`: Skip the confirmation prompt.

## `qos grant QOS_NAME -u USERS -p PART [-d DEFAULT] [-c CLUSTER] [-r REGEX] [-x] [-y]`

Grant a priority QoS to users across their matching accounts on a partition (via
`sacctmgr`). Slurm operator, or a coordinator of the account; a site that sets
`DisableCoordDBD` in `slurmdbd.conf` restricts this to operators.

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

Remove a priority QoS from users on a partition (via `sacctmgr`). Slurm
operator, or a coordinator of the account; a site that sets `DisableCoordDBD` in
`slurmdbd.conf` restricts this to operators.

Removes the QoS from each matching association, moving the default off it first
when needed and deleting the association if the QoS was its only entry. Pass
`all` for `--users` or `--partition` to act on every current holder. An unknown
partition name is refused rather than silently matching nothing. Dry run by
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
`sacctmgr`). Needs AdminLevel=Administrator, or root/SlurmUser, because it
deletes the definition.

Revokes the QoS from every holder, then deletes the QoS definition. Where the QoS
is an association's only one, the revoke deletes that association outright rather
than editing it, which drops its recorded usage.

Refuses up front if the QoS is named in any partition's configuration, if any
queued or running job carries it, or if any association still holding it would
not be revoked by this sweep, such as an account-level one, one with no
partition, or one on another cluster; it lists the ones it would leave behind.
The delete runs only after every revoke in the plan succeeded. Dry run by
default.

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
Slurm operator, or a coordinator of the account; a site that sets
`DisableCoordDBD` in `slurmdbd.conf` restricts this to operators.

Grants the QoS to account members who lack it and revokes it from holders no
longer in the account, on the given partition. Membership is the account's base
association, so a user whose partition association lingers after their membership
was removed is revoked. Granting works exactly as `qos grant` does, so it also
makes the QoS the association's default and strips the site's catch-all and the
partition-named QoS: a member who had chosen a different default gets it
overwritten on every run. Idempotent and cron-friendly. Dry run by default.

**Use cases**
- Keep a lab's priority QoS aligned with its Slurm account membership.

**Inputs**
- `QOS_NAME`: The QoS to reconcile.
- `-a, --account`: Account whose membership drives the QoS.
- `-p, --partition`: Partition to reconcile on.
- `-c, --cluster`: Slurm cluster (default: the site cluster).
- `-x, --execute` / `-y, --yes`: Apply, and skip the prompt.
