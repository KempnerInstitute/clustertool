"""Tests for the Slurm helper module."""

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
