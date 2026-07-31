"""Tests for the qos helper module."""

from cluster_tools import qos


def test_qos_exists_exact_match(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "kemp_gpu4\n")
    assert qos.qos_exists("kemp_gpu4") is True
    assert qos.qos_exists("kemp") is False


def test_qos_exists_absent(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "\n")
    assert qos.qos_exists("nope") is False


def test_holder_rows_filters(monkeypatch):
    sample = (
        "alice|kempner_dev|kempner_h100\n"
        "bob|kempner_eng|kempner_h100\n"
        "|kempner_dev|kempner_h100\n"
        "carol|kempner_dev|\n"
    )
    monkeypatch.setattr(qos, "_run", lambda cmd: sample)
    rows = qos.holder_rows("kemp_gpu4", cluster="odyssey")
    assert rows == [
        ("alice", "kempner_dev", "kempner_h100"),
        ("bob", "kempner_eng", "kempner_h100"),
    ]


def test_holder_rows_account_regex(monkeypatch):
    sample = "alice|kempner_dev|kempner_h100\nbob|kempner_eng|kempner_h100\n"
    monkeypatch.setattr(qos, "_run", lambda cmd: sample)
    rows = qos.holder_rows("q", account_regex="^kempner_dev$")
    assert rows == [("alice", "kempner_dev", "kempner_h100")]


def test_holder_rows_partition_in_where(monkeypatch):
    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return ""

    monkeypatch.setattr(qos, "_run", fake_run)
    qos.holder_rows("q", cluster="odyssey", partition="kempner_h100")
    assert "partition=kempner_h100" in captured["cmd"]
    assert "cluster=odyssey" in captured["cmd"]


def test_any_holders(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "odyssey|kempner_dev|alice|kempner_h100\n")
    assert qos.any_holders("q") == ["odyssey|kempner_dev|alice|kempner_h100"]


def test_build_limit_specs_all():
    specs = qos.build_limit_specs(
        gpu_per_user=4, node_per_user=1, group_gpu=8, job_gpu=2, jobs_per_user=12
    )
    assert specs == [
        "MaxTRESPU=node=1,gres/gpu=4",
        "GrpTRES=gres/gpu=8",
        "MaxTRES=gres/gpu=2",
        "MaxJobsPU=12",
    ]


def test_build_limit_specs_gpu_only():
    assert qos.build_limit_specs(gpu_per_user=4) == ["MaxTRESPU=gres/gpu=4"]


def test_build_limit_specs_clear():
    assert qos.build_limit_specs(group_gpu=-1, job_gpu=-1) == [
        "GrpTRES=gres/gpu=-1",
        "MaxTRES=gres/gpu=-1",
    ]


def test_build_limit_specs_empty():
    assert qos.build_limit_specs() == []


def test_valid_name():
    assert qos.valid_name("kemp_gpu4_id07") is True
    assert qos.valid_name("kempner-h200.x") is True
    assert qos.valid_name("a,b") is False
    assert qos.valid_name("a b") is False
    assert qos.valid_name("") is False
