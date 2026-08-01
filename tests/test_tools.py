"""Tests for site tool configuration and auto-hiding of tool-backed commands."""

import pathlib
import re

import click
import pytest
from click.testing import CliRunner

from clustertool import process, site
from clustertool.cli import main
from clustertool.commands.jobs import jobs as jobs_group


def test_tool_defaults():
    assert site.tool("queue") == "showq"
    assert site.tool("partitions") == "spart"
    assert site.tool("node_load") == "lsload"
    assert site.tool("account_usage") == "stotal"
    assert site.tool("account_efficiency") == "seff-account"
    assert site.tool("job_stats") == "jobstats"
    assert site.tool("quota") == "quota"


@pytest.mark.real_site_tools
def test_tool_available(monkeypatch):
    monkeypatch.setattr(site, "tool", lambda key: "sh")
    assert site.tool_available("queue") is True
    monkeypatch.setattr(site, "tool", lambda key: "no-such-binary-zzz-ct")
    assert site.tool_available("queue") is False


def test_command_hidden_when_tool_absent(monkeypatch):
    monkeypatch.setattr(site, "tool_available", lambda key: key != "queue")
    ctx = click.Context(jobs_group)
    assert jobs_group.get_command(ctx, "queue").hidden is True
    assert jobs_group.get_command(ctx, "list").hidden is False


def test_hidden_command_errors_with_pointer(monkeypatch):
    monkeypatch.setattr(site, "tool_available", lambda key: False)
    result = CliRunner().invoke(main, ["jobs", "queue", "part"])
    assert result.exit_code != 0
    assert "showq" in result.output
    assert "[tools].queue" in result.output


def test_search_skips_hidden(monkeypatch):
    monkeypatch.setattr(site, "tool_available", lambda key: key != "queue")
    result = CliRunner().invoke(main, ["search", "backlog"])
    assert "jobs queue" not in result.output


ADMIN_COMMANDS = {
    "account add-user",
    "account remove-user",
    "account set-fairshare",
    "diag ib",
    "gpu monitor-partition",
    "jobs set-priority",
    "nodes resume",
    "qos create",
    "qos delete",
    "qos grant",
    "qos modify",
    "qos retire",
    "qos revoke",
    "qos sync",
}


def _leaf_scopes() -> dict[str, str]:
    scopes: dict[str, str] = {}

    def walk(group: click.Group, prefix: str = "") -> None:
        for name, command in group.commands.items():
            if isinstance(command, click.Group):
                walk(command, f"{prefix}{name} ")
            else:
                scopes[f"{prefix}{name}"] = getattr(command, "scope", "user")

    walk(main)
    return scopes


def test_admin_scope_set_is_deliberate():
    admin = {path for path, scope in _leaf_scopes().items() if scope == "admin"}
    assert admin == ADMIN_COMMANDS


def test_index_scope_column_matches_the_code():
    index = pathlib.Path(__file__).resolve().parents[1] / "clustertool-commands-index.md"
    documented = {}
    for line in index.read_text().splitlines():
        match = re.match(r"^\|\s*`([^`]+)`\s*\|\s*(user|admin)\s*\|", line)
        if match:
            signature, scope = match.group(1), match.group(2)
            documented[signature.split(" [")[0].split(" <")[0]] = scope
    scopes = _leaf_scopes()
    for path, scope in scopes.items():
        matches = [s for s in documented if s == path or s.startswith(f"{path} ")]
        assert matches, f"{path} has no row in the command index"
        for signature in matches:
            assert documented[signature] == scope, (
                f"index says {path} is {documented[signature]}, code says {scope}"
            )
    assert len(scopes) == len(documented), "index row count does not match command count"


def test_configured_tool_name_is_used(monkeypatch):
    calls = []
    monkeypatch.setattr(site, "tool_available", lambda key: True)
    monkeypatch.setattr(site, "tool", lambda key: "myqueue" if key == "queue" else key)
    monkeypatch.setattr(process, "stream", lambda cmd, **kw: calls.append(cmd) or 0)
    result = CliRunner().invoke(main, ["jobs", "queue", "part"])
    assert result.exit_code == 0
    assert calls[0][0] == "myqueue"
