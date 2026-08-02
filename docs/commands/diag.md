# diag

Cluster diagnostics and benchmarks. Run `clustertool diag --help` to list these commands,
or `clustertool diag <command> --help` for one.

## `diag gpu-health [--json [FILE]] [--from-xml FILE]`

Probe the local node's GPUs for hardware health (via `nvidia-smi`).

Reports a tiered OK/WARN/FAIL verdict per GPU and for the node, from ECC and
row-remap state, clock throttling, and PCIe/NVLink error counters. Read-only and
hardware-only; for utilization and profiling use `jobs scope`. Run it on a GPU
node, for example inside an salloc or srun. The exit code is 0 OK, 1 WARN, 3
probe error, 4 FAIL, so it slots into a health cron or CI check. 2 is unused throughout the diagnostics, since click exits 2 on a usage error.

**Use cases**
- Confirm a node's GPUs are healthy before or after a large run.
- Capture a snapshot with `--json` for triage, or replay one with `--from-xml`.

**Inputs**
- `--json`: Emit a JSON snapshot (to FILE, or stdout) instead of the report.
- `--from-xml`: Analyze a saved `nvidia-smi -q -x` capture instead of probing
  the node (reads `FILE.nvlink` for NVLink counters when present).

## `diag ib PARTITION... [--parallel N]`

Report nodes whose InfiniBand ports are not ACTIVE, in one or more partitions.

For each partition, ssh to its nodes in parallel and read each InfiniBand port's
state from `/sys/class/infiniband`, which is what the RDMA stack itself reports.
A port whose link layer is Ethernet is not InfiniBand and is not counted.

A host that could not be reached is reported as unreachable rather than counted
as healthy, so a run that contacted nothing cannot read as a clean fabric.

Needs ssh to every node in the partition, not just the ones running your jobs.
Where node login is gated on having an allocation, as `pam_slurm_adopt` does,
only staff can reach the whole partition and an ordinary user sees every host
unreachable.

Exit codes: 0 every reachable host has all InfiniBand ports ACTIVE, 1 some hosts
were unreachable or have no InfiniBand ports, 3 a partition does not exist, 4 at
least one port is not ACTIVE. 2 is unused throughout the diagnostics, since click exits 2 on a usage error.

**Use cases**
- Find nodes with a downed IB link before scheduling a large job.
- Spot-check fabric health across a partition.

**Inputs**
- `PARTITION...`: One or more Slurm partition names.
- `--parallel`: Maximum parallel ssh checks (default 24).

## `diag ib-affinity [--snapshot FILE]`

Check GPU-to-IB-NIC NUMA affinity (via `nvidia-smi topo -m`).

Each GPU's best link to an InfiniBand NIC should be `NODE`-level or closer; a
`SYS` link crosses the CPU interconnect, which can cost a large fraction of the bandwidth the NIC could otherwise reach.
Run it on a GPU node. The exit code is 0 all NODE or better, 1 a GPU crosses
NUMA (WARN), 3 probe or parse error, 4 a GPU reaches no NIC (FAIL). 2 is unused throughout the diagnostics, since click exits 2 on a usage error.

**Use cases**
- Confirm every GPU has a same-NUMA path to an IB NIC before a distributed run.
- Triage a node that gets poor cross-node bandwidth.

**Inputs**
- `--snapshot`: Analyze a saved `ib-snapshot` JSON instead of probing the node.

## `diag ib-counters BEFORE AFTER`

Diff two `ib-snapshot` files for InfiniBand error-counter growth.

Compares the per-port counters in a BEFORE and AFTER snapshot (bracket a run with
two `diag ib-snapshot` captures). Benign traffic counters are shown but ignored;
growth on an error-class counter (symbol errors, discards, link recoveries, ...)
means the fabric hiccupped under load. The exit code is 0 no error growth, 3 a
file could not be read, 4 an error-class counter advanced. 2 is unused throughout the diagnostics, since click exits 2 on a usage error.

**Use cases**
- Confirm a benchmark did not degrade the fabric.
- Localize which port grew errors during a run.

**Inputs**
- `BEFORE`: The earlier `ib-snapshot` JSON.
- `AFTER`: The later `ib-snapshot` JSON.

## `diag ib-snapshot [OUTPUT]`

Capture a node's IB and GPU topology and counters as a JSON snapshot (via
`nvidia-smi`, `ibdev2netdev`, and sysfs).

Probes GPUs, the NVLink status, the GPU-to-NIC topology matrix, and each
InfiniBand HCA's port state, rate, and error counters into one JSON file, for
forensic comparison and for diffing across a run. Read-only. Run it on the node.
Write to OUTPUT, or print to stdout. Feed two snapshots to a counter diff, or one
to `diag ib-affinity --snapshot`.

Any probe that could not run is recorded under `probe_errors`, so an empty field
means the node genuinely had nothing to report rather than that the tool was
missing or timed out. Run on a login node with no GPUs, for instance, the snapshot
reports `{"nvidia-smi": "not installed"}` there rather than an unexplained empty
GPU list.

**Use cases**
- Capture a node's fabric state when it goes slow, for later comparison.
- Bracket a benchmark with two snapshots to check for error-counter growth.

**Inputs**
- `OUTPUT`: File to write the JSON snapshot to (default: stdout).

## `diag ib-verify GOLDEN [--current FILE] [--save-golden] [--strict] [--json]`

Compare a node's IB/GPU snapshot against a golden one and report drift (via
`ib-snapshot`).

Diffs the current snapshot (a fresh probe, or `--current FILE`) against the
GOLDEN snapshot. Identity fields are compared (GPU inventory, HCA port state and
rate, netdev mapping, topology); volatile fields (counters, temps) are ignored.
Driver, kernel, and CUDA changes are informational and count as drift only with
`--strict`. Bless a baseline with `--save-golden`. The exit code is 0 match, 3
setup error, 4 drift. 2 is unused throughout the diagnostics, since click exits 2 on a usage error.

**Use cases**
- Detect a swapped or downgraded HCA, or a changed link rate, on a node.
- Bless a known-good node with `--save-golden`, then re-check it over time.

**Inputs**
- `GOLDEN`: The golden snapshot file to compare against (or write).
- `--current`: Compare an existing snapshot instead of probing the node.
- `--save-golden`: Save the current snapshot as GOLDEN and exit.
- `--strict`: Count driver/kernel/CUDA drift as drift too.
- `--json`: Emit the findings as JSON.

## `diag io-probe -d TARGET [--size MB] [--meta-files N] [--min-write MBS] [--min-read MBS] [--max-meta-ms MS] [--keep] [--json]`

Probe a filesystem's write/read throughput and metadata latency (not a
benchmark).

Writes a bounded file (fsync included), re-reads it after asking the kernel to
drop its page cache, and times create/stat/delete on a batch of small files,
against a scratch subdirectory of the target. Where the cache cannot be dropped
the report says so, and the read figure is then memory rather than storage. Run it on a compute node (wrap in `srun`) to probe
from there. Set `--min-write`, `--min-read`, or `--max-meta-ms` to turn it into a
pass/fail gate. The exit code is 0 report or pass, 3 setup or IO error, 4 a gate
missed. 2 is unused throughout the diagnostics, since click exits 2 on a usage error.

**Use cases**
- Spot-check whether a filesystem is responsive from a node.
- Gate a job on minimum IO throughput in a health check.

**Inputs**
- `-d, --dir`: Directory to probe (a scratch subdir is created inside).
- `--size`: Sequential file size in MB (default 256).
- `--meta-files`: Metadata batch size (default 100).
- `--min-write` / `--min-read` / `--max-meta-ms`: Gate thresholds.
- `--keep`: Keep the scratch subdir.
- `--json`: Emit the structured result as JSON.

## `diag nccl [--python PY] [--timeout S] [--dry-run]`

Run a multi-node FSDP NCCL sanity check inside a Slurm allocation.

Add this to your srun/sbatch submission script (in place of a bare
nccl_check.sh). It launches a small PyTorch FSDP job across all tasks to confirm
NCCL works. Requires torch in the environment (activate your env, or pass
`--python /path/to/python`).

**Use cases**
- Verify NCCL and network health before a large distributed run.

**Inputs**
- `--python`: Python interpreter with torch (default: python).
- `--timeout`: Seconds before the check is aborted (default 300).
- `--dry-run`: Print the srun command instead of running it.

## `diag nvlink [BYTES_PER_GPU] [WARMUP] [REPORT_EVERY] [--gpus N] [--nvcc PATH] [--rebuild] [--dry-run]`

Saturate a node's NVLink fabric with continuous NCCL all-reduce.

Builds the bundled CUDA/NCCL benchmark (needs nvcc and NCCL on PATH, e.g. after
`module load nvhpc`) and runs it until Ctrl+C, reporting sustained aggregate
algorithm bandwidth. Uses every GPU on the node (2-8) unless `--gpus` limits it.

**Use cases**
- Stress-test or burn-in the NVLink/NVSwitch fabric on a GPU node.
- Benchmark sustained multi-GPU collective throughput.

**Inputs**
- `BYTES_PER_GPU`: Bytes per GPU (default 2147483648 = 2 GiB).
- `WARMUP`: Warmup iterations (default 20).
- `REPORT_EVERY`: Report interval in iterations (default 200).
- `--gpus`: Number of GPUs to use (default: all on the node).
- `--nvcc`: nvcc used to build the benchmark.
- `--rebuild`: Force rebuild of the cached binary.
- `--dry-run`: Print the build and run commands instead of running.

## `diag scheduler`

Show Slurm scheduler diagnostics (via `sdiag`): scheduling cycle times, backfill
statistics, and queue depth.

**Use cases**
- Check scheduler health and backfill activity when jobs are slow to start.
