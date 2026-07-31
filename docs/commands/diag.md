# diag

Cluster diagnostics and benchmarks. Run `clustertools diag --help` to list these commands,
or `clustertools diag <command> --help` for one.

## `diag gpu-health [--json [FILE]] [--from-xml FILE]`

Probe the local node's GPUs for hardware health (via `nvidia-smi`).

Reports a tiered OK/WARN/FAIL verdict per GPU and for the node, from ECC and
row-remap state, clock throttling, and PCIe/NVLink error counters. Read-only and
hardware-only; for utilization and profiling use `jobs scope`. Run it on a GPU
node, for example inside an salloc or srun. The exit code is 0 OK, 1 WARN, 2
FAIL, 3 probe error, so it slots into a health cron or CI check.

**Use cases**
- Confirm a node's GPUs are healthy before or after a large run.
- Capture a snapshot with `--json` for triage, or replay one with `--from-xml`.

**Inputs**
- `--json`: Emit a JSON snapshot (to FILE, or stdout) instead of the report.
- `--from-xml`: Analyze a saved `nvidia-smi -q -x` capture instead of probing
  the node (reads `FILE.nvlink` for NVLink counters when present).

## `diag ib PARTITION... [--parallel N]`

Report nodes with InfiniBand ports DOWN in one or more partitions.

For each partition, ssh to its nodes in parallel and flag any host whose `ip link
show` reports an `ib[0-9]` interface in state DOWN. Unreachable hosts are
skipped.

**Use cases**
- Find nodes with a downed IB link before scheduling a large job.
- Spot-check fabric health across a partition.

**Inputs**
- `PARTITION...`: One or more Slurm partition names (e.g. `kempner_h100`).
- `--parallel`: Maximum parallel ssh checks (default 24).

## `diag ib-affinity [--snapshot FILE]`

Check GPU-to-IB-NIC NUMA affinity (via `nvidia-smi topo -m`).

Each GPU's best link to an InfiniBand NIC should be `NODE`-level or closer; a
`SYS` link (across the CPU interconnect) costs 30-50% of cross-node bandwidth.
Run it on a GPU node. The exit code is 0 all NODE or better, 3 a GPU crosses
NUMA (WARN), 1 a GPU reaches no NIC (FAIL), 2 probe or parse error.

**Use cases**
- Confirm every GPU has a same-NUMA path to an IB NIC before a distributed run.
- Triage a node that gets poor cross-node bandwidth.

**Inputs**
- `--snapshot`: Analyze a saved `ib-snapshot` JSON instead of probing the node.

## `diag io-probe -d TARGET [--size MB] [--meta-files N] [--min-write MBS] [--min-read MBS] [--max-meta-ms MS] [--keep] [--json]`

Probe a filesystem's write/read throughput and metadata latency (not a
benchmark).

Writes a bounded file (fsync included), re-reads it (page-cache assisted), and
times create/stat/delete on a batch of small files, against a scratch
subdirectory of the target. Run it on a compute node (wrap in `srun`) to probe
from there. Set `--min-write`, `--min-read`, or `--max-meta-ms` to turn it into a
pass/fail gate. The exit code is 0 report or pass, 1 a gate missed, 3 setup or IO
error.

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
