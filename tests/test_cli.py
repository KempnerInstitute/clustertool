"""Tests for the CLI commands."""

import json
import os
import pwd
import re
import shutil
import sys

import click
import pytest
from click.testing import CliRunner
from test_gpuhealth import ECC_DISABLED, HEALTHY, _gpu, _nvlink, _smi_xml

from clustertool import completion, fabric, gpuhealth, process, qos, search, site, slurm, storage
from clustertool.cli import main
from clustertool.commands.account import _write


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


def test_gpu_node_status_parsing(monkeypatch):
    sample = "\n".join(
        [
            "hg1|idle|amd,gpu,h100,cc9.0|gpu:nvidia_h100_80gb_hbm3:4(S:0-1)",
            "hg2|mix|amd,gpu,h100,cc9.0|gpu:nvidia_h100_80gb_hbm3:4(S:0-1)",
            "hg3|drain*|amd,gpu,h100,cc9.0|gpu:nvidia_h100_80gb_hbm3:4(S:0-1)",
            "hg4|alloc|amd,gpu,h200,cc9.0|gpu:nvidia_h200:4(S:0-1)",
            "hg5|down|intel,gpu,a100,cc8.0|gpu:nvidia_a100-sxm4-40gb:4(S:0-1)",
            "hg6|mix|intel,gpu,a100-mig,cc8.0|gpu:nvidia_a100_1g.5gb:8",
            "hg7|resv|amd,gpu,rtx6000pro|gpu:nvidia_rtx_pro_6000:8(S:0-1)",
            "hc1|idle|intel,avx|(null)",
        ]
    )
    monkeypatch.setattr(slurm.process, "probe", lambda cmd, timeout=None: (0, sample, ""))
    rows = dict(slurm.gpu_node_status())
    assert rows["H100"] == {"idle": 1, "mixed": 1, "alloc": 0, "resv": 0, "drain": 1, "down": 0}
    assert rows["H200"]["alloc"] == 1
    assert rows["A100"]["down"] == 1
    assert rows["A100 MIG"]["mixed"] == 1
    assert rows["RTX"]["resv"] == 1
    assert [label for label, _ in slurm.gpu_node_status()] == [
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
        "gpu_node_status",
        lambda: [
            ("A100", {"idle": 1, "mixed": 20, "alloc": 6, "resv": 0, "drain": 1, "down": 0}),
            ("H100", {"idle": 0, "mixed": 72, "alloc": 20, "resv": 2, "drain": 1, "down": 1}),
        ],
    )
    result = CliRunner().invoke(main, ["gpu", "status"])
    assert result.exit_code == 0
    assert "GPU TYPE" in result.output
    assert "A100" in result.output
    assert "28" in result.output
    assert "TOTAL" in result.output


def test_gpu_status_reports_the_configured_partition(monkeypatch):
    monkeypatch.setattr(site, "requeue_partition", lambda: "gpu_requeue")
    monkeypatch.setattr(
        slurm,
        "gpu_node_status",
        lambda: [("A100", {"idle": 1, "mixed": 0, "alloc": 0, "resv": 0, "drain": 0, "down": 0})],
    )
    result = CliRunner().invoke(main, ["gpu", "status"])
    assert result.exit_code == 0
    assert "gpu_requeue" in result.output
    assert "kempner" not in result.output


def test_gpu_status_empty_names_the_configured_partition(monkeypatch):
    monkeypatch.setattr(site, "requeue_partition", lambda: "gpu_requeue")
    monkeypatch.setattr(slurm, "gpu_node_status", lambda: [])
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, "", ""))
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: "")
    result = CliRunner().invoke(main, ["gpu", "status"])
    assert result.exit_code == 0
    assert "No GPU nodes found in gpu_requeue." in result.output


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
    assert "_CLUSTERTOOL_COMPLETE=bash_source clustertool" in result.output


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


def test_me_access(monkeypatch):
    monkeypatch.setattr(slurm, "my_jobs", lambda user: [])
    monkeypatch.setattr(slurm, "user_gpu_count", lambda user: 0)
    monkeypatch.setattr(slurm, "user_fairshare", lambda user: [])
    monkeypatch.setattr(
        slurm,
        "user_associations",
        lambda user: [("kempner_dev", "kempner_h100", "kemp_gpu4"), ("kempner_eng", "", "normal")],
    )
    monkeypatch.setattr(slurm, "default_account", lambda user: "kempner_dev")
    monkeypatch.setattr(storage, "user_groups", lambda user: ["kempner_dev", "slurm_group_x"])
    result = CliRunner().invoke(main, ["me", "-u", "alice", "--access"])
    assert result.exit_code == 0
    assert "kempner_dev  (default)" in result.output
    assert "Where you can submit" in result.output
    assert "kempner_h100" in result.output
    assert "slurm_group_x" in result.output


def test_me_default_hides_access(monkeypatch):
    monkeypatch.setattr(slurm, "my_jobs", lambda user: [])
    monkeypatch.setattr(slurm, "user_gpu_count", lambda user: 0)
    monkeypatch.setattr(slurm, "user_fairshare", lambda user: [])
    result = CliRunner().invoke(main, ["me", "-u", "alice"])
    assert result.exit_code == 0
    assert "Where you can submit" not in result.output


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
    assert "--mem=737280" in out
    assert "--account=kempner_dev" in out
    assert "--job-name=train" in out


def test_jobs_new_submit(monkeypatch):
    captured = {}

    def fake_probe(cmd, timeout=None, input_text=None):
        captured["cmd"] = cmd
        captured["script"] = input_text
        return (0, "Submitted batch job 999", "")

    monkeypatch.setattr(process, "probe", fake_probe)
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
        slurm.process,
        "probe",
        lambda cmd, timeout=None: (
            0,
            "123|FAILED|1:0|00:14:51|03:00:00|1000G|cpu=96,gres/gpu=8|node01\n",
            "",
        ),
    )
    info = slurm.job_accounting("123")
    assert info["state"] == "FAILED"
    assert info["exit_code"] == "1:0"
    assert info["req_mem"] == "1000G"
    assert info["nodelist"] == "node01"


def test_diagnose_oom_and_timeout():
    from clustertool.commands.jobs.debug import _diagnose

    oom = _diagnose({"state": "OUT_OF_MEMORY", "exit_code": "0:0"})
    assert any("out of memory" in cause.lower() for cause, _ in oom)
    timeout = _diagnose({"state": "TIMEOUT", "exit_code": "0:0"})
    assert any("time limit" in cause.lower() for cause, _ in timeout)


def test_diagnose_exit_code_and_log():
    from clustertool.commands.jobs.debug import _diagnose, _log_findings

    findings = _diagnose({"state": "FAILED", "exit_code": "1:0"})
    assert any("code 1" in cause for cause, _ in findings)
    assert any("CUDA" in cause for cause, _ in _log_findings("CUDA out of memory. Tried ..."))


def test_log_patterns_do_not_override_a_completed_state():
    """A job Slurm recorded as COMPLETED succeeded, whatever text it printed."""
    from clustertool.commands.jobs.debug import _diagnose

    findings = _diagnose({"state": "COMPLETED", "exit_code": "0:0"})
    assert [cause for cause, _ in findings] == ["Completed successfully"]


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


def test_jobs_debug_array_shows_every_state(monkeypatch):
    """Reporting element zero let an array whose elements mostly failed read as COMPLETED."""
    monkeypatch.setattr(
        slurm,
        "job_accounting",
        lambda j: {
            "state": "COMPLETED",
            "exit_code": "0:0",
            "elapsed": "00:02:09",
            "timelimit": "3-00:00:00",
            "req_mem": "360G",
            "req_tres": "",
            "nodelist": "n1",
            "element_count": 177,
            "states": {"FAILED": 96, "COMPLETED": 75, "CANCELLED by 11222": 6},
        },
    )
    result = CliRunner().invoke(main, ["jobs", "debug", "9541734"])
    assert result.exit_code == 0
    assert "an array of 177 elements" in result.output
    assert "96  FAILED" in result.output
    assert "Completed successfully" not in result.output


def test_jobs_debug_pending_points_at_jobs_why(monkeypatch):
    monkeypatch.setattr(
        slurm,
        "job_accounting",
        lambda j: {
            "state": "PENDING",
            "exit_code": "0:0",
            "elapsed": "00:00:00",
            "timelimit": "06:00:00",
            "req_mem": "64G",
            "req_tres": "",
            "nodelist": "None assigned",
            "element_count": 1,
            "states": {"PENDING": 1},
        },
    )
    result = CliRunner().invoke(main, ["jobs", "debug", "123"])
    assert result.exit_code == 0
    assert "has not started" in result.output
    assert "jobs why 123" in result.output


def test_jobs_debug_does_not_invent_a_signal_for_oom(monkeypatch):
    """Slurm marks OOM as exit 0:125; 125 is not a signal, and kill tops out at 64."""
    monkeypatch.setattr(
        slurm,
        "job_accounting",
        lambda j: {
            "state": "OUT_OF_MEMORY",
            "exit_code": "0:125",
            "elapsed": "00:03:28",
            "timelimit": "01:00:00",
            "req_mem": "64G",
            "req_tres": "",
            "nodelist": "n1",
            "element_count": 1,
            "states": {"OUT_OF_MEMORY": 1},
        },
    )
    monkeypatch.setattr(slurm, "job_maxrss_mb", lambda j: 0.0)
    monkeypatch.setattr(slurm, "job_output_tail", lambda j: "")
    result = CliRunner().invoke(main, ["jobs", "debug", "123"])
    assert result.exit_code == 0
    assert "Ran out of memory" in result.output
    assert "signal 125" not in result.output


def test_jobs_debug_does_not_blame_memory_for_a_cancellation(monkeypatch):
    """scancel kills with SIGKILL, so 0:9 on a CANCELLED job says nothing about memory."""
    monkeypatch.setattr(
        slurm,
        "job_accounting",
        lambda j: {
            "state": "CANCELLED by 11222",
            "exit_code": "0:9",
            "elapsed": "00:03:28",
            "timelimit": "01:00:00",
            "req_mem": "64G",
            "req_tres": "",
            "nodelist": "n1",
            "element_count": 1,
            "states": {"CANCELLED": 1},
        },
    )
    monkeypatch.setattr(slurm, "job_maxrss_mb", lambda j: 0.0)
    monkeypatch.setattr(slurm, "job_output_tail", lambda j: "")
    result = CliRunner().invoke(main, ["jobs", "debug", "123"])
    assert result.exit_code == 0
    assert "Canceled" in result.output
    assert "out-of-memory" not in result.output


def test_jobs_debug_still_reads_a_signal_that_adds_information(monkeypatch):
    """FAILED alone does not explain the death, so the SIGKILL hint is worth keeping."""
    monkeypatch.setattr(
        slurm,
        "job_accounting",
        lambda j: {
            "state": "FAILED",
            "exit_code": "0:9",
            "elapsed": "00:03:28",
            "timelimit": "01:00:00",
            "req_mem": "64G",
            "req_tres": "",
            "nodelist": "n1",
            "element_count": 1,
            "states": {"FAILED": 1},
        },
    )
    monkeypatch.setattr(slurm, "job_maxrss_mb", lambda j: 0.0)
    monkeypatch.setattr(slurm, "job_output_tail", lambda j: "")
    result = CliRunner().invoke(main, ["jobs", "debug", "123"])
    assert result.exit_code == 0
    assert "signal 9" in result.output


def test_jobs_debug_no_record(monkeypatch):
    monkeypatch.setattr(slurm, "job_accounting", lambda jid: {})
    result = CliRunner().invoke(main, ["jobs", "debug", "999"])
    assert result.exit_code != 0
    assert "no accounting record" in result.output


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
    result = CliRunner().invoke(main, ["storage", "quota", "/n/netscratch", "-u", "auser"])
    assert result.exit_code == 0
    assert captured["cmd"] == ["quota", "-u", "auser", "/n/netscratch"]


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
    """The default user is the account this process runs as, not a stale $USER."""
    monkeypatch.setenv("USER", "someone-else")
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "list"])
    assert result.exit_code == 0
    assert calls[0] == ["squeue", "-u", pwd.getpwuid(os.getuid()).pw_name]


def test_jobs_list_trims_a_filter_value(monkeypatch):
    """A stray space passes an account lookup and then matches no job."""
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
    result = CliRunner().invoke(main, ["jobs", "list", "-A", " kempner_dev "])
    assert result.exit_code == 0
    assert calls[0][-1] == "kempner_dev"


def test_jobs_list_rejects_an_empty_filter(monkeypatch):
    """An unset shell variable would otherwise widen the query rather than fail."""
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(slurm, "partition_exists", lambda p: False)
    result = CliRunner().invoke(main, ["jobs", "list", "-p", ""])
    assert result.exit_code != 0
    assert calls == []


def test_jobs_list_filters(monkeypatch):
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(slurm, "user_exists", lambda u: True)
    monkeypatch.setattr(slurm, "partition_exists", lambda p: True)
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
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
    """man scontrol takes a single job id for show; a list reads as one bad id."""
    calls = []
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: calls.append(cmd) or (0, "JobId=x\n", "")
    )
    result = CliRunner().invoke(main, ["jobs", "show", "111", "222"])
    assert result.exit_code == 0
    assert calls == [
        ["scontrol", "show", "job", "-dd", "111"],
        ["scontrol", "show", "job", "-dd", "222"],
    ]


def test_jobs_show_refuses_an_argument_that_is_not_a_job_id(monkeypatch):
    """scontrol left with no id prints every job on the cluster."""
    calls = []
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: calls.append(cmd) or (0, "", "")
    )
    for bad in ("", "--json", "abc", "-o"):
        result = CliRunner().invoke(main, ["jobs", "show", "--", bad])
        assert result.exit_code != 0, bad
        assert "not a job id" in result.output, bad
    assert calls == []


def test_jobs_show_points_at_debug_for_a_finished_job(monkeypatch):
    """A job past MinJobAge is gone from the scheduler but still in accounting."""

    def fake_probe(cmd, timeout=None):
        if cmd[0] == "sacct":
            return 0, "123\n", ""
        return 1, "", "Invalid job id specified"

    monkeypatch.setattr(process, "probe", fake_probe)
    result = CliRunner().invoke(main, ["jobs", "show", "123"])
    assert result.exit_code != 0
    assert "has finished" in result.output
    assert "jobs debug 123" in result.output


def test_jobs_show_reports_each_failing_id(monkeypatch):
    """A good id must still print when another id in the same call fails."""

    def fake_probe(cmd, timeout=None):
        if cmd[0] == "sacct":
            return 0, "", ""
        return (0, "JobId=111\n", "") if cmd[-1] == "111" else (1, "", "Invalid job id specified")

    monkeypatch.setattr(process, "probe", fake_probe)
    result = CliRunner().invoke(main, ["jobs", "show", "111", "999"])
    assert result.exit_code != 0
    assert "JobId=111" in result.output
    assert "job 999" in result.output


_SPRIO_ROWS = (
    "          JOBID PARTITION     USER   PRIORITY        AGE  FAIRSHARE\n"
    "          12345 kempner_h100  alice      1234        100        900\n"
)


def test_jobs_why(monkeypatch):
    captured = {}

    def fake_probe(cmd, timeout=None):
        captured["cmd"] = cmd
        if cmd[0] == "squeue":
            return 0, "12345 PENDING Priority\n", ""
        return 0, _SPRIO_ROWS, ""

    monkeypatch.setattr(process, "probe", fake_probe)
    result = CliRunner().invoke(main, ["jobs", "why", "12345"])
    assert result.exit_code == 0
    assert "Priority" in result.output
    assert "FAIRSHARE" in result.output
    assert captured["cmd"] == ["sprio", "-j", "12345"]


def test_jobs_why_explains_an_empty_sprio_result(monkeypatch):
    """sprio ranks only pending jobs it is weighing, so a bare header is not an answer."""
    header_only = "          JOBID PARTITION     USER   PRIORITY        AGE  FAIRSHARE\n"
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: "RUNNING None\n")
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, header_only, ""))
    result = CliRunner().invoke(main, ["jobs", "why", "12345"])
    assert result.exit_code == 0
    assert "no priority record" in result.output


def test_jobs_history(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "history", "--days", "3"])
    assert result.exit_code == 0
    assert calls[0][:5] == ["sacct", "-u", "alice", "-S", "now-3days"]
    assert "-X" in calls[0]


def _cancel_stubs(monkeypatch, counts=None, exists=True):
    monkeypatch.setattr(slurm, "job_exists", lambda j: exists)
    monkeypatch.setattr(
        slurm,
        "job_state_counts",
        lambda u, pending_only=False: (
            counts if counts is not None else {"RUNNING": 3, "PENDING": 1}
        ),
    )
    monkeypatch.setattr(slurm, "job_owner", lambda j: pwd.getpwuid(os.getuid()).pw_name)


_ME = pwd.getpwuid(os.getuid()).pw_name


def test_jobs_cancel_ids(monkeypatch):
    _cancel_stubs(monkeypatch)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel", "111", "222"])
    assert result.exit_code == 0
    assert calls[0] == ["scancel", "111", "222"]


def test_jobs_cancel_all(monkeypatch):
    _cancel_stubs(monkeypatch)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel", "--all", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["scancel", "-u", pwd.getpwuid(os.getuid()).pw_name]


def test_jobs_cancel_pending(monkeypatch):
    _cancel_stubs(monkeypatch, counts={"PENDING": 1})
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel", "--pending", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["scancel", "-u", _ME, "-t", "PENDING"]


def test_jobs_cancel_all_prompts(monkeypatch):
    _cancel_stubs(monkeypatch)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel", "--all"], input="y\n")
    assert result.exit_code == 0
    assert calls[0] == ["scancel", "-u", _ME]


def test_jobs_cancel_all_abort_cancels_nothing(monkeypatch):
    _cancel_stubs(monkeypatch)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel", "--all"], input="n\n")
    assert result.exit_code != 0
    assert calls == []


def test_jobs_cancel_all_states_the_blast_radius(monkeypatch):
    """The prompt asked to cancel everything without saying what everything was."""
    _cancel_stubs(monkeypatch)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel", "--all"], input="n\n")
    assert f"Cancel all 4 jobs owned by {_ME} (1 pending, 3 running)?" in result.output
    assert calls == []


def test_jobs_cancel_all_with_nothing_to_cancel(monkeypatch):
    _cancel_stubs(monkeypatch, counts={})
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel", "--all", "-y"])
    assert result.exit_code == 0
    assert "no jobs to cancel" in result.output
    assert calls == []


def test_jobs_cancel_refuses_an_unknown_job(monkeypatch):
    """scancel exits 0 for an unknown id, so a typo canceled nothing and said nothing."""
    _cancel_stubs(monkeypatch, exists=False)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel", "99999997"])
    assert result.exit_code != 0
    assert "not in the queue: 99999997" in result.output
    assert calls == []


def test_jobs_cancel_rejects_conflicting_scopes(monkeypatch):
    _cancel_stubs(monkeypatch)
    calls = _capture_stream(monkeypatch)
    for args in (["--all", "--pending"], ["111", "--all"], ["111", "--pending"]):
        result = CliRunner().invoke(main, ["jobs", "cancel", *args, "-y"])
        assert result.exit_code == 2, args
        assert "not both" in result.output
    assert calls == []


def test_jobs_cancel_ids_do_not_prompt(monkeypatch):
    _cancel_stubs(monkeypatch)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "cancel", "333"])
    assert result.exit_code == 0
    assert calls[0] == ["scancel", "333"]


def test_jobs_cancel_none_errors(monkeypatch):
    _cancel_stubs(monkeypatch)
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
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: (0, f"PENDING {_ME} 0:00\n", "")
    )
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
    assert calls[0] == ["sshare", "-U", "-u", "alice", "-m"]


def test_account_fairshare_account(monkeypatch):
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
    result = CliRunner().invoke(main, ["account", "fairshare", "kempner_dev"])
    assert result.exit_code == 0
    assert calls[0] == ["sshare", "--account=kempner_dev", "-a", "-m"]


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
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, "normal\n", ""))
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
        process, "probe", lambda cmd, timeout=None: (0, "HEADER\nkempner row\nother row\n", "")
    )
    result = CliRunner().invoke(main, ["nodes", "partitions", "--filter", "kempner"])
    assert result.exit_code == 0
    assert "HEADER" in result.output
    assert "kempner row" in result.output
    assert "other row" not in result.output


def test_nodes_partitions_filter_reports_a_failed_tool(monkeypatch):
    """A filtered run that swallows the failure reads as a genuine no-match."""
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: (1, "", "spart: cannot contact slurmctld")
    )
    result = CliRunner().invoke(main, ["nodes", "partitions", "--filter", "kempner"])
    assert result.exit_code != 0
    assert "cannot contact slurmctld" in result.output


def test_storage_vast_usage(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["storage", "vast-usage", "netscratch", "-g", "kempner_dev"])
    assert result.exit_code == 0
    assert calls[0] == ["quota", "--group-user-usage", "kempner_dev", "/n/netscratch"]


def test_storage_scratch(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["storage", "scratch", "/n/netscratch"])
    assert result.exit_code == 0
    assert calls[0] == ["quota", "/n/netscratch"]
    assert "90 days" in result.output


def test_storage_lfs_stripe_get(monkeypatch, tmp_path):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["storage", "lfs-stripe", str(tmp_path)])
    assert result.exit_code == 0
    assert calls[0] == ["lfs", "getstripe", "-d", str(tmp_path)]


def test_storage_lfs_stripe_set(monkeypatch, tmp_path):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["storage", "lfs-stripe", str(tmp_path), "-c", "8", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["lfs", "setstripe", "-c", "8", str(tmp_path)]


def test_storage_lfs_stripe_set_prompts(monkeypatch, tmp_path):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main, ["storage", "lfs-stripe", str(tmp_path), "-c", "8"], input="y\n"
    )
    assert result.exit_code == 0
    assert calls[0] == ["lfs", "setstripe", "-c", "8", str(tmp_path)]


def test_storage_lfs_stripe_set_abort(monkeypatch, tmp_path):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main, ["storage", "lfs-stripe", str(tmp_path), "-c", "8"], input="n\n"
    )
    assert result.exit_code != 0
    assert "Aborted" in result.output
    assert calls == []


def test_storage_lfs_stripe_rejects_a_count_below_minus_one(monkeypatch, tmp_path):
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(storage, "lustre_ost_count", lambda path: 64)
    result = CliRunner().invoke(main, ["storage", "lfs-stripe", str(tmp_path), "-c", "-5", "-y"])
    assert result.exit_code != 0
    assert "invalid --count -5" in result.output
    assert calls == []


def test_storage_lfs_stripe_rejects_a_count_above_the_ost_count(monkeypatch, tmp_path):
    """lfs accepts it and silently clamps, so the directory would advertise a lie."""
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(storage, "lustre_ost_count", lambda path: 64)
    result = CliRunner().invoke(main, ["storage", "lfs-stripe", str(tmp_path), "-c", "65", "-y"])
    assert result.exit_code != 0
    assert "has 64 OSTs" in result.output
    assert calls == []


def test_storage_lfs_stripe_validates_before_prompting(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "lustre_ost_count", lambda path: 64)
    result = CliRunner().invoke(main, ["storage", "lfs-stripe", str(tmp_path), "-c", "-5"])
    assert result.exit_code != 0
    assert "Set stripe count" not in result.output


def test_storage_lfs_stripe_prompt_explains_the_special_counts(monkeypatch, tmp_path):
    """Per man lfs-setstripe, 0 restores the filesystem default and -1 uses every OST."""
    monkeypatch.setattr(storage, "lustre_ost_count", lambda path: 64)
    reset = CliRunner().invoke(
        main, ["storage", "lfs-stripe", str(tmp_path), "-c", "0"], input="n\n"
    )
    assert "filesystem default stripe count" in reset.output
    every = CliRunner().invoke(
        main, ["storage", "lfs-stripe", str(tmp_path), "-c", "-1"], input="n\n"
    )
    assert "across all 64 OSTs" in every.output


def test_storage_lfs_stripe_allows_the_ost_count(monkeypatch, tmp_path):
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(storage, "lustre_ost_count", lambda path: 64)
    result = CliRunner().invoke(main, ["storage", "lfs-stripe", str(tmp_path), "-c", "64", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["lfs", "setstripe", "-c", "64", str(tmp_path)]


@pytest.mark.real_site_tools
def test_lfs_commands_are_hidden_without_the_lfs_tool(monkeypatch):
    """A center with no Lustre should not be offered Lustre-only commands."""
    monkeypatch.setattr(site, "tool_available", lambda key: key != "lfs")
    result = CliRunner().invoke(main, ["storage", "--help"])
    assert result.exit_code == 0
    assert "lfs-stripe" not in result.output
    assert "lfs-inodes" not in result.output
    assert "home" in result.output


def test_storage_lfs_stripe_missing_path():
    result = CliRunner().invoke(main, ["storage", "lfs-stripe", "/n/holylfs06/nope-does-not-exist"])
    assert result.exit_code != 0
    assert "path not found" in result.output


def test_storage_lfs_inodes_missing_path():
    result = CliRunner().invoke(main, ["storage", "lfs-inodes", "/n/nope-does-not-exist"])
    assert result.exit_code != 0
    assert "path not found" in result.output


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
    assert "--mem=245760" in cmd


def test_gpu_session_h100(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["gpu", "session", "h100", "-A", "lab"])
    assert result.exit_code == 0
    cmd = calls[0]
    assert "kempner_h100" in cmd
    assert "--cpus-per-task=24" in cmd
    assert "--mem=368640" in cmd


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
    assert "--mem=245760" in cmd
    assert cmd[-3:] == ["--mem=500000", "-J", "dev"]


def test_nodes_down(monkeypatch):
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(qos, "partition_exists", lambda p, cluster=None: True)
    result = CliRunner().invoke(main, ["nodes", "down", "-p", "kempner"])
    assert result.exit_code == 0
    assert calls[0] == ["sinfo", "-R", "-o", "%60E %12u %19H %N", "-p", "kempner"]


def test_nodes_load_default(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "load"])
    assert result.exit_code == 0
    assert calls[0] == ["lsload"]


def test_nodes_load_filter(monkeypatch):
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: (0, "HEADER\nholygpu row\nother\n", "")
    )
    result = CliRunner().invoke(main, ["nodes", "load", "-f", "holygpu"])
    assert result.exit_code == 0
    assert "HEADER" in result.output and "holygpu row" in result.output
    assert "other" not in result.output


def test_nodes_frag_skips_gpu_less_partitions(monkeypatch):
    """A CPU-only partition has no GPU fragmentation to report."""
    nodes = [
        {
            "name": "cpu1",
            "partitions": ["bigmem"],
            "state": "IDLE",
            "available": True,
            "cpu_free": 64,
            "mem_free_mb": 500000,
            "gpu_tot": 0,
            "gpu_free": 0,
        },
        {
            "name": "g1",
            "partitions": ["kempner_h100"],
            "state": "IDLE",
            "available": True,
            "cpu_free": 96,
            "mem_free_mb": 900000,
            "gpu_tot": 4,
            "gpu_free": 4,
        },
    ]
    monkeypatch.setattr(slurm, "node_capacity", lambda: nodes)
    result = CliRunner().invoke(main, ["nodes", "frag"])
    assert result.exit_code == 0
    assert "kempner_h100" in result.output
    assert "bigmem" not in result.output


def test_nodes_frag_rejects_an_unknown_partition(monkeypatch):
    monkeypatch.setattr(slurm, "node_capacity", lambda: [])
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: False)
    result = CliRunner().invoke(main, ["nodes", "frag", "-p", "no_such_partition"])
    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_nodes_frag_distinguishes_a_cpu_only_partition(monkeypatch):
    """bigmem exists; saying it might not would send the user looking for a typo."""
    monkeypatch.setattr(slurm, "node_capacity", lambda: [])
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    result = CliRunner().invoke(main, ["nodes", "frag", "-p", "bigmem"])
    assert result.exit_code != 0
    assert "has no GPU nodes" in result.output


def test_nodes_reservations(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "reservations"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "show", "reservation"]


_SSTAT_ROWS = (
    "JobID                    AveCPU     AveRSS     MaxRSS  AveVMSize   NTasks \n"
    "-------------------- ---------- ---------- ---------- ---------- -------- \n"
    "123.extern           213503982+                                         1 \n"
    "123.batch              00:00:01       676K       676K          0        1 \n"
)


def test_jobs_top(monkeypatch):
    calls = []
    monkeypatch.setattr(slurm, "job_accounting", lambda j: {"state": "RUNNING"})
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: calls.append(cmd) or (0, _SSTAT_ROWS, "")
    )
    result = CliRunner().invoke(main, ["jobs", "top", "123"])
    assert result.exit_code == 0
    assert calls[0][:4] == ["sstat", "-a", "-j", "123"]
    assert "123.batch" in result.output


def test_jobs_top_drops_the_extern_sentinel(monkeypatch):
    """The extern step carries Slurm's unset AveCPU value, not a real figure."""
    monkeypatch.setattr(slurm, "job_accounting", lambda j: {"state": "RUNNING"})
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, _SSTAT_ROWS, ""))
    result = CliRunner().invoke(main, ["jobs", "top", "123"])
    assert "213503982" not in result.output
    assert ".extern" not in result.output


def test_jobs_top_refuses_a_job_whose_steps_it_cannot_read(monkeypatch):
    """sstat exits 0 after failing, which would leave a bare header behind."""
    header = "\n".join(_SSTAT_ROWS.splitlines()[:2]) + "\n"
    monkeypatch.setattr(slurm, "job_accounting", lambda j: {"state": "RUNNING"})
    monkeypatch.setattr(
        process,
        "probe",
        lambda cmd, timeout=None: (0, header, "sstat: error: ... rc = Invalid user id"),
    )
    result = CliRunner().invoke(main, ["jobs", "top", "123"])
    assert result.exit_code != 0
    assert "no live step data" in result.output


def test_jobs_top_reads_the_named_array_element(monkeypatch):
    """sstat matches an element by its own job id, not the array's."""
    calls = []
    monkeypatch.setattr(
        slurm, "job_accounting", lambda j: {"state": "RUNNING", "first_element": "7_3"}
    )
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: calls.append(cmd) or (0, _SSTAT_ROWS, "")
    )
    result = CliRunner().invoke(main, ["jobs", "top", "7_3"])
    assert result.exit_code == 0
    assert calls[0][3] == "7_3"


def test_jobs_queue(monkeypatch):
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(slurm, "partition_exists", lambda p: True)
    result = CliRunner().invoke(main, ["jobs", "queue", "kempner_h100"])
    assert result.exit_code == 0
    assert calls[0] == ["showq", "-o", "-p", "kempner_h100"]


def test_jobs_log_paths(monkeypatch):
    monkeypatch.setattr(
        process,
        "probe",
        lambda cmd, timeout=None: (0, "JobId=1 StdOut=/n/out.log StdErr=/n/err.log", ""),
    )
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "log", "1"])
    assert result.exit_code == 0
    assert "/n/out.log" in result.output and "/n/err.log" in result.output
    assert not calls


def test_jobs_log_array_master_names_an_element(monkeypatch):
    """dict() over the matches kept only the last of an array's paths."""
    out = (
        "JobId=1_0 StdOut=/n/out_0.log StdErr=/n/err_0.log\n"
        "JobId=1_1 StdOut=/n/out_1.log StdErr=/n/err_1.log\n"
    )
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, out, ""))
    result = CliRunner().invoke(main, ["jobs", "log", "1"])
    assert result.exit_code != 0
    assert "elements each write their own file" in result.output


def test_jobs_log_unstarted_array(monkeypatch):
    """Slurm leaves NO_VAL in the path until an element starts, so the file never exists."""
    out = "JobId=1 ArrayJobId=1 ArrayTaskId=0-3 StdOut=/n/job_1_4294967294.out"
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, out, ""))
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "log", "1", "-f"])
    assert result.exit_code != 0
    assert "have not started" in result.output
    assert calls == []


def test_jobs_log_unknown_job(monkeypatch):
    monkeypatch.setattr(
        process,
        "probe",
        lambda cmd, timeout=None: (1, "", "slurm_load_jobs error: Invalid job id specified"),
    )
    monkeypatch.setattr(slurm, "job_output_path", lambda j: "")
    monkeypatch.setattr(slurm, "job_accounting", lambda j: {})
    result = CliRunner().invoke(main, ["jobs", "log", "999999999"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_jobs_log_falls_back_to_accounting(monkeypatch):
    """The controller drops a job MinJobAge seconds after it ends; accounting keeps it."""
    monkeypatch.setattr(
        process,
        "probe",
        lambda cmd, timeout=None: (1, "", "slurm_load_jobs error: Invalid job id specified"),
    )
    monkeypatch.setattr(slurm, "job_output_paths", lambda j: ("/work/slurm-123.out", ""))
    result = CliRunner().invoke(main, ["jobs", "log", "123"])
    assert result.exit_code == 0
    assert "StdOut: /work/slurm-123.out" in result.output


def test_jobs_log_names_an_interactive_job_as_such(monkeypatch):
    """A job accounting still knows, but with no file, is not a missing job."""
    monkeypatch.setattr(
        process,
        "probe",
        lambda cmd, timeout=None: (1, "", "slurm_load_jobs error: Invalid job id specified"),
    )
    monkeypatch.setattr(slurm, "job_output_path", lambda j: "")
    monkeypatch.setattr(slurm, "job_accounting", lambda j: {"state": "COMPLETED"})
    result = CliRunner().invoke(main, ["jobs", "log", "123"])
    assert result.exit_code != 0
    assert "interactive job writes to your terminal" in result.output
    assert "not found" not in result.output


def test_jobs_log_follow(monkeypatch):
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, "StdOut=/n/out.log", ""))
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "log", "1", "-f"])
    assert result.exit_code == 0
    assert calls[0] == ["tail", "-f", "/n/out.log"]


def test_jobs_log_missing(monkeypatch):
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: (0, "JobId=1 JobState=RUNNING", "")
    )
    result = CliRunner().invoke(main, ["jobs", "log", "1"])
    assert result.exit_code != 0


def test_jobs_script(monkeypatch):
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: (0, "#!/bin/bash\n#SBATCH -c 4\n", "")
    )
    result = CliRunner().invoke(main, ["jobs", "script", "123"])
    assert result.exit_code == 0
    assert "#SBATCH -c 4" in result.output


def test_jobs_script_falls_back_to_the_controller(monkeypatch):
    """An array element that has not started has no accounting record yet."""
    seen = []

    def fake_probe(cmd, timeout=None):
        seen.append(cmd[0])
        if cmd[0] == "sacct":
            return 0, "", ""
        return 0, "#!/bin/bash\n#SBATCH -J pending\n", ""

    monkeypatch.setattr(process, "probe", fake_probe)
    result = CliRunner().invoke(main, ["jobs", "script", "123_0"])
    assert result.exit_code == 0
    assert "#SBATCH -J pending" in result.output
    assert seen == ["sacct", "scontrol"]


def test_jobs_script_treats_none_as_absent(monkeypatch):
    """sacct prints NONE when the cluster does not store scripts."""

    def fake_probe(cmd, timeout=None):
        if cmd[0] == "sacct":
            return 0, "NONE\n", ""
        return 1, "", "Invalid job id specified"

    monkeypatch.setattr(process, "probe", fake_probe)
    result = CliRunner().invoke(main, ["jobs", "script", "123"])
    assert result.exit_code != 0
    assert "ran without a batch script" in result.output


_SACCT_HEADER = "Batch Script for 123\n" + "-" * 80 + "\n"


def test_jobs_script_treats_a_headed_none_as_absent(monkeypatch):
    """sacct heads the script with a title and a rule, so NONE is never the whole output."""

    def fake_probe(cmd, timeout=None):
        if cmd[0] == "sacct":
            return 0, _SACCT_HEADER + "NONE\n", ""
        return 1, "", "Invalid job id specified"

    monkeypatch.setattr(process, "probe", fake_probe)
    result = CliRunner().invoke(main, ["jobs", "script", "123"])
    assert result.exit_code != 0
    assert "ran without a batch script" in result.output
    assert "NONE" not in result.output


def test_jobs_script_emits_only_the_script(monkeypatch):
    """The output must be redirectable to a runnable file, so the header is dropped."""
    monkeypatch.setattr(
        process,
        "probe",
        lambda cmd, timeout=None: (0, _SACCT_HEADER + "#!/bin/bash\n#SBATCH -c 4\n", ""),
    )
    result = CliRunner().invoke(main, ["jobs", "script", "123"])
    assert result.exit_code == 0
    assert result.output.startswith("#!/bin/bash\n")
    assert "Batch Script for" not in result.output


def test_jobs_list_start(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "list", "--start"])
    assert result.exit_code == 0
    assert calls[0] == ["squeue", "-u", pwd.getpwuid(os.getuid()).pw_name, "--start"]


def test_diag_scheduler(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["diag", "scheduler"])
    assert result.exit_code == 0
    assert calls[0] == ["sdiag"]


def test_jobs_set_priority(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "set-priority", "123", "5000", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "update", "jobid=123", "priority=5000"]


def test_jobs_set_priority_prompts(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "set-priority", "123", "5000"], input="y\n")
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "update", "jobid=123", "priority=5000"]


def test_jobs_set_priority_abort(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "set-priority", "123", "5000"], input="n\n")
    assert result.exit_code != 0
    assert calls == []


def test_jobs_setprio_alias(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "setprio", "123", "5000", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "update", "jobid=123", "priority=5000"]


def test_jobs_priorities(monkeypatch):
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle")])
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "priorities", "kempner_h100"])
    assert result.exit_code == 0
    assert calls[0] == ["sprio", "-p", "kempner_h100"]


def _gpu_node(name, partitions, gpu_tot, gpu_free, available=True):
    return {
        "name": name,
        "partitions": partitions,
        "state": "MIXED" if available else "DOWN",
        "available": available,
        "cpu_free": 0,
        "mem_free_mb": 0,
        "gpu_tot": gpu_tot,
        "gpu_free": gpu_free,
    }


def test_gpu_util(monkeypatch):
    monkeypatch.setattr(slurm, "node_capacity", lambda: [_gpu_node("n1", ["kempner_h100"], 8, 4)])
    monkeypatch.setattr(slurm, "gpus_allocated_in", lambda p: 4)
    result = CliRunner().invoke(main, ["gpu", "util", "kempner_h100"])
    assert result.exit_code == 0
    assert "kempner_h100" in result.output
    assert "50.0%" in result.output


def test_gpu_util_scopes_used_to_the_partition(monkeypatch):
    """A neighbor's jobs occupy the hardware but are not this partition's usage."""
    monkeypatch.setattr(slurm, "node_capacity", lambda: [_gpu_node("n1", ["kempner"], 8, 1)])
    monkeypatch.setattr(slurm, "gpus_allocated_in", lambda p: 2)
    result = CliRunner().invoke(main, ["gpu", "util", "kempner"])
    assert result.exit_code == 0
    row = next(line for line in result.output.splitlines() if line.startswith("kempner"))
    total, unavail, used, other, free, util = row.split()[1:]
    assert (total, unavail, used, other, free) == ("8", "0", "2", "5", "1")
    assert util == "25.0%"


def test_gpu_util_accepts_the_partition_as_an_option(monkeypatch):
    monkeypatch.setattr(slurm, "node_capacity", lambda: [_gpu_node("n1", ["kempner_h100"], 8, 4)])
    monkeypatch.setattr(slurm, "gpus_allocated_in", lambda p: 4)
    result = CliRunner().invoke(main, ["gpu", "util", "-p", "kempner_h100"])
    assert result.exit_code == 0
    assert "kempner_h100" in result.output


def test_gpu_util_counts_a_shared_node_once(monkeypatch):
    """sinfo -N emits a row per (node, partition); the totals must not double count."""
    shared = _gpu_node("n1", ["kempner_h100", "kempner_requeue"], 8, 2)
    monkeypatch.setattr(slurm, "node_capacity", lambda: [shared])
    monkeypatch.setattr(slurm, "gpus_allocated_in", lambda p: 3)
    result = CliRunner().invoke(main, ["gpu", "util", "kempner_h100", "kempner_requeue"])
    assert result.exit_code == 0
    rows = [line.split() for line in result.output.splitlines()[1:] if line.strip()]
    assert [row[1] for row in rows] == ["8", "8"]
    assert [row[3] for row in rows] == ["3", "3"]
    assert [row[4] for row in rows] == ["3", "3"]


def test_gpu_util_percent_cannot_exceed_100(monkeypatch):
    """A drained node still runs its jobs, so used must not be scored against a smaller total."""
    monkeypatch.setattr(
        slurm,
        "node_capacity",
        lambda: [_gpu_node("n1", ["gpu"], 8, 0, available=False)],
    )
    monkeypatch.setattr(slurm, "gpus_allocated_in", lambda p: 8)
    result = CliRunner().invoke(main, ["gpu", "util", "gpu"])
    assert result.exit_code == 0
    assert "100.0%" in result.output


def test_gpu_util_rejects_an_unknown_partition(monkeypatch):
    monkeypatch.setattr(slurm, "node_capacity", lambda: [_gpu_node("n1", ["gpu"], 8, 8)])
    result = CliRunner().invoke(main, ["gpu", "util", "no_such_partition"])
    assert result.exit_code != 0
    assert "does not exist, or has no nodes" in result.output


def test_nodes_resume_explicit(monkeypatch):
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(
        slurm, "resumable_nodes_by_name", lambda names: {names[0]: (names[0], "DOWN", "")}
    )
    result = CliRunner().invoke(main, ["nodes", "resume", "n1", "n2", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "update", "NodeName=n1,n2", "State=RESUME"]


def test_nodes_resume_partition(monkeypatch):
    monkeypatch.setattr(
        slurm, "resumable_nodes", lambda p: [("n3", "drained", "GPU error"), ("n4", "down", "")]
    )
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "resume", "-p", "kempner_requeue", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "update", "NodeName=n3,n4", "State=RESUME"]
    assert "GPU error" in result.output


def test_nodes_resume_partition_with_nothing_to_do(monkeypatch):
    """Giving --partition is not a usage error just because the partition is healthy."""
    monkeypatch.setattr(slurm, "resumable_nodes", lambda p: [])
    monkeypatch.setattr(slurm, "partition_exists", lambda p: True)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "resume", "-p", "bigmem", "-y"])
    assert result.exit_code == 1
    assert "no drained, down or invalid-registration nodes in 'bigmem'" in result.output
    assert calls == []


def test_nodes_resume_explicit_shows_the_reason(monkeypatch):
    """The hand-typed path is the riskier one, so it must show the reason too."""
    monkeypatch.setattr(slurm, "resumable_nodes", lambda p: [])
    monkeypatch.setattr(
        slurm, "resumable_nodes_by_name", lambda names: {"n9": ("n9", "drained", "NHC failure")}
    )
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "resume", "n9", "-y"])
    assert result.exit_code == 0
    assert "NHC failure" in result.output
    assert "unresolved" in result.output
    assert calls[0] == ["scontrol", "update", "NodeName=n9", "State=RESUME"]


def test_nodes_resume_needs_target(monkeypatch):
    _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["nodes", "resume"])
    assert result.exit_code != 0


def test_account_top_users(monkeypatch):
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
    out = "|900\nalice|500\nbob|900\n"
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, out, ""))
    result = CliRunner().invoke(main, ["account", "top-users", "kempner_dev"])
    assert result.exit_code == 0
    assert result.output.index("bob") < result.output.index("alice")


def test_account_top_users_keeps_long_usernames_whole(monkeypatch):
    """sshare's default format truncates to 10 characters under a USER header."""
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
    out = "|900\npaularodriguezflores|500\n"
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, out, ""))
    result = CliRunner().invoke(main, ["account", "top-users", "kempner_dev"])
    assert result.exit_code == 0
    assert "paularodriguezflores" in result.output


def test_account_top_users_sums_a_users_associations(monkeypatch):
    """A user's partition association accrues usage of its own."""
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
    out = "|900\nalice|500\nalice|400\n"
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, out, ""))
    result = CliRunner().invoke(main, ["account", "top-users", "kempner_dev"])
    assert result.exit_code == 0
    assert "900" in result.output


def test_account_top_users_reports_a_failed_sshare(monkeypatch):
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (1, "", "no slurmdbd"))
    result = CliRunner().invoke(main, ["account", "top-users", "kempner_dev"])
    assert result.exit_code != 0
    assert "no slurmdbd" in result.output


def test_account_limits_rejects_account_with_user(monkeypatch):
    result = CliRunner().invoke(main, ["account", "limits", "kempner_dev", "-u", "alice"])
    assert result.exit_code == 2
    assert "not both" in result.output


def test_account_limits_needs_a_user(monkeypatch):
    """An empty user= filter makes sacctmgr dump every association on the cluster."""
    monkeypatch.setenv("USER", "")
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, "", ""))
    result = CliRunner().invoke(main, ["account", "limits"])
    assert result.exit_code == 0
    assert calls[0][3] == f"user={pwd.getpwuid(os.getuid()).pw_name}"


def test_account_limits_rejects_an_empty_user(monkeypatch):
    """A blank -u would otherwise widen the query to every association."""
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(slurm, "user_exists", lambda u: False)
    result = CliRunner().invoke(main, ["account", "limits", "-u", ""])
    assert result.exit_code != 0
    assert "no such user" in result.output
    assert calls == []


def test_account_qos_default(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "qos"])
    assert result.exit_code == 0
    assert calls[0][:3] == ["sacctmgr", "show", "qos"]


def test_account_qos_filter(monkeypatch):
    out = "Name Priority\n---- ----\nnormal 0\nkempner_h100_priority 0\n"
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: out)
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, out, ""))
    result = CliRunner().invoke(main, ["account", "qos", "-f", "kempner"])
    assert result.exit_code == 0
    assert "kempner_h100_priority" in result.output
    assert "normal" not in result.output


def test_account_qos_long(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "qos", "--long"])
    assert result.exit_code == 0
    fmt = calls[0][-1]
    assert "Flags" in fmt and "Preempt" in fmt and "UsageFactor" in fmt and "MaxSubmitPU" in fmt


def _stub_add_user_prechecks(monkeypatch, member=False):
    monkeypatch.setattr(slurm, "user_exists", lambda user: True)
    monkeypatch.setattr(slurm, "account_exists", lambda account: True)
    monkeypatch.setattr(_write, "associations", lambda u, a, c: [("", "normal")] if member else [])


def test_account_add_user(monkeypatch):
    _stub_add_user_prechecks(monkeypatch)
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
        "cluster=odyssey",
        "fairshare=parent",
    ]


def test_account_add_user_uses_the_site_fairshare(monkeypatch):
    """[qos].grant_fairshare is the site's convention for a new association."""
    monkeypatch.setattr(site, "qos_grant_fairshare", lambda: "1000")
    _stub_add_user_prechecks(monkeypatch)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "add-user", "alice", "kempner_dev", "-y"])
    assert result.exit_code == 0
    assert "fairshare=1000" in calls[0]


def test_account_add_user_refuses_a_name_with_no_uid(monkeypatch):
    """-i skips the only prompt at which sacctmgr warns about this."""
    _stub_add_user_prechecks(monkeypatch)
    monkeypatch.setattr(slurm, "user_exists", lambda user: False)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "add-user", "nosuch", "kempner_dev", "-y"])
    assert result.exit_code == 1
    assert "no such user on this host" in result.output
    assert calls == []


def test_account_add_user_refuses_an_account_that_does_not_exist(monkeypatch):
    _stub_add_user_prechecks(monkeypatch)
    monkeypatch.setattr(slurm, "account_exists", lambda account: False)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "add-user", "alice", "nosuch", "-y"])
    assert result.exit_code == 1
    assert "does not exist" in result.output
    assert calls == []


def test_account_add_user_refuses_an_existing_member(monkeypatch):
    """sacctmgr reports this and a missing account with the same text."""
    _stub_add_user_prechecks(monkeypatch, member=True)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "add-user", "alice", "kempner_dev", "-y"])
    assert result.exit_code == 1
    assert "already a member" in result.output
    assert calls == []


def test_account_add_user_refuses_a_comma_in_the_cluster(monkeypatch):
    """man sacctmgr reads cluster= as a list, so a comma widens the write."""
    _stub_add_user_prechecks(monkeypatch)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main, ["account", "add-user", "alice", "kempner_dev", "-c", "a,b", "-y"]
    )
    assert result.exit_code == 1
    assert "invalid CLUSTER" in result.output
    assert calls == []


def test_account_add_user_names_the_cluster_in_the_prompt(monkeypatch):
    """-c is the one thing that changes the write, so it cannot be the one thing hidden."""
    _stub_add_user_prechecks(monkeypatch)
    _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main, ["account", "add-user", "alice", "kempner_dev", "-c", "elsewhere"], input="n\n"
    )
    assert "on elsewhere" in result.output


def test_account_add_user_keeps_an_explicit_empty_fairshare(monkeypatch):
    _stub_add_user_prechecks(monkeypatch)
    _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main, ["account", "add-user", "alice", "kempner_dev", "--fairshare", "", "-y"]
    )
    assert result.exit_code == 1
    assert "invalid fairshare" in result.output


def test_account_writes_reject_a_comma(monkeypatch):
    """sacctmgr reads account=A,B as a list, so one call would hit both."""
    calls = _capture_stream(monkeypatch)
    for args in (
        ["add-user", "alice", "kempner_dev,kempner_lab"],
        ["remove-user", "a,b", "kempner_dev"],
        ["set-fairshare", "alice", "kempner_dev,other", "50"],
    ):
        result = CliRunner().invoke(main, ["account", *args, "-y"])
        assert result.exit_code != 0, args
        assert "cannot contain a comma" in result.output
    assert calls == []


def test_account_set_fairshare_rejects_a_nonsense_share(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main, ["account", "set-fairshare", "alice", "kempner_dev", "nonsense", "-y"]
    )
    assert result.exit_code != 0
    assert "integer number of raw shares" in result.output
    assert calls == []


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


def test_storage_help_has_no_admin_section():
    result = CliRunner().invoke(main, ["storage", "--help"])
    assert result.exit_code == 0
    assert "Admin Commands:" not in result.output
    assert "Commands:" in result.output


def test_gpu_help_sections_monitor_partition_as_admin():
    result = CliRunner().invoke(main, ["gpu", "--help"])
    assert result.exit_code == 0
    out = result.output
    admin_idx = out.index("Admin Commands:")
    assert out.index("usage") < admin_idx
    assert out.index("monitor-partition") > admin_idx


def test_diag_help_sections_ib_as_admin():
    result = CliRunner().invoke(main, ["diag", "--help"])
    assert result.exit_code == 0
    out = result.output
    admin_idx = out.index("Admin Commands:")
    assert out.index("gpu-health") < admin_idx
    assert re.search(r"^\s+ib\s", out[admin_idx:], re.M)


def test_account_remove_user(monkeypatch):
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(qos, "show_assoc_rows", lambda u, a, c=None: ["|normal"])
    result = CliRunner().invoke(main, ["account", "remove-user", "alice", "kempner_dev", "-y"])
    assert result.exit_code == 0
    assert calls[0] == [
        "sacctmgr",
        "-i",
        "remove",
        "user",
        "name=alice",
        "account=kempner_dev",
        "cluster=odyssey",
    ]


def test_account_remove_user_lists_every_association(monkeypatch):
    """A user holds one association per partition, each with its own QoS."""
    monkeypatch.setattr(
        qos,
        "show_assoc_rows",
        lambda u, a, c=None: [
            "|h200_benchmarking,normal",
            "kempner_h200_priority|kemp_gpu16_id42",
            "kempner_rtx_priority|kemp_mlcommons_rtx",
        ],
    )
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main, ["account", "remove-user", "alice", "kempner_dev"], input="n\n"
    )
    assert result.exit_code != 0
    assert "Remove 3 association(s)?" in result.output
    assert "kempner_h200_priority" in result.output
    assert "kemp_mlcommons_rtx" in result.output
    assert calls == []


def test_account_remove_user_can_target_one_partition(monkeypatch):
    monkeypatch.setattr(
        qos,
        "show_assoc_rows",
        lambda u, a, c=None: ["|normal", "kempner_h200_priority|kemp_gpu16_id42"],
    )
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main,
        ["account", "remove-user", "alice", "kempner_dev", "-p", "kempner_h200_priority", "-y"],
    )
    assert result.exit_code == 0
    assert calls[0][-1] == "partition=kempner_h200_priority"
    assert "Remove 1 association(s)?" not in result.output


def test_account_remove_user_with_no_association(monkeypatch):
    monkeypatch.setattr(qos, "show_assoc_rows", lambda u, a, c=None: [])
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["account", "remove-user", "alice", "kempner_dev", "-y"])
    assert result.exit_code != 0
    assert "no association with account kempner_dev" in result.output
    assert calls == []


def test_account_set_fairshare(monkeypatch):
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(qos, "show_assoc_rows", lambda u, a, c=None: ["|normal"])
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
        "cluster=odyssey",
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


def test_pulse_split_args():
    from clustertool.commands.gpu.pulse import _split_args

    node, job, forward, dry = _split_args(("--node", "n1", "--once", "--gpus", "0,1"))
    assert node == "n1" and job is None and forward == ["--once", "--gpus", "0,1"] and dry is False
    node, job, forward, dry = _split_args(("--job=555", "--dry-run", "--poll", "5"))
    assert job == "555" and node is None and dry is True and forward == ["--poll", "5"]


def test_pulse_remote_command():
    from clustertool.commands.gpu.pulse import _remote_command

    cmd = _remote_command("/venv", "kempnerpulse", ["--once"])
    assert "source /venv/bin/activate" in cmd
    assert cmd.endswith("exec kempnerpulse --once")
    assert "nvidia-smi" in cmd
    assert _remote_command("/venv", "othertool", []).endswith("exec othertool")


def test_gpu_pulse_node_dry_run():
    result = CliRunner().invoke(
        main, ["gpu", "pulse", "--node", "holygpu123", "--once", "--dry-run"]
    )
    assert result.exit_code == 0
    assert "ssh" in result.output and "holygpu123" in result.output
    assert "exec kempnerpulse --once" in result.output


def test_gpu_pulse_job_resolves_node(monkeypatch):
    monkeypatch.setattr(slurm, "job_nodes", lambda j: ["nodeA", "nodeB"])
    result = CliRunner().invoke(main, ["gpu", "pulse", "--job", "1234567", "--dry-run"])
    assert result.exit_code == 0
    assert "nodeA" in result.output


def test_gpu_pulse_job_no_nodes(monkeypatch):
    monkeypatch.setattr(slurm, "job_nodes", lambda j: [])
    result = CliRunner().invoke(main, ["gpu", "pulse", "--job", "999"])
    assert result.exit_code != 0
    assert "no running nodes" in result.output


def test_gpu_pulse_node_not_configured(monkeypatch):
    monkeypatch.setattr(site, "pulse_remote_venv", lambda: "")
    result = CliRunner().invoke(main, ["gpu", "pulse", "--node", "x"])
    assert result.exit_code != 0
    assert "not configured" in result.output


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


def _cap_node(name, gpu_free, cpu_free, mem_free_mb, available=True, partition="kempner_h100"):
    return {
        "name": name,
        "partitions": [partition],
        "state": "IDLE" if available else "DRAINED",
        "available": available,
        "cpu_free": cpu_free,
        "mem_free_mb": mem_free_mb,
        "gpu_tot": gpu_free,
        "gpu_free": gpu_free,
    }


def test_gpu_avail(monkeypatch):
    nodes = [
        _cap_node("n1", 4, 96, 1474560),  # min(4, 96//24, 1474560//368640) = 4
        _cap_node("n2", 8, 48, 2880000),  # cpu-capped: min(8, 48//24=2, 8) = 2
        _cap_node("n3", 2, 96, 368640),  # mem-capped: min(2, 4, 368640//368640=1) = 1
        _cap_node("n4", 0, 0, 0),  # no gpu -> filtered
    ]
    monkeypatch.setattr(slurm, "node_capacity", lambda: nodes)
    result = CliRunner().invoke(main, ["gpu", "avail", "kempner_h100"])
    assert result.exit_code == 0
    fields = _node_fields(result.output)
    assert "n4" not in fields
    assert fields["n1"][1] == "4"
    assert fields["n2"][1] == "2" and fields["n2"][2] == "8"
    assert fields["n3"][1] == "1" and fields["n3"][2] == "2"
    assert result.output.index("n1") < result.output.index("n2") < result.output.index("n3")


def test_gpu_avail_raw_partition(monkeypatch):
    monkeypatch.setattr(
        slurm, "node_capacity", lambda: [_cap_node("n1", 4, 8, 1000, partition="kempner_eng")]
    )
    result = CliRunner().invoke(main, ["gpu", "avail", "kempner_eng"])
    assert result.exit_code == 0
    assert "raw free" in result.output
    assert _node_fields(result.output)["n1"][1] == "4"


def test_gpu_avail_cpus_per_gpu_override(monkeypatch):
    monkeypatch.setattr(
        slurm, "node_capacity", lambda: [_cap_node("n1", 8, 40, 1000000, partition="kempner_eng")]
    )
    result = CliRunner().invoke(
        main, ["gpu", "avail", "kempner_eng", "--cpus-per-gpu", "20", "--mem-per-gpu", "100000"]
    )
    assert result.exit_code == 0
    assert "capped by 20 CPU" in result.output
    assert _node_fields(result.output)["n1"][1] == "2"


def test_jobs_violators(monkeypatch):
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle")])
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


def test_jobs_violators_ignores_a_job_at_exactly_the_norm(monkeypatch):
    """--mem=360G is 368640 MiB, which is the ceiling the site enforces, not over it."""
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle")])
    jobs = [("at_limit", "alice", 24, 1, 368640)]
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: jobs)
    result = CliRunner().invoke(main, ["jobs", "violators", "kempner_h100"])
    assert result.exit_code == 0
    assert "at_limit" not in result.output
    assert "(no jobs over the norm)" in result.output


def test_jobs_violators_ranks_the_worst_first(monkeypatch):
    """A job just over must not sit above one at ten times the norm."""
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle")])
    jobs = [
        ("marginal", "alice", 24, 1, 380000),
        ("severe", "bob", 24, 1, 3686400),
    ]
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: jobs)
    result = CliRunner().invoke(main, ["jobs", "violators", "kempner_h100"])
    assert result.exit_code == 0
    assert result.output.index("severe") < result.output.index("marginal")
    assert "1.03x" in result.output
    assert "10.00x" in result.output


def test_jobs_violators_h200(monkeypatch):
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle")])
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: [("301", "x", 200, 2, 10000)])
    result = CliRunner().invoke(main, ["jobs", "violators", "kempner_h200"])
    assert result.exit_code == 0
    assert "301" in result.output


def test_jobs_violators_partition_without_a_policy(monkeypatch):
    """A real partition with no configured ratio is not the same as a typo."""
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: [])
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle")])
    result = CliRunner().invoke(main, ["jobs", "violators", "sapphire"])
    assert result.exit_code != 0
    assert "no per-GPU policy configured" in result.output


def test_jobs_violators_unknown_partition(monkeypatch):
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: [])
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [])
    result = CliRunner().invoke(main, ["jobs", "violators", "some_partition"])
    assert result.exit_code != 0
    assert "does not exist, or has no nodes" in result.output


def test_jobs_violators_rejects_a_zero_norm_flag(monkeypatch):
    """Dividing by the norm makes zero and negative values meaningless, not merely odd."""
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: [("201", "eve", 8, 1, 1000)])
    for flag, value in (("--cpus-per-gpu", "0"), ("--mem-per-gpu", "0"), ("--cpus-per-gpu", "-4")):
        result = CliRunner().invoke(main, ["jobs", "violators", "kempner_h100", flag, value])
        assert result.exit_code != 0
        assert "is not in the range" in result.output


def test_jobs_violators_rejects_a_zero_norm_from_the_site_config(monkeypatch):
    """A flag range cannot guard the policy path, which supplies the same divisor."""
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: [("201", "eve", 8, 1, 1000)])
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle")])
    monkeypatch.setattr(slurm, "PARTITION_LIMITS", {"broken": (0, 0)})
    result = CliRunner().invoke(main, ["jobs", "violators", "broken"])
    assert result.exit_code != 0
    assert "cannot be a norm" in result.output


def test_jobs_violators_override(monkeypatch):
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: [("201", "eve", 100, 2, 10000)])
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle")])
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


def test_account_members_all_uses_site_config(monkeypatch):
    asked = []
    monkeypatch.setattr(site, "roster_partition", lambda: "gpu")
    monkeypatch.setattr(site, "lab_account_prefix", lambda: "lab_")
    monkeypatch.setattr(
        slurm,
        "partition_accounts",
        lambda p: asked.append(p) or ["lab_alpha", "kempner_dev", "other"],
    )
    monkeypatch.setattr(slurm, "account_members", lambda a: ["u1"] if a == "lab_alpha" else [])
    monkeypatch.setattr(slurm, "user_fullnames", lambda users: {"u1": "User_One"})
    result = CliRunner().invoke(main, ["account", "members", "--all"])
    assert result.exit_code == 0
    assert asked == ["gpu"]
    assert "lab_alpha,u1,User_One" in result.output
    assert "kempner_dev" not in result.output


def test_account_members_all_names_the_configured_partition(monkeypatch):
    monkeypatch.setattr(site, "roster_partition", lambda: "gpu")
    monkeypatch.setattr(site, "lab_account_prefix", lambda: "lab_")
    monkeypatch.setattr(slurm, "partition_accounts", lambda p: [])
    result = CliRunner().invoke(main, ["account", "members", "--all"])
    assert result.exit_code != 0
    assert "'gpu' partition" in result.output


def test_account_members_needs_account():
    result = CliRunner().invoke(main, ["account", "members"])
    assert result.exit_code != 0
    assert "give an ACCOUNT or use --all" in result.output


_IB_OK = "__clustertool_ports__ 1\n"


def _fake_ib_probe(per_host):
    def probe(cmd, timeout=None):
        host = cmd[-2]
        return per_host.get(host, (0, _IB_OK, ""))

    return probe


def test_diag_ib(monkeypatch):
    monkeypatch.setattr(
        slurm, "partition_nodes", lambda p: [("n1", "idle"), ("n2", "idle"), ("n3", "idle")]
    )
    monkeypatch.setattr(
        process,
        "probe",
        _fake_ib_probe({"n2": (0, "mlx5_0/ports/1 1: DOWN\n" + _IB_OK, "")}),
    )
    result = CliRunner().invoke(main, ["diag", "ib", "kempner_h100"])
    assert result.exit_code == 4
    assert "n2" in result.output
    assert "mlx5_0/ports/1" in result.output
    assert "1 down, 2 ok" in result.output


def test_diag_ib_all_up(monkeypatch):
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle"), ("n2", "idle")])
    monkeypatch.setattr(process, "probe", _fake_ib_probe({}))
    result = CliRunner().invoke(main, ["diag", "ib", "kempner_h100"])
    assert result.exit_code == 0
    assert "0 down, 2 ok" in result.output


def test_diag_ib_does_not_certify_a_fabric_it_never_reached(monkeypatch):
    """Every ssh failing must not read as a clean fabric."""
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle"), ("n2", "idle")])
    monkeypatch.setattr(
        process,
        "probe",
        _fake_ib_probe(
            {"n1": (255, "", "Permission denied"), "n2": (255, "", "Permission denied")}
        ),
    )
    result = CliRunner().invoke(main, ["diag", "ib", "kempner_h100"])
    assert result.exit_code == 1
    assert "0 down, 0 ok" in result.output
    assert "2 unreachable" in result.output
    assert "n1: Permission denied" in result.output


def test_diag_ib_reports_a_host_without_infiniband(monkeypatch):
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle")])
    monkeypatch.setattr(
        process, "probe", _fake_ib_probe({"n1": (0, "__clustertool_ports__ 0\n", "")})
    )
    result = CliRunner().invoke(main, ["diag", "ib", "kempner_h100"])
    assert result.exit_code == 1
    assert "1 without IB" in result.output


def test_diag_ib_rejects_an_unknown_partition(monkeypatch):
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [])
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: False)
    result = CliRunner().invoke(main, ["diag", "ib", "no_such_partition"])
    assert result.exit_code == 3
    assert "does not exist" in result.output


def test_gpu_monitor_job(monkeypatch):
    from clustertool import monitor

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


def test_gpu_nvtop_refuses_an_existing_session(monkeypatch):
    """Splitting into an existing session left the caller's earlier panes mixed in."""
    monkeypatch.setattr(slurm, "job_nodes", lambda j: ["n1", "n2"])
    ran = []
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: ran.append(cmd) or "")
    monkeypatch.setattr(slurm, "job_owner", lambda j: "")
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: (1, "", "duplicate session: nvtop_123")
    )
    result = CliRunner().invoke(main, ["gpu", "nvtop", "123", "--no-attach"])
    assert result.exit_code != 0
    assert "duplicate session" in result.output
    assert "tmux kill-session -t nvtop_123" in result.output
    assert ran == []


def test_gpu_nvtop(monkeypatch):
    monkeypatch.setattr(slurm, "job_nodes", lambda j: ["n1", "n2"])
    calls = []

    def fake_run(cmd, input_text=None):
        calls.append(cmd)
        if cmd[:2] == ["tmux", "list-panes"]:
            return "0\n1\n"
        return ""

    monkeypatch.setattr(process, "run", fake_run)
    monkeypatch.setattr(slurm, "job_owner", lambda j: "")
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: calls.append(cmd) or (0, "", "")
    )
    result = CliRunner().invoke(main, ["gpu", "nvtop", "123", "--no-attach"])
    assert result.exit_code == 0
    assert calls[0][:3] == ["tmux", "new-session", "-d"]
    send_keys = [c for c in calls if c[:2] == ["tmux", "send-keys"]]
    assert len(send_keys) == 2
    assert any("n1" in c[4] and "nvtop" in c[4] for c in send_keys)
    assert "attach -t nvtop_123" in result.output


def test_gpu_monitor_job_refuses_another_users_job(monkeypatch):
    """Node login is gated on an allocation, so a foreign job would be refused anyway."""
    monkeypatch.setenv("USER", "alice")
    monkeypatch.setattr(slurm, "job_owner", lambda j: "bob")
    ran = []
    monkeypatch.setattr(slurm, "job_nodes", lambda j: ran.append(j) or ["n1"])
    result = CliRunner().invoke(main, ["gpu", "monitor-job", "123"])
    assert result.exit_code != 0
    assert "belongs to bob, not you" in result.output
    assert ran == []


def test_gpu_nvtop_refuses_another_users_job(monkeypatch):
    monkeypatch.setenv("USER", "alice")
    monkeypatch.setattr(slurm, "job_owner", lambda j: "bob")
    ran = []
    monkeypatch.setattr(slurm, "job_nodes", lambda j: ran.append(j) or ["n1"])
    result = CliRunner().invoke(main, ["gpu", "nvtop", "123", "--no-attach"])
    assert result.exit_code != 0
    assert "belongs to bob, not you" in result.output
    assert ran == []


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


def test_diag_nvlink_dry_run_gpus(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1,2,3,4,5,6,7")
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
    result = CliRunner().invoke(main, ["diag", "nvlink", "--all-gpus"])
    assert result.exit_code == 0
    run_env = [env for cmd, env in calls if env is not None][0]
    assert run_env["CUDA_VISIBLE_DEVICES"] == "0,1,2,3,4,5,6,7"
    assert "8 GPU(s)" in result.output


def test_diag_nvlink_refuses_the_whole_node_outside_a_job_step(monkeypatch, tmp_path):
    """With no CUDA_VISIBLE_DEVICES there is no allocation to narrow."""
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: _fake_nvidia_smi_l(8))
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/nvcc")
    calls = []
    monkeypatch.setattr(
        process, "stream", lambda cmd, extra_env=None: calls.append((cmd, extra_env)) or 0
    )
    result = CliRunner().invoke(main, ["diag", "nvlink"])
    assert result.exit_code == 1
    assert "no allocation to narrow" in result.output
    assert calls == []


def test_diag_nvlink_counts_the_devices_it_will_pass(monkeypatch, tmp_path):
    """--gpus is checked against nvidia-smi, but the binary sees the device list."""
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "3")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: _fake_nvidia_smi_l(8))
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/nvcc")
    result = CliRunner().invoke(main, ["diag", "nvlink", "--gpus", "4"])
    assert result.exit_code == 1
    assert "this step has 1" in result.output


def test_diag_nvlink_gpus_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1,2,3,4,5,6,7")
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
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
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
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1,2,3,4,5,6,7")
    monkeypatch.setattr(process, "run", lambda cmd, input_text=None: _fake_nvidia_smi_l(8))
    monkeypatch.setattr(shutil, "which", lambda name: None)
    result = CliRunner().invoke(main, ["diag", "nvlink"])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_nodes_frag(monkeypatch):
    nodes = [
        {
            "name": "n1",
            "partitions": ["kempner_h100"],
            "state": "IDLE",
            "available": True,
            "cpu_free": 96,
            "mem_free_mb": 1_000_000,
            "gpu_tot": 4,
            "gpu_free": 4,
        },
        {
            "name": "n2",
            "partitions": ["kempner_h100"],
            "state": "MIXED",
            "available": True,
            "cpu_free": 8,
            "mem_free_mb": 100_000,
            "gpu_tot": 4,
            "gpu_free": 2,
        },
        {
            "name": "n3",
            "partitions": ["kempner_h100"],
            "state": "DOWN",
            "available": False,
            "cpu_free": 0,
            "mem_free_mb": 0,
            "gpu_tot": 4,
            "gpu_free": 0,
        },
    ]
    monkeypatch.setattr(slurm, "node_capacity", lambda: nodes)
    result = CliRunner().invoke(
        main, ["nodes", "frag", "--cpus-per-gpu", "8", "--mem-per-gpu", "65536"]
    )
    assert result.exit_code == 0
    assert "1 GPU node(s) not accepting new work" in result.output
    row = next(line for line in result.output.splitlines() if "kempner_h100" in line)
    fields = row.split()
    assert fields[1] == "2"
    assert fields[2] == "0/0/1/0/1"
    assert fields[3:6] == ["5", "2", "1"]


def test_jobs_wait_times(monkeypatch):
    rows = [
        [
            "101",
            "kempner_h100",
            "qa",
            "2026-07-01T00:00:00",
            "2026-07-01T00:01:00",
            "COMPLETED",
            "cpu=8,gres/gpu=1",
        ],
        [
            "102",
            "kempner_h100",
            "qa",
            "2026-07-01T00:00:00",
            "2026-07-01T00:10:00",
            "COMPLETED",
            "cpu=8,gres/gpu=1",
        ],
        ["103", "kempner", "qb", "2026-07-01T00:00:00", "", "PENDING", "cpu=8"],
    ]
    monkeypatch.setattr(slurm, "sacct_window_rows", lambda *a, **k: rows)
    result = CliRunner().invoke(main, ["jobs", "wait-times", "-u", "bob"])
    assert result.exit_code == 0
    assert "2 started job(s); excluded 1 pending" in result.output
    part_row = next(
        line for line in result.output.splitlines() if line.strip().startswith("kempner_h100")
    )
    assert "1m 0s" in part_row and "10m 0s" in part_row


def test_jobs_failures(monkeypatch):
    rows = [
        ["201", "alice", "acct", "kempner", "COMPLETED", "0:0", "01:00:00", "n1", "train"],
        ["202", "bob", "acct", "kempner", "FAILED", "1:0", "00:10:00", "n2", "train"],
        ["203", "bob", "acct", "kempner", "OUT_OF_MEMORY", "0:125", "00:05:00", "n3", "big"],
        ["204", "carol", "acct", "kempner", "TIMEOUT", "0:0", "1-00:00:00", "n1", "long"],
        ["205", "dave", "acct", "kempner", "RUNNING", "0:0", "00:01:00", "n1", "live"],
    ]
    monkeypatch.setattr(slurm, "sacct_window_rows", lambda *a, **k: rows)
    result = CliRunner().invoke(main, ["jobs", "failures", "-p", "kempner"])
    assert result.exit_code == 0
    assert "4 terminal job(s), 1 still active" in result.output
    assert "failure rate: 75.0%" in result.output
    assert "oom=1" in result.output and "timeout=1" in result.output
    assert "n3" in result.output


def test_jobs_wait_times_skew_and_buckets(monkeypatch):
    rows = [
        ["1", "p", "q", "2026-07-01T00:05:00", "2026-07-01T00:00:00", "COMPLETED", "gres/gpu=1"],
        ["2", "p", "q", "2026-07-01T00:00:00", "2026-07-01T00:02:00", "COMPLETED", "gres/gpu=2"],
    ]
    monkeypatch.setattr(slurm, "sacct_window_rows", lambda *a, **k: rows)
    result = CliRunner().invoke(main, ["jobs", "wait-times"])
    assert result.exit_code == 0
    assert "1 clock-skew" in result.output
    assert "2-4" in result.output


def test_jobs_failures_node_fail(monkeypatch):
    rows = [["1", "u", "a", "p", "NODE_FAIL", "0:0", "00:10:00", "nX", "job"]]
    monkeypatch.setattr(slurm, "sacct_window_rows", lambda *a, **k: rows)
    result = CliRunner().invoke(main, ["jobs", "failures"])
    assert result.exit_code == 0
    assert "node_fail=1" in result.output
    assert "nX" in result.output


def test_nodes_frag_partition_filter(monkeypatch):
    nodes = [
        {
            "name": "a",
            "partitions": ["p1"],
            "state": "IDLE",
            "available": True,
            "cpu_free": 96,
            "mem_free_mb": 1_000_000,
            "gpu_tot": 4,
            "gpu_free": 4,
        },
        {
            "name": "b",
            "partitions": ["p2"],
            "state": "IDLE",
            "available": True,
            "cpu_free": 96,
            "mem_free_mb": 1_000_000,
            "gpu_tot": 4,
            "gpu_free": 4,
        },
    ]
    monkeypatch.setattr(slurm, "node_capacity", lambda: nodes)
    result = CliRunner().invoke(main, ["nodes", "frag", "-p", "p1"])
    assert result.exit_code == 0
    assert "p1" in result.output
    assert "p2" not in result.output


def test_account_balance(monkeypatch):
    accounts = [
        {
            "account": "acctA",
            "raw_shares": 1,
            "norm_shares": 0.1,
            "effectv_usage": 0.2,
            "raw_usage": 20,
        },
        {
            "account": "acctB",
            "raw_shares": 8,
            "norm_shares": 0.8,
            "effectv_usage": 0.2,
            "raw_usage": 20,
        },
        {
            "account": "acctC",
            "raw_shares": 0,
            "norm_shares": 0.0,
            "effectv_usage": 0.5,
            "raw_usage": 50,
        },
    ]
    monkeypatch.setattr(slurm, "account_shares", lambda a=None: accounts)
    result = CliRunner().invoke(main, ["account", "balance"])
    assert result.exit_code == 0
    assert "2 account(s) with shares, 2 with usage" in result.output
    over = result.output.split("over-served")[1].split("under-served")[0]
    under = result.output.split("under-served")[1]
    assert over.index("acctA") < over.index("acctB")
    assert under.index("acctB") < under.index("acctA")
    assert "2.00" in over


def test_account_balance_ranks_an_unused_account_as_most_under_served(monkeypatch):
    """man sshare: an association with no usage is the most under-served there is."""
    accounts = [
        {
            "account": "busy_lab",
            "raw_shares": 1,
            "norm_shares": 0.1,
            "effectv_usage": 0.5,
            "raw_usage": 500,
        },
        {
            "account": "idle_lab",
            "raw_shares": 2,
            "norm_shares": 0.2,
            "effectv_usage": 0.0,
            "raw_usage": 0,
        },
    ]
    monkeypatch.setattr(slurm, "account_shares", lambda a=None: accounts)
    result = CliRunner().invoke(main, ["account", "balance"])
    assert result.exit_code == 0
    assert "2 account(s) with shares, 1 with usage" in result.output
    under = result.output.split("under-served")[1]
    assert under.index("idle_lab") < under.index("busy_lab")


def test_account_balance_rejects_an_unknown_account(monkeypatch):
    monkeypatch.setattr(slurm, "account_exists", lambda a: False)
    result = CliRunner().invoke(main, ["account", "balance", "no_such_account"])
    assert result.exit_code != 0
    assert "not found" in result.output


def _write_capture(tmp_path, xml, nvlink=None):
    path = tmp_path / "smi.xml"
    path.write_text(xml)
    if nvlink is not None:
        (tmp_path / "smi.xml.nvlink").write_text(nvlink)
    return str(path)


def test_diag_gpu_health_from_xml_ok(tmp_path):
    path = _write_capture(tmp_path, HEALTHY, _nvlink())
    result = CliRunner().invoke(main, ["diag", "gpu-health", "--from-xml", path])
    assert result.exit_code == 0
    assert result.output.rstrip().endswith("node verdict: OK")


def test_diag_gpu_health_warn_exits_1(tmp_path):
    path = _write_capture(tmp_path, _smi_xml(_gpu(replay=gpuhealth.PCIE_REPLAY_WARN + 1)))
    result = CliRunner().invoke(main, ["diag", "gpu-health", "--from-xml", path])
    assert result.exit_code == 1
    assert "node verdict: WARN" in result.output


def test_diag_gpu_health_fail_exits_4(tmp_path):
    path = _write_capture(tmp_path, _smi_xml(_gpu(vol_unc=3)))
    result = CliRunner().invoke(main, ["diag", "gpu-health", "--from-xml", path])
    assert result.exit_code == 4
    assert "node verdict: FAIL (GPU 0)" in result.output


def test_diag_gpu_health_garbled_exits_3(tmp_path):
    path = _write_capture(tmp_path, "<nvidia_smi_log><gpu><product_name>NVIDIA")
    result = CliRunner().invoke(main, ["diag", "gpu-health", "--from-xml", path])
    assert result.exit_code == 3
    assert "error" in result.output.lower()


def test_diag_gpu_health_missing_file_exits_3():
    result = CliRunner().invoke(main, ["diag", "gpu-health", "--from-xml", "/nonexistent.xml"])
    assert result.exit_code == 3


def test_diag_gpu_health_probe_error_exits_3(monkeypatch):
    def boom():
        raise gpuhealth.ProbeError("nvidia-smi not found on this host")

    monkeypatch.setattr(gpuhealth, "collect", boom)
    result = CliRunner().invoke(main, ["diag", "gpu-health"])
    assert result.exit_code == 3
    assert "nvidia-smi" in result.output


def test_diag_gpu_health_json_stdout(tmp_path):
    path = _write_capture(tmp_path, HEALTHY, _nvlink())
    result = CliRunner().invoke(main, ["diag", "gpu-health", "--from-xml", path, "--json"])
    assert result.exit_code == 0
    snapshot = json.loads(result.output)
    assert snapshot["verdict"] == "OK"
    assert len(snapshot["gpus"]) == 2
    assert snapshot["gpus"][0]["checks"]["nvlink"]["status"] == "OK"


def test_diag_gpu_health_json_to_file(tmp_path):
    path = _write_capture(tmp_path, HEALTHY)
    out = tmp_path / "snap.json"
    result = CliRunner().invoke(
        main, ["diag", "gpu-health", "--from-xml", path, "--json", str(out)]
    )
    assert result.exit_code == 0
    assert json.loads(out.read_text())["verdict"] == "OK"


def test_diag_gpu_health_ecc_disabled_na(tmp_path):
    path = _write_capture(tmp_path, ECC_DISABLED)
    result = CliRunner().invoke(main, ["diag", "gpu-health", "--from-xml", path])
    assert result.exit_code == 0
    assert "ecc:      n/a" in result.output
    assert "nvlink:   n/a" in result.output


def test_diag_gpu_health_json_unwritable_exits_3(tmp_path):
    path = _write_capture(tmp_path, HEALTHY)
    bad = tmp_path / "nope" / "out.json"
    result = CliRunner().invoke(
        main, ["diag", "gpu-health", "--from-xml", path, "--json", str(bad)]
    )
    assert result.exit_code == 3
    assert "error" in result.output.lower()


def test_diag_gpu_health_from_xml_directory_exits_3(tmp_path):
    result = CliRunner().invoke(main, ["diag", "gpu-health", "--from-xml", str(tmp_path)])
    assert result.exit_code == 3


def test_qos_holders(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    rows = [("alice", "kempner_dev", "kempner_h100"), ("bob", "kempner_eng", "kempner_h100")]
    monkeypatch.setattr(qos, "holder_rows", lambda *a, **k: rows)
    result = CliRunner().invoke(main, ["qos", "holders", "kemp_gpu4"])
    assert result.exit_code == 0
    assert "alice" in result.output and "kempner_dev" in result.output
    assert result.output.splitlines()[0].split() == ["USER", "ACCOUNT", "PARTITION"]


def test_qos_holders_by_partition(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    rows = [("alice", "kempner_dev", "kempner_h100"), ("bob", "kempner_dev", "kempner_h200")]
    monkeypatch.setattr(qos, "holder_rows", lambda *a, **k: rows)
    result = CliRunner().invoke(main, ["qos", "holders", "q", "--by", "partition"])
    assert result.exit_code == 0
    assert result.output.split() == ["kempner_h100", "kempner_h200"]


def test_qos_holders_missing(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: False)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    result = CliRunner().invoke(main, ["qos", "holders", "ghost"])
    assert result.exit_code != 0
    assert "not defined" in result.output


def test_qos_create_dry_run(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: False)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    ran = []
    monkeypatch.setattr(process, "probe", lambda cmd: ran.append(cmd) or (0, "", ""))
    result = CliRunner().invoke(main, ["qos", "create", "new_qos", "-g", "4", "-G", "8"])
    assert result.exit_code == 0
    assert "[DRY ] sacctmgr -i add qos new_qos" in result.output
    assert "add qos new_qos MaxTRESPU=gres/gpu=4 GrpTRES=gres/gpu=8" in result.output
    assert "Dry run" in result.output
    assert ran == []


def test_qos_create_execute(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    ran = []
    monkeypatch.setattr(process, "probe", lambda cmd: ran.append(cmd) or (0, "", ""))
    result = CliRunner().invoke(main, ["qos", "create", "kemp", "-g", "4", "--execute", "--yes"])
    assert result.exit_code == 0
    assert ran[0] == ["sacctmgr", "-i", "modify", "qos", "kemp", "set", "MaxTRESPU=gres/gpu=4"]
    assert ran[1][:5] == ["sacctmgr", "-n", "-P", "show", "qos"]
    assert "[EXEC]" in result.output
    assert "now carries" in result.output


def test_qos_create_requires_a_limit():
    result = CliRunner().invoke(main, ["qos", "create", "kemp"])
    assert result.exit_code == 2
    assert "at least one limit" in result.output


def test_qos_modify_missing(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: False)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    result = CliRunner().invoke(main, ["qos", "modify", "ghost", "-g", "4"])
    assert result.exit_code != 0
    assert "does not exist" in result.output


def test_qos_modify_per_user_only(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    result = CliRunner().invoke(main, ["qos", "modify", "kemp", "-g", "4", "--per-user-only"])
    assert result.exit_code == 0
    assert "MaxTRESPU=gres/gpu=4" in result.output
    assert "GrpTRES=gres/gpu=-1" in result.output
    assert "MaxTRES=gres/gpu=-1" in result.output


def test_qos_delete_nonexistent(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: False)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    result = CliRunner().invoke(main, ["qos", "delete", "ghost"])
    assert result.exit_code == 0
    assert "nothing to do" in result.output


def test_qos_delete_held(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "any_holders", lambda name: ["odyssey|kempner_dev|alice|kempner_h100"])
    result = CliRunner().invoke(main, ["qos", "delete", "kemp"])
    assert result.exit_code != 0
    assert "still held" in result.output


def test_qos_revoke_refuses_an_unknown_partition(monkeypatch):
    """A typo must not report success after revoking nothing from a real holder."""
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: False)
    ran = []
    monkeypatch.setattr(qos, "revoke_targets_plan", lambda *a, **k: ran.append(1) or [])
    result = CliRunner().invoke(
        main, ["qos", "revoke", "kemp", "-u", "alice", "-p", "kempner_h200_priorty"]
    )
    assert result.exit_code != 0
    assert "no such partition: kempner_h200_priorty" in result.output
    assert ran == []


def test_qos_grant_refuses_an_unknown_partition(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: False)
    result = CliRunner().invoke(main, ["qos", "grant", "kemp", "-u", "alice", "-p", "nope"])
    assert result.exit_code != 0
    assert "no such partition: nope" in result.output


def test_qos_sync_refuses_an_unknown_partition(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: False)
    result = CliRunner().invoke(main, ["qos", "sync", "kemp", "-a", "lab", "-p", "nope"])
    assert result.exit_code != 0
    assert "no such partition: nope" in result.output


def test_qos_grant_rejects_a_comma_in_the_partition(monkeypatch):
    """sacctmgr reads Partitions=A,B as a list, which would widen the change."""
    result = CliRunner().invoke(main, ["qos", "grant", "kemp", "-u", "alice", "-p", "gpu_a,gpu_b"])
    assert result.exit_code != 0
    assert "cannot contain" in result.output


def test_qos_sync_rejects_a_comma_in_the_account(monkeypatch):
    result = CliRunner().invoke(main, ["qos", "sync", "kemp", "-a", "lab_a,lab_b", "-p", "gpu"])
    assert result.exit_code != 0
    assert "cannot contain" in result.output


def test_qos_revoke_rejects_a_comma_in_the_partition(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    result = CliRunner().invoke(main, ["qos", "revoke", "kemp", "-u", "alice", "-p", "gpu_a,gpu_b"])
    assert result.exit_code != 0
    assert "cannot contain a comma" in result.output


def test_qos_delete_refuses_while_jobs_carry_the_qos(monkeypatch):
    """A QoS with live jobs is still in force, whatever the associations say."""
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "any_holders", lambda name: [])
    monkeypatch.setattr(qos, "partitions_referencing", lambda name, cluster=None: [])
    monkeypatch.setattr(qos, "partition_references", lambda name, cluster=None: {})
    monkeypatch.setattr(qos, "jobs_using", lambda name, cluster=None: 11443)
    result = CliRunner().invoke(main, ["qos", "delete", "kemp", "-x", "-y"])
    assert result.exit_code != 0
    assert "11443 queued or running job(s)" in result.output


def test_qos_retire_refuses_while_jobs_carry_the_qos(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "partitions_referencing", lambda name, cluster=None: [])
    monkeypatch.setattr(qos, "partition_references", lambda name, cluster=None: {})
    monkeypatch.setattr(qos, "jobs_using", lambda name, cluster=None: 24)
    result = CliRunner().invoke(main, ["qos", "retire", "kemp", "-p", "all", "-x", "-y"])
    assert result.exit_code != 0
    assert "24 queued or running job(s)" in result.output


def test_qos_delete_dry_run(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "any_holders", lambda name: [])
    monkeypatch.setattr(qos, "partitions_referencing", lambda name, cluster=None: [])
    monkeypatch.setattr(qos, "partition_references", lambda name, cluster=None: {})
    monkeypatch.setattr(qos, "jobs_using", lambda name, cluster=None: 0)
    ran = []
    monkeypatch.setattr(process, "probe", lambda cmd: ran.append(cmd) or (0, "", ""))
    result = CliRunner().invoke(main, ["qos", "delete", "kemp"])
    assert result.exit_code == 0
    assert "[DRY ] sacctmgr -i delete qos kemp" in result.output
    assert ran == []


def test_qos_execute_non_tty_requires_yes(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "any_holders", lambda name: [])
    monkeypatch.setattr(qos, "partitions_referencing", lambda name, cluster=None: [])
    monkeypatch.setattr(qos, "partition_references", lambda name, cluster=None: {})
    monkeypatch.setattr(qos, "jobs_using", lambda name, cluster=None: 0)
    ran = []
    monkeypatch.setattr(process, "probe", lambda cmd: ran.append(cmd) or (0, "", ""))
    result = CliRunner().invoke(main, ["qos", "delete", "kemp", "--execute"], input="y\n")
    assert result.exit_code != 0
    assert "not a terminal" in result.output
    assert ran == []


def test_qos_create_rejects_unsafe_name(monkeypatch):
    ran = []
    monkeypatch.setattr(process, "probe", lambda cmd: ran.append(cmd) or (0, "", ""))
    result = CliRunner().invoke(main, ["qos", "create", "a,b", "-g", "4", "--execute", "--yes"])
    assert result.exit_code != 0
    assert "invalid QoS name" in result.output
    assert ran == []


def test_qos_create_execute_add_then_modify(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: False)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    ran = []
    monkeypatch.setattr(process, "probe", lambda cmd: ran.append(cmd) or (0, "", ""))
    result = CliRunner().invoke(main, ["qos", "create", "new_qos", "-g", "4", "--execute", "--yes"])
    assert result.exit_code == 0
    assert ran[0] == ["sacctmgr", "-i", "add", "qos", "new_qos", "MaxTRESPU=gres/gpu=4"]


def test_qos_modify_per_user_only_clears_the_account_cap(monkeypatch):
    """MaxTRESPA is a per-account cap, so leaving it set contradicts the flag."""
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    result = CliRunner().invoke(main, ["qos", "modify", "kemp", "--per-user-only"])
    assert result.exit_code == 0
    assert "MaxTRESPA=gres/gpu=-1" in result.output
    assert "GrpTRES=gres/gpu=-1" in result.output
    assert "MaxTRES=gres/gpu=-1" in result.output


def test_qos_modify_sets_the_account_cap(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    result = CliRunner().invoke(main, ["qos", "modify", "kemp", "-A", "96"])
    assert result.exit_code == 0
    assert "MaxTRESPA=gres/gpu=96" in result.output


def test_qos_modify_explicit_clear(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    result = CliRunner().invoke(main, ["qos", "modify", "kemp", "-g", "8", "-G", "-1"])
    assert result.exit_code == 0
    assert "MaxTRESPU=gres/gpu=8 GrpTRES=gres/gpu=-1" in result.output


def test_qos_execute_stops_after_failure(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: False)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    ran = []

    def fake_probe(cmd):
        ran.append(cmd)
        return (1, "", "sacctmgr: boom")

    monkeypatch.setattr(process, "probe", fake_probe)
    result = CliRunner().invoke(main, ["qos", "create", "new_qos", "-g", "4", "--execute", "--yes"])
    assert result.exit_code == 1
    assert ran == [["sacctmgr", "-i", "add", "qos", "new_qos", "MaxTRESPU=gres/gpu=4"]]


def test_qos_execute_reports_failure(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "any_holders", lambda name: [])
    monkeypatch.setattr(qos, "partitions_referencing", lambda name, cluster=None: [])
    monkeypatch.setattr(qos, "partition_references", lambda name, cluster=None: {})
    monkeypatch.setattr(qos, "jobs_using", lambda name, cluster=None: 0)
    monkeypatch.setattr(process, "probe", lambda cmd: (1, "", "sacctmgr: boom"))
    result = CliRunner().invoke(main, ["qos", "delete", "kemp", "--execute", "--yes"])
    assert result.exit_code == 1
    assert "command failed" in result.output


def test_qos_grant_dry_run(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "get_accounts", lambda user, **k: ["kempner_dev"])
    monkeypatch.setattr(
        qos,
        "grant_plan",
        lambda *a, **k: [["sacctmgr", "-i", "modify", "user", "set", "QOS+=kemp"]],
    )
    ran = []
    monkeypatch.setattr(process, "probe", lambda cmd: ran.append(cmd) or (0, "", ""))
    result = CliRunner().invoke(main, ["qos", "grant", "kemp", "-u", "alice", "-p", "kempner_h100"])
    assert result.exit_code == 0
    assert "[DRY ] sacctmgr -i modify user set QOS+=kemp" in result.output
    assert ran == []


def test_qos_grant_missing_qos(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: False)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    result = CliRunner().invoke(main, ["qos", "grant", "ghost", "-u", "alice", "-p", "p"])
    assert result.exit_code != 0
    assert "not defined" in result.output


def test_qos_grant_missing_default_qos(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: name == "kemp")
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    result = CliRunner().invoke(
        main, ["qos", "grant", "kemp", "-u", "alice", "-p", "p", "-d", "ghost"]
    )
    assert result.exit_code != 0
    assert "default QoS ghost is not defined" in result.output


def test_qos_grant_skips_user_without_accounts(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "get_accounts", lambda user, **k: [])
    result = CliRunner().invoke(main, ["qos", "grant", "kemp", "-u", "ghost", "-p", "p"])
    assert result.exit_code == 0
    assert "no matching accounts" in result.output
    assert "Nothing to change" in result.output


def test_qos_revoke_all_must_be_alone(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    result = CliRunner().invoke(main, ["qos", "revoke", "kemp", "-u", "all,alice", "-p", "p"])
    assert result.exit_code == 2
    assert "all must be used on its own" in result.output


def test_qos_revoke_dry_run(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(
        qos,
        "revoke_targets_plan",
        lambda *a, **k: [["sacctmgr", "-i", "modify", "user", "set", "QOS-=kemp"]],
    )
    result = CliRunner().invoke(
        main, ["qos", "revoke", "kemp", "-u", "alice", "-p", "kempner_h100"]
    )
    assert result.exit_code == 0
    assert "[DRY ] sacctmgr -i modify user set QOS-=kemp" in result.output


def test_qos_retire_appends_delete(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "partitions_referencing", lambda name, cluster=None: [])
    monkeypatch.setattr(qos, "partition_references", lambda name, cluster=None: {})
    monkeypatch.setattr(qos, "jobs_using", lambda name, cluster=None: 0)
    monkeypatch.setattr(qos, "any_holders", lambda name: [])
    monkeypatch.setattr(qos, "revoke_targets_plan", lambda *a, **k: [])
    result = CliRunner().invoke(main, ["qos", "retire", "kemp", "-p", "kempner_h100"])
    assert result.exit_code == 0
    assert "[DRY ] sacctmgr -i delete qos kemp" in result.output


def test_qos_retire_nonexistent(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: False)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    result = CliRunner().invoke(main, ["qos", "retire", "ghost", "-p", "p"])
    assert result.exit_code == 0
    assert "nothing to do" in result.output


def test_qos_sync_already_in_sync(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "account_exists", lambda name, **k: True)
    monkeypatch.setattr(qos, "account_base_members", lambda account, **k: ["alice"])
    monkeypatch.setattr(qos, "holder_rows", lambda *a, **k: [("alice", "kempner_dev", "p")])
    result = CliRunner().invoke(main, ["qos", "sync", "kemp", "-a", "kempner_dev", "-p", "p"])
    assert result.exit_code == 0
    assert "already in sync" in result.output


def test_qos_sync_dry_run(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "account_exists", lambda name, **k: True)
    monkeypatch.setattr(qos, "account_base_members", lambda account, **k: ["bob"])
    monkeypatch.setattr(qos, "holder_rows", lambda *a, **k: [("alice", "kempner_dev", "p")])
    monkeypatch.setattr(
        qos, "grant_plan", lambda *a, **k: [["sacctmgr", "-i", "add", "user", "bob"]]
    )
    monkeypatch.setattr(
        qos, "revoke_plan", lambda *a, **k: [["sacctmgr", "-i", "del", "user", "alice"]]
    )
    result = CliRunner().invoke(main, ["qos", "sync", "kemp", "-a", "kempner_dev", "-p", "p"])
    assert result.exit_code == 0
    assert "add user bob" in result.output and "del user alice" in result.output


def test_qos_grant_execute(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "get_accounts", lambda user, **k: ["kempner_dev"])
    monkeypatch.setattr(qos, "grant_plan", lambda *a, **k: [["sacctmgr", "-i", "add", "user", "x"]])
    ran = []
    monkeypatch.setattr(process, "probe", lambda cmd: ran.append(cmd) or (0, "", ""))
    result = CliRunner().invoke(
        main, ["qos", "grant", "kemp", "-u", "alice", "-p", "p", "--execute", "--yes"]
    )
    assert result.exit_code == 0
    assert ran == [["sacctmgr", "-i", "add", "user", "x"]]


_QUOTA_NFS = "/x 1.5T 10T 1200000 5000000\n"


def test_storage_quota_all(monkeypatch):
    monkeypatch.setattr(storage, "user_groups", lambda u: ["kempner_dev"])
    monkeypatch.setattr(
        storage, "lab_targets", lambda g, r, **k: [("/n/netscratch/kempner_dev", "kempner_dev")]
    )
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, _QUOTA_NFS, ""))
    result = CliRunner().invoke(main, ["storage", "quota", "--all"])
    assert result.exit_code == 0
    assert result.output.splitlines()[0].split() == ["STORAGE", "USED", "QUOTA", "DISK%", "FILES%"]
    assert "/n/netscratch/kempner_dev" in result.output
    assert "15%" in result.output and "24%" in result.output


def test_storage_quota_all_no_labs(monkeypatch):
    monkeypatch.setattr(storage, "user_groups", lambda u: [])
    monkeypatch.setattr(storage, "lab_targets", lambda g, r, **k: [])
    result = CliRunner().invoke(main, ["storage", "quota", "--all"])
    assert result.exit_code != 0
    assert "no lab storage" in result.output


def test_storage_quota_fleet_sorts_by_usage(monkeypatch):
    monkeypatch.setattr(
        storage,
        "fleet_targets",
        lambda root, kw: [
            ("/n/holylfs06/LABS/kempner_dev", "kempner_dev"),
            ("/n/holylfs06/LABS/kempner_eng", "kempner_eng"),
        ],
    )

    def fake_probe(cmd, timeout=None):
        full = "9T" if "kempner_dev" in " ".join(cmd) else "1T"
        return (0, f"/x {full} 10T 100 1000\n", "")

    monkeypatch.setattr(process, "probe", fake_probe)
    result = CliRunner().invoke(main, ["storage", "quota", "holylfs06", "--fleet", "kempner"])
    assert result.exit_code == 0
    lines = result.output.splitlines()
    dev = next(i for i, line in enumerate(lines) if "kempner_dev" in line)
    eng = next(i for i, line in enumerate(lines) if "kempner_eng" in line)
    assert dev < eng


def test_storage_quota_fleet_needs_path():
    result = CliRunner().invoke(main, ["storage", "quota", "--fleet", "kempner"])
    assert result.exit_code == 2
    assert "holylfs06/LABS --fleet kempner" in result.output


def test_storage_quota_all_rejects_conflicting_arguments():
    """--all reports your own labs, so a PATH or --group would be silently ignored."""
    for extra in (["netscratch"], ["-g", "kempner_lab"], ["--fleet", "kempner"]):
        result = CliRunner().invoke(main, ["storage", "quota", "--all", *extra])
        assert result.exit_code == 2, extra
        assert "--all reports your own lab directories" in result.output


def test_storage_quota_no_args_errors():
    result = CliRunner().invoke(main, ["storage", "quota"])
    assert result.exit_code == 2
    assert "PATH" in result.output


def test_storage_quota_all_timeout_row(monkeypatch):
    monkeypatch.setattr(storage, "user_groups", lambda u: ["kempner_dev"])
    monkeypatch.setattr(
        storage, "lab_targets", lambda g, r, **k: [("/n/x/kempner_dev", "kempner_dev")]
    )
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (124, "", ""))
    result = CliRunner().invoke(main, ["storage", "quota", "--all"])
    assert result.exit_code != 0
    assert "timeout" in result.output
    assert "no quota could be read" in result.output


def test_storage_quota_all_reports_a_failure_rather_than_n_a(monkeypatch):
    """A permission denial is not the same as a filesystem the tool does not track."""
    monkeypatch.setattr(storage, "user_groups", lambda u: ["other_lab"])
    monkeypatch.setattr(storage, "lab_targets", lambda g, r, **k: [("/n/x/other_lab", "other_lab")])
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: (1, "", "lfs quota: Permission denied")
    )
    result = CliRunner().invoke(main, ["storage", "quota", "--all"])
    assert result.exit_code != 0
    assert "error" in result.output
    assert "Permission denied" in result.output


def _ib_topo(quality):
    return f"\tGPU0\tNIC0\tCPU Affinity\nGPU0\t X \t{quality}\t0-47\n"


def test_diag_ib_affinity_ok(monkeypatch):
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, _ib_topo("NODE"), ""))
    result = CliRunner().invoke(main, ["diag", "ib-affinity"])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_diag_ib_affinity_warn(monkeypatch):
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, _ib_topo("SYS"), ""))
    result = CliRunner().invoke(main, ["diag", "ib-affinity"])
    assert result.exit_code == 1
    assert "WARN" in result.output


def test_diag_ib_affinity_fail(monkeypatch):
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, _ib_topo("X"), ""))
    result = CliRunner().invoke(main, ["diag", "ib-affinity"])
    assert result.exit_code == 4
    assert "FAIL" in result.output


def test_diag_ib_affinity_no_data(monkeypatch):
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (127, "", ""))
    result = CliRunner().invoke(main, ["diag", "ib-affinity"])
    assert result.exit_code == 3


def test_diag_ib_affinity_snapshot(tmp_path):
    snap = tmp_path / "s.json"
    snap.write_text(json.dumps({"topology": {"raw": _ib_topo("NODE")}}))
    result = CliRunner().invoke(main, ["diag", "ib-affinity", "--snapshot", str(snap)])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_diag_ib_snapshot_stdout(monkeypatch):
    monkeypatch.setattr(fabric, "collect_snapshot", lambda: {"hostname": "n1", "ib": {"hcas": []}})
    result = CliRunner().invoke(main, ["diag", "ib-snapshot"])
    assert result.exit_code == 0
    assert json.loads(result.output)["hostname"] == "n1"


def test_diag_ib_snapshot_file(monkeypatch, tmp_path):
    monkeypatch.setattr(fabric, "collect_snapshot", lambda: {"hostname": "n1"})
    out = tmp_path / "snap.json"
    result = CliRunner().invoke(main, ["diag", "ib-snapshot", str(out)])
    assert result.exit_code == 0
    assert json.loads(out.read_text())["hostname"] == "n1"
    assert "wrote" in result.output


def _counter_file(tmp_path, name, value):
    snap = {
        "ib": {
            "hcas": [
                {"name": "mlx5_0", "ports": [{"port": 1, "counters": {"symbol_error": value}}]}
            ]
        }
    }
    path = tmp_path / name
    path.write_text(json.dumps(snap))
    return str(path)


def test_diag_ib_counters_ok(tmp_path):
    before = _counter_file(tmp_path, "b.json", 0)
    after = _counter_file(tmp_path, "a.json", 0)
    result = CliRunner().invoke(main, ["diag", "ib-counters", before, after])
    assert result.exit_code == 0
    assert "OK" in result.output


def test_diag_ib_counters_error(tmp_path):
    before = _counter_file(tmp_path, "b.json", 0)
    after = _counter_file(tmp_path, "a.json", 7)
    result = CliRunner().invoke(main, ["diag", "ib-counters", before, after])
    assert result.exit_code == 4
    assert "ERROR" in result.output and "FAIL" in result.output


def test_diag_ib_counters_bad_json(tmp_path):
    before = tmp_path / "b.json"
    before.write_text("not json")
    after = tmp_path / "a.json"
    after.write_text("{}")
    result = CliRunner().invoke(main, ["diag", "ib-counters", str(before), str(after)])
    assert result.exit_code == 3


def _verify_file(tmp_path, name, snap):
    path = tmp_path / name
    path.write_text(json.dumps(snap))
    return str(path)


def test_diag_ib_verify_match(tmp_path):
    snap = {
        "gpus": [],
        "ib": {"hcas": []},
        "ibdev2netdev": [],
        "topology": {"raw": ""},
        "system": {},
    }
    golden = _verify_file(tmp_path, "g.json", snap)
    current = _verify_file(tmp_path, "c.json", snap)
    result = CliRunner().invoke(main, ["diag", "ib-verify", golden, "--current", current])
    assert result.exit_code == 0
    assert "MATCH" in result.output


def test_diag_ib_verify_drift(tmp_path):
    base = {"ib": {"hcas": []}, "ibdev2netdev": [], "topology": {"raw": ""}, "system": {}}
    golden = _verify_file(tmp_path, "g.json", {**base, "gpus": [{"index": 0, "name": "A100"}]})
    current = _verify_file(tmp_path, "c.json", {**base, "gpus": [{"index": 0, "name": "H100"}]})
    result = CliRunner().invoke(main, ["diag", "ib-verify", golden, "--current", current])
    assert result.exit_code == 4
    assert "DRIFT" in result.output


def test_diag_ib_verify_save_golden(monkeypatch, tmp_path):
    monkeypatch.setattr(fabric, "collect_snapshot", lambda: {"hostname": "n1", "gpus": []})
    golden = tmp_path / "g.json"
    result = CliRunner().invoke(main, ["diag", "ib-verify", str(golden), "--save-golden"])
    assert result.exit_code == 0
    assert json.loads(golden.read_text())["hostname"] == "n1"
    assert "golden saved" in result.output


def test_diag_ib_verify_no_golden(tmp_path):
    current = _verify_file(tmp_path, "c.json", {"gpus": []})
    result = CliRunner().invoke(
        main, ["diag", "ib-verify", str(tmp_path / "missing.json"), "--current", current]
    )
    assert result.exit_code == 3
    assert "no golden" in result.output


def test_jobs_why_missing_job_errors(monkeypatch):
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, "", ""))
    _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "why", "999999999"])
    assert result.exit_code != 0
    assert "no longer in the queue" in result.output


def test_jobs_why_does_not_call_a_failed_query_a_missing_job(monkeypatch):
    """squeue failing is not the same answer as the job having finished."""
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: (1, "", "squeue: fatal: bad config")
    )
    result = CliRunner().invoke(main, ["jobs", "why", "12345"])
    assert result.exit_code != 0
    assert "could not query job 12345" in result.output
    assert "finished" not in result.output


def test_jobs_priorities_unknown_partition_errors(monkeypatch):
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [])
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "priorities", "nosuch"])
    assert result.exit_code != 0
    assert "does not exist" in result.output
    assert calls == []


def test_jobs_script_missing_job_errors(monkeypatch):
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: (1, "", "Invalid job id specified")
    )
    result = CliRunner().invoke(main, ["jobs", "script", "999999999"])
    assert result.exit_code != 0
    assert "no job 999999999 on this cluster" in result.output


def test_jobs_top_missing_job_errors(monkeypatch):
    monkeypatch.setattr(slurm, "job_accounting", lambda j: {})
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "top", "999999999"])
    assert result.exit_code != 0
    assert calls == []


def test_qos_delete_refuses_a_partition_referenced_qos(monkeypatch):
    """A QoS named in partition config holds real limits even with no association."""
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "any_holders", lambda name: [])
    monkeypatch.setattr(
        qos,
        "partition_references",
        lambda name, cluster=None: {"gpu": ["QoS"], "gpu_big": ["DenyQos"]},
    )
    result = CliRunner().invoke(main, ["qos", "delete", "base_caps", "--execute", "--yes"])
    assert result.exit_code != 0
    assert "gpu (QoS), gpu_big (DenyQos)" in result.output


def test_qos_retire_refuses_a_partition_referenced_qos(monkeypatch):
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "partition_references", lambda name, cluster=None: {"gpu": ["QoS"]})
    result = CliRunner().invoke(main, ["qos", "retire", "base_caps", "-p", "all", "-x", "-y"])
    assert result.exit_code != 0
    assert "gpu" in result.output


def test_qos_retire_refuses_when_holders_are_outside_the_sweep(monkeypatch):
    """Revoking nothing while holders remain must not still delete the QoS."""
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "partitions_referencing", lambda name, cluster=None: [])
    monkeypatch.setattr(qos, "partition_references", lambda name, cluster=None: {})
    monkeypatch.setattr(qos, "jobs_using", lambda name, cluster=None: 0)
    monkeypatch.setattr(qos, "revoke_targets_plan", lambda *a, **k: [])
    monkeypatch.setattr(qos, "any_holders", lambda name: ["odyssey|lab|bob|"])
    result = CliRunner().invoke(main, ["qos", "retire", "kemp", "-p", "kempner_h100", "-x", "-y"])
    assert result.exit_code != 0
    assert "would not revoke" in result.output


def test_qos_retire_refuses_an_uncovered_holder_beside_a_covered_one(monkeypatch):
    """A sweep that revokes one holder must not delete a QoS another still holds."""
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "partitions_referencing", lambda name, cluster=None: [])
    monkeypatch.setattr(qos, "partition_references", lambda name, cluster=None: {})
    monkeypatch.setattr(qos, "jobs_using", lambda name, cluster=None: 0)
    monkeypatch.setattr(
        qos,
        "revoke_targets_plan",
        lambda *a, **k: [
            [
                "sacctmgr",
                "-i",
                "modify",
                "user",
                "where",
                "user=bob",
                "account=lab",
                "partition=kempner_h100",
                "cluster=odyssey",
                "set",
                "QOS-=kemp",
            ]
        ],
    )
    monkeypatch.setattr(
        qos,
        "any_holders",
        lambda name: ["odyssey|lab|bob|", "odyssey|lab|bob|kempner_h100"],
    )
    result = CliRunner().invoke(main, ["qos", "retire", "kemp", "-p", "all", "-x", "-y"])
    assert result.exit_code != 0
    assert "odyssey|lab|bob|" in result.output
    assert "delete qos kemp" not in result.output


def test_gpu_usage_without_a_cap_omits_the_denominator(monkeypatch):
    """A site with no per-account GPU cap gets plain counts, not a made up limit."""
    monkeypatch.setattr(slurm, "account_cap", lambda: None)
    monkeypatch.setattr(slurm, "gpu_by_account", lambda parts: {"lab_a": 7, "lab_b": 3})
    result = CliRunner().invoke(main, ["gpu", "usage"])
    assert result.exit_code == 0
    assert "no per-account GPU cap is set" in result.output
    assert "/" not in result.output.split("highest first")[1].split("----")[0]
    assert "10 GPU in use across 2 account(s)" in result.output


def test_gpu_usage_one_lab_without_a_cap(monkeypatch):
    monkeypatch.setattr(slurm, "account_cap", lambda: None)
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
    monkeypatch.setattr(slurm, "priority_partitions", lambda: [])
    monkeypatch.setattr(slurm, "gpu_rows", lambda a, parts: [("alice", "gpu", 4)])
    result = CliRunner().invoke(main, ["gpu", "usage", "lab_a"])
    assert result.exit_code == 0
    assert "ACCOUNT TOTAL: 4 GPU" in result.output
    assert "% of the cap" not in result.output
    assert "-GPU account cap" not in result.output


def test_gpu_usage_suggests_the_lab_account_when_nothing_found(monkeypatch):
    """A bare name with no usage anywhere is usually the wrong account."""
    monkeypatch.setattr(slurm, "account_cap", lambda: 96)
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
    monkeypatch.setattr(slurm, "priority_partitions", lambda: [])
    monkeypatch.setattr(slurm, "gpu_rows", lambda a, parts: [])
    monkeypatch.setattr(site, "lab_account_prefix", lambda: "kempner_")
    result = CliRunner().invoke(main, ["gpu", "usage", "ydu_lab"])
    assert result.exit_code == 0
    assert "kempner_ydu_lab also exists" in result.output


def test_gpu_usage_does_not_suggest_when_usage_exists(monkeypatch):
    monkeypatch.setattr(slurm, "account_cap", lambda: 96)
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
    monkeypatch.setattr(slurm, "priority_partitions", lambda: [])
    monkeypatch.setattr(slurm, "pending_at_cap", lambda a, p: 0)
    monkeypatch.setattr(slurm, "gpu_rows", lambda a, parts: [("alice", "kempner", 2)])
    monkeypatch.setattr(site, "lab_account_prefix", lambda: "kempner_")
    result = CliRunner().invoke(main, ["gpu", "usage", "ydu_lab"])
    assert result.exit_code == 0
    assert "also exists" not in result.output


def test_gpu_usage_does_not_suggest_for_an_already_prefixed_account(monkeypatch):
    monkeypatch.setattr(slurm, "account_cap", lambda: 96)
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
    monkeypatch.setattr(slurm, "priority_partitions", lambda: [])
    monkeypatch.setattr(slurm, "gpu_rows", lambda a, parts: [])
    monkeypatch.setattr(site, "lab_account_prefix", lambda: "kempner_")
    result = CliRunner().invoke(main, ["gpu", "usage", "kempner_ydu_lab"])
    assert result.exit_code == 0
    assert "also exists" not in result.output


def test_gpu_avail_skips_unschedulable_nodes(monkeypatch):
    """Free GPUs on a drained node cannot take a job, so listing them misleads."""
    nodes = [
        _cap_node("healthy", 4, 96, 1440000),
        _cap_node("drained", 4, 96, 1440000, available=False),
    ]
    monkeypatch.setattr(slurm, "node_capacity", lambda: nodes)
    result = CliRunner().invoke(main, ["gpu", "avail", "kempner_h100"])
    assert result.exit_code == 0
    assert "healthy" in result.output
    assert "drained" not in result.output


def test_gpu_avail_reads_the_fleet_once(monkeypatch):
    """One scontrol pass, not one per node: a large partition was taking minutes."""
    passes = []
    monkeypatch.setattr(
        slurm,
        "node_capacity",
        lambda: passes.append(1) or [_cap_node(f"n{i}", 4, 96, 1440000) for i in range(50)],
    )
    result = CliRunner().invoke(main, ["gpu", "avail", "kempner_h100"])
    assert result.exit_code == 0
    assert len(passes) == 1


def test_gpu_session_omits_sizing_without_configured_limits(monkeypatch):
    """A site can map a GPU type to a partition it sets no per-GPU ratio for."""
    monkeypatch.setattr(slurm, "GPU_TYPE_PARTITION", {"a100": "gpu"}, raising=False)
    monkeypatch.setattr(slurm, "PARTITION_LIMITS", {}, raising=False)
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["gpu", "session", "a100", "-A", "acct"])
    assert result.exit_code == 0
    built = " ".join(calls[0])
    assert "--gres=gpu:1" in built
    assert "--cpus-per-task" not in built
    assert "--mem=" not in built


def test_jobs_new_script_omits_sizing_without_configured_limits(monkeypatch):
    from clustertool.commands.jobs.new import _build_script

    monkeypatch.setattr(slurm, "GPU_TYPE_PARTITION", {"a100": "gpu"}, raising=False)
    monkeypatch.setattr(slurm, "PARTITION_LIMITS", {}, raising=False)
    script = _build_script("a100", 1, 1, "0-01:00", "acct", "job", None, None)
    assert "--gres=gpu:1" in script
    assert "--cpus-per-task" not in script
    assert "--mem=" not in script


def test_jobs_new_script_still_honors_an_override_without_config(monkeypatch):
    from clustertool.commands.jobs.new import _build_script

    monkeypatch.setattr(slurm, "GPU_TYPE_PARTITION", {"a100": "gpu"}, raising=False)
    monkeypatch.setattr(slurm, "PARTITION_LIMITS", {}, raising=False)
    script = _build_script("a100", 2, 1, "0-01:00", "acct", "job", 8, 50000)
    assert "--cpus-per-task=16" in script
    assert "--mem=100000" in script


def test_qos_sync_refuses_when_no_base_members(monkeypatch):
    """An account read that finds nobody would otherwise revoke every holder."""
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "account_exists", lambda name, **k: True)
    monkeypatch.setattr(qos, "account_base_members", lambda account, **k: [])
    result = CliRunner().invoke(
        main, ["qos", "sync", "kemp", "-a", "lab", "-p", "kempner_h100", "-x", "-y"]
    )
    assert result.exit_code != 0
    assert "every holder would be revoked" in result.output


def test_qos_sync_can_revoke_a_lingering_holder(monkeypatch):
    """A holder whose base membership is gone must actually be revoked."""
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)
    monkeypatch.setattr(qos, "account_exists", lambda name, **k: True)
    monkeypatch.setattr(qos, "account_base_members", lambda account, **k: ["alice"])
    monkeypatch.setattr(
        qos, "holder_rows", lambda *a, **k: [("alice", "lab", "p"), ("stale", "lab", "p")]
    )
    monkeypatch.setattr(qos, "grant_plan", lambda *a, **k: [])
    monkeypatch.setattr(qos, "revoke_plan", lambda u, *a, **k: [["sacctmgr", "revoke", u]])
    result = CliRunner().invoke(main, ["qos", "sync", "kemp", "-a", "lab", "-p", "p"])
    assert result.exit_code == 0
    assert "revoke stale" in result.output
    assert "revoke alice" not in result.output


def test_jobs_new_submit_reports_a_failed_sbatch(monkeypatch):
    """A rejected submission must not read as success."""
    monkeypatch.setattr(
        process,
        "probe",
        lambda cmd, timeout=None, input_text=None: (1, "", "sbatch: error: Invalid account\n"),
    )
    result = CliRunner().invoke(
        main, ["jobs", "new", "--gpu-type", "a100", "-A", "nope", "--submit"]
    )
    assert result.exit_code != 0
    assert "Invalid account" in result.output


def test_jobs_new_submit_reports_a_missing_sbatch(monkeypatch):
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None, input_text=None: (127, "", ""))
    result = CliRunner().invoke(main, ["jobs", "new", "--gpu-type", "a100", "-A", "x", "--submit"])
    assert result.exit_code != 0
    assert "not found on this host" in result.output


def test_jobs_new_rejects_non_positive_counts():
    for flag, value in (("--gpus", "0"), ("--gpus", "-1"), ("--nodes", "0")):
        result = CliRunner().invoke(
            main, ["jobs", "new", "--gpu-type", "a100", "-A", "x", flag, value]
        )
        assert result.exit_code != 0, f"{flag} {value} was accepted"


def test_jobs_new_output_error_is_reported_cleanly(tmp_path):
    target = tmp_path / "missing-dir" / "job.sh"
    result = CliRunner().invoke(
        main, ["jobs", "new", "--gpu-type", "a100", "-A", "x", "-o", str(target)]
    )
    assert result.exit_code != 0
    assert "cannot write" in result.output


def test_jobs_new_sets_one_task_per_node():
    result = CliRunner().invoke(
        main, ["jobs", "new", "--gpu-type", "a100", "-A", "x", "--nodes", "2"]
    )
    assert result.exit_code == 0
    assert "#SBATCH --ntasks-per-node=1" in result.output


def test_gpu_pulse_node_needs_a_value(monkeypatch):
    """--node swallowed the next flag as a hostname; --job silently ran locally."""
    calls = _capture_stream(monkeypatch)
    for args in (["--node", "--dry-run"], ["--job"], ["--node"]):
        result = CliRunner().invoke(main, ["gpu", "pulse", *args])
        assert result.exit_code != 0, args
        assert "needs a value" in result.output
    assert calls == []


def test_gpu_pulse_forwards_unknown_args(monkeypatch):
    from clustertool.commands.gpu.pulse import _split_args

    node, job, forward, dry_run = _split_args(("--node", "n1", "--once", "--gpus", "0,1"))
    assert node == "n1"
    assert job is None
    assert forward == ["--once", "--gpus", "0,1"]
    assert dry_run is False


def _counter_snap(**counters):
    return {"ib": {"hcas": [{"name": "mlx5_0", "ports": [{"port": 1, "counters": counters}]}]}}


def _write_snaps(tmp_path, before, after):
    (tmp_path / "b.json").write_text(json.dumps(before))
    (tmp_path / "a.json").write_text(json.dumps(after))
    return str(tmp_path / "b.json"), str(tmp_path / "a.json")


def test_ib_counters_renders_an_unreadable_counter(tmp_path):
    """A None delta must not reach a +format, which raises TypeError."""
    before, after = _write_snaps(
        tmp_path, _counter_snap(symbol_error=None), _counter_snap(symbol_error=5)
    )
    result = CliRunner().invoke(main, ["diag", "ib-counters", before, after])
    assert result.exit_code == 4
    assert "UNREADABLE" in result.output
    assert "Traceback" not in result.output


def test_ib_counters_flags_a_reset(tmp_path):
    """A counter that went backwards was reset, so its new value is unaccounted for."""
    before, after = _write_snaps(
        tmp_path, _counter_snap(symbol_error=900), _counter_snap(symbol_error=3)
    )
    result = CliRunner().invoke(main, ["diag", "ib-counters", before, after])
    assert result.exit_code == 4
    assert "RESET" in result.output


def test_ib_counters_clean_window(tmp_path):
    before, after = _write_snaps(
        tmp_path,
        _counter_snap(symbol_error=0, port_rcv_data=100),
        _counter_snap(symbol_error=0, port_rcv_data=200),
    )
    result = CliRunner().invoke(main, ["diag", "ib-counters", before, after])
    assert result.exit_code == 0
    assert "OK: no error-class counter growth" in result.output


def test_gpu_pulse_job_refuses_another_users_job(monkeypatch):
    """--job reaches a node by ssh, so it must be scoped like monitor-job and nvtop."""
    monkeypatch.setenv("USER", "alice")
    monkeypatch.setattr(slurm, "job_owner", lambda j: "bob")
    ran = []
    monkeypatch.setattr(slurm, "job_nodes", lambda j: ran.append(j) or ["n1"])
    result = CliRunner().invoke(main, ["gpu", "pulse", "--job", "123", "--dry-run"])
    assert result.exit_code != 0
    assert "belongs to bob, not you" in result.output
    assert ran == []


def test_ib_counters_ignores_a_port_in_ethernet_mode(tmp_path):
    """An adapter in Ethernet mode exposes IB counter files that often read as errors."""
    snap = {
        "ib": {
            "hcas": [
                {
                    "name": "mlx5_0",
                    "ports": [
                        {
                            "port": 1,
                            "link_layer": "InfiniBand",
                            "counters": {"symbol_error": 0, "port_rcv_data": 100},
                        }
                    ],
                },
                {
                    "name": "mlx5_1",
                    "ports": [
                        {
                            "port": 1,
                            "link_layer": "Ethernet",
                            "counters": {"symbol_error": None, "VL15_dropped": None},
                        }
                    ],
                },
            ]
        }
    }
    before, after = _write_snaps(tmp_path, snap, snap)
    result = CliRunner().invoke(main, ["diag", "ib-counters", before, after])
    assert result.exit_code == 0
    assert "mlx5_1" not in result.output


def test_nvlink_narrows_the_slurm_allocation(monkeypatch):
    """--gpus must select within CUDA_VISIBLE_DEVICES, not be discarded by it."""
    import importlib

    nv = importlib.import_module("clustertool.commands.diag.nvlink")

    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "4,5,6,7")
    assert nv._device_list(2, False) == ["4", "5"]
    assert nv._device_list(4, False) == ["4", "5", "6", "7"]
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES")
    with pytest.raises(click.ClickException):
        nv._device_list(2, False)
    assert nv._device_list(2, True) == ["0", "1"]


def test_entry_restores_the_default_sigpipe_disposition():
    """Python's ignore-and-raise turns a closed pipe into a spurious exit 1."""
    import signal

    from clustertool import entry

    original = signal.getsignal(signal.SIGPIPE)
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
        entry._restore_sigpipe()
        assert signal.getsignal(signal.SIGPIPE) == signal.SIG_DFL
    finally:
        signal.signal(signal.SIGPIPE, original)


def test_jobs_list_rejects_a_filter_that_names_nothing(monkeypatch):
    """squeue answers a mistyped user, partition or account with an empty list."""
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(slurm, "user_exists", lambda u: False)
    monkeypatch.setattr(slurm, "partition_exists", lambda p: False)
    monkeypatch.setattr(slurm, "account_exists", lambda a: False)
    for flag, value, expected in (
        ("-u", "nobody", "no such user"),
        ("-p", "nowhere", "does not exist"),
        ("-A", "nothing", "does not exist"),
    ):
        result = CliRunner().invoke(main, ["jobs", "list", flag, value])
        assert result.exit_code != 0
        assert expected in result.output
    assert calls == []


def test_jobs_list_does_not_check_the_default_user(monkeypatch):
    """The current user always exists, so the common path stays one squeue call."""
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(slurm, "user_exists", _unexpected)
    result = CliRunner().invoke(main, ["jobs", "list"])
    assert result.exit_code == 0
    assert calls[0][0] == "squeue"


def _unexpected(*args, **kwargs):
    raise AssertionError("no lookup should happen")


def test_status_bucket_counts_a_non_responding_node_as_down():
    """man sinfo: a node marked * "will not be allocated any new work"."""
    for state in ("idle*", "mix*", "alloc*"):
        assert slurm._status_bucket(state) == "down", state


def test_status_bucket_keeps_the_reason_for_an_already_unavailable_node():
    """drain and resv say the same thing about availability, and name the cause."""
    assert slurm._status_bucket("drain*") == "drain"
    assert slurm._status_bucket("resv*") == "resv"


def test_diag_reserves_exit_2_for_usage_errors():
    """A caller has to tell a mistyped command from a fault the probe found."""
    for args in (
        ["diag", "ib", "--no-such-flag"],
        ["diag", "gpu-health", "--no-such-flag"],
        ["diag", "io-probe", "--no-such-flag"],
        ["diag", "ib-counters"],
    ):
        result = CliRunner().invoke(main, args)
        assert result.exit_code == 2, args


def test_ib_affinity_separates_corrupt_json_from_the_wrong_shape(tmp_path):
    """A truncated file and a valid file of the wrong kind need different fixes."""
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json")
    result = CliRunner().invoke(main, ["diag", "ib-affinity", "--snapshot", str(corrupt)])
    assert result.exit_code == 3
    assert "not valid JSON" in result.output

    wrong = tmp_path / "wrong.json"
    wrong.write_text('{"a": 1}')
    result = CliRunner().invoke(main, ["diag", "ib-affinity", "--snapshot", str(wrong)])
    assert result.exit_code == 3
    assert "not an ib-snapshot file" in result.output


def test_ib_counters_names_the_file_it_could_not_read(tmp_path):
    """With two snapshot arguments, the error has to say which one failed."""
    good = tmp_path / "good.json"
    good.write_text('{"ib": {"hcas": []}}')
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json")

    result = CliRunner().invoke(main, ["diag", "ib-counters", str(good), str(corrupt)])
    assert result.exit_code == 3
    assert "AFTER" in result.output and "corrupt.json" in result.output

    result = CliRunner().invoke(main, ["diag", "ib-counters", str(corrupt), str(good)])
    assert result.exit_code == 3
    assert "BEFORE" in result.output and "corrupt.json" in result.output


def test_counter_deltas_does_not_fault_a_congestion_counter():
    """port_xmit_wait reads in the billions on a healthy busy node."""

    def snap(wait, symbol=0):
        return {
            "ib": {
                "hcas": [
                    {
                        "name": "mlx5_0",
                        "ports": [
                            {
                                "port": 1,
                                "link_layer": "InfiniBand",
                                "counters": {"port_xmit_wait": wait, "symbol_error": symbol},
                            }
                        ],
                    }
                ]
            }
        }

    rows, any_error = fabric.counter_deltas(snap(1000), snap(9_000_000))
    assert any_error is False
    assert any(row[1] == "port_xmit_wait" for row in rows)
    _, any_error = fabric.counter_deltas(snap(1000), snap(9_000_000, symbol=3))
    assert any_error is True


def test_qos_write_reads_the_definition_back(monkeypatch):
    """A limit that can be written has to be readable, and no command showed it."""
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    monkeypatch.setattr(qos, "partition_exists", lambda name, cluster=None: True)

    def fake_probe(cmd, timeout=None):
        if cmd[:4] == ["sacctmgr", "-n", "-P", "show"]:
            return 0, "12|gres/gpu=4|gres/gpu=32|||||\n", ""
        return 0, "", ""

    monkeypatch.setattr(process, "probe", fake_probe)
    result = CliRunner().invoke(main, ["qos", "modify", "kemp", "-A", "32", "--execute", "--yes"])
    assert result.exit_code == 0
    assert "Per-account max  gres/gpu=32" in result.output
    assert "Per-user max     gres/gpu=4" in result.output


def test_qos_dry_run_does_not_claim_a_definition(monkeypatch):
    """Nothing was written, so there is nothing to read back."""
    monkeypatch.setattr(qos, "qos_exists", lambda name: True)
    result = CliRunner().invoke(main, ["qos", "modify", "kemp", "-A", "32"])
    assert result.exit_code == 0
    assert "now carries" not in result.output


def test_jobs_script_takes_only_the_first_block_of_an_array(monkeypatch):
    """sacct answers a whole array with one titled block per element."""
    rule = "-" * 80
    out = (
        f"Batch Script for 7_0\n{rule}\n#!/bin/bash\necho one\n"
        f"Batch Script for 7_1\n{rule}\n#!/bin/bash\necho one\n"
    )
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, out, ""))
    result = CliRunner().invoke(main, ["jobs", "script", "7"])
    assert result.exit_code == 0
    assert "Batch Script for" not in result.output
    assert result.output.strip() == "#!/bin/bash\necho one"


def test_jobs_script_names_a_denied_script(monkeypatch):
    """Slurm lets only the owner or a privileged user read a batch script."""

    def fake_probe(cmd, timeout=None):
        if cmd[0] == "sacct":
            return 0, "", ""
        return 1, "", "Access/permission denied"

    monkeypatch.setattr(process, "probe", fake_probe)
    result = CliRunner().invoke(main, ["jobs", "script", "123"])
    assert result.exit_code != 0
    assert "belongs to another user" in result.output


def test_jobs_why_does_not_force_sprio_to_show_unweighted_factors(monkeypatch):
    """man sprio's default format lists only the factors a cluster weights."""
    captured = {}

    def fake_probe(cmd, timeout=None):
        captured.setdefault(cmd[0], cmd)
        if cmd[0] == "squeue":
            return 0, "12345 PENDING Priority\n", ""
        return 0, _SPRIO_ROWS, ""

    monkeypatch.setattr(process, "probe", fake_probe)
    result = CliRunner().invoke(main, ["jobs", "why", "12345"])
    assert result.exit_code == 0
    assert "-l" not in captured["sprio"]


def test_job_accounting_counts_array_elements_not_rows(monkeypatch):
    """sacct folds a contiguous pending range onto one row without --array."""
    rows = (
        "7_0|RUNNING|0:0|00:01:00|01:00:00|1G||n1\n"
        "7_1|RUNNING|0:0|00:01:00|01:00:00|1G||n1\n"
        "7_2|PENDING|0:0|00:00:00|01:00:00|1G||None assigned\n"
        "7_3|PENDING|0:0|00:00:00|01:00:00|1G||None assigned\n"
    )
    seen = {}

    def fake_probe(cmd, timeout=None):
        seen["cmd"] = cmd
        return 0, rows, ""

    monkeypatch.setattr(slurm.process, "probe", fake_probe)
    info = slurm.job_accounting("7")
    assert "--array" in seen["cmd"]
    assert info["element_count"] == 4
    assert info["states"] == {"RUNNING": 2, "PENDING": 2}
    assert info["first_element"] == "7_0"


def test_jobs_violators_checks_the_partition_even_when_both_norms_are_given(monkeypatch):
    """The existence check sat inside the branch that only ran when norms were missing."""
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [])
    monkeypatch.setattr(slurm, "running_jobs_reqtres", lambda p: [])
    result = CliRunner().invoke(
        main, ["jobs", "violators", "nope", "--cpus-per-gpu", "4", "--mem-per-gpu", "1000"]
    )
    assert result.exit_code != 0
    assert "does not exist" in result.output


def _requeue_stub(monkeypatch, state="RUNNING", owner=None, elapsed="01:00:00"):
    owner = owner if owner is not None else _ME
    row = f"{state} {owner} {elapsed}\n" if state else ""
    monkeypatch.setattr(process, "probe", lambda cmd, timeout=None: (0, row, ""))


def test_jobs_requeue_refuses_another_users_job(monkeypatch):
    calls = _capture_stream(monkeypatch)
    _requeue_stub(monkeypatch, owner="someone-else")
    result = CliRunner().invoke(main, ["jobs", "requeue", "123"])
    assert result.exit_code != 0
    assert "belong to another user" in result.output
    assert calls == []


def test_jobs_requeue_refuses_a_job_not_in_the_queue(monkeypatch):
    """scontrol requeue on a purged id reports only 'Invalid job id specified'."""
    calls = _capture_stream(monkeypatch)
    _requeue_stub(monkeypatch, state="")
    result = CliRunner().invoke(main, ["jobs", "requeue", "123"])
    assert result.exit_code != 0
    assert "not in the queue" in result.output
    assert calls == []


def test_jobs_requeue_prompts_for_a_running_job(monkeypatch):
    calls = _capture_stream(monkeypatch)
    _requeue_stub(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "requeue", "123"], input="n\n")
    assert result.exit_code != 0
    assert "that work will be discarded" in result.output
    assert calls == []


def test_jobs_requeue_does_not_prompt_for_a_pending_job(monkeypatch):
    """A pending job has no work to lose, so the prompt would be noise."""
    calls = _capture_stream(monkeypatch)
    _requeue_stub(monkeypatch, state="PENDING", elapsed="0:00")
    result = CliRunner().invoke(main, ["jobs", "requeue", "123"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "requeue", "123"]


def test_jobs_requeue_yes_skips_the_prompt(monkeypatch):
    calls = _capture_stream(monkeypatch)
    _requeue_stub(monkeypatch)
    result = CliRunner().invoke(main, ["jobs", "requeue", "123", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "requeue", "123"]


def test_account_balance_keeps_a_share_too_small_to_print(monkeypatch):
    """sshare prints NormShares to six decimals, so a real share can round to zero."""
    accounts = [
        {
            "account": "big_lab",
            "raw_shares": 3578602,
            "norm_shares": 0.999999,
            "effectv_usage": 0.5,
            "raw_usage": 500,
        },
        {
            "account": "tiny_lab",
            "raw_shares": 1,
            "norm_shares": 0.0,
            "effectv_usage": 0.0,
            "raw_usage": 0,
        },
    ]
    monkeypatch.setattr(slurm, "account_shares", lambda a=None: accounts)
    result = CliRunner().invoke(main, ["account", "balance"])
    assert result.exit_code == 0
    assert "2 account(s) with shares" in result.output
    assert "tiny_lab" in result.output


def test_account_balance_does_not_invent_a_share_for_one_account(monkeypatch):
    """With no siblings in the result there is nothing to normalize against."""
    accounts = [
        {
            "account": "tiny_lab",
            "raw_shares": 1,
            "norm_shares": 0.0,
            "effectv_usage": 0.0,
            "raw_usage": 0,
        },
    ]
    monkeypatch.setattr(slurm, "account_shares", lambda a=None: accounts)
    monkeypatch.setattr(slurm, "account_exists", lambda a: True)
    result = CliRunner().invoke(main, ["account", "balance", "tiny_lab"])
    assert result.exit_code == 0
    assert "1.000000" not in result.output
    assert "most over-served" not in result.output


def test_jobs_script_keeps_a_dashes_line_inside_the_script():
    """A rule of dashes is ordinary in a heredoc; splitting there truncates silently."""
    from clustertool.commands.jobs.script import _script_body

    rule = "-" * 80
    body = f"#!/bin/bash\ncat <<EOF\n{rule}\n---\nEOF\necho done"
    out = f"Batch Script for 7\n{rule}\n{body}\n"
    assert _script_body(out) == ("script", body)


def test_jobs_script_still_splits_an_array_on_the_title():
    from clustertool.commands.jobs.script import _script_body

    rule = "-" * 80
    out = (
        f"Batch Script for 7_0\n{rule}\n#!/bin/bash\necho one\n"
        f"Batch Script for 7_1\n{rule}\n#!/bin/bash\necho one\n"
    )
    assert _script_body(out) == ("script", "#!/bin/bash\necho one")


def test_jobs_script_refuses_a_step_id(monkeypatch):
    """scontrol show job takes no step id, and sacct answers one for the job."""
    calls = []
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: calls.append(cmd) or (0, "", "")
    )
    result = CliRunner().invoke(main, ["jobs", "script", "123.batch"])
    assert result.exit_code != 0
    assert "names a step" in result.output
    assert calls == []


def test_jobs_show_accepts_a_heterogeneous_component(monkeypatch):
    """man squeue: a heterogeneous allocation's id is of the form #+#."""
    calls = []
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: calls.append(cmd) or (0, "JobId=x\n", "")
    )
    result = CliRunner().invoke(main, ["jobs", "show", "123+0"])
    assert result.exit_code == 0
    assert calls[0][-1] == "123+0"


def test_jobs_show_refuses_forms_scontrol_rejects(monkeypatch):
    """A step id and an array range both fail client-side in scontrol show job."""
    calls = []
    monkeypatch.setattr(
        process, "probe", lambda cmd, timeout=None: calls.append(cmd) or (0, "", "")
    )
    for bad in ("123.batch", "123_[0-9]", "١٢٣"):
        result = CliRunner().invoke(main, ["jobs", "show", bad])
        assert result.exit_code != 0, bad
    assert calls == []


def test_nodes_resume_expands_a_hostlist(monkeypatch):
    """scontrol expands node[1-4], so the count must be of nodes, not arguments."""
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(
        slurm,
        "resumable_nodes_by_name",
        lambda names: {"n1": ("n1", "DOWN", "a"), "n2": ("n2", "DOWN+DRAIN", "b")},
    )
    result = CliRunner().invoke(main, ["nodes", "resume", "n[1-2]"], input="n\n")
    assert "Resume 2 node(s)" in result.output
    assert "n1" in result.output and "n2" in result.output
    assert calls == []


def test_nodes_resume_refuses_a_name_that_resolves_to_nothing(monkeypatch):
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(slurm, "resumable_nodes_by_name", lambda names: {})
    result = CliRunner().invoke(main, ["nodes", "resume", "nope", "-y"])
    assert result.exit_code != 0
    assert "Slurm does not know: nope" in result.output
    assert calls == []


def test_nodes_resume_collapses_a_repeated_name(monkeypatch):
    calls = _capture_stream(monkeypatch)
    monkeypatch.setattr(slurm, "resumable_nodes_by_name", lambda names: {"n1": ("n1", "DOWN", "")})
    result = CliRunner().invoke(main, ["nodes", "resume", "n1", "n1", "-y"])
    assert result.exit_code == 0
    assert calls[0] == ["scontrol", "update", "NodeName=n1", "State=RESUME"]


def test_resumable_states_match_what_slurm_prints():
    """Slurm prints REBOOT_REQUESTED and REBOOT_ISSUED, never a bare REBOOT."""
    assert "REBOOT_REQUESTED" in slurm.RESUMABLE_STATES
    assert "REBOOT_ISSUED" in slurm.RESUMABLE_STATES
    assert "REBOOT" not in slurm.RESUMABLE_STATES


def test_gpu_monitor_job_ignores_a_spoofed_user(monkeypatch):
    """$USER is writable by the caller, so it cannot stand in for the real uid."""
    monkeypatch.setenv("USER", "someoneelse")
    monkeypatch.setattr(slurm, "job_owner", lambda jobid: "someoneelse")
    result = CliRunner().invoke(main, ["gpu", "monitor-job", "1"])
    assert result.exit_code == 1
    assert "belongs to someoneelse" in result.output


def test_gpu_nvtop_ignores_a_spoofed_user(monkeypatch):
    monkeypatch.setenv("USER", "someoneelse")
    monkeypatch.setattr(slurm, "job_owner", lambda jobid: "someoneelse")
    result = CliRunner().invoke(main, ["gpu", "nvtop", "1"])
    assert result.exit_code == 1
    assert "belongs to someoneelse" in result.output


def test_gpu_pulse_ignores_a_spoofed_user(monkeypatch):
    monkeypatch.setenv("USER", "someoneelse")
    monkeypatch.setattr(slurm, "job_owner", lambda jobid: "someoneelse")
    result = CliRunner().invoke(main, ["gpu", "pulse", "--job", "1"])
    assert result.exit_code == 1
    assert "belongs to someoneelse" in result.output


def test_diag_ib_reports_active_defer(monkeypatch):
    """State 5 is ACTIVE_DEFER, which the word ACTIVE is a substring of."""
    monkeypatch.setattr(qos, "partition_exists", lambda p: True)
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle")])
    monkeypatch.setattr(
        process,
        "probe",
        lambda cmd, **kw: (0, "mlx5_0/ports/1 5: ACTIVE_DEFER\n__clustertool_ports__ 1\n", ""),
    )
    result = CliRunner().invoke(main, ["diag", "ib", "p"])
    assert result.exit_code == 4
    assert "ACTIVE_DEFER" in result.output


def test_diag_ib_refuses_a_partition_that_returned_no_nodes(monkeypatch):
    """sinfo hides a partition the caller's group cannot use, so empty is not proof."""
    monkeypatch.setattr(qos, "partition_exists", lambda p: True)
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [])
    result = CliRunner().invoke(main, ["diag", "ib", "p"])
    assert result.exit_code == 3
    assert "not proof" in result.output


def test_diag_ib_checks_every_name_before_probing(monkeypatch):
    """A typo at the end of the list must not discard a fault found earlier in it."""
    monkeypatch.setattr(qos, "partition_exists", lambda p: p != "typo")
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: pytest.fail("probed anyway"))
    result = CliRunner().invoke(main, ["diag", "ib", "good", "typo"])
    assert result.exit_code == 3
    assert "'typo' does not exist" in result.output


def test_diag_ib_reports_why_a_host_was_unreachable(monkeypatch):
    monkeypatch.setattr(qos, "partition_exists", lambda p: True)
    monkeypatch.setattr(slurm, "partition_nodes", lambda p: [("n1", "idle")])
    monkeypatch.setattr(
        process,
        "probe",
        lambda cmd, **kw: (
            255,
            "",
            "Warning: Permanently added 'n1' to the list of known hosts.\n"
            "Access denied by pam_slurm_adopt: you have no active jobs on this node\n",
        ),
    )
    result = CliRunner().invoke(main, ["diag", "ib", "p"])
    assert result.exit_code == 1
    assert "n1: Access denied by pam_slurm_adopt" in result.output


def test_diag_ib_affinity_rejects_a_non_string_raw(tmp_path):
    """json.loads accepts null there, and .strip() would then traceback out as exit 1."""
    path = tmp_path / "s.json"
    path.write_text('{"topology": {"raw": null}}')
    result = CliRunner().invoke(main, ["diag", "ib-affinity", "--snapshot", str(path)])
    assert result.exit_code == 3
    assert "not text" in result.output


def test_diag_ib_affinity_rejects_a_file_that_is_not_utf8(tmp_path):
    path = tmp_path / "s.json"
    path.write_bytes(b"\xf0\x9d\x00\xff\x9d")
    result = CliRunner().invoke(main, ["diag", "ib-affinity", "--snapshot", str(path)])
    assert result.exit_code == 3
    assert "cannot read" in result.output


def test_diag_ib_affinity_reports_an_unknown_quality_as_a_parse_gap(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(
        json.dumps({"topology": {"raw": "\tGPU0\tNIC0\nGPU0\t X \tC2C\nNIC0\tC2C\t X \n"}})
    )
    result = CliRunner().invoke(main, ["diag", "ib-affinity", "--snapshot", str(path)])
    assert result.exit_code == 3
    assert "does not know: C2C" in result.output
    assert "reach no NIC" not in result.output


def test_storage_quota_refuses_verbose_with_a_table():
    """-v shows the command behind one lookup, and a table runs one per directory."""
    result = CliRunner().invoke(main, ["storage", "quota", "--all", "-v"])
    assert result.exit_code == 2
    assert "applies to neither" in result.output


def test_storage_quota_refuses_fleet_with_a_group():
    result = CliRunner().invoke(
        main, ["storage", "quota", "holylfs06/LABS", "--fleet", "kempner", "-g", "x"]
    )
    assert result.exit_code == 2
    assert "takes neither --group nor --user" in result.output


def test_storage_home_refuses_ncdu_with_scan():
    result = CliRunner().invoke(main, ["storage", "home", "--ncdu", "--scan"])
    assert result.exit_code == 2
    assert "replaces --scan" in result.output


def test_storage_scratch_does_not_print_the_purge_note_after_a_failure(monkeypatch):
    monkeypatch.setattr(process, "stream", lambda cmd, **kw: 1)
    result = CliRunner().invoke(main, ["storage", "scratch"])
    assert result.exit_code == 1
    assert "deleted after" not in result.output


def test_storage_lfs_stripe_refuses_a_file(tmp_path, monkeypatch):
    """A file's layout is fixed when it is written; only a directory has a default."""
    monkeypatch.setattr(storage, "lustre_ost_count", lambda path: 8)
    target = tmp_path / "f"
    target.write_text("")
    result = CliRunner().invoke(main, ["storage", "lfs-stripe", str(target), "-c", "2", "-y"])
    assert result.exit_code == 1
    assert "is not a directory" in result.output


def test_storage_lfs_stripe_says_what_the_change_does_not_cover(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "lustre_ost_count", lambda path: 8)
    result = CliRunner().invoke(
        main, ["storage", "lfs-stripe", str(tmp_path), "-c", "2"], input="n\n"
    )
    assert "subdirectories that already exist" in result.output


def test_gpu_node_status_skips_nodes_with_no_gpu(monkeypatch):
    """The requeue partition is configured, not guaranteed to hold only GPU nodes."""
    sample = "hg1|idle|amd,gpu,h100|gpu:nvidia_h100_80gb_hbm3:4\nhc1|idle|intel,avx|(null)\n"
    monkeypatch.setattr(slurm.process, "probe", lambda cmd, timeout=None: (0, sample, ""))
    rows = dict(slurm.gpu_node_status())
    assert sum(sum(counts.values()) for counts in rows.values()) == 1


def test_gpu_usage_refuses_an_empty_base_partition_list(monkeypatch):
    """Otherwise squeue -p '' returns nothing and reads as no usage."""
    monkeypatch.setattr(site, "base_partitions", tuple)
    result = CliRunner().invoke(main, ["gpu", "usage"])
    assert result.exit_code == 1
    assert "no base partitions configured" in result.output


def test_gpu_nvtop_uses_the_configured_binaries(monkeypatch, tmp_path):
    """Neither tmux nor the remote viewer is hardcoded."""
    monkeypatch.setattr(slurm, "job_owner", lambda jobid: pwd.getpwuid(os.getuid()).pw_name)
    monkeypatch.setattr(slurm, "job_nodes", lambda jobid: ["n1"])
    monkeypatch.setattr(site, "tool", lambda key: {"tmux": "mytmux", "nvtop": "myviewer"}[key])
    calls = []
    monkeypatch.setattr(process, "probe", lambda cmd, **kw: (calls.append(cmd), (0, "", ""))[1])
    monkeypatch.setattr(process, "run", lambda cmd, **kw: (calls.append(cmd), "0")[1])
    monkeypatch.setattr(process, "stream", lambda cmd, **kw: calls.append(cmd) or 0)
    result = CliRunner().invoke(main, ["gpu", "nvtop", "1"])
    assert result.exit_code == 0
    assert all(cmd[0] == "mytmux" for cmd in calls)
    remote = next(cmd for cmd in calls if "send-keys" in cmd)
    assert "if command -v myviewer" in remote[-2]
    assert "&&" not in remote[-2]


def test_gpu_pulse_documents_its_own_options():
    """--help reaches the pulse tool, so the wrapper's flags need their own route."""
    result = CliRunner().invoke(main, ["gpu", "pulse", "--wrapper-help"])
    for flag in ("--node", "--job", "--dry-run"):
        assert flag in result.output


def test_gpu_session_drops_a_default_salloc_refuses(monkeypatch):
    """man salloc: --mem and --mem-per-gpu are mutually exclusive, not last-wins."""
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main, ["gpu", "session", "h100", "-A", "lab", "--mem-per-gpu=100000"]
    )
    assert result.exit_code == 0
    assert not any(arg.startswith("--mem=") for arg in calls[0])
    assert "--mem-per-gpu=100000" in calls[0]
    assert any(arg.startswith("--cpus-per-task=") for arg in calls[0])


def test_gpu_session_drops_cpus_per_task_for_cpus_per_gpu(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(
        main, ["gpu", "session", "h100", "-A", "lab", "--cpus-per-gpu", "8"]
    )
    assert result.exit_code == 0
    assert not any(arg.startswith("--cpus-per-task=") for arg in calls[0])
    assert any(arg.startswith("--mem=") for arg in calls[0])


def test_gpu_session_keeps_both_defaults_by_default(monkeypatch):
    calls = _capture_stream(monkeypatch)
    result = CliRunner().invoke(main, ["gpu", "session", "h100", "-A", "lab"])
    assert result.exit_code == 0
    assert any(arg.startswith("--mem=") for arg in calls[0])
    assert any(arg.startswith("--cpus-per-task=") for arg in calls[0])
