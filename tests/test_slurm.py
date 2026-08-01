"""Tests for the Slurm helper module."""

import pytest

from clustertool import slurm


def test_parse_gpu_count():
    assert slurm.parse_gpu_count("cpu=32,mem=100G,gres/gpu=4") == 4
    assert slurm.parse_gpu_count("cpu=32,mem=100G") == 0


def test_gpu_by_account(monkeypatch):
    sample = (
        "acct_a               cpu=32,mem=100G,gres/gpu=4\n"
        "acct_b               cpu=16,mem=64G,gres/gpu=2\n"
        "acct_a               cpu=8,mem=32G,gres/gpu=1\n"
        "acct_c               cpu=8,mem=32G\n"
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    assert slurm.gpu_by_account(slurm.BASE_PARTITIONS) == {"acct_a": 5, "acct_b": 2}


def test_gpu_rows(monkeypatch):
    sample = (
        "alice   kempner_h100   cpu=32,gres/gpu=4\n"
        "bob     kempner        cpu=16,gres/gpu=2\n"
        "carol   kempner        cpu=8,mem=32G\n"
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    rows = slurm.gpu_rows("acct_a", slurm.BASE_PARTITIONS)
    assert rows == [("alice", "kempner_h100", 4), ("bob", "kempner", 2)]


def test_account_cap_prefers_gpu_tres(monkeypatch):
    monkeypatch.setattr(slurm, "_run", lambda cmd: "cpu=1000,gres/gpu=96\n")
    assert slurm.account_cap() == 96


def test_account_cap_default(monkeypatch):
    monkeypatch.setattr(slurm, "_run", lambda cmd: "\n")
    assert slurm.account_cap() == slurm.DEFAULT_CAP


def test_priority_partitions(monkeypatch):
    sample = (
        "PartitionName=kempner State=UP\n"
        "PartitionName=kempner_h100_priority State=UP\n"
        "PartitionName=kempner_requeue State=UP\n"
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    assert slurm.priority_partitions() == ["kempner_h100_priority"]


def test_pending_at_cap(monkeypatch):
    sample = "MaxGRESPerAccount\nResources\nMaxGRESPerAccount\n"
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    assert slurm.pending_at_cap("acct_a", slurm.BASE_PARTITIONS) == 2


def test_partition_nodes(monkeypatch):
    sample = "node01 idle\nnode02 mix\nbad\n"
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    assert slurm.partition_nodes("kempner") == [("node01", "idle"), ("node02", "mix")]


def test_account_members(monkeypatch):
    sample = (
        "Account|User|RawShares|NormShares|RawUsage|EffectvUsage|FairShare\n"
        "kempner_dev||250|0.0004|1|0.002|\n"
        " kempner_dev|alice|20|0.00003|1|0.0002|0.004\n"
        " kempner_dev|alice|parent|0.0003|0|0.002|0.008\n"
        " kempner_dev|bob|20|0.00003|1|0.0002|0.004\n"
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    assert slurm.account_members("kempner_dev") == ["alice", "bob"]


def test_node_info_gpu(monkeypatch):
    sample = (
        "NodeName=holygpu8a11101 Arch=x86_64\n"
        "CfgTRES=cpu=96,mem=1547208M,billing=2302,gres/gpu=4\n"
        "Partitions=kempner_h100,kempner_h100_priority\n"
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    info = slurm.node_info("holygpu8a11101")
    assert info["name"] == "holygpu8a11101"
    assert info["gpus"] == 4
    assert info["partitions"] == ["kempner_h100", "kempner_h100_priority"]


def test_node_info_non_gpu(monkeypatch):
    sample = "NodeName=cpu01\nCfgTRES=cpu=48,mem=192000M,billing=48\nPartitions=shared\n"
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    assert slurm.node_info("cpu01")["gpus"] == 0


def test_node_info_missing(monkeypatch):
    monkeypatch.setattr(slurm, "_run", lambda cmd: "")
    with pytest.raises(slurm.SlurmError):
        slurm.node_info("nope")


def test_node_free_resources(monkeypatch):
    sample = (
        "NodeName=n1\n"
        "CfgTRES=cpu=96,mem=1547208M,billing=100,gres/gpu=4\n"
        "AllocTRES=cpu=32,mem=200G,gres/gpu=1\n"
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    free_gpu, free_cpu, free_mem = slurm.node_free_resources("n1")
    assert free_gpu == 3
    assert free_cpu == 64
    assert round(free_mem) == 1342408


def test_node_free_resources_idle(monkeypatch):
    sample = "NodeName=n1\nCfgTRES=cpu=96,mem=1024000M,gres/gpu=4\nAllocTRES=\n"
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    free_gpu, free_cpu, free_mem = slurm.node_free_resources("n1")
    assert free_gpu == 4
    assert free_cpu == 96
    assert round(free_mem) == 1024000


def test_running_jobs_reqtres(monkeypatch):
    out = (
        "JobId=101 UserId=alice(1001) JobState=RUNNING Partition=kempner_h100 "
        "ReqTRES=cpu=200,mem=100000M,node=1,gres/gpu=8\n"
        "JobId=102 UserId=bob(1002) JobState=RUNNING Partition=kempner_h100,kempner "
        "ReqTRES=cpu=96,mem=2000000M,gres/gpu=4\n"
        "JobId=103 UserId=carol(1003) JobState=PENDING Partition=kempner_h100 "
        "ReqTRES=cpu=8,mem=100M,gres/gpu=1\n"
        "JobId=104 UserId=dave(1004) JobState=RUNNING Partition=kempner "
        "ReqTRES=cpu=8,mem=100M,gres/gpu=1\n"
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd: out)
    jobs = slurm.running_jobs_reqtres("kempner_h100")
    assert jobs == [
        ("101", "alice", 200, 8, 100000),
        ("102", "bob", 96, 4, 2000000),
    ]


def test_partition_accounts(monkeypatch):
    monkeypatch.setattr(
        slurm,
        "_run",
        lambda cmd: "PartitionName=kempner AllowAccounts=kempner_dev,kempner_sham_lab State=UP\n",
    )
    assert slurm.partition_accounts("kempner") == ["kempner_dev", "kempner_sham_lab"]


def test_user_fullnames(monkeypatch):
    out = "auser:*:1:2:A User:/home:/bin/bash\nbuser:*:3:4:B Example User:/h:/bin/bash\n"
    monkeypatch.setattr(slurm, "_run", lambda cmd: out)
    assert slurm.user_fullnames(["auser", "buser"]) == {
        "auser": "A_User",
        "buser": "B_Example_User",
    }


def test_job_nodes(monkeypatch):
    def fake_run(cmd):
        if cmd[0] == "squeue":
            return "holygpu8a[11101-11102]\n"
        return "holygpu8a11101\nholygpu8a11102\n"

    monkeypatch.setattr(slurm, "_run", fake_run)
    assert slurm.job_nodes("123") == ["holygpu8a11101", "holygpu8a11102"]


def test_job_nodes_not_running(monkeypatch):
    monkeypatch.setattr(slurm, "_run", lambda cmd: "\n")
    assert slurm.job_nodes("123") == []


def test_node_capacity(monkeypatch):
    sample = (
        "NodeName=n1 State=IDLE CPUTot=96 CPUAlloc=0 RealMemory=1000000 AllocMem=0 "
        "CfgTRES=cpu=96,mem=1000000M,gres/gpu=4 AllocTRES= Partitions=kempner_h100\n"
        "NodeName=n2 State=MIXED CPUTot=96 CPUAlloc=48 RealMemory=1000000 AllocMem=500000 "
        "CfgTRES=cpu=96,mem=1000000M,gres/gpu=4 AllocTRES=cpu=48,gres/gpu=2 "
        "Partitions=kempner_h100\n"
        "NodeName=n3 State=DOWN+DRAIN CPUTot=96 CPUAlloc=0 RealMemory=1000000 AllocMem=0 "
        "CfgTRES=cpu=96,gres/gpu=4 AllocTRES= Partitions=kempner_h100\n"
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    n1, n2, n3 = slurm.node_capacity()
    assert n1["available"] and n1["gpu_free"] == 4 and n1["cpu_free"] == 96
    assert n2["gpu_free"] == 2 and n2["cpu_free"] == 48 and n2["mem_free_mb"] == 500000
    assert n3["available"] is False


def test_sacct_window_rows_scoping(monkeypatch):
    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return "1|kempner|q|s|e\n\n"

    monkeypatch.setattr(slurm, "_run", fake_run)
    rows = slurm.sacct_window_rows("A,B", "S", "E", account="acct")
    assert rows == [["1", "kempner", "q", "s", "e"]]
    assert "-A" in captured["cmd"] and "acct" in captured["cmd"] and "-a" in captured["cmd"]
    slurm.sacct_window_rows("A,B", "S", "E", user="bob")
    assert captured["cmd"][-2:] == ["-u", "bob"]


def test_percentile():
    values = list(range(1, 11))
    assert slurm.percentile(values, 50) == 5
    assert slurm.percentile(values, 90) == 9
    assert slurm.percentile(values, 100) == 10
    assert slurm.percentile([10, 20, 30], 50) == 20
    assert slurm.percentile([], 50) is None


def test_account_shares(monkeypatch):
    sample = (
        "Account|User|RawShares|NormShares|RawUsage|EffectvUsage|FairShare\n"
        "root||1|1.0|100|1.0|0.5\n"
        "lab_a||100|0.5|80|0.8|0.3\n"
        " lab_a|alice|10|0.1|8|0.2|0.4\n"
        "lab_b||100|0.5|10|0.1|0.7\n"
        "lab_c||100|0.5|10|bad|xyz\n"
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    rows = slurm.account_shares()
    assert [r["account"] for r in rows] == ["lab_a", "lab_b", "lab_c"]
    assert rows[0]["norm_shares"] == 0.5
    assert rows[0]["effectv_usage"] == 0.8
    assert rows[0]["fairshare"] == 0.3
    assert rows[2]["effectv_usage"] is None
    assert rows[2]["fairshare"] is None


def test_user_associations(monkeypatch):
    sample = (
        "kempner_dev|kempner_h100|kemp_gpu4\n"
        "kempner_dev||normal\n"
        "kempner_dev|kempner_h100|kemp_gpu4\n"
        "|bad|row\n"
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    assert slurm.user_associations("alice") == [
        ("kempner_dev", "kempner_h100", "kemp_gpu4"),
        ("kempner_dev", "", "normal"),
    ]


def test_default_account(monkeypatch):
    monkeypatch.setattr(slurm, "_run", lambda cmd: "kempner_dev\n")
    assert slurm.default_account("alice") == "kempner_dev"
    monkeypatch.setattr(slurm, "_run", lambda cmd: "\n")
    assert slurm.default_account("alice") == ""
