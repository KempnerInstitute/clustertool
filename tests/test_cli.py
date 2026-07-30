"""Tests for the CLI commands."""

import os
import shutil
import sys

from click.testing import CliRunner

from cluster_tools import completion, process, search, slurm
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


def test_kempner_gpu_node_status_parsing(monkeypatch):
    sample = "\n".join(
        [
            "hg1|idle|amd,gpu,h100,cc9.0",
            "hg2|mix|amd,gpu,h100,cc9.0",
            "hg3|drain*|amd,gpu,h100,cc9.0",
            "hg4|alloc|amd,gpu,h200,cc9.0",
            "hg5|down|intel,gpu,a100,cc8.0",
            "hg6|mix|intel,gpu,a100-mig,cc8.0",
            "hg7|resv|amd,gpu,rtx6000pro",
        ]
    )
    monkeypatch.setattr(slurm, "_run", lambda cmd, input_text=None: sample)
    rows = dict(slurm.kempner_gpu_node_status())
    assert rows["H100"] == {"idle": 1, "mixed": 1, "alloc": 0, "resv": 0, "drain": 1, "down": 0}
    assert rows["H200"]["alloc"] == 1
    assert rows["A100"]["down"] == 1
    assert rows["A100 MIG"]["mixed"] == 1
    assert rows["RTX"]["resv"] == 1
    assert [label for label, _ in slurm.kempner_gpu_node_status()] == [
        "A100",
        "A100 MIG",
        "H100",
        "H200",
        "RTX",
    ]


def test_status_bucket_covers_all_states():
    cases = {
        "idle": "idle",
        "plnd": "idle",
        "planned": "idle",
        "mix": "mixed",
        "mix-": "mixed",
        "mixed": "mixed",
        "alloc": "alloc",
        "allocated": "alloc",
        "comp": "alloc",
        "completing": "alloc",
        "resv": "resv",
        "reserved": "resv",
        "maint": "resv",
        "drain": "drain",
        "drain*": "drain",
        "drained*": "drain",
        "drng": "drain",
        "draining": "drain",
        "down": "down",
        "down*": "down",
        "inval": "down",
        "fail": "down",
        "boot": "down",
    }
    for state, bucket in cases.items():
        assert slurm._status_bucket(state) == bucket, state


def test_gpu_status_command(monkeypatch):
    monkeypatch.setattr(
        slurm,
        "kempner_gpu_node_status",
        lambda: [
            ("A100", {"idle": 1, "mixed": 20, "alloc": 6, "resv": 0, "drain": 1, "down": 0}),
            ("H100", {"idle": 0, "mixed": 72, "alloc": 20, "resv": 2, "drain": 1, "down": 1}),
        ],
    )
    result = CliRunner().invoke(main, ["gpu", "status"])
    assert result.exit_code == 0
    assert "GPU type" in result.output
    assert "A100" in result.output
    assert "28" in result.output
    assert "Total" in result.output


def test_nodes_list(monkeypatch):
    monkeypatch.setattr(
        slurm, "partition_nodes", lambda partition: [("node01", "idle"), ("node02", "mix")]
    )
    result = CliRunner().invoke(main, ["nodes", "list", "kempner_h100"])
    assert result.exit_code == 0
    assert "node01" in result.output
    assert "2 node(s)" in result.output


def test_search_finds_command_by_name():
    result = CliRunner().invoke(main, ["search", "fairshare"])
    assert result.exit_code == 0
    assert result.output.splitlines()[0].startswith("account fairshare")


def test_search_matches_slang_keyword():
    result = CliRunner().invoke(main, ["search", "kill"])
    assert result.exit_code == 0
    assert "jobs cancel" in result.output


def test_search_ranks_rarer_term_first():
    result = CliRunner().invoke(main, ["search", "gpu", "reservation"])
    assert result.exit_code == 0
    assert result.output.splitlines()[0].startswith("nodes reservations")


def test_search_no_match():
    result = CliRunner().invoke(main, ["search", "zzzznotacommand"])
    assert result.exit_code == 0
    assert "No commands matched" in result.output


def test_search_alias_find_works():
    result = CliRunner().invoke(main, ["find", "fairshare"])
    assert result.exit_code == 0
    assert "account fairshare" in result.output


def test_did_you_mean_group():
    result = CliRunner().invoke(main, ["accont"])
    assert result.exit_code != 0
    assert "Did you mean" in result.output
    assert "account" in result.output


def test_did_you_mean_subcommand():
    result = CliRunner().invoke(main, ["account", "membrs"])
    assert result.exit_code != 0
    assert "members" in result.output


def test_search_rank_unit():
    def rec(path, short="", kw=()):
        name_tokens = set(search._tokens(path))
        kw_tokens = {t for term in kw for t in search._tokens(term)}
        short_tokens = set(search._tokens(short))
        return {
            "path": path,
            "name": path.split()[-1],
            "short": short,
            "scope": "user",
            "name_tokens": name_tokens,
            "kw_tokens": kw_tokens,
            "short_tokens": short_tokens,
            "full_tokens": set(),
            "all_tokens": name_tokens | kw_tokens | short_tokens,
        }

    records = [
        rec("account fairshare", "Show fairshare standing and priority"),
        rec("nodes reservations", "List active reservations", kw=("reservation",)),
        rec("gpu util", "GPU occupancy per partition"),
        rec("jobs cancel", "Cancel jobs", kw=("kill",)),
    ]
    assert search.rank(records, ["fairshare"])[0]["path"] == "account fairshare"
    assert search.rank(records, ["kill"])[0]["path"] == "jobs cancel"
    assert search.rank(records, ["reservation"])[0]["path"] == "nodes reservations"
    assert search.rank(records, ["zzz"]) == []


def test_completion_prints_eval_line():
    result = CliRunner().invoke(main, ["completion", "bash"])
    assert result.exit_code == 0
    assert "_CLUSTERTOOLS_COMPLETE=bash_source clustertools" in result.output


def test_completion_install_is_idempotent(tmp_path, monkeypatch):
    rc = tmp_path / ".bashrc"
    monkeypatch.setattr(completion, "rc_path", lambda shell: rc)
    first = CliRunner().invoke(main, ["completion", "bash", "--install"])
    assert first.exit_code == 0
    assert "eval " in rc.read_text()
    second = CliRunner().invoke(main, ["completion", "bash", "--install"])
    assert "already set up" in second.output
    assert rc.read_text().count("eval ") == 1


def test_complete_job_ids(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    monkeypatch.setattr(completion, "_run", lambda cmd: "101\n102\n1123\n")
    assert completion.complete_job_ids(None, None, "1") == ["101", "102", "1123"]
    assert completion.complete_job_ids(None, None, "11") == ["1123"]


def test_complete_partitions_strips_default_marker(monkeypatch):
    monkeypatch.setattr(completion, "_run", lambda cmd: "kempner*\nkempner_h100\nsapphire\n")
    assert completion.complete_partitions(None, None, "kempner") == ["kempner", "kempner_h100"]


def test_complete_accounts(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    monkeypatch.setattr(completion, "_run", lambda cmd: "kempner_dev\nkempner_grads\n")
    assert completion.complete_accounts(None, None, "kempner_d") == ["kempner_dev"]


def test_completion_callbacks_safe_on_error(monkeypatch):
    monkeypatch.setenv("USER", "alice")

    def boom(cmd):
        raise process.CommandError("nope")

    monkeypatch.setattr(completion, "_run", boom)
    assert completion.complete_job_ids(None, None, "") == []
    assert completion.complete_partitions(None, None, "") == []
    assert completion.complete_accounts(None, None, "") == []


def test_me_overview(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    monkeypatch.setattr(
        slurm,
        "my_jobs",
        lambda user: [
            ("111", "RUNNING", "kempner_h100", "2:00:00", "None"),
            ("222", "PENDING", "kempner", "0:00", "Priority"),
        ],
    )
    monkeypatch.setattr(slurm, "user_gpu_count", lambda user: 4)
    monkeypatch.setattr(slurm, "user_fairshare", lambda user: [("kempner_dev", "0.87")])
    result = CliRunner().invoke(main, ["me"])
    assert result.exit_code == 0
    assert "overview for alice" in result.output
    assert "1 running, 1 pending, 4 GPU(s)" in result.output
    assert "Priority" in result.output
    assert "kempner_dev" in result.output


def test_me_explicit_user(monkeypatch):
    monkeypatch.setattr(slurm, "my_jobs", lambda user: [])
    monkeypatch.setattr(slurm, "user_gpu_count", lambda user: 0)
    monkeypatch.setattr(slurm, "user_fairshare", lambda user: [])
    result = CliRunner().invoke(main, ["me", "-u", "bob"])
    assert result.exit_code == 0
    assert "overview for bob" in result.output
    assert "0 running, 0 pending, 0 GPU(s)" in result.output


def test_my_jobs_parsing(monkeypatch):
    monkeypatch.setattr(
        slurm,
        "_run",
        lambda cmd: "111|RUNNING|shared|1:00|None\n222|PENDING|kempner|0:00|Priority\n",
    )
    assert slurm.my_jobs("alice") == [
        ("111", "RUNNING", "shared", "1:00", "None"),
        ("222", "PENDING", "kempner", "0:00", "Priority"),
    ]


def test_user_fairshare_parsing(monkeypatch):
    monkeypatch.setattr(slurm, "_run", lambda cmd: "kempner_dev|0.5\nkempner_grads|0.3\n")
    assert slurm.user_fairshare("alice") == [("kempner_dev", "0.5"), ("kempner_grads", "0.3")]


def test_user_gpu_count(monkeypatch):
    monkeypatch.setattr(
        slurm, "_run", lambda cmd: "cpu=4,mem=32G,gres/gpu=2,node=1\ncpu=8,gres/gpu=1\n"
    )
    assert slurm.user_gpu_count("alice") == 3


def test_jobs_new_builds_script():
    result = CliRunner().invoke(
        main,
        ["jobs", "new", "--gpu-type", "h100", "--gpus", "2", "-A", "kempner_dev", "-J", "train"],
    )
    assert result.exit_code == 0
    out = result.output
    assert "--partition=kempner_h100" in out
    assert "--gres=gpu:2" in out
    assert "--cpus-per-task=48" in out
    assert "--mem=720000" in out
    assert "--account=kempner_dev" in out
    assert "--job-name=train" in out


def test_jobs_new_submit(monkeypatch):
    captured = {}

    def fake_run(cmd, input_text=None):
        captured["cmd"] = cmd
        captured["script"] = input_text
        return "Submitted batch job 999"

    monkeypatch.setattr(process, "run", fake_run)
    result = CliRunner().invoke(
        main, ["jobs", "new", "--gpu-type", "a100", "-A", "LAB", "--submit"]
    )
    assert result.exit_code == 0
    assert captured["cmd"] == ["sbatch"]
    assert "--partition=kempner" in captured["script"]
    assert "Submitted batch job 999" in result.output


def test_jobs_new_output_file(tmp_path):
    path = tmp_path / "job.sh"
    result = CliRunner().invoke(
        main, ["jobs", "new", "--gpu-type", "rtx", "-A", "LAB", "-o", str(path)]
    )
    assert result.exit_code == 0
    assert "--partition=kempner_rtx" in path.read_text()


def test_jobs_new_prompts():
    result = CliRunner().invoke(main, ["jobs", "new"], input="h200\nkempner_dev\n")
    assert result.exit_code == 0
    assert "--partition=kempner_h200" in result.output


def test_gpu_session_jupyter(monkeypatch):
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        return 0

    monkeypatch.setattr(process, "stream", fake_stream)
    result = CliRunner().invoke(
        main, ["gpu", "session", "h100", "-A", "LAB", "--jupyter", "--port", "9999"]
    )
    assert result.exit_code == 0
    joined = " ".join(captured["cmd"])
    assert "bash" in captured["cmd"]
    assert "jupyter lab --no-browser" in joined
    assert "9999" in joined
    assert "--gres=gpu:1" in joined


def test_gpu_session_plain(monkeypatch):
    captured = {}

    def fake_stream(cmd):
        captured["cmd"] = cmd
        return 0

    monkeypatch.setattr(process, "stream", fake_stream)
    result = CliRunner().invoke(main, ["gpu", "session", "a100", "-A", "LAB"])
    assert result.exit_code == 0
    assert "bash" not in captured["cmd"]
    assert "--account=LAB" in captured["cmd"]


def test_mem_to_mb():
    assert 2.0 < slurm._mem_to_mb("2136K") < 2.1
    assert slurm._mem_to_mb("1000G") == 1024000.0
    assert slurm._mem_to_mb("") == 0.0


def test_job_accounting_parsing(monkeypatch):
    monkeypatch.setattr(
        slurm, "_run", lambda cmd: "FAILED|1:0|00:14:51|03:00:00|1000G|cpu=96,gres/gpu=8|node01\n"
    )
    info = slurm.job_accounting("123")
    assert info["state"] == "FAILED"
    assert info["exit_code"] == "1:0"
    assert info["req_mem"] == "1000G"
    assert info["nodelist"] == "node01"


def test_diagnose_oom_and_timeout():
    from cluster_tools.commands.jobs.debug import _diagnose

    oom = _diagnose({"state": "OUT_OF_MEMORY", "exit_code": "0:0"}, "")
    assert any("out of memory" in cause.lower() for cause, _ in oom)
    timeout = _diagnose({"state": "TIMEOUT", "exit_code": "0:0"}, "")
    assert any("time limit" in cause.lower() for cause, _ in timeout)


def test_diagnose_exit_code_and_log():
    from cluster_tools.commands.jobs.debug import _diagnose

    findings = _diagnose({"state": "FAILED", "exit_code": "1:0"}, "CUDA out of memory. Tried ...")
    causes = [cause for cause, _ in findings]
    assert any("code 1" in cause for cause in causes)
    assert any("CUDA" in cause for cause in causes)


def test_jobs_debug_command(monkeypatch):
    monkeypatch.setattr(
        slurm,
        "job_accounting",
        lambda jid: {
            "state": "FAILED",
            "exit_code": "1:0",
            "elapsed": "0:14:51",
            "timelimit": "3:00:00",
            "req_mem": "1000G",
            "req_tres": "",
            "nodelist": "node01",
        },
    )
    monkeypatch.setattr(slurm, "job_maxrss_mb", lambda jid: 2.0)
    monkeypatch.setattr(
        slurm, "job_output_tail", lambda jid: "ModuleNotFoundError: no module named x"
    )
    result = CliRunner().invoke(main, ["jobs", "debug", "123"])
    assert result.exit_code == 0
    assert "FAILED (exit 1:0)" in result.output
    assert "Exited with non-zero code 1" in result.output
    assert "module was missing" in result.output


def test_jobs_debug_no_record(monkeypatch):
    monkeypatch.setattr(slurm, "job_accounting", lambda jid: {})
    result = CliRunner().invoke(main, ["jobs", "debug", "999"])
    assert result.exit_code != 0
    assert "No accounting record" in result.output


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


def test_storage_quota_home(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        process, "stream", lambda cmd, extra_env=None: captured.update(cmd=cmd) or 0
    )
    monkeypatch.setenv("HOME", "/n/home14/alice")
    result = CliRunner().invoke(main, ["storage", "quota", "home"])
    assert result.exit_code == 0
    assert captured["cmd"] == ["quota", "/n/home14/alice"]


def _capture_stream(monkeypatch):
    calls = []
    monkeypatch.setattr(process, "stream", lambda cmd, extra_env=None: calls.append(cmd) or 0)
    return calls


def test_jobs_list_default(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "list"])
    assert result.exit_code == 0
    assert calls[0] == ["squeue", "-u", "alice"]


def test_jobs_list_filters(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main, ["jobs", "list", "-u", "bob", "-t", "pending", "-p", "kempner", "-A", "kempner_dev"]
    )
    assert result.exit_code == 0
    assert calls[0] == [
        "squeue",
        "-u",
        "bob",
        "-t",
        "PENDING",
        "-p",
        "kempner",
        "-A",
        "kempner_dev",
    ]


def test_jobs_show(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "show", "111", "222"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "show", "job", "-dd", "111,222"]


def test_jobs_why(monkeypatch):
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: "PENDING Priority\n")
    result = CliRunner().invoke(main, ["jobs", "why", "12345"])
    assert result.exit_code == 0
    assert "Priority" in result.output
    assert calls[0] == ["sprio", "-j", "12345", "-l"]


def test_jobs_history(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "history", "--days", "3"])
    assert result.exit_code == 0
    assert calls[0][:5] == ["sacct", "-u", "alice", "-S", "now-3days"]
    assert "-X" in calls[0]


def test_jobs_cancel_ids(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel", "111", "222"])
    assert result.exit_code == 0
    assert calls[0] == ["scancel", "111", "222"]


def test_jobs_cancel_all(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel", "--all"])
    assert result.exit_code == 0
    assert calls[0] == ["scancel", "-u", "alice"]


def test_jobs_cancel_pending(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel", "--pending"])
    assert result.exit_code == 0
    assert calls[0] == ["scancel", "-u", "alice", "-t", "PENDING"]


def test_jobs_cancel_none_errors(monkeypatch):
    _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel"])
    assert result.exit_code != 0


def test_jobs_hold(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "hold", "111", "222"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "hold", "111,222"]


def test_jobs_release(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "release", "111"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "release", "111"]


def test_jobs_requeue(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "requeue", "111"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "requeue", "111"]


def test_jobs_submit_passthrough(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "submit", "-p", "kempner", "job.sh"])
    assert result.exit_code == 0
    assert calls[0] == ["sbatch", "-p", "kempner", "job.sh"]


def test_account_fairshare_self(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "fairshare"])
    assert result.exit_code == 0
    assert calls[0] == ["sshare", "-U", "-u", "alice"]


def test_account_fairshare_account(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "fairshare", "kempner_dev"])
    assert result.exit_code == 0
    assert calls[0] == ["sshare", "--account=kempner_dev", "-a"]


def test_account_usage_self(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "usage", "--days", "7"])
    assert result.exit_code == 0
    assert calls[0][0] == "stotal"
    assert calls[0][1:3] == ["-u", "alice"]
    assert "-S" in calls[0] and "-E" in calls[0] and "-d" in calls[0]


def test_account_usage_efficiency_account(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "usage", "kempner_dev", "--efficiency"])
    assert result.exit_code == 0
    assert calls[0][0] == "seff-account"
    assert calls[0][1:3] == ["-A", "kempner_dev"]


def test_account_usage_account_and_user_error(monkeypatch):
    _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "usage", "kempner_dev", "-u", "alice"])
    assert result.exit_code != 0


def test_account_limits(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "limits", "kempner_dev"])
    assert result.exit_code == 0
    assert calls[0][:4] == ["sacctmgr", "show", "assoc", "account=kempner_dev"]
    assert calls[0][4].startswith("format=")


def test_nodes_partitions_default(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "partitions"])
    assert result.exit_code == 0
    assert calls[0] == ["spart"]


def test_nodes_partitions_filter(monkeypatch):
    monkeypatch.setattr(
        process, "run", lambda cmd, input_text=None: "HEADER\nkempner row\nother row\n"
    )
    result = CliRunner().invoke(main, ["nodes", "partitions", "--filter", "kempner"])
    assert result.exit_code == 0
    assert "HEADER" in result.output
    assert "kempner row" in result.output
    assert "other row" not in result.output


def test_storage_usage(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["storage", "usage", "netscratch", "-g", "kempner_dev"])
    assert result.exit_code == 0
    assert calls[0] == ["quota", "--group-user-usage", "kempner_dev", "/n/netscratch"]


def test_storage_scratch(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["storage", "scratch", "/n/netscratch"])
    assert result.exit_code == 0
    assert calls[0] == ["quota", "/n/netscratch"]
    assert "90 days" in result.output


def test_storage_lfs_stripe_get(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["storage", "lfs-stripe", "/n/holylfs06/x"])
    assert result.exit_code == 0
    assert calls[0] == ["lfs", "getstripe", "/n/holylfs06/x"]


def test_storage_lfs_stripe_set(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["storage", "lfs-stripe", "/n/holylfs06/x", "-c", "8"])
    assert result.exit_code == 0
    assert calls[0] == ["lfs", "setstripe", "-c", "8", "/n/holylfs06/x"]


def test_gpu_session_a100(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["gpu", "session", "a100", "-A", "kempner_dev"])
    assert result.exit_code == 0
    cmd = calls[0]
    assert cmd[0] == "salloc"
    assert "-p" in cmd and "kempner" in cmd
    assert "--account=kempner_dev" in cmd
    assert "--gres=gpu:1" in cmd
    assert "--cpus-per-task=16" in cmd
    assert "--mem=240000" in cmd


def test_gpu_session_h100(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["gpu", "session", "h100", "-A", "lab"])
    assert result.exit_code == 0
    cmd = calls[0]
    assert "kempner_h100" in cmd
    assert "--cpus-per-task=24" in cmd
    assert "--mem=360000" in cmd


def test_gpu_session_requires_account(monkeypatch):
    _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["gpu", "session", "a100"])
    assert result.exit_code != 0


def test_gpu_session_bad_type(monkeypatch):
    _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["gpu", "session", "v100", "-A", "lab"])
    assert result.exit_code != 0


def test_gpu_session_extra_args(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main, ["gpu", "session", "a100", "-A", "lab", "--mem=500000", "-J", "dev"]
    )
    assert result.exit_code == 0
    cmd = calls[0]
    assert "--mem=240000" in cmd
    assert cmd[-3:] == ["--mem=500000", "-J", "dev"]


def test_nodes_down(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "down", "-p", "kempner"])
    assert result.exit_code == 0
    assert calls[0] == ["sinfo", "-R", "-p", "kempner"]


def test_nodes_load_default(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "load"])
    assert result.exit_code == 0
    assert calls[0] == ["lsload"]


def test_nodes_load_filter(monkeypatch):
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: "HEADER\nholygpu row\nother\n")
    result = CliRunner().invoke(main, ["nodes", "load", "-f", "holygpu"])
    assert result.exit_code == 0
    assert "HEADER" in result.output and "holygpu row" in result.output
    assert "other" not in result.output


def test_nodes_reservations(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "reservations"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "show", "reservation"]


def test_jobs_top(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "top", "123"])
    assert result.exit_code == 0
    assert calls[0][:4] == ["sstat", "-a", "-j", "123"]


def test_jobs_queue(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "queue", "kempner_h100"])
    assert result.exit_code == 0
    assert calls[0] == ["showq", "-o", "-p", "kempner_h100"]


def test_jobs_log_paths(monkeypatch):
    monkeypatch.setattr(
        process, "run", lambda cmd, input_text=None: "JobId=1 StdOut=/n/out.log StdErr=/n/err.log"
    )
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "log", "1"])
    assert result.exit_code == 0
    assert "/n/out.log" in result.output and "/n/err.log" in result.output
    assert not calls


def test_jobs_log_follow(monkeypatch):
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: "StdOut=/n/out.log")
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "log", "1", "-f"])
    assert result.exit_code == 0
    assert calls[0] == ["tail", "-f", "/n/out.log"]


def test_jobs_log_missing(monkeypatch):
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: "JobId=1 JobState=RUNNING")
    result = CliRunner().invoke(main, ["jobs", "log", "1"])
    assert result.exit_code != 0


def test_jobs_script(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "script", "123"])
    assert result.exit_code == 0
    assert calls[0] == ["sacct", "-j", "123", "--batch"]


def test_jobs_list_start(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "list", "--start"])
    assert result.exit_code == 0
    assert calls[0] == ["squeue", "-u", "alice", "--start"]


def test_diag_scheduler(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["diag", "scheduler"])
    assert result.exit_code == 0
    assert calls[0] == ["sdiag"]


def test_jobs_set_priority(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "set-priority", "123", "5000"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "update", "jobid=123", "priority=5000"]


def test_jobs_setprio_alias(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "setprio", "123", "5000"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "update", "jobid=123", "priority=5000"]


def test_jobs_priorities(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "priorities", "kempner_h100"])
    assert result.exit_code == 0
    assert calls[0] == ["sprio", "-p", "kempner_h100"]


def test_gpu_util(monkeypatch):
    monkeypatch.setattr(slurm, "partition_gpu_util", lambda p: (100, 20, 80, 40, 50.0))
    result = CliRunner().invoke(main, ["gpu", "util", "kempner_h100"])
    assert result.exit_code == 0
    assert "kempner_h100" in result.output
    assert "50.0%" in result.output


def test_nodes_resume_explicit(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "resume", "n1", "n2", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "update", "NodeName=n1,n2", "State=RESUME"]


def test_nodes_resume_partition(monkeypatch):
    monkeypatch.setattr(slurm, "drained_nodes", lambda p: ["n3", "n4"])
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "resume", "-p", "kempner_requeue", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "update", "NodeName=n3,n4", "State=RESUME"]


def test_nodes_resume_needs_target(monkeypatch):
    _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "resume"])
    assert result.exit_code != 0


def test_account_top_users(monkeypatch):
    out = "acct 700 0.1 900 0.2\n acct alice 20 0.1 500 0.2 0.3\n acct bob 20 0.1 900 0.2 0.3\n"
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: out)
    result = CliRunner().invoke(main, ["account", "top-users", "kempner_dev"])
    assert result.exit_code == 0
    assert result.output.index("bob") < result.output.index("alice")


def test_account_qos_default(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "qos"])
    assert result.exit_code == 0
    assert calls[0][:3] == ["sacctmgr", "show", "qos"]


def test_account_qos_filter(monkeypatch):
    out = "Name Priority\n---- ----\nnormal 0\nkempner_h100_priority 0\n"
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: out)
    result = CliRunner().invoke(main, ["account", "qos", "-f", "kempner"])
    assert result.exit_code == 0
    assert "kempner_h100_priority" in result.output
    assert "normal" not in result.output


def test_account_add_user(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "add-user", "alice", "kempner_dev", "-y"])
    assert result.exit_code == 0
    assert calls[0] == [
        "sacctmgr",
        "-i",
        "add",
        "user",
        "name=alice",
        "account=kempner_dev",
        "fairshare=parent",
    ]


def test_account_help_splits_user_and_admin():
    result = CliRunner().invoke(main, ["account", "--help"])
    assert result.exit_code == 0
    out = result.output
    assert "User Commands:" in out
    assert "Admin Commands:" in out
    admin_idx = out.index("Admin Commands:")
    assert out.index("User Commands:") < admin_idx
    assert out.index("members") < admin_idx
    for name in ("add-user", "remove-user", "set-fairshare"):
        assert out.index(name) > admin_idx


def test_gpu_help_has_no_admin_section():
    result = CliRunner().invoke(main, ["gpu", "--help"])
    assert result.exit_code == 0
    assert "Admin Commands:" not in result.output
    assert "Commands:" in result.output


def test_account_remove_user(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "remove-user", "alice", "kempner_dev", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["sacctmgr", "-i", "remove", "user", "alice", "account=kempner_dev"]


def test_account_set_fairshare(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main, ["account", "set-fairshare", "alice", "kempner_dev", "50", "-y"]
    )
    assert result.exit_code == 0
    assert calls[0] == [
        "sacctmgr",
        "-i",
        "modify",
        "user",
        "where",
        "name=alice",
        "account=kempner_dev",
        "set",
        "fairshare=50",
    ]


def test_storage_lfs_inodes(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["storage", "lfs-inodes", "holylfs06"])
    assert result.exit_code == 0
    assert calls[0] == ["lfs", "df", "-i", "/n/holylfs06"]


def test_gpu_pulse_passthrough(monkeypatch):
    calls = []
    monkeypatch.setattr(process, "stream", lambda cmd, extra_env=None: calls.append(cmd) or 0)
    result = CliRunner().invoke(main, ["gpu", "pulse", "--once", "--gpus", "0,1"])
    assert result.exit_code == 0
    assert calls[0][:3] == [sys.executable, "-m", "kempnerpulse"]
    assert calls[0][3:] == ["--once", "--gpus", "0,1"]


def test_gpu_pulse_exit_code(monkeypatch):
    monkeypatch.setattr(process, "stream", lambda cmd, extra_env=None: 3)
    result = CliRunner().invoke(main, ["gpu", "pulse", "--backend", "bogus"])
    assert result.exit_code == 3


def test_jobs_scope_passthrough(monkeypatch):
    calls = []
    monkeypatch.setattr(process, "stream", lambda cmd, extra_env=None: calls.append(cmd) or 0)
    result = CliRunner().invoke(main, ["jobs", "scope", "-D", "3", "--gpu"])
    assert result.exit_code == 0
    assert calls[0][:3] == [sys.executable, "-m", "jobscope"]
    assert calls[0][3:] == ["-D", "3", "--gpu"]


def test_jobs_scope_forwards_subcommand(monkeypatch):
    calls = []
    monkeypatch.setattr(process, "stream", lambda cmd, extra_env=None: calls.append(cmd) or 0)
    result = CliRunner().invoke(main, ["jobs", "scope", "detail", "1234567", "--ext"])
    assert result.exit_code == 0
    assert calls[0][3:] == ["detail", "1234567", "--ext"]


def test_jobs_scope_exit_code(monkeypatch):
    monkeypatch.setattr(process, "stream", lambda cmd, extra_env=None: 2)
    result = CliRunner().invoke(main, ["jobs", "scope", "bogus"])
    assert result.exit_code == 2


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


def test_gpu_avail_cpus_per_gpu_override(monkeypatch):
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "x")])
    monkeypatch.setattr(slurm, "node_free_resources", lambda node: (8, 40, 1000000))
    result = CliRunner().invoke(
        main, ["gpu", "avail", "kempner_eng", "--cpus-per-gpu", "20", "--mem-per-gpu", "100000"]
    )
    assert result.exit_code == 0
    assert "capped by 20 CPU" in result.output
    assert _node_fields(result.output)["n1"][1] == "2"


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
        main, ["jobs", "violators", "custom", "--cpus-per-gpu", "40", "--mem-per-gpu", "100000"]
    )
    assert result.exit_code == 0
    assert "201" in result.output


def test_jobs_violators_old_flag_rejected(monkeypatch):
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: [])
    result = CliRunner().invoke(
        main, ["jobs", "violators", "custom", "--cpu-per-gpu", "40", "--mem-per-gpu", "100000"]
    )
    assert result.exit_code != 0
    assert "no such option" in result.output.lower()


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
