"""Site configuration.

Externalizes cluster-specific values (partition names, per-GPU limits, GPU type
map, account conventions, storage paths) so the commands stay portable. Values
load from the first file found among $CLUSTERTOOL_SITE_CONFIG, the user config,
then the system config, deep-merged over the packaged default.
"""

import os
import shutil
from importlib import resources
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ENV_VAR = "CLUSTERTOOL_SITE_CONFIG"
USER_PATH = Path.home() / ".config" / "clustertool" / "site.toml"
SYSTEM_PATH = Path("/etc/clustertool/site.toml")

_cache: dict | None = None


def _packaged_default() -> dict:
    """Return the packaged default configuration (the Kempner profile)."""
    text = (
        resources.files("clustertool")
        .joinpath("data", "site.default.toml")
        .read_text(encoding="utf-8")
    )
    return tomllib.loads(text)


def _deep_merge(base: dict, override: dict) -> dict:
    """Return a recursive merge of override onto base, mutating neither."""
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _discover() -> Path | None:
    """Return the first existing site config file, or None for the default."""
    candidates = []
    env = os.environ.get(ENV_VAR)
    if env:
        candidates.append(Path(env))
    candidates += [USER_PATH, SYSTEM_PATH]
    return next((path for path in candidates if path.is_file()), None)


def load_file(path) -> dict:
    """Return the packaged default deep-merged with the config file at path."""
    override = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return _deep_merge(_packaged_default(), override)


def load() -> dict:
    """Return the active configuration (default, overridden by a site file)."""
    found = _discover()
    return _packaged_default() if found is None else load_file(found)


def config() -> dict:
    """Return the cached active configuration."""
    global _cache
    if _cache is None:
        _cache = load()
    return _cache


def reload() -> None:
    """Clear the cached configuration so the next access reloads it."""
    global _cache
    _cache = None


def slurm_group_prefix() -> str:
    """Return the prefix of Slurm pseudo-groups that map to priority tiers."""
    return str(config()["site"]["slurm_group_prefix"])


def site_name() -> str:
    """Return the human-readable site name."""
    return str(config()["site"]["name"])


def base_partitions() -> tuple[str, ...]:
    """Return the base GPU partitions that count toward the account cap."""
    return tuple(config()["partitions"]["base"])


def requeue_partition() -> str:
    """Return the partition that spans every GPU node."""
    return str(config()["partitions"]["requeue"])


def priority_pattern() -> str:
    """Return the regex identifying priority partitions."""
    return str(config()["partitions"]["priority_pattern"])


def base_qos() -> str:
    """Return the QoS whose MaxTRESPA encodes the per-account GPU cap."""
    return str(config()["qos"]["base"])


def default_cap() -> int:
    """Return the fallback per-account GPU cap."""
    return int(config()["qos"]["default_cap"])


def qos_cluster() -> str:
    """Return the Slurm cluster name the admin qos commands operate on."""
    return str(config()["qos"]["cluster"])


def qos_grant_fairshare() -> str:
    """Return the fairshare set on a new association created by qos grant."""
    return str(config()["qos"]["grant_fairshare"])


def qos_grant_strip() -> list[str]:
    """Return the QoS names stripped from a user's list on a priority grant."""
    return [str(name) for name in config()["qos"]["grant_strip"]]


def partition_limits() -> dict[str, tuple[int, int]]:
    """Return {partition: (cpus_per_gpu, mem_per_gpu_mb)} enforced limits."""
    limits = config()["partitions"]["limits"]
    return {name: (int(v["cpus_per_gpu"]), int(v["mem_per_gpu_mb"])) for name, v in limits.items()}


def gpu_type_partition() -> dict[str, str]:
    """Return the GPU type to partition map used by sessions and job builder."""
    return dict(config()["gpu_types"])


def gpu_status_types() -> list[tuple[str, str]]:
    """Return [(label, node_feature)] GPU types in display order."""
    return [(t["label"], t["feature"]) for t in config()["gpu_status"]["types"]]


def roster_partition() -> str:
    """Return the partition whose AllowAccounts enumerates lab accounts."""
    return str(config()["accounts"]["roster_partition"])


def lab_account_prefix() -> str:
    """Return the prefix identifying lab accounts."""
    return str(config()["accounts"]["lab_prefix"])


def path_prefix() -> str:
    """Return the prefix a bare filesystem name expands to."""
    return str(config()["storage"]["path_prefix"])


def storage_lab_roots() -> list[str]:
    """Return the storage roots probed by storage quota --all for lab directories."""
    return [str(root) for root in config()["storage"]["lab_roots"]]


def pulse_remote_venv() -> str:
    """Return the remote venv that gpu pulse --node activates, or '' if unset."""
    return str(config().get("pulse", {}).get("remote_venv", ""))


def scratch_path() -> str:
    """Return the default networked scratch path."""
    return str(config()["storage"]["scratch"])


def scratch_purge_days() -> int:
    """Return the scratch auto-purge age in days."""
    return int(config()["storage"]["scratch_purge_days"])


def tool(key: str) -> str:
    """Return the configured binary name for a site tool."""
    return str(config()["tools"][key])


def tool_available(key: str) -> bool:
    """Return True if the configured binary for a site tool is on PATH."""
    return shutil.which(tool(key)) is not None


def disabled_commands() -> list[str]:
    """Return the command paths a site has turned off."""
    return list(config().get("commands", {}).get("disable", []))
