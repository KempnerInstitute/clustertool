# storage

Inspect storage quotas. Run `clustertools storage --help` to list these commands.

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
- `PATH` — Filesystem path, or a bare name that becomes `/n/<name>`.
- `-g, --group` — Group/lab name for the lookup.
- `-u, --user` — User name for the lookup.
- `-v, --verbose` — Show the underlying quota command.

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
- `-s, --scan` — Also list the largest subdirectories under home.
- `-n, --top` — How many directories to list with `--scan` (default 10).
- `--ncdu` — Launch the interactive ncdu explorer on home.
