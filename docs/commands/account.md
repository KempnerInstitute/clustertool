# account

Inspect Slurm accounts. Run `clustertools account --help` to list these commands.

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
