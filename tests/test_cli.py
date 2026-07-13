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


def test_gpu_avail(monkeypatch):
    monkeypatch.setattr(
        slurm, "partition_nodes", lambda p: [("n1", "mix"), ("n2", "idle"), ("n3", "alloc")]
    )
    free = {"n1": (2, 40, 500.0), "n2": (4, 90, 1000.0), "n3": (0, 0, 0.0)}
    monkeypatch.setattr(slurm, "node_free_resources", lambda node: free[node])
    result = CliRunner().invoke(main, ["gpu", "avail", "kempner_h100"])
    assert result.exit_code == 0
    assert "n1" in result.output
    assert "n2" in result.output
    assert "n3" not in result.output
    assert result.output.index("n2") < result.output.index("n1")


def test_jobs_violators(monkeypatch):
    jobs = [
        ("101", "alice", 200, 8, 100000),
        ("102", "bob", 96, 4, 2000000),
        ("103", "carol", 96, 4, 1440000),
        ("104", "dave", 400, 0, 100000),
    ]
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: jobs)
    result = CliRunner().invoke(main, ["jobs", "violators", "kempner_h100"])
    assert result.exit_code == 0
    assert "101" in result.output
    assert "102" in result.output
    assert "103" not in result.output
    assert "104" not in result.output
    assert result.output.index("101") < result.output.index("102")


def test_jobs_violators_unknown_partition(monkeypatch):
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: [])
    result = CliRunner().invoke(main, ["jobs", "violators", "some_partition"])
    assert result.exit_code != 0
    assert "unknown partition" in result.output


def test_jobs_violators_override(monkeypatch):
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: [("201", "eve", 100, 2, 10000)])
    result = CliRunner().invoke(
        main, ["jobs", "violators", "custom", "--cpu-per-gpu", "40", "--mem-per-gpu", "100000"]
    )
    assert result.exit_code == 0
    assert "201" in result.output


def test_account_members_all(monkeypatch):
    monkeypatch.setattr(
        slurm, "partition_accounts", lambda p: ["kempner_dev", "kempner_x_lab", "other_acct"]
    )
    members_map = {"kempner_dev": ["alice", "bob"], "kempner_x_lab": ["carol"], "other_acct": ["z"]}
    monkeypatch.setattr(slurm, "account_members", lambda a: members_map.get(a, []))
    monkeypatch.setattr(
        slurm,
        "user_fullnames",
        lambda users: {"alice": "Alice_A", "bob": "Bob_B", "carol": "Carol_C"},
    )
    result = CliRunner().invoke(main, ["account", "members", "--all"])
    assert result.exit_code == 0
    assert "account,username,full_name" in result.output
    assert "kempner_dev,alice,Alice_A" in result.output
    assert "kempner_x_lab,carol,Carol_C" in result.output
    assert "other_acct" not in result.output


def test_account_members_needs_account():
    result = CliRunner().invoke(main, ["account", "members"])
    assert result.exit_code != 0
    assert "give an ACCOUNT or use --all" in result.output
