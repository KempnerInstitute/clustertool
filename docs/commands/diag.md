# diag

Run cluster diagnostics. Run `clustertools diag --help` to list these commands,
or `clustertools diag <command> --help` for one.

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
