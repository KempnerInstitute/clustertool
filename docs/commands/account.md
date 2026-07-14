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
- `ACCOUNT` — Slurm account name (e.g. `kempner_dev`). Omit when using `--all`.
- `--all` — List all Kempner lab accounts and members as CSV.
