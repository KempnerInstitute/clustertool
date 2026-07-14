"""Tests for the CLI commands."""

import os
import shutil

from click.testing import CliRunner

from cluster_tools import process, slurm
from cluster_tools.cli import main


def test_usage_all_labs(monkeypatch):
    monkeypatch.setattr(slurm, "account_cap", lambda: 96)
    monkeypatch.setattr(slurm, "gpu_by_account", lambda partitions: {"acct_a": 8, "acct_b": 4})
    result = CliRunner().invoke(main, ["gpu", "usage"])
    assert result.exit_code == 0
    assert "acct_a" in result.output
    assert "TOTAL" in result.output
    assert "12 GPU in use across 2 account(s)" in result.output


def test_usage_all_labs_empty(monkeypatch):
    monkeypatch.setattr(slurm, "account_cap", lambda: 96)
    monkeypatch.setattr(slurm, "gpu_by_account", lambda partitions: {})
    result = CliRunner().invoke(main, ["gpu", "usage"])
    assert result.exit_code == 0
    assert "no running GPU jobs" in result.output


def test_usage_one_lab_unknown_account(monkeypatch):
    monkeypatch.setattr(slurm, "account_exists", lambda account: False)
    result = CliRunner().invoke(main, ["gpu", "usage", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_usage_one_lab(monkeypatch):
    monkeypatch.setattr(slurm, "account_exists", lambda account: True)
    monkeypatch.setattr(slurm, "account_cap", lambda: 96)
    monkeypatch.setattr(slurm, "priority_partitions", lambda: [])
    monkeypatch.setattr(
        slurm,
        "gpu_rows",
        lambda account, partitions: [("alice", "kempner", 4)] if "kempner" in partitions else [],
    )
    monkeypatch.setattr(slurm, "pending_at_cap", lambda account, partitions: 0)
    result = CliRunner().invoke(main, ["gpu", "usage", "acct_a"])
    assert result.exit_code == 0
    assert "account: acct_a" in result.output
    assert "alice" in result.output
    assert "4 / 96 GPU" in result.output


def test_slurm_error_is_clean(monkeypatch):
    def boom():
        raise slurm.SlurmError("'squeue' not found on this host")

    monkeypatch.setattr(slurm, "account_cap", boom)
    result = CliRunner().invoke(main, ["gpu", "usage"])
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


def test_storage_quota_group(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        process, "stream", lambda cmd, extra_env=None: captured.update(cmd=cmd) or 0
    )
    result = CliRunner().invoke(main, ["storage", "quota", "holylfs06", "-g", "kempner_dev"])
    assert result.exit_code == 0
    assert captured["cmd"] == ["quota", "-g", "kempner_dev", "/n/holylfs06"]


def test_storage_quota_user_full_path(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        process, "stream", lambda cmd, extra_env=None: captured.update(cmd=cmd) or 0
    )
    result = CliRunner().invoke(main, ["storage", "quota", "/n/netscratch", "-u", "mmsh"])
    assert result.exit_code == 0
    assert captured["cmd"] == ["quota", "-u", "mmsh", "/n/netscratch"]


def test_storage_quota_infer(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        process, "stream", lambda cmd, extra_env=None: captured.update(cmd=cmd) or 0
    )
    result = CliRunner().invoke(main, ["storage", "quota", "netscratch"])
    assert result.exit_code == 0
    assert captured["cmd"] == ["quota", "/n/netscratch"]


def test_storage_home(monkeypatch):
    calls = []
    monkeypatch.setattr(process, "stream", lambda cmd, extra_env=None: calls.append(cmd) or 0)
    result = CliRunner().invoke(main, ["storage", "home"])
    assert result.exit_code == 0
    assert calls[0][:2] == ["df", "-h"]


def test_storage_home_scan(monkeypatch):
    home = os.path.expanduser("~")
    monkeypatch.setattr(process, "stream", lambda cmd, extra_env=None: 0)
    du_out = f"5000000\t{home}/big\n2000000\t{home}/med\n1000\t{home}/small\n9999999\t{home}\n"
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: du_out)
    result = CliRunner().invoke(main, ["storage", "home", "--scan", "--top", "2"])
    assert result.exit_code == 0
    assert f"{home}/big" in result.output
    assert f"{home}/med" in result.output
    assert f"{home}/small" not in result.output
    assert result.output.index("/big") < result.output.index("/med")


def test_storage_home_ncdu(monkeypatch):
    calls = []
    monkeypatch.setattr(process, "stream", lambda cmd, extra_env=None: calls.append(cmd) or 0)
    result = CliRunner().invoke(main, ["storage", "home", "--ncdu"])
    assert result.exit_code == 0
    assert calls[0][0] == "ncdu"


def test_storage_quota_group_and_user_error():
    result = CliRunner().invoke(main, ["storage", "quota", "/n/holylfs06", "-g", "x", "-u", "y"])
    assert result.exit_code != 0
    assert "at most one" in result.output


def test_diag_nccl_dry_run():
    result = CliRunner().invoke(main, ["diag", "nccl", "--dry-run"])
    assert result.exit_code == 0
    assert "timeout 300 srun" in result.output
    assert "--ntasks-per-node=" in result.output
    assert result.output.strip().endswith("-u <nccl_fsdp_test.py>")


def test_diag_nccl_no_slurm(monkeypatch):
    for var in ["SLURM_PROCID", "SLURM_NNODES", "SLURM_NTASKS_PER_NODE"]:
        monkeypatch.delenv(var, raising=False)
    result = CliRunner().invoke(main, ["diag", "nccl"])
    assert result.exit_code != 0
    assert "Slurm allocation" in result.output


def test_diag_nccl_run(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SLURM_PROCID", "0")
    monkeypatch.setenv("SLURM_NNODES", "2")
    monkeypatch.setenv("SLURM_NTASKS_PER_NODE", "4")
    monkeypatch.setenv("SLURM_JOB_ID", "999")
    monkeypatch.setattr(slurm, "first_hostname", lambda: "node0")
    monkeypatch.setattr(process, "succeeds", lambda cmd: True)
    captured = {}

    def fake_stream(cmd, extra_env=None):
        captured["cmd"] = cmd
        captured["env"] = extra_env
        return 0

    monkeypatch.setattr(process, "stream", fake_stream)
    result = CliRunner().invoke(main, ["diag", "nccl"])
    assert result.exit_code == 0
    assert captured["cmd"][:3] == ["timeout", "300", "srun"]
    assert "--ntasks-per-node=4" in captured["cmd"]
    assert captured["env"]["WORLD_SIZE"] == "8"
    assert captured["env"]["MASTER_ADDR"] == "node0"
    assert "passed" in result.output
    assert not list(tmp_path.glob("nccl_fsdp_test_*.py"))


def test_diag_nccl_no_torch(monkeypatch):
    monkeypatch.setenv("SLURM_PROCID", "0")
    monkeypatch.setenv("SLURM_NNODES", "2")
    monkeypatch.setenv("SLURM_NTASKS_PER_NODE", "4")
    monkeypatch.setattr(process, "succeeds", lambda cmd: False)
    result = CliRunner().invoke(main, ["diag", "nccl"])
    assert result.exit_code != 0
    assert "cannot import torch" in result.output


def _node_fields(output):
    return {
        line.split()[0]: line.split()
        for line in output.splitlines()
        if line.strip().startswith("n")
    }


def test_gpu_avail(monkeypatch):
    monkeypatch.setattr(
        slurm, "partition_nodes", lambda p: [("n1", "x"), ("n2", "x"), ("n3", "x"), ("n4", "x")]
    )
    free = {
        "n1": (4, 96, 1440000),  # min(4, 96//24, 1440000//360000) = 4
        "n2": (8, 48, 2880000),  # cpu-capped: min(8, 48//24=2, 8) = 2
        "n3": (2, 96, 360000),  # mem-capped: min(2, 4, 360000//360000=1) = 1
        "n4": (0, 0, 0),  # no gpu -> filtered
    }
    monkeypatch.setattr(slurm, "node_free_resources", lambda node: free[node])
    result = CliRunner().invoke(main, ["gpu", "avail", "kempner_h100"])
    assert result.exit_code == 0
    fields = _node_fields(result.output)
    assert "n4" not in fields
    assert fields["n1"][1] == "4"
    assert fields["n2"][1] == "2" and fields["n2"][2] == "8"
    assert fields["n3"][1] == "1" and fields["n3"][2] == "2"
    assert result.output.index("n1") < result.output.index("n2") < result.output.index("n3")


def test_gpu_avail_raw_partition(monkeypatch):
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "x")])
    monkeypatch.setattr(slurm, "node_free_resources", lambda node: (4, 8, 1000))
    result = CliRunner().invoke(main, ["gpu", "avail", "kempner_eng"])
    assert result.exit_code == 0
    assert "raw free" in result.output
    assert _node_fields(result.output)["n1"][1] == "4"


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


def test_jobs_violators_h200(monkeypatch):
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: [("301", "x", 200, 2, 10000)])
    result = CliRunner().invoke(main, ["jobs", "violators", "kempner_h200"])
    assert result.exit_code == 0
    assert "301" in result.output


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


def test_diag_ib(monkeypatch):
    monkeypatch.setattr(
        slurm, "partition_nodes", lambda p: [("n1", "idle"), ("n2", "idle"), ("n3", "idle")]
    )

    def fake_run(cmd):
        host = cmd[-2]
        return "5: ib1: <BROADCAST,MULTICAST> mtu 4092 state DOWN\n" if host == "n2" else ""

    monkeypatch.setattr(process, "run", fake_run)
    result = CliRunner().invoke(main, ["diag", "ib", "kempner_h100"])
    assert result.exit_code == 0
    assert "n2" in result.output
    assert "ib1" in result.output
    assert "1 host(s) with IB ports DOWN" in result.output


def test_gpu_monitor_job(monkeypatch):
    from cluster_tools import monitor

    monkeypatch.setattr(slurm, "job_nodes", lambda j: ["n1", "n2"])
    captured = {}
    monkeypatch.setattr(
        monitor,
        "run_monitor",
        lambda title, hosts, interval: captured.update(title=title, hosts=hosts),
    )
    result = CliRunner().invoke(main, ["gpu", "monitor-job", "12345"])
    assert result.exit_code == 0
    assert captured["hosts"] == ["n1", "n2"]
    assert "12345" in captured["title"]


def test_gpu_monitor_job_no_nodes(monkeypatch):
    monkeypatch.setattr(slurm, "job_nodes", lambda j: [])
    result = CliRunner().invoke(main, ["gpu", "monitor-job", "99999"])
    assert result.exit_code != 0
    assert "no nodes found" in result.output


def test_gpu_nvtop(monkeypatch):
    monkeypatch.setattr(slurm, "job_nodes", lambda j: ["n1", "n2"])
    calls = []

    def fake_run(cmd, input_text=None):
        calls.append(cmd)
        if cmd[:2] == ["tmux", "list-panes"]:
            return "0\n1\n"
        return ""

    monkeypatch.setattr(process, "run", fake_run)
    result = CliRunner().invoke(main, ["gpu", "nvtop", "123", "--no-attach"])
    assert result.exit_code == 0
    assert calls[0][:3] == ["tmux", "new-session", "-d"]
    send_keys = [c for c in calls if c[:2] == ["tmux", "send-keys"]]
    assert len(send_keys) == 2
    assert any("n1" in c[4] and "nvtop" in c[4] for c in send_keys)
    assert "attach -t nvtop_123" in result.output


def test_gpu_nvtop_no_nodes(monkeypatch):
    monkeypatch.setattr(slurm, "job_nodes", lambda j: [])
    result = CliRunner().invoke(main, ["gpu", "nvtop", "9", "--no-attach"])
    assert result.exit_code != 0
    assert "no nodes found" in result.output


def _fake_nvidia_smi_l(n):
    return "\n".join(f"GPU {i}: NVIDIA H100 (UUID: GPU-{i})" for i in range(n)) + "\n"


def test_diag_nvlink_dry_run():
    result = CliRunner().invoke(main, ["diag", "nvlink", "--dry-run"])
    assert result.exit_code == 0
    assert "-lnccl" in result.output
    assert "nvlink_saturate_forever.cu" in result.output
    assert "2147483648 20 200" in result.output
    assert "NCCL_IB_DISABLE=1" in result.output
    assert "all GPUs on the node" in result.output


def test_diag_nvlink_dry_run_gpus():
    result = CliRunner().invoke(
        main, ["diag", "nvlink", "1024", "5", "50", "--gpus", "4", "--dry-run"]
    )
    assert result.exit_code == 0
    assert "1024 5 50" in result.output
    assert "CUDA_VISIBLE_DEVICES=0,1,2,3" in result.output


def test_diag_nvlink_run_all_gpus(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: _fake_nvidia_smi_l(8))
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/nvcc")
    calls = []
    monkeypatch.setattr(
        process, "stream", lambda cmd, extra_env=None: calls.append((cmd, extra_env)) or 0
    )
    result = CliRunner().invoke(main, ["diag", "nvlink"])
    assert result.exit_code == 0
    run_env = [env for cmd, env in calls if env is not None][0]
    assert run_env["CUDA_VISIBLE_DEVICES"] == "0,1,2,3,4,5,6,7"
    assert "8 GPU(s)" in result.output


def test_diag_nvlink_gpus_override(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: _fake_nvidia_smi_l(8))
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/nvcc")
    calls = []
    monkeypatch.setattr(
        process, "stream", lambda cmd, extra_env=None: calls.append((cmd, extra_env)) or 0
    )
    result = CliRunner().invoke(main, ["diag", "nvlink", "--gpus", "4"])
    assert result.exit_code == 0
    run_env = [env for cmd, env in calls if env is not None][0]
    assert run_env["CUDA_VISIBLE_DEVICES"] == "0,1,2,3"


def test_diag_nvlink_gpus_exceeds(monkeypatch):
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: _fake_nvidia_smi_l(4))
    result = CliRunner().invoke(main, ["diag", "nvlink", "--gpus", "8"])
    assert result.exit_code != 0
    assert "exceeds" in result.output


def test_diag_nvlink_too_few_gpus(monkeypatch):
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: _fake_nvidia_smi_l(1))
    result = CliRunner().invoke(main, ["diag", "nvlink"])
    assert result.exit_code != 0
    assert "at least 2 GPUs" in result.output


def test_diag_nvlink_no_gpus(monkeypatch):
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: "")
    result = CliRunner().invoke(main, ["diag", "nvlink"])
    assert result.exit_code != 0
    assert "no GPUs detected" in result.output


def test_diag_nvlink_no_nvcc(monkeypatch):
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: _fake_nvidia_smi_l(8))
    monkeypatch.setattr(shutil, "which", lambda name: None)
    result = CliRunner().invoke(main, ["diag", "nvlink"])
    assert result.exit_code != 0
    assert "not found" in result.output
