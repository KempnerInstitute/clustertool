# Plan: an interactive TUI for `clustertool me`

A light, fast, information-dense terminal dashboard answering one question:
where do I stand on this cluster right now. It replaces the four commands a user
runs every morning (`jobs list`, `storage quota --all`, `account fairshare`,
`jobs scope`) with one screen.

Built on [Textual](https://textual.textualize.io/). Textual is chosen over Rich
because this screen is interactive, not a display: it needs focus, a selectable
row, keybindings, a confirmation dialog before a `scancel`, background workers so
a slow panel cannot freeze the UI, and a test driver. Rich provides the rendering
and Textual is built on it, so `gpu pulse` staying on Rich is consistent rather
than contradictory: that command only displays.

Out of scope: a PI-facing dashboard. The panel and data layers below are written
so a later `clustertool pi` can reuse them, but nothing here is built for it.

## Measurements this plan rests on

Taken on a login node, 2026-08-02, and the reason the design looks as it does.

| Data | Cost |
| --- | --- |
| jobs, `squeue` | 0.06s |
| fairshare, `sshare` | 0.07s |
| lab quota, one filesystem | 0.01 to 0.19s |
| user quota on Lustre, `lfs quota -u` | 0.86s |
| home, `df` | 0.02s |
| all 40 lab dirs, serial (what `storage quota --all` does today) | 6.9s |
| `jobs scope -D 7` through the CLI | 4.7s |

An earlier cold-cache run of `storage quota --all` took 22.4s. Warm, it is 7.4s
through the CLI and 6.9s as a raw serial fan-out, repeatably. The lower figure is
the one to design against.

Thread scaling on that same 40-target fan-out:

| Threads | Time | Speedup |
| --- | --- | --- |
| 1 | 6.9s | |
| 2 | 3.4s | 2.0x |
| 4 | 1.7s | 4.0x |
| 6 | 1.2s | 5.7x |
| 8 | 0.90s | 7.7x |
| 16 | 0.59s | 11.7x |

Near-linear to 8, flat after. **Six threads** is the choice: 1.2s is already below
the point anyone notices for a panel that loads behind a spinner, and doubling
concurrency past 8 buys tenths of a second. This is a shared login node, so
twenty people running the TUI at six threads each is 120 concurrent quota calls
and at sixteen would be 320. The number is a named constant a site can lower.

Two conclusions. The jobs panel is cheap enough to refresh continuously. The
storage panel needs its queries in parallel, and its cost is a property of the
current serial implementation rather than of the quota service.

## Layout

```
┌─ clustertool me ─────────────────────────────┬──────────────────┐
│  JOBS  (focused, auto-refresh)               │  STORAGE   (r)   │
│   ID    PART      ST  GPU  ELAP   NODE       │  home    80% ███░│
│  >3666  h100      R    4   2:14   gpu8a15    │  lab:            │
│   3660  sapphire  R    -   6:02   holy7c04   │   holylfs06  60% │
│   3664  h100      PD   4    -     (Priority) │   netscratch 41% │
│                                              │   holylabs   93% │
│  DETAIL for the selected job                 │  you (Lustre):   │
│   reason / TRES / nodes / log tail           │   holylfs06  12% │
├──────────────────────────────────────────────┴──────────────────┤
│  STANDING  (r)                                                  │
│  fairshare 0.000445   4 of 96 GPU on the cap                    │
│  last 7d: 41 jobs  CPU 38%  GPU 71%  mem 22%   2 OOM, 1 timeout │
├─────────────────────────────────────────────────────────────────┤
│ jdoe (Jane Doe) @ holy8a24209   odyssey   Sun 2026-08-02 14:32  │
└─────────────────────────────────────────────────────────────────┘
```

Status bar, always visible: username and full name from `getent`, the host the
app is running on, the cluster name from the site config, and a live clock with
the date. A refresh indicator and the last-refresh age sit at the right.

## Data sources

Every panel reads through helpers that already exist. No new Slurm integration.

| Panel | Source |
| --- | --- |
| Jobs | `slurm.my_jobs`, `slurm.user_gpu_count` |
| Job detail | `slurm.job_accounting`, `slurm.job_output_paths`, `scontrol show job` |
| Storage, lab | `storage.quota_cmd` per target, `storage.lab_targets` |
| Storage, user | `lfs quota -u` on Lustre roots only |
| Storage, home | `df -h ~` |
| Fairshare | `slurm.user_fairshare` |
| GPU cap | `slurm.account_cap`, `slurm.gpu_by_account` |
| Efficiency | the `jobscope` library, not its CLI |
| Identity | `pwd.getpwuid(os.getuid())`, `slurm.user_fullnames` |

VAST filesystems are reported at lab level only. Per-user figures come from
Lustre, where `lfs quota -u` is fast and meaningful.

Efficiency goes through `jobscope.sacct.fetch` and `jobscope.report` rather than
parsing CLI text. Parsing another tool's output would break the first time its
format changed.

## Refresh model

Three tiers, because the panels differ in cost by two orders of magnitude.

- **Jobs**: a Textual worker on a timer, default 5s, `--interval` to change it.
  Skipped rather than queued while one is still in flight, so two never overlap.
- **Storage and Standing**: loaded once at startup in background workers, each
  showing a spinner until its data lands. Refreshed on `r` for the focused panel
  or `R` for all. They are not on a timer: quota and fairshare move slowly, and
  polling them every few seconds would put pointless load on shared services.
- **Clock**: a 1s timer that touches no subprocess.

Every panel guards its worker with an in-flight flag, so a held-down `r` cannot
stack queries. A `exclusive=True` worker does not achieve this: it cancels the
coroutine awaiting the thread, and the subprocess the thread started runs to
completion regardless, so one query per keypress still reaches the controller.

A panel that fails keeps its last good data, marks itself stale, and shows the
reason both on its border title and in its body, rather than tearing down the
app. The title carries it because the body is what a short terminal clips first.
Every exception reaches that path, not only `CommandError`, since a dashboard
that dumps a traceback over the screen is worse than one showing stale data.

## Actions

All routed through the existing command functions, never by calling `scancel` or
`scontrol` directly, so the TUI inherits the ownership and existence checks
rather than duplicating them.

Read-only, no confirmation:

| Key | Action |
| --- | --- |
| `l` | show the job's log tail in the detail pane |
| `f` | follow the log, `esc` to stop |
| `w` | why this job is pending |
| `s` | this job's efficiency |
| `y` | copy the job id |
| `enter` | expand or collapse the detail pane |

Mutating, each behind a modal naming the job, its partition, and its elapsed
time, defaulting to No. Requeue is on `ctrl+r` rather than `q`: `q` is one shift
key from `Q`, and the action that throws away a running job's work should not be
a slip of the shift key from the one that leaves the app.

| Key | Action | Routes through |
| --- | --- | --- |
| `c` | cancel | `jobs cancel` |
| `h` | hold | `jobs hold` |
| `H` | release | `jobs release` |
| `ctrl+r` | requeue | `jobs requeue` |

Ownership is not re-implemented. `slurm.job_owner` reads the caller's uid, so a
user can only ever act on their own jobs, and the TUI shows only their jobs in
the first place.

Global: `r` refresh focused, `R` refresh all, `?` help overlay, `tab` cycle
panels, `ctrl+c` or `Q` quit.

## Invocation

`clustertool me` launches the TUI when stdout is a terminal and Textual is
installed. Otherwise it prints exactly what it prints today. `--plain` forces the
one-shot output.

The TUI shows the caller only, and `-u` implies `--plain`. A dashboard of someone
else's jobs that cannot act on them is a half-feature: the actions below are
gated on ownership, so every key would be inert. Keeping `-u` on the one-shot
path leaves today's behavior untouched, needs no privilege check, and avoids a
screen whose efficiency panel would render empty anyway, since slurmdbd's
`PrivateData=jobs` already withholds another user's job records. Revisit only
with a reason.

This keeps three properties: the command a user types is unchanged, piping or
redirecting `me` still yields plain text for scripts, and a site that does not
install the extra loses nothing it has today.

Textual is an optional extra, `clustertool[tui]`, not a runtime dependency. It
adds six packages to a runtime tree that is otherwise `click` plus two bundled
tools, and the portability claim in the README is that the tool needs only what
the cluster already provides. `me --plain` must never import Textual.

## Phases

Each phase ends green: lint clean, the suite passing with no Slurm binary on
`PATH`, and the phase's own verification done. Each is one PR.

### Phase 0: dependency and skeleton

1. Add `[project.optional-dependencies] tui = ["textual>=0.80"]` and refresh
   `uv.lock`, since CI installs frozen.
2. Add `pytest-textual-snapshot` to the dev group.
3. `src/clustertool/tui/` package: `app.py`, `panels/`, `data.py`.
4. `me` grows `--plain` and the TTY-and-import check. With the extra absent,
   `me` behaves exactly as it does today.

Verification: `me` output byte-identical to current output with the extra
uninstalled, and again with `--plain` while it is installed. A test asserts
`clustertool.commands.me` does not import Textual at module scope.

### Phase 1: shell, status bar, clock

1. Three-region layout with `tab` cycling and no data.
2. Status bar: username, full name, host, cluster, live clock and date.
3. `?` help overlay, `Q` quit.

Verification: a snapshot test of the empty shell. The clock is injected, never
read from the wall clock in tests, so snapshots are stable.

### Phase 2: jobs panel and detail

1. Table of the user's jobs with the timer worker.
2. Row selection and the detail pane: pending reason, TRES, nodes.
3. Empty state that reads as "no jobs", not as a failed query.
4. Failure state that names the cause and keeps the previous data.

Verification: Pilot tests driving arrow keys and `enter` against a stubbed
`my_jobs`; snapshots for populated, empty, and failed. One live check on the
cluster against real running jobs.

### Phase 3: storage panel

1. Parallel fan-out over the user's lab targets, six workers, named constant.
2. Lab rows per filesystem, user rows for Lustre, home from `df`.
3. Usage bars with a threshold color, and `-` where no quota is set.
4. Loads in a worker with a spinner, refreshes on `r`.

Verification: unit tests on the parsing and threshold logic with stubbed
`process.probe`; a test asserting the fan-out is parallel by timing stubbed
delays; snapshots for loading, loaded, partial failure. Live check that the panel
matches `storage quota --all` row for row.

### Phase 4: standing panel

1. Fairshare per account, GPUs against the cap.
2. 7-day efficiency through the jobscope library, with the window configurable.
3. Degrade to fairshare alone if jobscope raises, saying so on the panel.

Verification: unit tests against a stubbed jobscope; snapshot of the degraded
state; live comparison against `account fairshare` and `jobs scope -D 7`.

### Phase 5: actions

1. Confirmation modal, defaulting to No, naming the job.
2. Wire `c`, `h`, `H`, `q` to the existing command functions.
3. Read-only keys `l`, `f`, `w`, `s`, `y`.
4. Result banner: what was done, or the error verbatim.

Verification: Pilot tests asserting the modal appears, that `esc` and No leave
the command function uncalled, and that Yes calls it exactly once with the right
job id. Every mutating test uses a stubbed command function. One live end to end
on a throwaway job of my own, submitted and canceled deliberately.

### Phase 6: polish

1. `--interval` and `--plain`. Done: `--plain` was there from phase 0, and
   `-i/--interval` is new. See item 5, which asked for the same flag.
2. Color that works on light and dark terminals, and with `NO_COLOR`. Done: the
   emphasis colors are ANSI names, which Textual maps through a palette chosen for
   the theme's lightness, so the share warning is #fd971f on the dark theme and
   #cb9000 on the light one rather than one hex value that is wrong on one of them.
   A `--theme` flag picks between them, since the app paints its own background and
   the terminal cannot be asked. Under `NO_COLOR` Textual maps every color to its
   luminance, which put the alarm red at a darker gray than the dim label beside
   it: the emphasis now falls back to bold and underline, which that filter leaves
   alone. Snapshots cover the light theme and `NO_COLOR`.
3. Narrow-terminal behavior: below 100 columns the right column moves below the
   jobs panel; below 80, the panels stack. Phase 2 hides the side column below 80
   rather than stacking it, which is the cheap half of this. Done, with one
   breakpoint rather than two: below 80 columns the side column goes underneath
   instead of being hidden, so a narrow terminal loses the arrangement rather than
   the quotas. The 100-column step was dropped deliberately. Moving the panel at 100
   and stacking it again at 80 changes the layout twice inside twenty columns, and
   the panel is beside the jobs table down to 80 without either one losing a
   heading, so there is nothing for the first move to fix.

   Stacking left the jobs panel two thirds of the height it had, which is what
   exposed the detail pane's row budget being a constant: it claimed five rows of a
   pane that had two and left two rows of a pane that had seven unused. The budget
   is now the layout's own arithmetic, it covers the plain detail as well as a read,
   and it is checked against the painted frame at every size.
4. Give a jobs column no more width than its widest value needs. Phase 2 shares
   spare width round by round against a per-column ceiling, so at 100 columns ID
   takes 18 for a 9-character id while NODE is cut to 9 from 47. Capping growth at
   the widest value in the current rows spends that width where it is read,
   at the cost of columns that shift when the data does. Done: at 100 columns ID
   now takes 12, its minimum, and PART and NODE 13 each. Width left over once every
   column holds its widest value is unspent rather than padding the columns out.
5. A `--days` flag for the standing window, which Phase 4 made a keyword argument
   but nothing passes, and a `--interval` for the jobs timer. Done: both, as
   `-d/--days` and `-i/--interval`, the flag names the other commands already use.
   The interval has a floor of two seconds, since every tick is a controller query
   and `r` refreshes on demand.
6. Show the share of GPU-hours that went unused. Phase 4 reports a median
   utilization, which is honest but not the figure that changes behavior: over the
   caller's last week, 88% of the GPU-hours they held were idle. Elapsed and
   AllocTRES are already read and discarded, so this needs no new query. Done: a
   fifth line on the standing panel, weighted by how long each job held its GPUs and
   carrying its own coverage, since 21 of this caller's 49 GPU jobs are all that
   record utilization. Checked against the same figure computed independently off
   sacct: 88% of 34 GPU-hours. The panel's five facts now fill its five rows, so the
   reading mark went to the border title alone.

7. The panel heights over-commit a short terminal. Done: the banner now takes no
   room until it has something to say, which moved the floor from 20 rows to 18,
   and budgeting the pane from the height the panel actually has moved it to 15 at
   every width rather than at 80 columns and up. Below 15 rows the whole of the
   pane's region is its border, so no budget inside it can help.

   The floor is 15 rows while the banner is silent and 17 once it has spoken, and
   only below 80 columns, where the panels stack. The banner's row comes out of the
   panels and nothing takes it back, so pressing `y` or acting on a job moves the
   floor for the rest of the session. Both figures are measured across every width
   from 30 to 200 and parametrized in the suite. The remaining cost is the standing
   panel's own height on a terminal that short.

Docs are deliberately not part of Phase 6. The dashboard gets a review from the
user first, and whatever that changes would make documentation written now wrong.
`docs/commands/me.md`, the README row and the command index come after it, as
their own piece of work.

Verification: snapshots at 70, 80, 100, 120, 130 and 160 columns, a light-theme
snapshot and a `NO_COLOR` one. The read guarantee is swept over every width from 30
to 300 against the painted frame rather than the widget's own state. The resize
harness drives the real app through a walk of sizes and checks each column against
the widest value painted in it, which is the property item 4 added; run against the
old behavior it reports the over-allocation, so the check can see what it is for.
The doc audit from `CONTRIBUTING.md` step 7 belongs to the documentation work that
follows the user's review, not here.

### Phase 7: a menu on the selected job

The keys stay. This adds a way in for anyone who does not know them yet.

1. Enter on a row opens a modal menu of everything the keys do to that job, with
   cancel selected. Up and down move, Enter chooses, escape closes. Each row shows
   its key, so the menu teaches the shortcut rather than replacing it.
2. The mutating four keep their confirmation, so choosing cancel asks first and the
   answer still defaults to No. Three presses of Enter therefore land on No rather
   than canceling a job. The read-only entries run at once, having nothing to
   confirm.
3. Every entry is offered whatever the job's state. Slurm refuses what does not
   apply, and the planner already says why in words; hiding an entry would leave a
   reader wondering where it went.
4. The menu acts on the job it named, not on whatever the cursor is on when it
   closes, which is the same rule the confirmation follows.
5. The menu, the help overlay and the bindings come from one table, so an action
   cannot appear in one and go missing from the others.

Verification: Pilot tests for the default selection, for up and down, for escape
running nothing, and for Yes running once with the right id; a test that moving the
cursor while the menu is open does not change its target; a test that the three
lists agree; snapshots at 100x30 and 46x18.

## Testing strategy

The honest risk here is that a TUI becomes a large untested surface. `monitor.py`
sits at 38% coverage for exactly that reason and is the weakest module in the
badge we just published. Three layers keep that from repeating.

1. **Data layer, plain unit tests.** Every panel's data function is a pure
   function of stubbed `process.probe` output, tested without Textual. This is
   where the parsing, thresholds, and failure handling are covered, and it should
   be the bulk of the lines.
2. **Behavior, Textual Pilot.** `async with app.run_test() as pilot` drives real
   keypresses and asserts on widget state: selection moves, the modal opens,
   canceling does not call the command, refresh restarts the worker.
3. **Appearance, snapshots.** `pytest-textual-snapshot` stores an SVG per state.
   A diff is a review artifact rather than a guess, which is the closest thing to
   visual inspection that CI can hold.

Every test runs with no Slurm binary on `PATH`. Verified by running the suite
against a shim directory holding only coreutils, the way CI sees it. A test that
reaches a live scheduler passes on a login node and fails in CI.

Coverage target: the TUI package at or above the package average, currently 88%.
If a phase would drop it, the phase is not done.

## Visual inspection

Snapshots catch regressions but not ugliness. Once per phase, on a real login
node, in a real terminal:

1. Run it at 80, 120 and 200 columns, and at 24 and 50 rows.
2. Run it in a light terminal and a dark one.
3. Run it with `NO_COLOR=1`.
4. Run it over a slow ssh link and confirm the redraw is not visibly torn.
5. Run it with no jobs, with 1 job, and with 40 jobs.
6. Hold `r` down and confirm queries do not stack.
7. Attach the resulting screenshots to the phase's PR.

## Open decisions

- Whether `me` should launch the TUI by default when interactive, as planned
  here, or require `--tui`. The plan takes the first; it is a one-line change.
- Whether the efficiency window default is 7 or 14 days.

## Prerequisite, tracked separately

`storage quota --all` should parallelize its fan-out: 6.9s to 1.2s on the same
data. Worth doing on its own merit, and the storage panel then reuses it rather
than carrying its own copy. Not a blocker for Phase 0 through 2.
