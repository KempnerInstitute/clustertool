# storage

Inspect storage quotas and usage. Run `clustertools storage --help` to list
these commands.

## `storage quota PATH [-g GROUP | -u USER] [-v]`

Show a storage quota on any filesystem (via the FASRC `quota` tool).

Reports quota and usage for PATH, which selects the filesystem: VAST
(`/n/netscratch`), Lustre (`/n/holylfs06`, `/n/holystore01`, ...), home, and so
on. Use `--group` for a lab's quota or `--user` for a user's; with neither, the
quota tool infers from the path. A bare name like `holylfs06` becomes
`/n/holylfs06`.

**Use cases**
- Lab quota on scratch: `storage quota netscratch -g kempner_dev`
- Lab quota on Lustre: `storage quota holylfs06 -g kempner_dev`
- Your own usage: `storage quota holystore01 -u $USER`

**Inputs**
- `PATH`: Filesystem path, or a bare name that becomes `/n/<name>`.
- `-g, --group`: Group/lab name for the lookup.
- `-u, --user`: User name for the lookup.
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

## `storage usage PATH -g GROUP`

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
Reports quota and usage for your netscratch path and reminds you that files on
`/n/netscratch` are deleted after 90 days and are not backed up. PATH defaults
to `$SCRATCH`, then `/n/netscratch`.

**Use cases**
- Check how full your lab's netscratch allocation is.
- Remember the 90-day auto-deletion before staging data there.

**Inputs**
- `PATH`: Scratch path (default: `$SCRATCH`, else `/n/netscratch`).

## `storage stripe PATH [-c COUNT]`

Show or set Lustre striping for a path (via `lfs`). Without `--count`, print the
current stripe layout (`lfs getstripe`). With `--count`, set the stripe count
for newly created files under PATH (`lfs setstripe`); existing files are not
restriped. Use 8 to 16 for large multi-GB or TB files.

**Use cases**
- Check how a directory is striped across Lustre targets.
- Widen striping before writing very large files for throughput.

**Inputs**
- `PATH`: A path on a Lustre filesystem (e.g. `/n/holylfs06/...`).
- `-c, --count`: Stripe count to set for new files under PATH.

## `storage inodes PATH`

Show inode capacity and usage for a Lustre filesystem (via `lfs df -i`). PATH
must be on Lustre (for example `/n/holylfs06`); a bare name like `holylfs06`
becomes `/n/holylfs06`.

**Use cases**
- Check whether a Lustre filesystem is running low on inodes.

**Inputs**
- `PATH`: A Lustre path, or a bare name that becomes `/n/<name>`.
