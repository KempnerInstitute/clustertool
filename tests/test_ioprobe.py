"""Tests for io-probe. The CLI tests run the real probe with tiny sizes."""

import json
import os

from click.testing import CliRunner

from cluster_tools import ioprobe
from cluster_tools.cli import main

METRICS = {
    "write_mbs": 500.0,
    "read_mbs": 2000.0,
    "meta_ms": {"create": 0.5, "stat": 0.1, "delete": 0.4},
}


def test_verdict_no_gates_is_report():
    status, reasons = ioprobe.verdict(
        METRICS, {"min_write": None, "min_read": None, "max_meta_ms": None}
    )
    assert status == "REPORT"
    assert reasons == []


def test_verdict_gates_pass():
    status, _ = ioprobe.verdict(
        METRICS, {"min_write": 100.0, "min_read": 100.0, "max_meta_ms": 5.0}
    )
    assert status == "PASS"


def test_verdict_write_gate_fail():
    status, reasons = ioprobe.verdict(
        METRICS, {"min_write": 1000.0, "min_read": None, "max_meta_ms": None}
    )
    assert status == "FAIL"
    assert "write" in reasons[0]


def test_verdict_meta_gate_uses_worst_mean():
    status, _ = ioprobe.verdict(METRICS, {"min_write": None, "min_read": None, "max_meta_ms": 0.45})
    assert status == "FAIL"


def _probe(tmp_path, *extra):
    args = ["diag", "io-probe", "-d", str(tmp_path), "--size", "1", "--meta-files", "5", *extra]
    return CliRunner().invoke(main, args)


def test_ioprobe_report_exit_0_and_cleanup(tmp_path):
    result = _probe(tmp_path)
    assert result.exit_code == 0
    assert "MB/s" in result.output
    assert "page-cache-assisted" in result.output
    assert [d for d in os.listdir(tmp_path) if d.startswith(".io_probe.")] == []


def test_ioprobe_json_schema(tmp_path):
    result = _probe(tmp_path, "--json")
    payload = json.loads(result.output)
    assert payload["write_mbs"] > 0
    assert payload["read_mbs"] > 0
    assert payload["read_cached"] is True
    assert sorted(payload["meta_ms"]) == ["create", "delete", "stat"]
    assert payload["status"] == "REPORT"


def test_ioprobe_size_rounds_to_one_chunk(tmp_path):
    payload = json.loads(_probe(tmp_path, "--json").output)
    assert payload["size_mb"] == 4.0


def test_ioprobe_impossible_gate_exit_1(tmp_path):
    result = _probe(tmp_path, "--min-write", "1e12")
    assert result.exit_code == 1
    assert "FAIL" in result.output


def test_ioprobe_keep_leaves_scratch(tmp_path):
    result = _probe(tmp_path, "--keep")
    assert result.exit_code == 0
    assert len([d for d in os.listdir(tmp_path) if d.startswith(".io_probe.")]) == 1


def test_ioprobe_missing_dir_exit_3():
    result = CliRunner().invoke(main, ["diag", "io-probe", "-d", "/nonexistent-io-probe-xyz"])
    assert result.exit_code == 3
    assert "error:" in result.output


def test_ioprobe_not_a_directory_exit_3(tmp_path):
    target = tmp_path / "afile"
    target.write_text("x")
    result = CliRunner().invoke(main, ["diag", "io-probe", "-d", str(target)])
    assert result.exit_code == 3


def test_ioprobe_bad_size_exit_3(tmp_path):
    result = CliRunner().invoke(main, ["diag", "io-probe", "-d", str(tmp_path), "--size", "0"])
    assert result.exit_code == 3
