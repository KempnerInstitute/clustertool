"""Tests for the site configuration layer."""

import pytest
from click.testing import CliRunner

from clustertool import entry, site, slurm
from clustertool.cli import main


def test_packaged_default_is_kempner():
    data = site._packaged_default()
    assert data["site"]["name"] == "Kempner AI Cluster"
    assert data["partitions"]["requeue"] == "kempner_requeue"


def test_default_accessors():
    assert site.site_name() == "Kempner AI Cluster"
    assert "kempner_h100" in site.base_partitions()
    assert site.requeue_partition() == "kempner_requeue"
    assert site.base_qos() == "kempner_base"
    assert site.default_cap() == 0
    assert site.partition_limits()["kempner_h100"] == (24, 360000)
    assert site.partition_limits()["kempner"] == (16, 240000)
    assert site.gpu_type_partition()["h100"] == "kempner_h100"
    assert ("H100", "h100") in site.gpu_status_types()
    assert site.priority_pattern() == "kempner.*priority"
    assert site.roster_partition() == "kempner"
    assert site.lab_account_prefix() == "kempner_"
    assert site.path_prefix() == "/n"
    assert site.scratch_path() == "/n/netscratch"
    assert site.scratch_purge_days() == 90
    assert site.slurm_group_prefix() == "slurm_group_"
    assert site.qos_cluster() == "odyssey"
    assert site.qos_grant_fairshare() == "parent"
    assert site.qos_grant_strip() == ["normal"]
    assert site.storage_lab_roots()[0] == "/n/netscratch"
    assert "kempnerpulse" in site.pulse_remote_venv()


def test_deep_merge_is_recursive():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    over = {"a": {"y": 20, "z": 30}}
    merged = site._deep_merge(base, over)
    assert merged == {"a": {"x": 1, "y": 20, "z": 30}, "b": 3}
    assert base == {"a": {"x": 1, "y": 2}, "b": 3}


def test_load_file_deep_merges_over_default(tmp_path):
    cfg = tmp_path / "site.toml"
    cfg.write_text(
        "[site]\n"
        'name = "Della"\n'
        "[partitions]\n"
        'base = ["gpu", "gpu-shared"]\n'
        'requeue = "all"\n'
        "[partitions.limits.gpu]\n"
        "cpus_per_gpu = 8\n"
        "mem_per_gpu_mb = 100000\n"
        "[storage]\n"
        'path_prefix = "/scratch"\n'
    )
    data = site.load_file(cfg)
    assert data["site"]["name"] == "Della"
    assert data["partitions"]["base"] == ["gpu", "gpu-shared"]
    assert data["partitions"]["requeue"] == "all"
    assert data["partitions"]["limits"]["gpu"] == {"cpus_per_gpu": 8, "mem_per_gpu_mb": 100000}
    assert data["storage"]["path_prefix"] == "/scratch"
    assert data["qos"]["base"] == "kempner_base"
    assert data["storage"]["scratch_purge_days"] == 90
    assert data["gpu_types"]["h100"] == "kempner_h100"


def test_slurm_constants_are_sourced_from_site():
    assert slurm.BASE_PARTITIONS == site.base_partitions()
    assert slurm.REQUEUE_PARTITION == site.requeue_partition()
    assert slurm.PARTITION_LIMITS == site.partition_limits()
    assert slurm.GPU_TYPE_PARTITION == site.gpu_type_partition()
    assert slurm.DEFAULT_CAP == site.default_cap()
    assert slurm.BASE_QOS == site.base_qos()


def test_unknown_slurm_attribute_still_raises():
    missing = "NOT_A_REAL_CONSTANT"
    with pytest.raises(AttributeError):
        getattr(slurm, missing)


def test_commands_honor_a_different_site(monkeypatch):
    monkeypatch.setattr(site, "base_partitions", lambda: ("alpha", "beta"))
    monkeypatch.setattr(slurm, "partition_gpu_util", lambda p: (10, 0, 10, 5, 50.0))
    result = CliRunner().invoke(main, ["gpu", "util"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output


def test_bad_toml_raises_config_error(tmp_path):
    bad = tmp_path / "site.toml"
    bad.write_text("not valid toml [[[\n")
    with pytest.raises(site.ConfigError) as excinfo:
        site.load_file(bad)
    assert str(bad) in str(excinfo.value)


def test_env_var_pointing_at_missing_file_is_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv(site.ENV_VAR, str(tmp_path / "absent.toml"))
    with pytest.raises(site.ConfigError) as excinfo:
        site.load()
    assert site.ENV_VAR in str(excinfo.value)


def test_unreadable_config_raises_config_error(tmp_path):
    with pytest.raises(site.ConfigError):
        site.load_file(tmp_path / "does-not-exist.toml")


def test_entry_reports_config_error_without_traceback(monkeypatch):
    """The guard turns an unusable config into one line, not an import traceback."""

    def boom():
        raise site.ConfigError("site config /x/site.toml is not valid TOML: bad key")

    monkeypatch.setattr(entry, "_load_main", boom)
    with pytest.raises(SystemExit) as excinfo:
        entry.run()
    assert "not valid TOML" in str(excinfo.value)
    assert "clustertool: error:" in str(excinfo.value)


def test_entry_runs_the_cli_when_the_config_loads(monkeypatch):
    called = []
    monkeypatch.setattr(entry, "_load_main", lambda: lambda: called.append(1))
    entry.run()
    assert called == [1]


def test_gpu_types_replace_rather_than_merge(tmp_path):
    """A site inventory must not keep the packaged entries it did not name."""
    cfg = tmp_path / "site.toml"
    cfg.write_text('[gpu_types]\nv100 = "gpu"\n')
    merged = site.load_file(cfg)
    assert merged["gpu_types"] == {"v100": "gpu"}


def test_partition_limits_replace_rather_than_merge(tmp_path):
    cfg = tmp_path / "site.toml"
    cfg.write_text("[partitions.limits.gpu]\ncpus_per_gpu = 8\nmem_per_gpu_mb = 100000\n")
    merged = site.load_file(cfg)
    assert list(merged["partitions"]["limits"]) == ["gpu"]


def test_settings_tables_still_merge(tmp_path):
    """Overriding one tool must leave the others at their packaged values."""
    cfg = tmp_path / "site.toml"
    cfg.write_text('[tools]\nqueue = "myqueue"\n')
    merged = site.load_file(cfg)
    assert merged["tools"]["queue"] == "myqueue"
    assert merged["tools"]["partitions"] == "spart"
    assert merged["tools"]["quota"] == "quota"


def test_unnamed_inventory_keeps_the_packaged_default(tmp_path):
    """A site that says nothing about gpu_types still gets the packaged profile."""
    cfg = tmp_path / "site.toml"
    cfg.write_text('[site]\nname = "Example"\n')
    merged = site.load_file(cfg)
    assert "h100" in merged["gpu_types"]


def test_gpu_types_keys_are_lower_cased(tmp_path):
    """TOML allows an upper-case bare key; the type lookup is lower-case."""
    cfg = tmp_path / "site.toml"
    cfg.write_text('[gpu_types]\nV100 = "gpu"\nL40S = "gpu_big"\n')
    monkey = site._cache
    try:
        site._cache = site.load_file(cfg)
        assert site.gpu_type_partition() == {"v100": "gpu", "l40s": "gpu_big"}
    finally:
        site._cache = monkey
