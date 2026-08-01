# storage

Storage quotas, usage, and filesystem layout. Run `clustertool storage --help` to
list these commands. The Lustre commands (`lfs-stripe`, `lfs-inodes`) are hidden
at a site whose `[tools].lfs` binary is not installed.

## `storage quota [PATH] [-g GROUP | -u USER] [-a] [--fleet LAB] [-v]`

Show a storage quota on any filesystem (via the FASRC `quota` tool).

Reports quota and usage for PATH, which selects the filesystem: VAST
(`/n/netscratch`), Lustre (`/n/holylfs06`, `/n/holystore01`, ...), home, and so
on. Use `--group` for a lab's quota or `--user` for a user's; with neither, the
quota tool infers from the path. A bare name like `holylfs06` becomes
`/n/holylfs06`.

With `--all`, PATH is optional and the command reports every lab directory you
belong to (auto-detected from your Unix groups across the site's lab roots) as a
`USED / QUOTA / DISK% / FILES%` table. With `--fleet LAB`, it reports every
`LAB*` directory directly under PATH, sorted by usage. Lab directories usually
sit in a subdirectory of the filesystem, so point `--fleet` at that parent rather
than at the mount point: `/n/holylfs06/LABS`, not `/n/holylfs06`.

**Use cases**
- Lab quota on scratch: `storage quota netscratch -g kempner_dev`
- Your lab dirs at a glance: `storage quota --all`
- Fleet view of one root: `storage quota holylfs06/LABS --fleet kempner`

**Inputs**
- `PATH`: Filesystem path, or a bare name that becomes `/n/<name>`. Optional with `--all`.
- `-g, --group`: Group/lab name for the lookup.
- `-u, --user`: User for the lookup (also whose labs `--all` reports).
- `-a, --all`: Report every lab directory you belong to as a table.
- `--fleet LAB`: Report every `LAB*` directory directly under PATH, by usage.
- `-v, --verbose`: Show the underlying quota command.

## `storage home [--scan] [--top N] [--ncdu]`

Show home directory usage, and optionally its largest subdirectories.

Runs `df -h ~` to show your home quota (Size), usage, and available space. With
`--scan`, also lists the `--top` N largest subdirectories (default 10) so you can
find what to clean up. With `--ncdu`, opens the interactive ncdu explorer
instead.

**Use cases**
- See how much home space you have left (df).
- Find the biggest directories when near the cap (`--scan` or `--ncdu`).

**Inputs**
- `-s, --scan`: Also list the largest subdirectories under home.
- `-n, --top`: How many directories to list with `--scan` (default 10).
- `--ncdu`: Launch the interactive ncdu explorer on home.

## `storage vast-usage PATH -g GROUP`

Show per-user usage for a group on a VAST filesystem such as `/n/netscratch`
(via the FASRC `quota` tool). Lists how much each member of GROUP is using under
PATH. A bare name like `netscratch` becomes `/n/netscratch`.

**Use cases**
- See who in a lab is filling a shared scratch or VAST allocation.

**Inputs**
- `PATH`: Filesystem path, or a bare name that becomes `/n/<name>`.
- `-g, --group`: Unix group to break usage down by.

## `storage scratch [PATH]`

Show networked scratch usage and the purge policy (via the FASRC `quota` tool).
Reports quota and usage for your scratch path, then restates the site's purge
policy: how long files survive there, and that scratch is not backed up. The path
and the purge age both come from `[storage]` in the site config, so a center with
a 30-day scratch sees 30 days. PATH defaults to `$SCRATCH`, then the configured
scratch path (`/n/netscratch` with the packaged Kempner profile).

**Use cases**
- Check how full your lab's scratch allocation is.
- Remember the auto-deletion age before staging data there.

**Inputs**
- `PATH`: Scratch path (default: `$SCRATCH`, else the site's scratch path).

## `storage lfs-stripe PATH [-c COUNT] [-y]`

Show or set Lustre striping for a path (via `lfs`). Without `--count`, print the
layout of PATH itself and not of anything inside it (`lfs getstripe -d`). With
`--count`, set the stripe count for newly created files under PATH (`lfs
setstripe`); existing files are not restriped.

A count spreads each new file over that many OSTs, so it trades throughput on
large files against more metadata work and wider exposure to a single OST going
away. Match it to the file size: one stripe suits ordinary files, and a file in
the hundreds of GB or larger benefits from many. Two counts are special, as
`lfs-setstripe` defines them: `0` restores the filesystem-wide default rather
than setting zero stripes, and `-1` stripes over every available OST. A count
above the number of OSTs is refused, since `lfs` would silently clamp it; use
`lfs setstripe -C` directly if you really want more than one stripe per OST.

Setting a count changes the default for everyone who writes new files there,
including in a shared lab directory, so it prompts for confirmation unless `-y`.
Lustre allows it only on a directory you own, whatever the write permissions.

**Use cases**
- Check how a directory is striped across Lustre targets.
- Widen striping before writing very large files for throughput.

**Inputs**
- `PATH`: A path on a Lustre filesystem.
- `-c, --count`: Stripe count for new files under PATH, or `0` / `-1`.
- `-y, --yes`: Skip the confirmation prompt.

## `storage lfs-inodes PATH`

Show inode capacity and usage for a Lustre filesystem (via `lfs df -i`). PATH
must be on Lustre (for example `/n/holylfs06`); a bare name like `holylfs06`
becomes `/n/holylfs06`.

**Use cases**
- Check whether a Lustre filesystem is running low on inodes.

**Inputs**
- `PATH`: A Lustre path, or a bare name that becomes `/n/<name>`.
