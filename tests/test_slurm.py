"""Tests for the Slurm helper module."""

import pytest

from clustertool import process, slurm


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


def test_account_cap_is_none_without_a_gpu_cap(monkeypatch):
    """No cap beats a made up one: the denominator would otherwise be fiction."""
    monkeypatch.setattr(slurm, "_run", lambda cmd: "\n")
    assert slurm.account_cap() is None


def test_account_cap_ignores_a_non_gpu_limit(monkeypatch):
    """A cpu or memory ceiling on the base QoS is not a GPU cap."""
    monkeypatch.setattr(slurm, "_run", lambda cmd: "cpu=100,mem=200G\n")
    assert slurm.account_cap() is None


def test_account_cap_uses_a_configured_default(monkeypatch):
    monkeypatch.setattr(slurm, "_run", lambda cmd: "\n")
    monkeypatch.setattr(slurm.site, "default_cap", lambda: 48)
    assert slurm.account_cap() == 48


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
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, sample, ""))
    assert slurm.partition_nodes("kempner") == [("node01", "idle"), ("node02", "mix")]


def test_partition_nodes_raises_when_sinfo_fails(monkeypatch):
    """An empty result reads as a partition that does not exist, so a failure cannot."""
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (1, "", "boom"))
    with pytest.raises(slurm.CommandError):
        slurm.partition_nodes("kempner")


def test_account_members(monkeypatch):
    sample = (
        "Account|User|RawShares|NormShares|RawUsage|EffectvUsage|FairShare\n"
        "kempner_dev||250|0.0004|1|0.002|\n"
        " kempner_dev|alice|20|0.00003|1|0.0002|0.004\n"
        " kempner_dev|alice|parent|0.0003|0|0.002|0.008\n"
        " kempner_dev|bob|20|0.00003|1|0.0002|0.004\n"
    )
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, sample, ""))
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
        slurm.process,
        "probe",
        lambda cmd, timeout=None: (
            0,
            "PartitionName=kempner AllowAccounts=kempner_dev,kempner_sham_lab State=UP\n",
            "",
        ),
    )
    assert slurm.partition_accounts("kempner") == ["kempner_dev", "kempner_sham_lab"]


def test_partition_accounts_raises_when_the_read_fails(monkeypatch):
    """An unreachable controller must not read as a partition open to every account."""
    monkeypatch.setattr(slurm.process, "probe", lambda cmd, timeout=None: (1, "", "no controller"))
    with pytest.raises(slurm.SlurmError):
        slurm.partition_accounts("kempner")


def test_user_fullnames(monkeypatch):
    out = "auser:*:1:2:A User:/home:/bin/bash\nbuser:*:3:4:B Example User:/h:/bin/bash\n"
    monkeypatch.setattr(slurm, "_run", lambda cmd: out)
    assert slurm.user_fullnames(["auser", "buser"]) == {
        "auser": "A_User",
        "buser": "B_Example_User",
    }


def test_job_nodes(monkeypatch):
    monkeypatch.setattr(
        slurm.process, "probe", lambda cmd, timeout=None: (0, "holygpu8a[11101-11102]\n", "")
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd: "holygpu8a11101\nholygpu8a11102\n")
    assert slurm.job_nodes("123") == ["holygpu8a11101", "holygpu8a11102"]


def test_job_nodes_not_running(monkeypatch):
    """A pending job exists and holds no nodes; that is not the same as no such job."""
    monkeypatch.setattr(slurm.process, "probe", lambda cmd, timeout=None: (0, "\n", ""))
    assert slurm.job_nodes("123") == []


def test_job_nodes_raises_for_an_unknown_job(monkeypatch):
    monkeypatch.setattr(
        slurm.process,
        "probe",
        lambda cmd, timeout=None: (1, "", "slurm_load_jobs error: Invalid job id specified"),
    )
    with pytest.raises(slurm.SlurmError):
        slurm.job_nodes("99999991")


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

    def fake_probe(cmd, timeout=None):
        captured["cmd"] = cmd
        return 0, "1|kempner|q|s|e\n\n", ""

    monkeypatch.setattr(slurm.process, "probe", fake_probe)
    rows = slurm.sacct_window_rows("A,B", "S", "E", account="acct")
    assert rows == [["1", "kempner", "q", "s", "e"]]
    assert "-A" in captured["cmd"] and "acct" in captured["cmd"] and "-a" in captured["cmd"]
    slurm.sacct_window_rows("A,B", "S", "E", user="bob")
    assert captured["cmd"][-2:] == ["-u", "bob"]


def test_sacct_window_rows_raises_on_a_bad_window(monkeypatch):
    """A bad time string must not be reported as a window in which nothing ran."""
    monkeypatch.setattr(
        slurm.process,
        "probe",
        lambda cmd, timeout=None: (1, "", "Invalid time specification (pos=0): julyfirst"),
    )
    with pytest.raises(slurm.SlurmError):
        slurm.sacct_window_rows("A,B", "julyfirst", "now")


def test_percentile():
    values = list(range(1, 11))
    assert slurm.percentile(values, 50) == 5
    assert slurm.percentile(values, 90) == 9
    assert slurm.percentile(values, 100) == 10
    assert slurm.percentile([10, 20, 30], 50) == 20
    assert slurm.percentile([], 50) is None


def test_account_shares(monkeypatch):
    sample = (
        "Account|User|RawShares|NormShares|RawUsage|EffectvUsage\n"
        "root||1|1.0|100|1.0\n"
        "lab_a||100|0.5|80|0.8\n"
        " lab_a|alice|10|0.1|8|0.2\n"
        "lab_b||100|0.5|10|0.1\n"
    )
    monkeypatch.setattr(slurm.process, "probe", lambda cmd, timeout=None: (0, sample, ""))
    rows = slurm.account_shares()
    assert [r["account"] for r in rows] == ["lab_a", "lab_b"]
    assert rows[0]["norm_shares"] == 0.5
    assert rows[0]["effectv_usage"] == 0.8
    assert rows[1]["effectv_usage"] == 0.1


def test_account_shares_computes_usage_below_sshare_rounding(monkeypatch):
    """sshare prints EffectvUsage to six decimals, so small accounts round to zero."""
    sample = (
        "Account|User|RawShares|NormShares|RawUsage|EffectvUsage\n"
        "root||1|1.0|1000000000|1.0\n"
        "tiny_lab||700|0.000196|58300|0.000000\n"
    )
    monkeypatch.setattr(slurm.process, "probe", lambda cmd, timeout=None: (0, sample, ""))
    rows = slurm.account_shares()
    assert rows[0]["raw_usage"] == 58300
    assert rows[0]["effectv_usage"] > 0


def test_account_shares_raises_when_sshare_fails(monkeypatch):
    """A failed read must not be reported as a cluster with no accounts."""
    monkeypatch.setattr(slurm.process, "probe", lambda cmd, timeout=None: (1, "", "no slurmdbd"))
    with pytest.raises(slurm.SlurmError):
        slurm.account_shares()


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


def test_account_exists_is_case_insensitive(monkeypatch):
    """sacctmgr resolves names without regard to case, so the reply may differ."""
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, "kempner_dev\n", ""))
    assert slurm.account_exists("Kempner_Dev") is True
    assert slurm.account_exists("kempner_dev") is True


def test_account_exists_rejects_an_unrelated_reply(monkeypatch):
    monkeypatch.setattr(slurm.process, "probe", lambda cmd, timeout=None: (0, "other_acct\n", ""))
    assert slurm.account_exists("kempner_dev") is False


def test_account_exists_raises_when_the_query_fails(monkeypatch):
    """A failed read must not be reported as an account that does not exist."""
    monkeypatch.setattr(slurm.process, "probe", lambda cmd, timeout=None: (1, "", "no slurmdbd"))
    with pytest.raises(slurm.SlurmError):
        slurm.account_exists("kempner_dev")


def test_partition_gpu_util_columns_sum_to_total(monkeypatch):
    """Every GPU belongs to exactly one column, so the four must reconcile."""
    nodes = [
        {
            "name": "up",
            "partitions": ["gpu"],
            "state": "MIXED",
            "available": True,
            "cpu_free": 0,
            "mem_free_mb": 0,
            "gpu_tot": 4,
            "gpu_free": 1,
        },
        {
            "name": "draining",
            "partitions": ["gpu"],
            "state": "MIXED+DRAIN",
            "available": False,
            "cpu_free": 0,
            "mem_free_mb": 0,
            "gpu_tot": 4,
            "gpu_free": 3,
        },
    ]
    monkeypatch.setattr(slurm, "gpus_allocated_in", lambda p: 2)
    total, unavailable, used, other, free, _ = slurm.partition_gpu_util("gpu", nodes)
    assert total == 8
    assert unavailable + used + other + free == total
    assert (used, other, free, unavailable) == (2, 2, 1, 3)


def test_resumable_nodes_includes_an_invalid_registration(monkeypatch):
    """sinfo %T collapses DOWN+DRAIN+INVALID_REG to 'inval', hiding the node."""
    out = (
        "NodeName=n1 State=DOWN+DRAIN+INVALID_REG Partitions=gpu "
        "Reason=gres/gpu count reported lower than configured (3 < 4) [slurm@2026-07-28T17:13:24]\n"
        "NodeName=n2 State=IDLE Partitions=gpu Reason=none\n"
        "NodeName=n3 State=IDLE+POWERED_DOWN Partitions=gpu Reason=none\n"
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd: out)
    rows = slurm.resumable_nodes("gpu")
    assert [name for name, _, _ in rows] == ["n1"]
    assert rows[0][2] == "gres/gpu count reported lower than configured (3 < 4)"


def test_job_exists_raises_when_the_controller_is_unreachable(monkeypatch):
    """An outage must not read as a job that does not exist, on a cancel path."""
    monkeypatch.setattr(
        slurm.process,
        "probe",
        lambda cmd, timeout=None: (
            1,
            "",
            "slurm_load_jobs error: Unable to contact slurm controller",
        ),
    )
    with pytest.raises(slurm.SlurmError):
        slurm.job_exists("123")


def test_job_exists_false_only_for_an_invalid_id(monkeypatch):
    monkeypatch.setattr(
        slurm.process,
        "probe",
        lambda cmd, timeout=None: (1, "", "slurm_load_jobs error: Invalid job id specified"),
    )
    assert slurm.job_exists("99999997") is False


def test_job_state_counts_raises_when_the_query_fails(monkeypatch):
    monkeypatch.setattr(slurm.process, "probe", lambda cmd, timeout=None: (1, "", "down"))
    with pytest.raises(slurm.SlurmError):
        slurm.job_state_counts("alice")


def test_job_output_path_assumes_no_default_for_an_interactive_job(monkeypatch):
    """An interactive allocation writes to the terminal, so it has no file to name."""
    rows = (
        "32923082|32923082|||/work|bash|mmsh|n1\n"
        "32923082.extern|32923082.extern||||extern||n1\n"
        "32923082.0|32923082.0||||bash||n1\n"
    )

    def fake_probe(cmd, timeout=None):
        if cmd[0] == "scontrol":
            return 1, "", "Invalid job id specified"
        return (
            0,
            "\n".join("|".join([r.split("|")[0], *r.split("|")]) for r in rows.splitlines()),
            "",
        )

    monkeypatch.setattr(process, "probe", fake_probe)
    assert slurm.job_output_path("32923082") == ""


def test_job_output_path_assumes_the_sbatch_default_for_a_batch_job(monkeypatch):
    """A batch job submitted without -o writes slurm-<jobid>.out in its WorkDir."""

    def fake_probe(cmd, timeout=None):
        if cmd[0] == "scontrol":
            return 1, "", "Invalid job id specified"
        return 0, "77|77|||/work|run|mmsh|n1\n77.batch|77.batch||||batch||n1\n", ""

    monkeypatch.setattr(process, "probe", fake_probe)
    assert slurm.job_output_path("77") == "/work/slurm-77.out"


def test_expand_log_pattern_follows_man_sbatch():
    """Checked against the names Slurm itself wrote for jobs using each symbol."""
    plain = {"raw_id": "36684103", "job_id": "36684103", "user": "mmsh", "name": "nm", "node": ""}
    node = dict(plain, node="holy8a26602")
    element = {"raw_id": "36684140", "job_id": "36684139_1", "user": "mmsh", "name": "nm"}
    cases = [
        ("w20_%20j.out", plain, "w20_0036684103.out"),
        ("trail_out%", plain, "trail_out"),
        (r"esc_\%j.out", plain, "esc_%j.out"),
        ("undef_%z.out", plain, "undef_%z.out"),
        ("nona_%a.out", plain, "nona_4294967294.out"),
        ("bmod_%b.out", plain, "bmod_4.out"),
        ("node_%N.out", node, "node_holy8a26602.out"),
        ("arr_%A_%a_%b.out", element, "arr_36684139_1_1.out"),
        ("%%j.out", plain, "%j.out"),
        ("job%4j.out", plain, "job36684103.out"),
    ]
    for pattern, fields, expected in cases:
        assert slurm._expand_log_pattern(pattern, fields) == expected, pattern


def test_expand_log_pattern_caps_the_pad_width_at_ten():
    """man sbatch: a width above 10 pads to 10, not to the width given."""
    fields = {"raw_id": "7", "job_id": "7", "user": "u", "name": "n", "node": ""}
    assert slurm._expand_log_pattern("%20j.out", fields) == "0000000007.out"


def test_expand_log_pattern_keeps_an_unresolvable_symbol_out_of_the_name():
    """A symbol with no value would otherwise name a file the job never wrote."""
    fields = {"raw_id": "7", "job_id": "7", "user": "u", "name": "n", "node": ""}
    assert slurm._expand_log_pattern("%N.out", fields) == ""


def test_first_node_takes_the_head_of_a_range():
    assert slurm._first_node("holygpu8a[10102,10202]") == "holygpu8a10102"
    assert slurm._first_node("holygpu8a[10301-10302]") == "holygpu8a10301"
    assert slurm._first_node("holy8a26602") == "holy8a26602"
    assert slurm._first_node("None assigned") == ""


def test_account_members_raises_when_sshare_fails(monkeypatch):
    """An empty list reads as an account with no members, which a failure is not."""
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (1, "", "no plugin"))
    with pytest.raises(slurm.CommandError):
        slurm.account_members("lab")


def test_job_owner_refuses_a_comma_list(monkeypatch):
    """squeue answers a list in its own sort order, so one owner would stand for all."""
    monkeypatch.setattr(process, "probe", lambda *a, **k: (0, "someone\n", ""))
    with pytest.raises(slurm.CommandError, match="names more than one job"):
        slurm.job_owner("1,2")


def test_job_owner_refuses_disagreeing_owners(monkeypatch):
    monkeypatch.setattr(process, "probe", lambda *a, **k: (0, "alice\nbob\n", ""))
    with pytest.raises(slurm.CommandError, match="more than one owner"):
        slurm.job_owner("1")


def test_job_nodes_asks_for_every_state(monkeypatch):
    """A suspended job still holds its nodes, and squeue's defaults would omit it."""
    seen = []

    def fake(cmd, **kwargs):
        seen.append(cmd)
        return (0, "", "")

    monkeypatch.setattr(process, "probe", fake)
    assert slurm.job_nodes("1") == []
    assert "-t" in seen[0] and "all" in seen[0]
