# Contributing

Thanks for adding a tool. This guide shows how to turn a cluster script into a
`clustertools` command via a pull request.

## Principles

- One umbrella CLI. Every task is a subcommand under a group.
- Commands are thin. Put reusable logic (Slurm queries, parsing) in a helper
  module such as `src/cluster_tools/slurm.py` so it can be shared and tested.
- Read the official documentation (Slurm, Python, a library's own docs) for how
  a command or API behaves. Do not guess flags or output formats.

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

1. Pick a group. Add to an existing group module in
   `src/cluster_tools/commands/`, or create a new one (for example `jobs.py`,
   `nccl.py`).

2. Write the command with `click`. The docstring becomes `--help`, so it must
   explain what the command does, its use cases, and its inputs. A line
   containing only `\b` (a backspace escape in a normal, non-raw docstring)
   keeps the following block from being re-wrapped.

   ```python
   """Job commands."""
   import click


   @click.group()
   def jobs() -> None:
       """Inspect Slurm jobs."""


   @jobs.command("list")
   @click.argument("account")
   def list_jobs(account: str) -> None:
       """List running and pending jobs for an account.

       \b
       Use cases:
         - See what an account is currently running.

       \b
       Inputs:
         ACCOUNT  Slurm account name (e.g. kempner_sham_lab).
       """
       ...
   ```

3. Inputs: a command may take no input, or a required/optional list of inputs.
   Use `click.argument` for required inputs and `click.option` for optional
   ones. Document each input in the docstring.

4. Register a new group in `src/cluster_tools/cli.py`:

   ```python
   from cluster_tools.commands.jobs import jobs

   main.add_command(jobs)
   ```

   A command added to an existing group needs no change in `cli.py`.

5. Put shared Slurm logic in `src/cluster_tools/slurm.py` and keep it read-only
   unless a command is explicitly meant to change cluster state.

## Add tests

Add tests under `tests/`. Mock external commands by monkeypatching the helper
(for example `slurm._run`) so tests do not depend on a live cluster. Use
`click.testing.CliRunner` for command tests.

## Run checks before opening a PR

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Open the pull request

Describe the command, its inputs, and example output. A maintainer will review
behavior, help text, and tests before merging.
