"""diag nvlink command."""

import importlib.resources
import os
import pathlib
import shutil

import click

from cluster_tools import process

_ENV = {"CUDA_VISIBLE_DEVICES": "0,1,2,3", "NCCL_DEBUG": "WARN", "NCCL_IB_DISABLE": "1"}


def _binary_path() -> pathlib.Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return pathlib.Path(base) / "cluster-tools" / "nvlink_saturate_forever"


@click.command("nvlink")
@click.argument("bytes_per_gpu", type=int, default=2147483648, required=False)
@click.argument("warmup", type=int, default=20, required=False)
@click.argument("report_every", type=int, default=200, required=False)
@click.option("--nvcc", default="nvcc", show_default=True, help="nvcc used to build the benchmark.")
@click.option("--rebuild", is_flag=True, help="Force rebuild of the benchmark binary.")
@click.option("--dry-run", is_flag=True, help="Print the build and run commands without running.")
def nvlink(
    bytes_per_gpu: int, warmup: int, report_every: int, nvcc: str, rebuild: bool, dry_run: bool
) -> None:
    """Saturate a 4-GPU node's NVLink fabric with continuous NCCL all-reduce.

    Builds the bundled CUDA/NCCL benchmark (needs nvcc and NCCL on PATH, e.g.
    after 'module load nvhpc') and runs it until Ctrl+C, reporting sustained
    aggregate algorithm bandwidth. Requires a node with 4 GPUs.

    \b
    Use cases:
      - Stress-test or burn-in the NVLink/NVSwitch fabric on a GPU node.
      - Benchmark sustained multi-GPU collective throughput.

    \b
    Inputs:
      BYTES_PER_GPU  Bytes per GPU (default 2147483648 = 2 GiB).
      WARMUP         Warmup iterations (default 20).
      REPORT_EVERY   Report interval in iterations (default 200).
      --nvcc         nvcc used to build the benchmark.
      --rebuild      Force rebuild of the cached binary.
      --dry-run      Print the build and run commands instead of running.
    """
    source = importlib.resources.files("cluster_tools") / "data" / "nvlink_saturate_forever_4gpu.cu"
    binary = _binary_path()
    run_cmd = [str(binary), str(bytes_per_gpu), str(warmup), str(report_every)]

    if dry_run:
        build = [nvcc, "-O3", "-std=c++17", str(source), "-o", str(binary), "-lnccl"]
        env = " ".join(f"{key}={value}" for key, value in _ENV.items())
        click.echo("build: " + " ".join(build))
        click.echo("run:   " + env + " " + " ".join(run_cmd))
        return

    if not shutil.which(nvcc):
        raise click.ClickException(
            f"'{nvcc}' not found; load a CUDA/NCCL module (e.g. 'module load nvhpc') or pass --nvcc"
        )
    if rebuild or not binary.exists():
        binary.parent.mkdir(parents=True, exist_ok=True)
        with importlib.resources.as_file(source) as src:
            build = [nvcc, "-O3", "-std=c++17", str(src), "-o", str(binary), "-lnccl"]
            click.echo("Building: " + " ".join(build))
            if process.stream(build) != 0:
                raise click.ClickException("nvcc build failed")
    click.echo("Running NVLink saturation benchmark (Ctrl+C to stop)...")
    code = process.stream(run_cmd, extra_env=_ENV)
    if code:
        raise SystemExit(code)
