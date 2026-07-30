"""Tests for site tool configuration and auto-hiding of tool-backed commands."""

import click
from click.testing import CliRunner

from cluster_tools import process, site
from cluster_tools.cli import main
from cluster_tools.commands.jobs import jobs as jobs_group


def test_tool_defaults():
    assert site.tool("queue") == "showq"
    assert site.tool("partitions") == "spart"
    assert site.tool("node_load") == "lsload"
    assert site.tool("account_usage") == "stotal"
    assert site.tool("account_efficiency") == "seff-account"
    assert site.tool("job_stats") == "jobstats"
    assert site.tool("quota") == "quota"


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


def test_configured_tool_name_is_used(monkeypatch):
    calls = []
    monkeypatch.setattr(site, "tool_available", lambda key: True)
    monkeypatch.setattr(site, "tool", lambda key: "myqueue" if key == "queue" else key)
    monkeypatch.setattr(process, "stream", lambda cmd, **kw: calls.append(cmd) or 0)
    result = CliRunner().invoke(main, ["jobs", "queue", "part"])
    assert result.exit_code == 0
    assert calls[0][0] == "myqueue"
