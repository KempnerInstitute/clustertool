"""Tests for the qos helper module."""

import pytest

from clustertool import qos


def test_qos_exists_exact_match(monkeypatch):
    monkeypatch.setattr(qos.process, "probe", lambda cmd, timeout=None: (0, "kemp_gpu4\n", ""))
    assert qos.qos_exists("kemp_gpu4") is True
    assert qos.qos_exists("kemp") is False


def test_qos_exists_absent(monkeypatch):
    monkeypatch.setattr(qos.process, "probe", lambda cmd, timeout=None: (0, "\n", ""))
    assert qos.qos_exists("nope") is False


def test_qos_exists_ignores_case(monkeypatch):
    """sacctmgr treats QoS names case-insensitively, so a case variant is the same QoS."""
    monkeypatch.setattr(qos.process, "probe", lambda cmd, timeout=None: (0, "kemp_gpu4\n", ""))
    assert qos.qos_exists("KEMP_GPU4") is True


def test_qos_exists_raises_when_the_query_fails(monkeypatch):
    """A failed read must not be reported as 'does not exist; nothing to do'."""
    monkeypatch.setattr(qos.process, "probe", lambda cmd, timeout=None: (1, "", "slurmdbd down"))
    with pytest.raises(qos.CommandError):
        qos.qos_exists("kemp_gpu4")


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
    monkeypatch.setattr(
        qos.process,
        "probe",
        lambda cmd, timeout=None: (0, "odyssey|kempner_dev|alice|kempner_h100\n", ""),
    )
    assert qos.any_holders("q") == ["odyssey|kempner_dev|alice|kempner_h100"]


def test_any_holders_raises_when_the_query_fails(monkeypatch):
    """An empty result is permission to delete, so a failed read must not look empty."""
    monkeypatch.setattr(qos.process, "probe", lambda cmd, timeout=None: (1, "", "slurmdbd down"))
    with pytest.raises(qos.CommandError):
        qos.any_holders("q")


def test_partitions_referencing_finds_default_and_allowed(monkeypatch):
    out = (
        "PartitionName=gpu AllowQos=ALL QoS=base_caps State=UP\n"
        "PartitionName=cpu AllowQos=other,base_caps State=UP\n"
        "PartitionName=idle AllowQos=ALL State=UP\n"
    )
    monkeypatch.setattr(qos.process, "probe", lambda cmd, timeout=None: (0, out, ""))
    assert qos.partitions_referencing("base_caps") == ["cpu", "gpu"]
    assert qos.partitions_referencing("absent") == []


def test_partitions_referencing_reads_hidden_partitions_on_the_site_cluster(monkeypatch):
    seen = {}

    def fake_probe(cmd, timeout=None):
        seen["cmd"] = cmd
        return 0, "PartitionName=secret QoS=base_caps State=UP\n", ""

    monkeypatch.setattr(qos.process, "probe", fake_probe)
    assert qos.partitions_referencing("BASE_CAPS", cluster="bigred") == ["secret"]
    assert seen["cmd"] == ["scontrol", "-a", "-M", "bigred", "show", "partition"]


def test_partition_exists(monkeypatch):
    monkeypatch.setattr(
        qos.process, "probe", lambda cmd, timeout=None: (0, "PartitionName=gpu", "")
    )
    assert qos.partition_exists("gpu") is True


def test_partition_exists_false_for_an_unknown_name(monkeypatch):
    """scontrol writes 'not found' to stdout, not stderr."""
    monkeypatch.setattr(
        qos.process, "probe", lambda cmd, timeout=None: (1, "Partition nope not found\n", "")
    )
    assert qos.partition_exists("nope") is False


def test_partition_exists_raises_when_the_lookup_itself_fails(monkeypatch):
    """An unreachable controller must not be reported as a partition that does not exist."""
    monkeypatch.setattr(
        qos.process,
        "probe",
        lambda cmd, timeout=None: (1, "", "Unable to contact slurm controller"),
    )
    with pytest.raises(qos.CommandError):
        qos.partition_exists("gpu")


def test_grant_plan_keeps_the_qos_it_sets_as_the_default(monkeypatch):
    """Stripping the catch-all must not remove the QoS just installed as the default."""
    monkeypatch.setattr(qos, "read_assoc", lambda *a, **k: ("normal,other", "other"))
    monkeypatch.setattr(qos, "_strip_names", lambda partition: ["normal", partition])
    plan = qos.grant_plan("alice", "lab", "gpu", "kemp", "normal", "odyssey")
    specs = [cmd[-1] for cmd in plan]
    assert "QOS+=kemp" in specs
    assert "DefaultQOS=normal" in specs
    assert not [spec for spec in specs if spec.startswith("QOS-=")]


def test_grant_plan_still_strips_the_catch_all_for_the_usual_default(monkeypatch):
    monkeypatch.setattr(qos, "read_assoc", lambda *a, **k: ("normal,other", "other"))
    monkeypatch.setattr(qos, "_strip_names", lambda partition: ["normal", partition])
    plan = qos.grant_plan("alice", "lab", "gpu", "kemp", "kemp", "odyssey")
    specs = [cmd[-1] for cmd in plan]
    assert "QOS+=kemp" in specs
    assert "DefaultQOS=kemp" in specs
    assert "QOS-=normal" in specs


def test_jobs_using_counts_exact_matches(monkeypatch):
    monkeypatch.setattr(
        qos.process, "probe", lambda cmd, timeout=None: (0, "normal\nKEMP\nnormal\nkemp_x\n", "")
    )
    assert qos.jobs_using("normal") == 2
    assert qos.jobs_using("kemp") == 1
    assert qos.jobs_using("absent") == 0


def test_jobs_using_raises_when_the_query_fails(monkeypatch):
    """An empty result is permission to delete, so a failed read must not look empty."""
    monkeypatch.setattr(qos.process, "probe", lambda cmd, timeout=None: (1, "", "down"))
    with pytest.raises(qos.CommandError):
        qos.jobs_using("normal")


def test_uncovered_holders_flags_a_holder_the_plan_would_not_revoke(monkeypatch):
    """The base association survives a partition-scoped sweep, so the QoS stays in force."""
    monkeypatch.setattr(
        qos,
        "any_holders",
        lambda name: [
            "odyssey|kempner_dev|nkhoshnevis|",
            "odyssey|kempner_dev|nkhoshnevis|kempner_h200_priority",
        ],
    )
    plan = [
        [
            "sacctmgr",
            "-i",
            "modify",
            "user",
            "where",
            "user=nkhoshnevis",
            "account=kempner_dev",
            "partition=kempner_h200_priority",
            "cluster=odyssey",
            "set",
            "QOS-=h200_benchmarking",
        ]
    ]
    assert qos.uncovered_holders("h200_benchmarking", plan) == ["odyssey|kempner_dev|nkhoshnevis|"]


def test_uncovered_holders_empty_when_the_plan_covers_everyone(monkeypatch):
    monkeypatch.setattr(qos, "any_holders", lambda name: ["odyssey|kempner_dev|alice|kempner_h100"])
    plan = [
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
    assert qos.uncovered_holders("kemp", plan) == []


def test_uncovered_holders_flags_another_cluster(monkeypatch):
    monkeypatch.setattr(qos, "any_holders", lambda name: ["bigred|kempner_dev|alice|kempner_h100"])
    plan = [
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
    assert qos.uncovered_holders("kemp", plan) == ["bigred|kempner_dev|alice|kempner_h100"]


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


def test_account_base_members_keeps_only_the_base_association(monkeypatch):
    """A partition-scoped row is not membership, or nothing could ever be revoked."""
    out = "bob|\nalice|\nbob|kempner_h100\ncarol|kempner_h100\n|\n"
    monkeypatch.setattr(qos.process, "probe", lambda cmd, timeout=None: (0, out, ""))
    assert qos.account_base_members("kempner_dev") == ["alice", "bob"]


def test_account_base_members_raises_when_the_query_fails(monkeypatch):
    """An empty read must not look like an empty account: sync would revoke all."""
    monkeypatch.setattr(qos.process, "probe", lambda cmd, timeout=None: (1, "", "dbd down"))
    with pytest.raises(qos.CommandError):
        qos.account_base_members("kempner_dev")


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
