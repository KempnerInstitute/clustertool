"""Tests for the CLI commands."""

import shutil

from click.testing import CliRunner

from cluster_tools import process, slurm
from cluster_tools.cli import main


def test_labs_util(monkeypatch):
    monkeypatch.setattr(slurm, "account_cap", lambda: 96)
    monkeypatch.setattr(slurm, "gpu_by_account", lambda partitions: {"acct_a": 8, "acct_b": 4})
    result = CliRunner().invoke(main, ["gpu", "labs-util"])
    assert result.exit_code == 0
    assert "acct_a" in result.output
    assert "TOTAL" in result.output
    assert "12 GPU in use across 2 account(s)" in result.output


def test_labs_util_empty(monkeypatch):
    monkeypatch.setattr(slurm, "account_cap", lambda: 96)
    monkeypatch.setattr(slurm, "gpu_by_account", lambda partitions: {})
    result = CliRunner().invoke(main, ["gpu", "labs-util"])
    assert result.exit_code == 0
    assert "no running GPU jobs" in result.output


def test_lab_util_unknown_account(monkeypatch):
    monkeypatch.setattr(slurm, "account_exists", lambda account: False)
    result = CliRunner().invoke(main, ["gpu", "lab-util", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_lab_util(monkeypatch):
    monkeypatch.setattr(slurm, "account_exists", lambda account: True)
    monkeypatch.setattr(slurm, "account_cap", lambda: 96)
    monkeypatch.setattr(slurm, "priority_partitions", lambda: [])
    monkeypatch.setattr(
        slurm,
        "gpu_rows",
        lambda account, partitions: [("alice", "kempner", 4)] if "kempner" in partitions else [],
    )
    monkeypatch.setattr(slurm, "pending_at_cap", lambda account, partitions: 0)
    result = CliRunner().invoke(main, ["gpu", "lab-util", "acct_a"])
    assert result.exit_code == 0
    assert "account: acct_a" in result.output
    assert "alice" in result.output
    assert "4 / 96 GPU" in result.output


def test_slurm_error_is_clean(monkeypatch):
    def boom():
        raise slurm.SlurmError("'squeue' not found on this host")

    monkeypatch.setattr(slurm, "account_cap", boom)
    result = CliRunner().invoke(main, ["gpu", "labs-util"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_nodes_list(monkeypatch):
    monkeypatch.setattr(
        slurm, "partition_nodes", lambda partition: [("node01", "idle"), ("node02", "mix")]
    )
    result = CliRunner().invoke(main, ["nodes", "list", "kempner_h100"])
    assert result.exit_code == 0
    assert "node01" in result.output
    assert "2 node(s)" in result.output


def test_account_members(monkeypatch):
    monkeypatch.setattr(slurm, "account_exists", lambda account: True)
    monkeypatch.setattr(slurm, "account_members", lambda account: ["alice", "bob"])
    result = CliRunner().invoke(main, ["account", "members", "kempner_dev"])
    assert result.exit_code == 0
    assert "kempner_dev (2)" in result.output
    assert "alice" in result.output
    assert "bob" in result.output


def test_jobs_stats(monkeypatch):
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        return 0

    monkeypatch.setattr(process, "stream", fake_stream)
    result = CliRunner().invoke(main, ["jobs", "stats", "123", "456"])
    assert result.exit_code == 0
    assert captured["cmd"] == ["jobstats", "123", "456"]


def test_storage_quota_lustre(monkeypatch):
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        return 0

    monkeypatch.setattr(process, "stream", fake_stream)
    result = CliRunner().invoke(main, ["storage", "quota", "kempner_dev", "-f", "lustre"])
    assert result.exit_code == 0
    assert captured["cmd"] == ["lfs", "quota", "-hg", "kempner_dev", "/n/holylfs06"]


def test_diag_nccl_not_gpu(monkeypatch):
    monkeypatch.setattr(
        slurm, "node_info", lambda node: {"name": node, "gpus": 0, "partitions": ["shared"]}
    )
    result = CliRunner().invoke(main, ["diag", "nccl", "cpu01"])
    assert result.exit_code != 0
    assert "not a GPU node" in result.output


def test_diag_nccl_dry_run(monkeypatch):
    monkeypatch.setattr(
        slurm,
        "node_info",
        lambda node: {"name": node, "gpus": 4, "partitions": ["kempner_h100"]},
    )
    result = CliRunner().invoke(
        main,
        ["diag", "nccl", "holygpu8a11101", "--binary", "/opt/all_reduce_perf", "--dry-run"],
    )
    assert result.exit_code == 0
    assert "srun" in result.output
    assert "--nodelist=holygpu8a11101" in result.output
    assert "--gpus-per-node=4" in result.output
    assert "--partition=kempner_h100" in result.output
    assert result.output.strip().endswith("/opt/all_reduce_perf -b 8 -e 128M -f 2 -g 4")


def test_diag_nccl_partition_override(monkeypatch):
    monkeypatch.setattr(
        slurm,
        "node_info",
        lambda node: {"name": node, "gpus": 8, "partitions": ["kempner_requeue"]},
    )
    result = CliRunner().invoke(
        main,
        [
            "diag",
            "nccl",
            "gpunode",
            "--binary",
            "/opt/arp",
            "--partition",
            "kempner_h100",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0
    assert "--partition=kempner_h100" in result.output
    assert "--gpus-per-node=8" in result.output


def test_diag_nccl_dry_run_without_binary(monkeypatch):
    monkeypatch.setattr(
        slurm,
        "node_info",
        lambda node: {"name": node, "gpus": 4, "partitions": ["kempner_h100"]},
    )
    monkeypatch.delenv("NCCL_TESTS_PATH", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    result = CliRunner().invoke(main, ["diag", "nccl", "gpunode", "--dry-run"])
    assert result.exit_code == 0
    assert "all_reduce_perf -b 8 -e 128M -f 2 -g 4" in result.output
