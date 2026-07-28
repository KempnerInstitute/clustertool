# account

Account membership, fairshare, usage, and limits. Run `clustertools account --help` to list these commands.

## `account members ACCOUNT | --all`

List the users in a Slurm fairshare account.

With `--all`, list every Kempner lab account (from the kempner partition's
allowed accounts) and its members as CSV: `account,username,full_name`.

**Use cases**
- See who belongs to a lab's Slurm account.
- Export a full account/user/name roster with `--all`.

**Inputs**
- `ACCOUNT`: Slurm account name (e.g. `kempner_dev`). Omit when using `--all`.
- `--all`: List all Kempner lab accounts and members as CSV.

## `account fairshare [ACCOUNT] [-u USER]`

Show fairshare standing and priority (via `sshare`). With an ACCOUNT, show every
member's shares and usage; otherwise show your own across the accounts you
belong to. The FairShare column is the effective score (higher is higher
priority).

**Use cases**
- See your priority standing and why jobs may be deprioritized.
- Compare members' usage within a lab account.

**Inputs**
- `ACCOUNT`: Slurm account (e.g. `kempner_dev`). Omit for your own standing.
- `-u, --user`: User to look up (default: current user).

## `account usage [ACCOUNT] [-d DAYS] [--efficiency]`

Report cumulative CPU/GPU/TRES-hours for an account or user over the last
`--days` (via `stotal`). With `--efficiency`, show the `seff-account` efficiency
summary instead. Querying accounts you do not belong to needs operator rights.

**Use cases**
- See how many GPU-hours a lab or member used this month.
- Check the efficiency of a lab's jobs over a period.

**Inputs**
- `ACCOUNT`: Slurm account. Omit to report yourself.
- `-d, --days`: Period length in days (default 30).
- `-u, --user`: User to report (default: current user).
- `--efficiency`: Use `seff-account` (efficiency) instead of `stotal` (hours).

## `account limits [ACCOUNT] [-u USER]`

Show account associations: QOS, partitions, priority, and TRES limits (via
`sacctmgr`). With an ACCOUNT, show that account's associations; otherwise yours.

**Use cases**
- See which QOS and partitions an account may use.
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

## `account qos [-f TEXT]`

List QOS definitions and their limits (via `sacctmgr`): priority, max wall time,
and TRES limits including the per-user and total GPU caps.

**Use cases**
- See the GPU cap and priority of a partition's QOS.

**Inputs**
- `-f, --filter`: Only show rows containing this text (the header is kept).

## `account add-user USER ACCOUNT`

Add a user to a fairshare account (via `sacctmgr`). Prompts for confirmation
unless `-y`. Operator only.

**Use cases**
- Grant a new lab member access to the lab's Slurm account.

**Inputs**
- `USER`: Username to add.
- `ACCOUNT`: Slurm account to add them to.
- `--fairshare`: Fairshare value (default `parent`).
- `-y, --yes`: Skip the confirmation prompt.

## `account remove-user USER ACCOUNT`

Remove a user's association with an account (via `sacctmgr`). Removes only the
USER and ACCOUNT association, not the user's other accounts. Prompts for
confirmation unless `-y`. Operator only.

**Use cases**
- Remove a former member from a lab's Slurm account.

**Inputs**
- `USER`: Username to remove.
- `ACCOUNT`: Slurm account to remove them from.
- `-y, --yes`: Skip the confirmation prompt.

## `account set-fairshare USER ACCOUNT SHARE`

Set a user's fairshare in an account (via `sacctmgr`). SHARE is an integer
number of raw shares, or `parent` to inherit the account's shares. Prompts for
confirmation unless `-y`. Operator only.

**Use cases**
- Adjust a member's fairshare weight within a lab.

**Inputs**
- `USER`: Username.
- `ACCOUNT`: Slurm account.
- `SHARE`: Raw shares (integer) or `parent`.
- `-y, --yes`: Skip the confirmation prompt.
