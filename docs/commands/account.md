# account

Account membership, fairshare, usage, and limits. Run `clustertool account --help` to list these commands.

## `account members ACCOUNT | --all`

List the users in a Slurm fairshare account.

With `--all`, list every lab account and its members as CSV:
`account,username,full_name`. Lab accounts are the ones allowed on the site's
roster partition whose name carries the site's lab prefix, both set under
`[accounts]` in the site config.

**Use cases**
- See who belongs to a lab's Slurm account.
- Export a full account/user/name roster with `--all`.

**Inputs**
- `ACCOUNT`: Slurm account name (e.g. `kempner_dev`). Omit when using `--all`.
- `--all`: List all lab accounts and members as CSV.

## `account fairshare [ACCOUNT] [-u USER]`

Show fairshare standing and priority (via `sshare`). With an ACCOUNT, show every
member's shares and usage; otherwise show your own across the accounts you belong
to. The FairShare column is the effective score (higher is higher priority).
Partition-scoped associations are labeled with their partition (`sshare -m`), so
a user's several rows in one account can be told apart. ACCOUNT and `--user`
cannot be combined.

**Use cases**
- See your priority standing and why jobs may be deprioritized.
- Compare members' usage within a lab account.

**Inputs**
- `ACCOUNT`: Slurm account (e.g. `kempner_dev`). Omit for your own standing.
- `-u, --user`: User to look up (default: current user).

## `account balance [ACCOUNT] [-n TOP]`

Rank accounts by fairshare balance (via `sshare`): effective usage versus
normalized share. A ratio above 1 means an account is over-served (drawing more
than its share); below 1 means under-served. An account with shares and no usage
is the most under-served there is, so it ranks at a ratio of zero rather than
being left out. Point-in-time only, since `sshare` keeps no history.

Effective usage is computed from `RawUsage` against the root account rather than
read from `sshare`'s own `EffectvUsage` column, which is printed to six decimals
and so rounds any account below a millionth of cluster usage to zero.

The ranking compares accounts against each other, which holds where shares are
normalized cluster-wide. Under Slurm's default `PriorityFlags=FAIR_TREE` those
figures are normalized within each level instead, so at a site with nested
accounts compare siblings rather than the whole list.

**Use cases**
- See which labs are drawing more than their fair share right now.
- Find under-served accounts that are due more scheduling priority.

**Inputs**
- `ACCOUNT`: Narrow to one account subtree (optional).
- `-n, --top`: Rows to show per ranking (default 10).

## `account usage [ACCOUNT] [-d DAYS] [--efficiency]`

Report cumulative CPU/GPU/TRES-hours for an account or user over the last
`--days` (via `stotal`). With `--efficiency`, show the `seff-account` efficiency
summary instead. Reading another user's jobs, including other members of your own
account, needs `AdminLevel=Operator` or above, or coordinator of that account;
without it the report silently covers only your own jobs and still exits 0.

**Use cases**
- See how many GPU-hours a lab or member used this month.
- Check the efficiency of a lab's jobs over a period.

**Inputs**
- `ACCOUNT`: Slurm account. Omit to report yourself.
- `-d, --days`: Period length in days (default 30).
- `-u, --user`: User to report (default: current user).
- `--efficiency`: Use `seff-account` (efficiency) instead of `stotal` (hours).

## `account limits [ACCOUNT] [-u USER]`

Show account associations: QoS, partitions, priority, and TRES limits (via
`sacctmgr`). With an ACCOUNT, show that account's associations; otherwise yours.

**Use cases**
- See which QoS and partitions an account may use.
- Check configured TRES limits for a lab.

**Inputs**
- `ACCOUNT`: Slurm account. Omit to show your own associations.
- `-u, --user`: User to look up (default: current user).

## `account top-users ACCOUNT`

Rank an account's members by RawUsage (via `sshare`), highest first.

**Use cases**
- See who in a lab has consumed the most recently.

**Inputs**
- `ACCOUNT`: Slurm account (e.g. `kempner_dev`).

## `account qos [-f TEXT] [-l]`

List QoS definitions and their limits (via `sacctmgr`): priority, max wall time,
and TRES limits including the per-user, per-account, per-job, and total GPU caps,
so every limit `qos create` and `qos modify` can set is readable here. With
`--long`, add the per-user job-count, submit, Flags, Preempt, and UsageFactor
columns.

**Use cases**
- See the GPU cap and priority of a partition's QoS.
- Inspect preemption and flags with `--long`.

**Inputs**
- `-f, --filter`: Only show rows containing this text (the header is kept).
- `-l, --long`: Show the full field set instead of the compact one.

## `account add-user USER ACCOUNT`

Add a user to a fairshare account (via `sacctmgr`), creating the account's base
association for them. The fairshare value defaults to `[qos].grant_fairshare`
from the site config, the same value `qos grant` gives the associations it
creates. Prompts for confirmation unless `-y`. Slurm operator, or a coordinator of the account; a site that sets
`DisableCoordDBD` in `slurmdbd.conf` restricts this to operators.

**Use cases**
- Grant a new lab member access to the lab's Slurm account.

**Inputs**
- `USER`: Username to add.
- `ACCOUNT`: Slurm account to add them to.
- `--fairshare`: Fairshare value (default: the site's `grant_fairshare`).
- `-c, --cluster`: Slurm cluster (default: the site cluster).
- `-y, --yes`: Skip the confirmation prompt.

## `account remove-user USER ACCOUNT`

Remove a user's associations with an account (via `sacctmgr`).

A user can hold several associations in one account: a base one, plus one per
partition, each with its own QoS list. Without `--partition` this removes all of
them, so a priority QoS granted on a single partition goes too; every association
is listed before you confirm. Give `--partition` to remove just that one. The
user's other accounts are untouched. Prompts for confirmation unless `-y`. Slurm operator, or a coordinator of the account; a site that sets
`DisableCoordDBD` in `slurmdbd.conf` restricts this to operators.

**Use cases**
- Remove a former member from a lab's Slurm account.
- Drop one partition's association while keeping the account membership.

**Inputs**
- `USER`: Username to remove.
- `ACCOUNT`: Slurm account to remove them from.
- `-p, --partition`: Remove only the association on this partition.
- `-c, --cluster`: Slurm cluster (default: the site cluster).
- `-y, --yes`: Skip the confirmation prompt.

## `account set-fairshare USER ACCOUNT SHARE`

Set a user's fairshare in an account (via `sacctmgr`). SHARE is an integer number
of raw shares, or `parent` to inherit the account's shares; anything else is
refused. The condition carries no partition, so sacctmgr matches every association the user holds in the account and overwrites each one, including a partition association set to `parent`. The associations it will change are listed before you confirm. Prompts
for confirmation unless `-y`. Slurm operator, or a coordinator of the account; a site that sets
`DisableCoordDBD` in `slurmdbd.conf` restricts this to operators.

**Use cases**
- Adjust a member's fairshare weight within a lab.

**Inputs**
- `USER`: Username.
- `ACCOUNT`: Slurm account.
- `SHARE`: Raw shares (integer) or `parent`.
- `-c, --cluster`: Slurm cluster (default: the site cluster).
- `-y, --yes`: Skip the confirmation prompt.
