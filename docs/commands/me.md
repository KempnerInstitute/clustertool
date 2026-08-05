# me

Where you stand on the cluster: your jobs, your storage, and your standing. `me`
is top-level rather than in a group. Run `clustertool me --help` for the summary
of what follows.

## `me [-u USER] [--plain] [-a] [-i SECONDS] [-d DAYS] [--theme NAME]`

Show a personal overview: your jobs, GPUs in use, and fairshare standing.

In a terminal, with no other flags, this opens an interactive dashboard. Naming
a user, asking for the access map, or redirecting the output prints a one-shot
text summary instead, as does a terminal that cannot render the dashboard or an
install without the optional `tui` extra:

```bash
uv tool install 'clustertool[tui]'   # or: pipx install 'clustertool[tui]'
```

Both forms read only. Nothing changes a job unless you confirm it.

## The dashboard

Three panels and a status bar.

**Jobs** lists everything of yours that is queued or running, refreshed every
five seconds, with the selected job described underneath: its state, how long it
has run, what it holds, and where. A value too long for its column is cut with
an ellipsis and shown in full in that pane. The panel keeps its last rows and
marks itself stale if the controller stops answering, since an empty table would
read as having no jobs.

**Storage** shows your home directory, every lab directory you belong to
(fullest first), and your own usage on Lustre. It loads once at startup rather
than on a timer, because quotas move slowly and the lookup fans out across every
lab root. A directory that could not be read says so instead of showing a
figure, and one that had not answered by the deadline is marked unfinished.

**Standing** carries five facts: your fairshare per account, the GPUs you hold
against your cap and your account's against its own, how the last week of your
jobs ended, your median utilization, and the share of the GPU-hours you held
that went unused. The last of those is weighted by how long each job held its
GPUs, which the median cannot show, and both utilization figures name how many
jobs they cover, since not every job records it.

## Keys

`?` lists every key over the dashboard. `Q` quits.

| Key | |
| --- | --- |
| up, down | move between jobs |
| enter | menu of everything you can do to the selected job |
| tab, shift+tab | next or previous panel |
| r | refresh the focused panel |
| R | refresh every panel |
| escape | stop following a log |

On the selected job, each asking first:

| Key | |
| --- | --- |
| c | cancel it |
| h | hold it |
| H | release it |
| ctrl+r | requeue it, losing its work |

Read-only, on the selected job:

| Key | |
| --- | --- |
| l | the tail of its output |
| f | follow its output |
| w | why it is not running |
| s | how well it used its request |
| y | copy its id |

`enter` opens the same actions as a menu, with cancel selected, so the keys do
not have to be memorized. Choosing one of the four that change a job asks first,
and the answer defaults to No. Requeue is on `ctrl+r` rather than a plain letter
because it throws away a running job's work.

The four that change a job go through the same checks as `jobs cancel`, `jobs
hold`, `jobs release`, and `jobs requeue`, so the dashboard refuses the same jobs
for the same reasons and reports the refusal on its banner.

## Inputs

`-u, --user USER` shows another user, which implies `--plain`. The dashboard
covers the caller only.

`--plain` prints the one-shot summary: your job counts and first ten jobs, GPUs
in use, and fairshare per account.

`-a, --access` adds the accounts you may submit under, the account to partition
to QoS map, and your Slurm priority tiers. It implies `--plain`.

`-i, --interval SECONDS` sets how often the jobs panel refreshes, five by
default, with a floor of two: every tick is a query on the controller, and `r`
refreshes on demand.

`-d, --days DAYS` sets how far back the standing panel looks, seven by default. A
wide window slows that panel, which reads that many days of accounting.

`--theme NAME` takes `dark`, `light`, `ansi`, or any Textual theme name. The
dashboard paints its own background, so the theme rather than the terminal
decides whether the screen is light; the `ansi` themes use the terminal's own
colors instead. `NO_COLOR` is honored, and the emphasis falls back to bold and
underline.

## What it needs from the site config

Nothing about the dashboard is specific to one center. It reads the same site
config as every other command:

| Panel | Keys |
| --- | --- |
| Status bar | `[site].name` |
| Jobs | none beyond Slurm itself |
| Storage | `[storage].lab_roots`, `[storage].path_prefix`, `[tools].quota`, `[tools].lfs` |
| Standing | `[partitions].base`, `[qos].base`, `[accounts].lab_prefix` |
| Access map | `[site].slurm_group_prefix` |

A figure whose source a site does not have degrades rather than misleads: with
no GPU cap on the configured QoS the line says the cap is unknown, and with no
utilization data recorded against jobs the median and unused lines say so.

## Terminal size

Below 80 columns the storage panel moves underneath the jobs panel rather than
beside it, and the dashboard stays usable down to about 30 columns and 15 rows.
Below 15 rows the detail pane has no room left for a log tail. Anything that does
not fit is marked rather than silently cut.
