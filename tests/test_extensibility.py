"""Tests for command disabling and plugin registration."""

import importlib.metadata

import click
from click.testing import CliRunner

from clustertool import site
from clustertool.cli import _register_plugins, main


def test_not_disabled_by_default():
    assert site.disabled_commands() == []


def test_disabled_command_hidden_and_unresolvable(monkeypatch):
    monkeypatch.setattr(site, "disabled_commands", lambda: ["gpu pulse"])
    help_out = CliRunner().invoke(main, ["gpu", "--help"])
    assert help_out.exit_code == 0
    assert "pulse" not in help_out.output
    run = CliRunner().invoke(main, ["gpu", "pulse", "--help"])
    assert run.exit_code != 0


def test_disabled_command_absent_from_search(monkeypatch):
    monkeypatch.setattr(site, "disabled_commands", lambda: ["gpu pulse"])
    result = CliRunner().invoke(main, ["search", "pulse"])
    assert "gpu pulse" not in result.output


def test_disabled_whole_group(monkeypatch):
    monkeypatch.setattr(site, "disabled_commands", lambda: ["diag"])
    top = CliRunner().invoke(main, ["--help"])
    assert "diag" not in top.output
    run = CliRunner().invoke(main, ["diag", "--help"])
    assert run.exit_code != 0


def test_plugin_command_registered(monkeypatch):
    @click.command("myplugin")
    def _cmd():
        pass

    class FakeEP:
        name = "myplugin"

        def load(self):
            return _cmd

    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda group=None: [FakeEP()] if group == "clustertool.commands" else [],
    )
    group = click.Group("root")
    _register_plugins(group)
    assert "myplugin" in group.commands


def test_broken_plugin_skipped(monkeypatch):
    class BadEP:
        name = "bad"

        def load(self):
            raise ImportError("boom")

    monkeypatch.setattr(importlib.metadata, "entry_points", lambda group=None: [BadEP()])
    group = click.Group("root")
    _register_plugins(group)
    assert "bad" not in group.commands
