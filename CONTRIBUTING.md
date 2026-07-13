# Contributing

Thanks for adding a tool. This guide shows how to turn a cluster script into a
`clustertools` command via a pull request.

## Principles

- One umbrella CLI. Every task is a subcommand under a group.
- Commands are thin. Put reusable logic (Slurm queries, parsing) in a helper
  module such as `src/cluster_tools/slurm.py` so it can be shared and tested.
- Read the official documentation (Slurm, Python, a library's own docs) for how
  a command or API behaves. Do not guess flags or output formats.

## Command groups

Every command belongs to a group. Pick the group whose scope fits; create a new
group only when none does. A group's module is added when its first command
lands, so `--help` never shows an empty group.

| Group | Scope |
| --- | --- |
| `gpu` | GPU usage and availability |
| `jobs` | Job queue and history |
| `account` | Account membership, limits, fairshare |
| `nodes` | Node status and health |
| `storage` | Filesystem quotas |
| `diag` | Diagnostics and benchmarks |

## Style rules

- US spelling only.
- No extra comments in code. A simple docstring is enough.
- Type-hint public functions.
- Keep lines within 100 characters (enforced by ruff).

## Set up

```bash
uv sync
uv run clustertools --help
```

## Add a command

1. Pick the group whose scope fits your command (see Command groups). Add your
   command to that group's module in `src/cluster_tools/commands/`, or create a
   new module if you are introducing a new group.

2. Write the command with `click`. The docstring becomes `--help`, so it must
   explain what the command does, its use cases, and its inputs. A line
   containing only `\b` (a backspace escape in a normal, non-raw docstring)
   keeps the following block from being re-wrapped.

   ```python
   """Environment commands."""
   import click


   @click.group()
   def env() -> None:
       """Inspect the software environment."""


   @env.command("modules")
   @click.argument("name", required=False)
   def modules(name: str | None) -> None:
       """List available modules, optionally filtered by name.

       \b
       Use cases:
         - Find which versions of a package are available.

       \b
       Inputs:
         NAME  Optional name filter (e.g. cuda).
       """
       ...
   ```

3. Inputs: a command may take no input, or a required/optional list of inputs.
   Use `click.argument` for required inputs and `click.option` for optional
   ones. Document each input in the docstring.

4. Register a new group in `src/cluster_tools/cli.py`:

   ```python
   from cluster_tools.commands.env import env

   main.add_command(env)
   ```

   A command added to an existing group needs no change in `cli.py`.

5. Put shared Slurm logic in `src/cluster_tools/slurm.py` and keep it read-only
   unless a command is explicitly meant to change cluster state. Run external
   tools through `cluster_tools.process`: `run` captures stdout for parsing, and
   `stream` passes a tool's output straight through to the user.

## Add tests

Add tests under `tests/`. Mock external commands by monkeypatching the helper
(for example `slurm._run`, or `process.stream` for passthrough commands) so
tests do not depend on a live cluster. Use `click.testing.CliRunner` for
command tests.

## Run checks before opening a PR

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Open the pull request

Describe the command, its inputs, and example output. A maintainer will review
behavior, help text, and tests before merging.
