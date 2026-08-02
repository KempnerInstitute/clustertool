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


def _device_list(count: int, allow_every_gpu: bool) -> list[str]:
    """Return the devices to run on, narrowed to the allocation where there is one.

    CUDA_VISIBLE_DEVICES is what Slurm sets for the job step, so narrowing it
    keeps a saturation benchmark off a GPU another job holds on a shared node.
    With the variable unset there is no allocation to narrow, and the fallback of
    every GPU nvidia-smi can see is only safe where the cgroup already restricts
    that, so it takes --all-gpus rather than being assumed.
    """
    visible = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    if visible:
        return [dev for dev in visible.split(",") if dev][:count]
    if not allow_every_gpu:
        raise click.ClickException(
            "CUDA_VISIBLE_DEVICES is not set, so there is no allocation to narrow "
            "and this would load every GPU on the node, including any another job "
            "is using. Run it inside a job step, or pass --all-gpus if you mean to "
            "take the whole node"
        )
    return [str(i) for i in range(count)]


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
    "--gpus",
    type=click.IntRange(min=2),
    default=None,
    help="Number of GPUs to use (default: every GPU in the job step).",
)
@click.option("--nvcc", default="nvcc", show_default=True, help="nvcc used to build the benchmark.")
@click.option("--rebuild", is_flag=True, help="Force rebuild of the benchmark binary.")
@click.option(
    "--all-gpus",
    is_flag=True,
    help="Outside a job step, use every GPU on the node rather than refusing.",
)
@click.option("--dry-run", is_flag=True, help="Print the build and run commands without running.")
def nvlink(
    bytes_per_gpu: int,
    warmup: int,
    report_every: int,
    gpus: int | None,
    nvcc: str,
    rebuild: bool,
    all_gpus: bool,
    dry_run: bool,
) -> None:
    """Saturate a node's NVLink fabric with continuous NCCL all-reduce.

    Builds the bundled CUDA/NCCL benchmark (needs nvcc and NCCL on PATH, e.g.
    after 'module load nvhpc') and runs it until Ctrl+C, reporting sustained
    aggregate algorithm bandwidth. Under sbatch there is no Ctrl+C: the benchmark
    holds the allocation at full power until scancel, which it handles cleanly, or
    the time limit.

    Runs on the GPUs of the job step it is in, read from CUDA_VISIBLE_DEVICES,
    narrowed further by --gpus. Outside a job step there is no allocation to
    narrow, so it refuses rather than loading GPUs another job may hold; --all-gpus
    says to take the whole node anyway. At least 2 GPUs are needed and there is no
    upper bound.

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
      --all-gpus     Outside a job step, take every GPU on the node.
      --dry-run      Print the build and run commands instead of running.
    """
    source = importlib.resources.files("clustertool") / "data" / "nvlink_saturate_forever.cu"
    binary = _binary_path()
    run_cmd = [str(binary), str(bytes_per_gpu), str(warmup), str(report_every)]

    if dry_run:
        build = [nvcc, "-O3", "-std=c++17", str(source), "-o", str(binary), "-lnccl"]
        detected = _detect_gpus()
        count = gpus or detected
        devices = ",".join(_device_list(count, all_gpus)) if count else "<none detected>"
        env = {**_ENV_BASE, "CUDA_VISIBLE_DEVICES": devices}
        env_str = " ".join(f"{key}={value}" for key, value in env.items())
        click.echo("build: " + " ".join(build))
        click.echo("run:   " + env_str + " " + " ".join(run_cmd))
        return

    detected = _detect_gpus()
    if detected == 0:
        raise click.ClickException("no GPUs detected (nvidia-smi); run this on a GPU node")
    if gpus and gpus > detected:
        raise click.ClickException(f"--gpus {gpus} exceeds the {detected} GPU(s) on this node")
    devices = _device_list(gpus or detected, all_gpus)
    count = len(devices)
    if count < 2:
        raise click.ClickException(
            f"need at least 2 GPUs for an NVLink test; this step has {count}"
        )

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

    env = {**_ENV_BASE, "CUDA_VISIBLE_DEVICES": ",".join(devices)}
    click.echo(f"Running NVLink saturation benchmark on {count} GPU(s) (Ctrl+C to stop)...")
    code = process.stream(run_cmd, extra_env=env)
    if code:
        raise click.ClickException(f"the NVLink benchmark exited {code}")
