"""Tests for the Slurm helper module."""

import pytest

from cluster_tools import slurm


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
    assert round(free_mem) == 1311


def test_node_free_resources_idle(monkeypatch):
    sample = "NodeName=n1\nCfgTRES=cpu=96,mem=1024000M,gres/gpu=4\nAllocTRES=\n"
    monkeypatch.setattr(slurm, "_run", lambda cmd: sample)
    free_gpu, free_cpu, free_mem = slurm.node_free_resources("n1")
    assert free_gpu == 4
    assert free_cpu == 96
    assert round(free_mem) == 1000
