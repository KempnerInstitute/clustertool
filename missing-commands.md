# Missing commands: gap analysis

What common Kempner AI Cluster and FASRC tasks ClusterTools does not yet cover,
and the specific commands each would wrap. Sources checked: the Harvard FASRC
documentation (docs.rc.fas.harvard.edu) and the Kempner Computing Handbook
(handbook.eng.kempnerinstitute.harvard.edu), cross-referenced against the tools
actually installed on the login node.

## Current coverage

- `gpu`: usage, avail, monitor-partition, monitor-job, nvtop, pulse
- `jobs`: stats (jobstats), scope (jobscope), violators
- `account`: members
- `nodes`: list
- `storage`: quota, home
- `diag`: ib, nccl, nvlink

The tool is read and diagnostics oriented: thin wrappers over host tools, plus a
few that launch things (nvtop, pulse, diag nccl/nvlink). Gaps below are grouped
by how well they fit that design. Every underlying tool named here is present on
the login node unless noted.

## High priority (read-only, strong fit, frequent)

These are everyday tasks with no equivalent today, and two of them fulfill the
`account` group's stated but unimplemented scope ("membership, limits,
fairshare").

- `jobs list`: your queued and running jobs. Wraps `squeue -u $USER` with
  `-t RUNNING|PENDING` and `-p` filters (or `showq -u`). The single most common
  task and entirely missing; `stats`/`scope`/`violators` never show your current
  jobs. Source: FASRC convenient-slurm-commands; Handbook `myjobs`/`sq` aliases.
- `account fairshare [ACCOUNT]`: your and your lab's fairshare standing and
  priority. Wraps `sshare -u $USER` and `sshare --account=<lab> -a`
  (RawShares/NormShares/RawUsage/FairShare per member). Directly fills the
  "fairshare" half of the account scope; answers "what is my priority". Source:
  FASRC fairshare; Handbook understanding_slurm.
- `jobs show JOBID`: live detail for one job, including the pending reason. Wraps
  `scontrol show job -dd <jobid>`. Complements `jobs stats` (post-hoc) with the
  live "why is it pending / where is it running" view. Source: FASRC
  convenient-slurm-commands; Handbook `jobinfo` alias.
- `jobs why JOBID` (or fold into `jobs show`): priority breakdown for a pending
  job. Wraps `sprio -j <jobid>` plus the `scontrol` pending reason. Answers "why
  is my job not starting and where does it rank". Source: FASRC fairshare.
- `nodes partitions`: partitions you can submit to, their GPU types and features,
  and which schedules fastest. Wraps `spart`, `sinfo -p ... --Format=...`, and
  `find-best-partition`. `gpu avail` shows free GPUs on one partition but there
  is no partition/QOS catalog or picker. Source: FASRC convenient-slurm-commands;
  Handbook advanced_slurm_features.
- `account usage [ACCOUNT]`: cumulative CPU/GPU/TRES-hours and efficiency over a
  period, per lab and member. Wraps `stotal -A <lab> -d` and
  `seff-account -A <lab> -S -E`. Distinct from `gpu usage` (live GPUs in use) and
  from `violators` (org-wide). Source: FASRC fairshare, slurm-stats.

## Medium priority

- `jobs history`: your recent finished jobs (state, elapsed, nodes, exit).
  Wraps `sacct -S <date> -u $USER --format=JobID,JobName,Partition,State,Elapsed,MaxRSS,NodeList`.
  Lighter and faster than `jobs scope` (which is efficiency-focused). Source:
  FASRC convenient-slurm-commands.
- `account limits [ACCOUNT]`: the QOS, partitions, and priority an account or
  user is associated with. Wraps
  `sacctmgr show assoc format=account,user,qos,priority`. Fills the "limits" half
  of the account scope. Source: FASRC convenient-slurm-commands.
- `storage scratch`: netscratch usage against the 50 TB / inode limit, and files
  nearing the 90-day auto-purge. Wraps `quota /n/netscratch/<lab>_lab` plus a
  `find -mtime` age scan. The purge is documented only in prose today and has no
  tool anywhere. Source: FASRC policy-scratch; Handbook understanding_storage.
- `storage usage`: per-member usage table for a lab share. Wraps
  `quota --group-user-usage <group> <path>`. Extends `storage quota` from a
  single number to a who-is-using-what breakdown. Source: FASRC
  checking-quota-and-usage.
- `storage stripe PATH`: show or set Lustre striping for large files. Wraps
  `lfs getstripe` and `lfs setstripe -c <N>` (recommended 8 to 16 for multi-GB
  or TB files). Read side fits cleanly; the set side mutates a directory config.
  Source: Handbook understanding_storage.

## Higher user value but a design shift (these mutate scheduler state)

The tool currently avoids submitting or cancelling work. These are frequent and
useful, but adding them changes its scope, so they are listed separately.

- `gpu session` (or `session`): an interactive GPU allocation with Kempner
  defaults (partition, account, GPUs, CPUs, mem, time). Wraps `salloc --gres=gpu:N ...`.
  The handbook's most repeated action and its recommended `onegpu` alias. Highest
  user value on this page. Source: Handbook job_submission_basics, customizing_bashrc.
- `jobs cancel [JOBID...]`: cancel jobs. Wraps `scancel <id>`, `scancel -u $USER`,
  `scancel -t PENDING -u $USER`. Handbook `killmyjobs` alias. Source: FASRC
  convenient-slurm-commands.
- `jobs submit`: an sbatch helper with Kempner defaults and array/dependency
  support. Wraps `sbatch` (`--wrap`, `--array`, `--dependency`, mail flags).
  Largest scope of the three; templating territory. Source: Handbook
  job_submission_basics, advanced_slurm_features.
- Related, niche: `scontrol hold/release/requeue` as `jobs hold/release/requeue`.

## Likely out of scope (user-owned environment and transfer)

Heavily documented but per-user and better left to the native tools. Listed for
completeness.

- Software environments: `module` (avail/spider/load), `spack`, `mamba`/`conda`,
  `uv`. A thin `module search` is the only mild candidate. Source: FASRC
  modules-intro, spack; Handbook software_module_and_environment_management.
- Data transfer: `rsync`, `scp`, `fpsync`, Globus. The one scriptable candidate
  is the Kempner-documented `srun ... fpsync` pattern for large on-cluster copies
  (could be a `storage sync` or `data transfer` helper). Globus has no CLI here.
  Source: FASRC rsync, globus; Handbook data_transfer.

## Second pass (deeper search)

A follow-up sweep of the FASRC docs, the Kempner Handbook, and the deployed
Kempner `cluster_scripts` bin surfaced these additional gaps.

Implemented in this pass:

- `nodes down [-p PARTITION]`: down and drained nodes with the scheduler's
  reason. Wraps `sinfo -R`. Read-only.
- `nodes load [-f TEXT]`: per-node load and free CPU/GPU/memory. Wraps `lsload`.
  Read-only.
- `nodes reservations`: active reservations on the cluster. Wraps
  `scontrol show reservation`. Read-only.
- `jobs top JOBID`: live resource use (CPU/memory) of a running job's steps.
  Wraps `sstat -a -j <id> --format=...`. Read-only. Only jobs with an active
  step report data.
- `jobs queue PARTITION`: the partition's pending jobs in priority order (where
  you sit). Wraps `showq -o -p <partition>`. Read-only.
- `jobs log JOBID [-f]`: print, or tail, a job's stdout/stderr. Reads the
  `StdOut`/`StdErr` paths from `scontrol show job`. Read-only.
- `jobs script JOBID`: the stored batch script of a submitted job. Wraps
  `sacct -j <id> --batch`. Read-only.
- `jobs list --start`: estimated start time for your pending jobs. Wraps
  `squeue -u $USER --start`. Read-only.
- `diag scheduler`: scheduler cycle, backfill, and queue diagnostics. Wraps
  `sdiag`. Read-only.

Noted but not implemented:

- `account resources` (or a top-level `whoami`): a consolidated "your resources"
  overview (identity, accounts, submit rights, fairshare, QOS limits, storage),
  as in the deployed Kempner `cluster_resources.sh`. High value, but a larger
  native port spanning several tools; a good dedicated follow-up. Read-only.
- `account report`: `sreport` cluster/lab utilization over time. Overlaps
  `account usage` (stotal); skipped to avoid redundancy.
- Recurring jobs: `scrontab -l/-e/-r`. Editor-driven and niche; skipped.
- `find-best-partition` and `scalc` (FASRC helpers): non-standard option parsing
  and an interactive stdin prompt respectively, so neither wraps cleanly. Point
  users to them directly.

## Feasibility notes

- Present on the login node: all stock Slurm CLIs (`squeue`, `sacct`, `sstat`,
  `sprio`, `sinfo`, `scontrol`, `sshare`, `sreport`, `seff`, `sacctmgr`,
  `salloc`, `sbatch`, `srun`, `scancel`, `scrontab`, `sdiag`), the FASRC wrappers
  (`spart`, `scalc`, `showq`, `showq-slurm`, `find-best-partition`, `lsload`,
  `seff-account`, `stotal`, `fpsync`), and `lfs`, `quota`, `jobstats`, `rsync`,
  `module` (lmod), `mamba`, `conda`.
- Not present here: `nvidia-smi` and `dcgmi` (compute nodes only, as expected),
  `spack` (needs `module load`), `globus` CLI (Globus is web/endpoint based).
- `spart`, `scalc`, `stotal`, `seff-account`, `find-best-partition`, `lsload`,
  `showq` are FASRC wrappers, not stock Slurm. Confirm exact flags with
  `<cmd> --help` on a login node before wrapping; the docs show usage patterns
  but not always the full flag set.
- The Kempner helper `free_resources <partition>` (in
  `/n/holylfs06/LABS/kempner_shared/Everyone/cluster_scripts`) overlaps
  `gpu avail`; confirm parity if a partition catalog is added.

## Suggested first additions

If picking a few, the highest value-to-effort are: `jobs list`,
`account fairshare`, `jobs show`, and `nodes partitions`. They are read-only,
fit existing groups, wrap tools that are all present, and cover the most common
"where are my jobs / why are they pending / what can I use" questions that the
tool cannot answer today.

## Sources

FASRC: convenient-slurm-commands, running-jobs, fairshare, slurm-stats,
checking-quota-and-usage, policy-scratch, getting-started-with-fasrc-storage,
modules-intro, spack, rsync, globus-file-transfer, kempner-partitions (all under
https://docs.rc.fas.harvard.edu/kb/).

Kempner Handbook (https://handbook.eng.kempnerinstitute.harvard.edu/):
job_submission_basics, advanced_slurm_features, array_jobs, job_dependencies,
understanding_slurm, fair_use_and_prioritization_policies, customizing_bashrc,
understanding_storage_options, data_transfer, new_user_checklist,
software_module_and_environment_management, using_conda_env, using_uv_env,
handling_dependencies_with_spack, containerization, gpu_profiling.
