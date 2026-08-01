"""diag gpu-health command."""

import pathlib

import click

from clustertool import gpuhealth
from clustertool.grouping import keywords


def _read_capture(path: str) -> tuple[str, str | None]:
    """Read a captured nvidia-smi XML dump and its optional .nvlink companion."""
    xml_text = pathlib.Path(path).read_text()
    companion = pathlib.Path(f"{path}.nvlink")
    nvlink_text = companion.read_text() if companion.exists() else None
    return xml_text, nvlink_text


@keywords("ecc", "throttle", "nvlink", "pcie", "row-remap", "nvidia-smi")
@click.command("gpu-health")
@click.option(
    "--json",
    "json_out",
    is_flag=False,
    flag_value="-",
    default=None,
    metavar="FILE",
    help="Emit a JSON snapshot to FILE (stdout if FILE omitted) instead of the report.",
)
@click.option(
    "--from-xml",
    "from_xml",
    type=click.Path(),
    default=None,
    metavar="FILE",
    help="Analyze a captured 'nvidia-smi -q -x' dump (reads FILE.nvlink if present).",
)
@click.pass_context
def gpu_health(ctx: click.Context, json_out: str | None, from_xml: str | None) -> None:
    """Probe the local node's GPUs for hardware health.

    Runs nvidia-smi on this node and reports a tiered OK/WARN/FAIL verdict per
    GPU and for the node, from ECC and row-remap state, clock throttling, and
    PCIe/NVLink error counters. Read-only and hardware-only; for utilization and
    profiling use jobs scope. Run it on a GPU node, for example inside an salloc
    or srun. The exit code is 0 OK, 1 WARN, 2 FAIL, 3 probe error.

    \b
    Use cases:
      - Confirm a node's GPUs are healthy before or after a large run.
      - Capture a snapshot with --json for triage or a health cron.

    \b
    Inputs:
      --json      Emit a JSON snapshot (to FILE, or stdout) instead of text.
      --from-xml  Analyze a saved 'nvidia-smi -q -x' capture instead of probing.
    """
    try:
        if from_xml:
            xml_text, nvlink_text = _read_capture(from_xml)
        else:
            xml_text, nvlink_text = gpuhealth.collect()
        parsed = gpuhealth.parse_smi_xml(xml_text)
    except (gpuhealth.ProbeError, ValueError, OSError) as exc:
        click.echo(f"gpu-health: error: {exc}", err=True)
        ctx.exit(gpuhealth.EXIT_ERROR)

    nvlink_by_gpu = gpuhealth.parse_nvlink(nvlink_text) if nvlink_text else {}
    if not nvlink_by_gpu:
        nvlink_by_gpu = None
    result = gpuhealth.build_result(parsed, nvlink_by_gpu)

    if json_out is not None:
        payload = gpuhealth.render_json(result)
        if json_out == "-":
            click.echo(payload, nl=False)
        else:
            try:
                pathlib.Path(json_out).write_text(payload)
            except OSError as exc:
                click.echo(f"gpu-health: error: cannot write {json_out}: {exc}", err=True)
                ctx.exit(gpuhealth.EXIT_ERROR)
    else:
        click.echo(gpuhealth.render_text(result))
    ctx.exit(gpuhealth.exit_code(result["verdict"]))
