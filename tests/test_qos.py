"""Tests for the qos helper module."""

from clustertool import qos


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


def test_flatten_users():
    assert qos.flatten_users(("a,b", "b", " c ")) == ["a", "b", "c"]
    assert qos.flatten_users(("all",)) == ["all"]


def test_get_accounts_filters(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "kempner_dev\nkempner_eng\nother_lab\n")
    assert qos.get_accounts("alice", account_regex="^kempner_") == ["kempner_dev", "kempner_eng"]


def test_account_members(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "bob\nalice\nbob\n\n")
    assert qos.account_members("kempner_dev") == ["alice", "bob"]


def test_account_exists(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "kempner_dev\n")
    assert qos.account_exists("kempner_dev") is True
    monkeypatch.setattr(qos, "_run", lambda cmd: "\n")
    assert qos.account_exists("ghost") is False


def test_read_assoc(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "alice|kemp,normal|kemp\n")
    assert qos.read_assoc("alice", "kempner_dev", "kempner_h100") == ("kemp,normal", "kemp")
    monkeypatch.setattr(qos, "_run", lambda cmd: "")
    assert qos.read_assoc("alice", "kempner_dev", "kempner_h100") is None


def test_grant_plan_create(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "")
    plan = qos.grant_plan("alice", "kempner_dev", "kempner_h100", "kemp", "kemp", "odyssey")
    assert plan == [
        [
            "sacctmgr",
            "-i",
            "add",
            "user",
            "name=alice",
            "account=kempner_dev",
            "partition=kempner_h100",
            "cluster=odyssey",
            "fairshare=parent",
            "qos=kemp",
            "defaultqos=kemp",
        ]
    ]


def test_grant_plan_create_distinct_default(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "")
    plan = qos.grant_plan("alice", "kempner_dev", "kempner_h100", "kemp", "normal", "odyssey")
    assert "qos=kemp,normal" in plan[0]
    assert "defaultqos=normal" in plan[0]


def test_grant_plan_update_and_strip(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "alice|normal,kempner_h100|normal\n")
    plan = qos.grant_plan("alice", "kempner_dev", "kempner_h100", "kemp", "kemp", "odyssey")
    joined = [" ".join(cmd) for cmd in plan]
    assert any(j.endswith("set QOS+=kemp") for j in joined)
    assert any(j.endswith("set DefaultQOS=kemp") for j in joined)
    assert any(j.endswith("set QOS-=normal,kempner_h100") for j in joined)


def test_grant_plan_noop(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "alice|kemp|kemp\n")
    assert qos.grant_plan("alice", "kempner_dev", "kempner_h100", "kemp", "kemp", "odyssey") == []


def test_revoke_plan_only_entry(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "alice|kemp|kemp\n")
    plan = qos.revoke_plan("alice", "kempner_dev", "kempner_h100", "kemp", "odyssey")
    assert plan == [
        [
            "sacctmgr",
            "-i",
            "delete",
            "user",
            "where",
            "cluster=odyssey",
            "name=alice",
            "account=kempner_dev",
            "partition=kempner_h100",
        ]
    ]


def test_revoke_plan_moves_default_then_removes(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "alice|kemp,normal|kemp\n")
    plan = qos.revoke_plan("alice", "kempner_dev", "kempner_h100", "kemp", "odyssey")
    joined = [" ".join(cmd) for cmd in plan]
    assert joined[0].endswith("set DefaultQOS=normal")
    assert joined[1].endswith("set QOS-=kemp")


def test_revoke_plan_removes_without_default_move(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "alice|kemp,normal|normal\n")
    plan = qos.revoke_plan("alice", "kempner_dev", "kempner_h100", "kemp", "odyssey")
    joined = [" ".join(cmd) for cmd in plan]
    assert joined == [
        "sacctmgr -i modify user where user=alice account=kempner_dev "
        "partition=kempner_h100 cluster=odyssey set QOS-=kemp"
    ]


def test_revoke_plan_skips(monkeypatch):
    monkeypatch.setattr(qos, "_run", lambda cmd: "")
    assert qos.revoke_plan("alice", "kempner_dev", "kempner_h100", "kemp", "odyssey") == []
    monkeypatch.setattr(qos, "_run", lambda cmd: "alice|other|other\n")
    assert qos.revoke_plan("alice", "kempner_dev", "kempner_h100", "kemp", "odyssey") == []


def test_revoke_targets_plan_expands_all(monkeypatch):
    def fake(cmd):
        tail = " ".join(cmd).split("format=")[-1]
        if tail == "User,Account,Partition":
            return "alice|kempner_dev|kempner_h100\n"
        if tail == "Account":
            return "kempner_dev\n"
        if tail == "User,QOS,DefaultQOS":
            return "alice|kemp|kemp\n"
        return ""

    monkeypatch.setattr(qos, "_run", fake)
    plan = qos.revoke_targets_plan("kemp", ["all"], "all", cluster="odyssey")
    assert plan == [
        [
            "sacctmgr",
            "-i",
            "delete",
            "user",
            "where",
            "cluster=odyssey",
            "name=alice",
            "account=kempner_dev",
            "partition=kempner_h100",
        ]
    ]
