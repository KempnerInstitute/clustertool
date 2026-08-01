"""diag nvlink command."""

import importlib.resources
import os
import pathlib
import shutil

import click

from clustertool import process
from clustertool.grouping import keywords

_ENV_BASE = {"NCCL_DEBUG": "WARN", "NCCL_IB_DISABLE": "1"}


def _binary_path() -> pathlib.Path:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return pathlib.Path(base) / "clustertool" / "nvlink_saturate_forever"


def _device_list(count: int) -> str:
    """Return the CUDA_VISIBLE_DEVICES value for count GPUs.

    Narrows the allocation Slurm already made rather than replacing it, so a
    saturation benchmark cannot reach a GPU held by another job on a shared node.
    """
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    allowed = visible.split(",") if visible else [str(i) for i in range(count)]
    return ",".join(allowed[:count])


def _detect_gpus() -> int:
    """Return the number of GPUs on this node via nvidia-smi, or 0."""
    try:
        out = process.run(["nvidia-smi", "-L"])
    except process.CommandError:
        return 0
    return sum(1 for line in out.splitlines() if line.strip().startswith("GPU "))


@keywords("bandwidth", "fabric", "interconnect")
@click.command("nvlink")
@click.argument("bytes_per_gpu", type=int, default=2147483648, required=False)
@click.argument("warmup", type=int, default=20, required=False)
@click.argument("report_every", type=int, default=200, required=False)
@click.option(
    "--gpus", type=int, default=None, help="Number of GPUs to use (default: all on the node)."
)
@click.option("--nvcc", default="nvcc", show_default=True, help="nvcc used to build the benchmark.")
@click.option("--rebuild", is_flag=True, help="Force rebuild of the benchmark binary.")
@click.option("--dry-run", is_flag=True, help="Print the build and run commands without running.")
def nvlink(
    bytes_per_gpu: int,
    warmup: int,
    report_every: int,
    gpus: int | None,
    nvcc: str,
    rebuild: bool,
    dry_run: bool,
) -> None:
    """Saturate a node's NVLink fabric with continuous NCCL all-reduce.

    Builds the bundled CUDA/NCCL benchmark (needs nvcc and NCCL on PATH, e.g.
    after 'module load nvhpc') and runs it until Ctrl+C, reporting sustained
    aggregate algorithm bandwidth. Uses every GPU on the node (2-8) unless
    --gpus limits it.

    \b
    Use cases:
      - Stress-test or burn-in the NVLink/NVSwitch fabric on a GPU node.
      - Benchmark sustained multi-GPU collective throughput.

    \b
    Inputs:
      BYTES_PER_GPU  Bytes per GPU (default 2147483648 = 2 GiB).
      WARMUP         Warmup iterations (default 20).
      REPORT_EVERY   Report interval in iterations (default 200).
      --gpus         Number of GPUs to use (default: all on the node).
      --nvcc         nvcc used to build the benchmark.
      --rebuild      Force rebuild of the cached binary.
      --dry-run      Print the build and run commands instead of running.
    """
    source = importlib.resources.files("clustertool") / "data" / "nvlink_saturate_forever.cu"
    binary = _binary_path()
    run_cmd = [str(binary), str(bytes_per_gpu), str(warmup), str(report_every)]

    if dry_run:
        build = [nvcc, "-O3", "-std=c++17", str(source), "-o", str(binary), "-lnccl"]
        detected = _detect_gpus()
        count = gpus or detected
        devices = _device_list(count) if count else "<all GPUs on the node>"
        env = {**_ENV_BASE, "CUDA_VISIBLE_DEVICES": devices}
        env_str = " ".join(f"{key}={value}" for key, value in env.items())
        click.echo("build: " + " ".join(build))
        click.echo("run:   " + env_str + " " + " ".join(run_cmd))
        return

    detected = _detect_gpus()
    if detected == 0:
        raise click.ClickException("no GPUs detected (nvidia-smi); run this on a GPU node")
    count = gpus or detected
    if gpus and gpus > detected:
        raise click.ClickException(f"--gpus {gpus} exceeds the {detected} GPU(s) on this node")
    if count < 2:
        raise click.ClickException(f"need at least 2 GPUs for an NVLink test; using {count}")

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

    env = {**_ENV_BASE, "CUDA_VISIBLE_DEVICES": _device_list(count)}
    click.echo(f"Running NVLink saturation benchmark on {count} GPU(s) (Ctrl+C to stop)...")
    code = process.stream(run_cmd, extra_env=env)
    if code:
        raise click.ClickException(f"the NVLink benchmark exited {code}")
